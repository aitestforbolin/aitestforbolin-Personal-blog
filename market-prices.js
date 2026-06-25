(function () {
  const MARKETS = {
    "BITSTAMP:BTCUSD": {
      name: "BTC",
      proxy: "BTC/USD",
      summary: "比特币兑美元",
      url: "https://www.tradingview.com/chart/?symbol=BITSTAMP%3ABTCUSD",
    },
    "OANDA:XAUUSD": {
      name: "黄金",
      proxy: "XAU/USD",
      summary: "现货黄金兑美元",
      url: "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD",
    },
    "AMEX:SPY": {
      name: "S&P 500",
      proxy: "SPY ETF",
      summary: "标普 500 代理 ETF",
      url: "https://www.tradingview.com/chart/?symbol=AMEX%3ASPY",
    },
    "NASDAQ:QQQ": {
      name: "纳斯达克100",
      proxy: "QQQ ETF",
      summary: "纳斯达克 100 代理 ETF",
      url: "https://www.tradingview.com/chart/?symbol=NASDAQ%3AQQQ",
    },
    "AMEX:DIA": {
      name: "道琼斯",
      proxy: "DIA ETF",
      summary: "道琼斯工业指数代理 ETF",
      url: "https://www.tradingview.com/chart/?symbol=AMEX%3ADIA",
    },
  };

  const chart = document.querySelector("[data-market-chart]");
  const tabs = Array.from(document.querySelectorAll("[data-market-symbol]"));
  const name = document.querySelector("[data-market-name]");
  const proxy = document.querySelector("[data-market-proxy]");

  if (!chart || !tabs.length || !name || !proxy) {
    return;
  }

  function renderChart(symbol) {
    const market = MARKETS[symbol];
    if (!market) {
      return;
    }

    name.textContent = market.name;
    proxy.textContent = `${market.proxy} · 24h`;

    tabs.forEach((tab) => {
      const isActive = tab.dataset.marketSymbol === symbol;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", String(isActive));
    });

    chart.innerHTML = "";

    const cards = Object.entries(MARKETS)
      .map(([marketSymbol, item]) => {
        const activeClass = marketSymbol === symbol ? " is-active" : "";
        return `
          <a class="market-asset-card${activeClass}" href="${item.url}" target="_blank" rel="noreferrer">
            <span>${item.name}</span>
            <strong>${item.proxy}</strong>
            <small>${item.summary}</small>
          </a>
        `;
      })
      .join("");

    chart.innerHTML = `
      <div class="market-asset-panel">
        <div class="market-asset-copy">
          <strong>${market.name}</strong>
          <p>${market.summary}。当前网络环境下 TradingView 内嵌图表不可用，请打开外部行情页查看实时价格与走势。</p>
          <a class="market-open-link" href="${market.url}" target="_blank" rel="noreferrer">打开 ${market.name} 行情</a>
        </div>
        <div class="market-asset-grid">${cards}</div>
      </div>
    `;
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      renderChart(tab.dataset.marketSymbol);
    });
  });

  renderChart(tabs[0].dataset.marketSymbol);
})();
