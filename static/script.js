console.log('Script.js loaded');

async function fetchSatPrice() {
  console.log('fetchSatPrice called'); // Добавим для отладки

  const cachedPrice = localStorage.getItem('satPrice');
  const cachedBtcPrice = localStorage.getItem('btcPrice');
  const lastFetch = localStorage.getItem('lastFetch');
  const now = Date.now();

  // Используем кэшированные данные, если они есть и прошло менее 60 секунд
  if (cachedPrice && cachedBtcPrice && lastFetch && (now - lastFetch < 60000)) {
    console.log('Using cached prices:', { satPrice: cachedPrice, btcPrice: cachedBtcPrice });
    const satElement = document.getElementById('sat-price');
    const btcElement = document.getElementById('btc-price');
    if (satElement) satElement.textContent = cachedPrice;
    if (btcElement) btcElement.textContent = cachedBtcPrice;
    return;
  }

  console.log('Fetching prices...');
  try {
    let btcPrice;
    let response = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd');
    let data = await response.json();
    if (data.bitcoin && data.bitcoin.usd) {
      btcPrice = data.bitcoin.usd;
    } else {
      // Резервный API (Binance), если CoinGecko не сработал
      response = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT');
      data = await response.json();
      btcPrice = parseFloat(data.price);
    }

    const satPrice = btcPrice / 100000000;
    const formattedBtcPrice = btcPrice.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
    const formattedSatPrice = satPrice.toFixed(6);

    const satElement = document.getElementById('sat-price');
    const btcElement = document.getElementById('btc-price');
    if (satElement) {
      satElement.textContent = `$${formattedSatPrice}`;
      console.log('Sat price updated successfully');
    } else {
      console.error('Element with id "sat-price" not found');
    }
    if (btcElement) {
      btcElement.textContent = `$${formattedBtcPrice}`;
      console.log('BTC price updated successfully');
    } else {
      console.error('Element with id "btc-price" not found');
    }

    // Сохраняем данные в localStorage
    localStorage.setItem('satPrice', `$${formattedSatPrice}`);
    localStorage.setItem('btcPrice', `$${formattedBtcPrice}`);
    localStorage.setItem('lastFetch', now);
  } catch (error) {
    console.error('Ошибка при получении цены:', error);
    const satElement = document.getElementById('sat-price');
    const btcElement = document.getElementById('btc-price');
    if (satElement) satElement.textContent = 'ошибка';
    if (btcElement) btcElement.textContent = 'ошибка';
  }
}

// Немедленный вызов функции
fetchSatPrice();

// Вызываем каждые 60 секунд
setInterval(fetchSatPrice, 60000);