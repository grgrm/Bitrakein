#!/usr/bin/env python3
"""
Bitrakein News Bot
"""

import os
import json
import hashlib
import feedparser
import requests
import time
from datetime import datetime, timezone, timedelta
from groq import Groq

RSS_FEEDS = [
    "https://www.theblock.co/rss.xml",
    "https://forklog.com/feed/",
    "https://incrypted.com/feed/",
    "https://99bitcoins.com/feed/",
    "https://decrypt.co/feed",
]

NEWS_MAX_AGE_HOURS = 12
SEEN_FILE    = "seen_news.json"
PENDING_FILE = "pending_posts.json"

GROQ_API_KEY        = os.environ["GROQ_API_KEY"]
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]
NOSTR_NSEC          = os.environ.get("NOSTR_NSEC", "")

client = Groq(api_key=GROQ_API_KEY)

def load_seen():
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_seen(seen):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def load_pending():
    try:
        with open(PENDING_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_pending(pending):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

def news_id(url):
    return hashlib.md5(url.encode()).hexdigest()

def fetch_recent_news():
    seen = load_seen()
    cutoff = datetime.now(timezone.utc) - timedelta(hours=NEWS_MAX_AGE_HOURS)
    results = []
    for feed_url in RSS_FEEDS:
        try:
            feed = feedparser.parse(feed_url)
            for entry in feed.entries[:20]:
                url = entry.get("link", "")
                nid = news_id(url)
                if nid in seen:
                    continue
                published = entry.get("published_parsed") or entry.get("updated_parsed")
                if published:
                    pub_dt = datetime(*published[:6], tzinfo=timezone.utc)
                    if pub_dt < cutoff:
                        continue
                results.append({
                    "id": nid,
                    "title": entry.get("title", ""),
                    "url": url,
                    "summary": entry.get("summary", "")[:500],
                    "source": feed.feed.get("title", feed_url),
                })
        except Exception as e:
            print(f"Ошибка при загрузке {feed_url}: {e}")
    return results

SYSTEM_PROMPT = """Ты редактор новостного канала Bitrakein — русскоязычного ресурса 
о биткоине, экономике и свободе. Канал придерживается либертарианских ценностей, 
критически смотрит на традиционные финансы и государственное регулирование.

Твои задачи:
1. Определить релевантна ли новость для канала (биткоин-адопшн, макроэкономика, 
   политика центробанков, громкие события в крипто, свобода денег)
2. Если релевантна — написать пост строго в формате:

ЗАГОЛОВОК: [короткий заголовок на русском, 5-8 слов]
ТЕКСТ: [2-4 предложения по сути новости. Только факты, без шаблонных подводок и комментариев.]
ССЫЛКА: [оригинальная ссылка]

Если не релевантна — ответь только: SKIP

Стиль: лаконично, по делу, без воды, без хайпа."""

def filter_and_write(news_item):
    prompt = f"""Новость:
Заголовок: {news_item['title']}
Источник: {news_item['source']}
Краткое содержание: {news_item['summary']}
Ссылка: {news_item['url']}

Оцени релевантность и напиши пост по формату."""

    response = client.chat.completions.create(
        model="llama-3.3-70b-versatile",
        max_tokens=1000,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt}
        ]
    )
    text = response.choices[0].message.content.strip()
    if text.upper().startswith("SKIP"):
        return None

    title, body, url = "", "", news_item['url']
    for line in text.splitlines():
        if line.startswith("ЗАГОЛОВОК:"):
            title = line.replace("ЗАГОЛОВОК:", "").strip()
        elif line.startswith("ТЕКСТ:"):
            body = line.replace("ТЕКСТ:", "").strip()
        elif line.startswith("ССЫЛКА:"):
            url = line.replace("ССЫЛКА:", "").strip()

    if not title or not body:
        return None
    return {"title": title, "body": body, "url": url}

def format_post_channel(post):
    """Для публикации в канал — только заголовок и текст."""
    return f"<b>{post['title']}</b>\n\n{post['body']}"

def format_post_preview(post, source):
    """Для превью тебе — с источником и ссылкой."""
    return f"📰 <b>Источник:</b> {source}\n🔗 {post['url']}\n\n<b>{post['title']}</b>\n\n{post['body']}"

def tg_api(method, payload):
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/{method}",
        json=payload
    )
    return r.json()

def tg_send(chat_id, text, reply_markup=None):
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": True,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    return tg_api("sendMessage", payload)

def send_for_approval(news_item, post):
    pending = load_pending()
    pending[news_item["id"]] = {
        "title": post["title"],
        "body": post["body"],
        "url": post["url"],
        "source": news_item["source"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "awaiting_edit": False,
    }
    save_pending(pending)

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Опубликовать",  "callback_data": f"approve:{news_item['id']}"},
            {"text": "✏️ Редактировать", "callback_data": f"edit:{news_item['id']}"},
            {"text": "🗑 Пропустить",    "callback_data": f"skip:{news_item['id']}"},
        ]]
    }
    message = format_post_preview(post, news_item['source'])
    tg_send(TELEGRAM_CHAT_ID, message, reply_markup=keyboard)

def publish_to_channel(post):
    tg_send(TELEGRAM_CHANNEL_ID, format_post_channel(post))
    print("✅ Опубликовано в Telegram канал")

def publish_to_nostr(post):
    if not NOSTR_NSEC:
        print("⚠️ NOSTR_NSEC не задан, пропускаем Nostr")
        return
    try:
        import subprocess
        plain = f"{post['title']}\n\n{post['body']}"
        result = subprocess.run(
            ["nak", "event", "--sec", NOSTR_NSEC, "--content", plain,
             "wss://relay.damus.io", "wss://relay.primal.net", "wss://nos.lol"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("✅ Опубликовано в Nostr")
        else:
            print(f"⚠️ Ошибка Nostr: {result.stderr}")
    except Exception as e:
        print(f"⚠️ Nostr недоступен: {e}")

def process_approvals():
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    r = requests.get(url, params={"timeout": 5})
    updates = r.json().get("result", [])

    pending = load_pending()
    seen = load_seen()
    last_offset = None

    for update in updates:
        last_offset = update["update_id"]
        callback = update.get("callback_query")
        message  = update.get("message")

        if callback:
            data = callback.get("data", "")
            action, nid = data.split(":", 1) if ":" in data else ("", "")

            if action == "approve" and nid in pending:
                post = pending[nid]
                publish_to_channel(post)
                publish_to_nostr(post)
                tg_api("answerCallbackQuery", {
                    "callback_query_id": callback["id"], "text": "✅ Опубликовано!"
                })
                seen.add(nid)
                del pending[nid]

            elif action == "edit" and nid in pending:
                pending[nid]["awaiting_edit"] = True
                save_pending(pending)
                tg_api("answerCallbackQuery", {
                    "callback_query_id": callback["id"], "text": "✏️ Жду исправленный текст"
                })
                tg_send(TELEGRAM_CHAT_ID,
                    "✏️ Отправь исправленный текст:\n"
                    "<b>Первая строка</b> — заголовок\n"
                    "<b>Остальное</b> — тело поста\n\n"
                    "Ссылка подставится автоматически.")

            elif action == "skip" and nid in pending:
                tg_api("answerCallbackQuery", {
                    "callback_query_id": callback["id"], "text": "🗑 Пропущено"
                })
                seen.add(nid)
                del pending[nid]

        elif message and message.get("text"):
            for nid, post in list(pending.items()):
                if post.get("awaiting_edit"):
                    lines = message["text"].strip().splitlines()
                    if lines:
                        post["title"] = lines[0].strip()
                        post["body"]  = "\n".join(lines[1:]).strip() if len(lines) > 1 else post["body"]
                        post["awaiting_edit"] = False
                        pending[nid] = post

                        keyboard = {
                            "inline_keyboard": [[
                                {"text": "✅ Опубликовать", "callback_data": f"approve:{nid}"},
                                {"text": "🗑 Пропустить",   "callback_data": f"skip:{nid}"},
                            ]]
                        }
                        tg_send(TELEGRAM_CHAT_ID,
                            f"📝 <b>Обновлённый пост:</b>\n\n{format_post_channel(post)}",
                            reply_markup=keyboard)
                    break

    if last_offset is not None:
        requests.get(url, params={"offset": last_offset + 1})

    save_pending(pending)
    save_seen(seen)

def main():
    print(f"🚀 Запуск Bitrakein News Bot — {datetime.now()}")

    print("⏳ Проверяем одобрения...")
    process_approvals()

    print("📡 Загружаем RSS ленты...")
    news_list = fetch_recent_news()
    print(f"   Найдено {len(news_list)} новых новостей")

    seen = load_seen()
    sent_count = 0

    for item in news_list:
        if sent_count >= 5:
            break
        print(f"🤖 Анализируем: {item['title'][:60]}...")
        post = filter_and_write(item)
        if post is None:
            print("   → Нерелевантно, пропускаем")
            seen.add(item["id"])
            continue
        print("   → Релевантно! Отправляем на одобрение")
        send_for_approval(item, post)
        seen.add(item["id"])
        sent_count += 1
        time.sleep(2)

    save_seen(seen)
    print(f"✅ Готово. Отправлено на одобрение: {sent_count} новостей")

if __name__ == "__main__":
    main()
