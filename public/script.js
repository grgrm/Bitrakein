document.addEventListener('DOMContentLoaded', function () {
  console.log('Script.js loaded');

  async function fetchSatPrice() {
    console.log('fetchSatPrice called');

    const cachedBtcPriceUSD = localStorage.getItem('btcPriceUSD');
    const cachedBtcPriceRUB = localStorage.getItem('btcPriceRUB');
    const cachedSatPriceUSD = localStorage.getItem('satPriceUSD');
    const cachedSatPriceRUB = localStorage.getItem('satPriceRUB');
    const lastFetch = localStorage.getItem('lastFetch');
    const now = Date.now();

    const btcElement = document.getElementById('btc-price');
    const satElement = document.getElementById('sat-price');
    const btcPriceContainer = document.querySelector('.price-left');
    const satPriceContainer = document.querySelector('.price-right');
    const btcCurrentCurrency = btcPriceContainer ? btcPriceContainer.getAttribute('data-currency') : 'USD';
    const satCurrentCurrency = satPriceContainer ? satPriceContainer.getAttribute('data-currency') : 'USD';

    // Используем кэшированные данные, если они есть и прошло менее 60 секунд
    if (
      cachedBtcPriceUSD &&
      cachedBtcPriceRUB &&
      cachedSatPriceUSD &&
      cachedSatPriceRUB &&
      lastFetch &&
      (now - lastFetch < 60000)
    ) {
      console.log('Using cached prices:', {
        btcPriceUSD: cachedBtcPriceUSD,
        btcPriceRUB: cachedBtcPriceRUB,
        satPriceUSD: cachedSatPriceUSD,
        satPriceRUB: cachedSatPriceRUB,
      });
      if (btcElement) btcElement.textContent = btcCurrentCurrency === 'USD' ? cachedBtcPriceUSD : cachedBtcPriceRUB;
      if (satElement) satElement.textContent = satCurrentCurrency === 'USD' ? cachedSatPriceUSD : cachedSatPriceRUB;
      return;
    }

    console.log('Fetching prices...');
    try {
      let btcPriceUSD, btcPriceRUB;
      let response = await fetch('https://api.coingecko.com/api/v3/simple/price?ids=bitcoin&vs_currencies=usd,rub');
      let data = await response.json();
      if (data.bitcoin && data.bitcoin.usd && data.bitcoin.rub) {
        btcPriceUSD = data.bitcoin.usd;
        btcPriceRUB = data.bitcoin.rub;
      } else {
        // Резервный API (Binance) для USD, для RUB используем конвертацию
        response = await fetch('https://api.binance.com/api/v3/ticker/price?symbol=BTCUSDT');
        data = await response.json();
        btcPriceUSD = parseFloat(data.price);

        // Получаем курс USD/RUB через другой API (например, exchangerate-api)
        response = await fetch('https://api.exchangerate-api.com/v4/latest/USD');
        data = await response.json();
        const usdToRubRate = data.rates.RUB;
        btcPriceRUB = btcPriceUSD * usdToRubRate;
      }

      const satPriceUSD = btcPriceUSD / 100000000;
      const satPriceRUB = btcPriceRUB / 100000000;

      const formattedBtcPriceUSD = btcPriceUSD.toLocaleString('en-US', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const formattedBtcPriceRUB = btcPriceRUB.toLocaleString('ru-RU', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
      const formattedSatPriceUSD = satPriceUSD.toFixed(6);
      const formattedSatPriceRUB = satPriceRUB.toFixed(6);

      if (btcElement) {
        btcElement.textContent = btcCurrentCurrency === 'USD' ? `$${formattedBtcPriceUSD}` : `₽${formattedBtcPriceRUB}`;
        console.log('BTC price updated successfully');
      } else {
        console.error('Element with id "btc-price" not found');
      }
      if (satElement) {
        satElement.textContent = satCurrentCurrency === 'USD' ? `$${formattedSatPriceUSD}` : `₽${formattedSatPriceRUB}`;
        console.log('Sat price updated successfully');
      } else {
        console.error('Element with id "sat-price" not found');
      }

      // Сохраняем данные в localStorage
      localStorage.setItem('btcPriceUSD', `$${formattedBtcPriceUSD}`);
      localStorage.setItem('btcPriceRUB', `₽${formattedBtcPriceRUB}`);
      localStorage.setItem('satPriceUSD', `$${formattedSatPriceUSD}`);
      localStorage.setItem('satPriceRUB', `₽${formattedSatPriceRUB}`);
      localStorage.setItem('lastFetch', now);
    } catch (error) {
      console.error('Ошибка при получении цены:', error);
      const satElement = document.getElementById('sat-price');
      const btcElement = document.getElementById('btc-price');
      if (satElement) satElement.textContent = 'ошибка';
      if (btcElement) btcElement.textContent = 'ошибка';
    }
  }

  // Обработчик клика/тапа для переключения валюты 1 BTC
  const btcPriceContainer = document.querySelector('.price-left');
  if (btcPriceContainer) {
    btcPriceContainer.addEventListener('click', function () {
      const currentCurrency = btcPriceContainer.getAttribute('data-currency');
      const newCurrency = currentCurrency === 'USD' ? 'RUB' : 'USD';
      btcPriceContainer.setAttribute('data-currency', newCurrency);

      const btcElement = document.getElementById('btc-price');
      const cachedBtcPriceUSD = localStorage.getItem('btcPriceUSD');
      const cachedBtcPriceRUB = localStorage.getItem('btcPriceRUB');

      if (btcElement) {
        btcElement.textContent = newCurrency === 'USD' ? cachedBtcPriceUSD : cachedBtcPriceRUB;
      }
    });

    btcPriceContainer.addEventListener('touchstart', function (e) {
      e.preventDefault();
      const currentCurrency = btcPriceContainer.getAttribute('data-currency');
      const newCurrency = currentCurrency === 'USD' ? 'RUB' : 'USD';
      btcPriceContainer.setAttribute('data-currency', newCurrency);

      const btcElement = document.getElementById('btc-price');
      const cachedBtcPriceUSD = localStorage.getItem('btcPriceUSD');
      const cachedBtcPriceRUB = localStorage.getItem('btcPriceRUB');

      if (btcElement) {
        btcElement.textContent = newCurrency === 'USD' ? cachedBtcPriceUSD : cachedBtcPriceRUB;
      }
    });
  }

  // Обработчик клика/тапа для переключения валюты 1 сатоши
  const satPriceContainer = document.querySelector('.price-right');
  if (satPriceContainer) {
    satPriceContainer.addEventListener('click', function () {
      const currentCurrency = satPriceContainer.getAttribute('data-currency');
      const newCurrency = currentCurrency === 'USD' ? 'RUB' : 'USD';
      satPriceContainer.setAttribute('data-currency', newCurrency);

      const satElement = document.getElementById('sat-price');
      const cachedSatPriceUSD = localStorage.getItem('satPriceUSD');
      const cachedSatPriceRUB = localStorage.getItem('satPriceRUB');

      if (satElement) {
        satElement.textContent = newCurrency === 'USD' ? cachedSatPriceUSD : cachedSatPriceRUB;
      }
    });

    satPriceContainer.addEventListener('touchstart', function (e) {
      e.preventDefault();
      const currentCurrency = satPriceContainer.getAttribute('data-currency');
      const newCurrency = currentCurrency === 'USD' ? 'RUB' : 'USD';
      satPriceContainer.setAttribute('data-currency', newCurrency);

      const satElement = document.getElementById('sat-price');
      const cachedSatPriceUSD = localStorage.getItem('satPriceUSD');
      const cachedSatPriceRUB = localStorage.getItem('satPriceRUB');

      if (satElement) {
        satElement.textContent = newCurrency === 'USD' ? cachedSatPriceUSD : cachedSatPriceRUB;
      }
    });
  }

  // Немедленный вызов функции
  fetchSatPrice();

  // Вызываем каждые 60 секунд
  setInterval(fetchSatPrice, 60000);
});