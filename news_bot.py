#!/usr/bin/env python3
"""
Bitrakein News Bot
Собирает новости из RSS, фильтрует через Claude, отправляет в Telegram для одобрения.
После одобрения публикует в Telegram канал и Nostr.
"""

import os
import json
import hashlib
import feedparser
import requests
import time
from datetime import datetime, timezone, timedelta
from groq import Groq

# ─── Конфиг ──────────────────────────────────────────────────────────────────

RSS_FEEDS = [
    "https://www.theblock.co/rss.xml",
    "https://forklog.com/feed/",
    "https://incrypted.com/feed/",
    "https://99bitcoins.com/feed/",
    "https://decrypt.co/feed",
]

# Сколько часов назад считать новость свежей
NEWS_MAX_AGE_HOURS = 12

# Файл для хранения уже опубликованных новостей (чтобы не дублировать)
SEEN_FILE = "seen_news.json"

# ─── Secrets (берутся из GitHub Secrets / переменных окружения) ───────────────

GROQ_API_KEY        = os.environ["GROQ_API_KEY"]
TELEGRAM_BOT_TOKEN  = os.environ["TELEGRAM_BOT_TOKEN"]
TELEGRAM_CHAT_ID    = os.environ["TELEGRAM_CHAT_ID"]      # твой личный chat_id для одобрения
TELEGRAM_CHANNEL_ID = os.environ["TELEGRAM_CHANNEL_ID"]   # id канала для публикации
NOSTR_NSEC          = os.environ.get("NOSTR_NSEC", "")    # nsec ключ Nostr (опционально)

client = Groq(api_key=GROQ_API_KEY)

# ─── Хранилище просмотренных новостей ────────────────────────────────────────

def load_seen() -> set:
    try:
        with open(SEEN_FILE) as f:
            return set(json.load(f))
    except FileNotFoundError:
        return set()

def save_seen(seen: set):
    with open(SEEN_FILE, "w") as f:
        json.dump(list(seen), f)

def news_id(url: str) -> str:
    return hashlib.md5(url.encode()).hexdigest()

# ─── RSS парсинг ──────────────────────────────────────────────────────────────

def fetch_recent_news() -> list[dict]:
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

                # Парсим дату
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

# ─── Фильтрация и написание поста через Claude ────────────────────────────────

SYSTEM_PROMPT = """Ты редактор новостного канала Bitrakein — русскоязычного ресурса 
о биткоине, экономике и свободе. Канал придерживается либертарианских ценностей, 
критически смотрит на традиционные финансы и государственное регулирование.

Твои задачи:
1. Определить релевантна ли новость для канала (биткоин-адопшн, макроэкономика, 
   политика центробанков, громкие события в крипто, свобода денег)
2. Если релевантна — написать короткий пост на русском языке (3-5 предложений)

Стиль постов: лаконично, по делу, без воды. Можно добавить короткий комментарий 
с точки зрения свободных денег. Без хайпа и кликбейта."""

def filter_and_write(news_item: dict) -> str | None:
    """Возвращает текст поста или None если новость не релевантна."""
    
    prompt = f"""Новость:
Заголовок: {news_item['title']}
Источник: {news_item['source']}
Краткое содержание: {news_item['summary']}
Ссылка: {news_item['url']}

Если эта новость релевантна для канала Bitrakein — напиши короткий пост для Telegram/Nostr.
Если не релевантна — ответь только словом: SKIP

Пост должен заканчиваться ссылкой на источник."""

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
    return text

# ─── Telegram ─────────────────────────────────────────────────────────────────

def tg_send(chat_id: str, text: str, reply_markup: dict = None) -> dict:
    payload = {
        "chat_id": chat_id,
        "text": text,
        "parse_mode": "HTML",
        "disable_web_page_preview": False,
    }
    if reply_markup:
        payload["reply_markup"] = json.dumps(reply_markup)
    
    r = requests.post(
        f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/sendMessage",
        json=payload
    )
    return r.json()

def send_for_approval(news_item: dict, post_text: str):
    """Отправляет новость тебе в личку для одобрения."""
    
    # Сохраняем пост во временный файл (GitHub Actions прочитает при следующем запуске)
    pending = load_pending()
    pending[news_item["id"]] = {
        "post_text": post_text,
        "url": news_item["url"],
        "title": news_item["title"],
        "timestamp": datetime.now(timezone.utc).isoformat(),
    }
    save_pending(pending)

    keyboard = {
        "inline_keyboard": [[
            {"text": "✅ Опубликовать", "callback_data": f"approve:{news_item['id']}"},
            {"text": "🗑 Пропустить",   "callback_data": f"skip:{news_item['id']}"},
        ]]
    }
    
    message = (
        f"📰 <b>Новая новость для публикации</b>\n\n"
        f"<b>Источник:</b> {news_item['source']}\n"
        f"<b>Заголовок:</b> {news_item['title']}\n\n"
        f"<b>Предлагаемый пост:</b>\n\n"
        f"{post_text}"
    )
    
    tg_send(TELEGRAM_CHAT_ID, message, reply_markup=keyboard)

def publish_to_channel(post_text: str):
    """Публикует пост в Telegram канал."""
    tg_send(TELEGRAM_CHANNEL_ID, post_text)
    print(f"✅ Опубликовано в Telegram канал")

# ─── Nostr ────────────────────────────────────────────────────────────────────

def publish_to_nostr(post_text: str):
    """Публикует пост в Nostr через nostr-tool CLI."""
    if not NOSTR_NSEC:
        print("⚠️ NOSTR_NSEC не задан, пропускаем Nostr")
        return
    
    try:
        import subprocess
        # Используем nak (nostr army knife) — простой CLI инструмент
        result = subprocess.run(
            ["nak", "event", "--sec", NOSTR_NSEC, "--content", post_text,
             "wss://relay.damus.io", "wss://relay.primal.net", "wss://nos.lol"],
            capture_output=True, text=True, timeout=30
        )
        if result.returncode == 0:
            print("✅ Опубликовано в Nostr")
        else:
            print(f"⚠️ Ошибка Nostr: {result.stderr}")
    except Exception as e:
        print(f"⚠️ Nostr недоступен: {e}")

# ─── Pending (ожидают одобрения) ─────────────────────────────────────────────

PENDING_FILE = "pending_posts.json"

def load_pending() -> dict:
    try:
        with open(PENDING_FILE) as f:
            return json.load(f)
    except FileNotFoundError:
        return {}

def save_pending(pending: dict):
    with open(PENDING_FILE, "w") as f:
        json.dump(pending, f, ensure_ascii=False, indent=2)

def process_approvals():
    """Проверяет ответы от тебя через Telegram webhook/polling."""
    url = f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/getUpdates"
    r = requests.get(url, params={"timeout": 5})
    updates = r.json().get("result", [])
    
    pending = load_pending()
    seen = load_seen()
    
    for update in updates:
        callback = update.get("callback_query")
        if not callback:
            continue
        
        data = callback.get("data", "")
        action, nid = data.split(":", 1) if ":" in data else ("", "")
        
        if action == "approve" and nid in pending:
            post = pending[nid]
            publish_to_channel(post["post_text"])
            publish_to_nostr(post["post_text"])
            
            # Подтверждаем в Telegram
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                json={"callback_query_id": callback["id"], "text": "✅ Опубликовано!"}
            )
            
            seen.add(nid)
            del pending[nid]
            
        elif action == "skip" and nid in pending:
            requests.post(
                f"https://api.telegram.org/bot{TELEGRAM_BOT_TOKEN}/answerCallbackQuery",
                json={"callback_query_id": callback["id"], "text": "🗑 Пропущено"}
            )
            seen.add(nid)
            del pending[nid]
        
        # Сдвигаем offset чтобы не обрабатывать повторно
        requests.get(url, params={"offset": update["update_id"] + 1})
    
    save_pending(pending)
    save_seen(seen)

# ─── Главный запуск ───────────────────────────────────────────────────────────

def main():
    print(f"🚀 Запуск Bitrakein News Bot — {datetime.now()}")
    
    # Сначала обрабатываем одобрения от предыдущего запуска
    print("⏳ Проверяем одобрения...")
    process_approvals()
    
    # Затем ищем новые новости
    print("📡 Загружаем RSS ленты...")
    news_list = fetch_recent_news()
    print(f"   Найдено {len(news_list)} новых новостей")
    
    seen = load_seen()
    sent_count = 0
    
    for item in news_list:
        if sent_count >= 5:  # не более 5 новостей за один запуск
            break
        
        print(f"🤖 Анализируем: {item['title'][:60]}...")
        post_text = filter_and_write(item)
        
        if post_text is None:
            print("   → Нерелевантно, пропускаем")
            seen.add(item["id"])
            continue
        
        print("   → Релевантно! Отправляем на одобрение")
        send_for_approval(item, post_text)
        seen.add(item["id"])
        sent_count += 1
        
        time.sleep(2)  # пауза между запросами к Claude
    
    save_seen(seen)
    print(f"✅ Готово. Отправлено на одобрение: {sent_count} новостей")

if __name__ == "__main__":
    main()
