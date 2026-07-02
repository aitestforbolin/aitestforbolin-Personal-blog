(function () {
  const WIDGET_SCRIPT =
    "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
  const CHART_HEIGHT = 520;
  const MARKETS = {
    "BINANCE:BTCUSDT": {
      name: "BTC",
      proxy: "BTC/USDT",
      url: "https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT",
    },
    "OANDA:XAUUSD": {
      name: "黄金",
      proxy: "XAU/USD",
      url: "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD",
    },
    "BINANCE:ETHUSDT": {
      name: "ETH",
      proxy: "ETH/USDT",
      url: "https://www.tradingview.com/chart/?symbol=BINANCE%3AETHUSDT",
    },
  };

  const chart = document.querySelector("[data-market-chart]");
  const tabs = Array.from(document.querySelectorAll("[data-market-symbol]"));
  const name = document.querySelector("[data-market-name]");
  const proxy = document.querySelector("[data-market-proxy]");

  if (!chart || !tabs.length || !name || !proxy) {
    return;
  }

  function getExternalLinksMarkup(activeSymbol) {
    const assetLinks = Object.entries(MARKETS)
      .map(([symbol, market]) => {
        const activeClass = symbol === activeSymbol ? " is-active" : "";
        return `<a class="market-fallback-link${activeClass}" href="${market.url}" target="_blank" rel="noreferrer">${market.name}</a>`;
      })
      .join("");

    return `
      <div class="market-chart-fallback" aria-label="外部行情链接">
        <p>图表可拖动、缩放并查看分钟级时间点；加载较慢时可直接打开 TradingView。</p>
        <div class="market-fallback-links">${assetLinks}</div>
      </div>
    `;
  }

  function getWidgetConfig(symbol) {
    return {
      autosize: true,
      symbol,
      interval: "5",
      range: "1D",
      timezone: "Asia/Shanghai",
      theme: "light",
      style: "1",
      locale: "zh_CN",
      withdateranges: true,
      hide_side_toolbar: false,
      allow_symbol_change: false,
      save_image: false,
      calendar: false,
      support_host: "https://www.tradingview.com",
      backgroundColor: "#fffdf8",
      gridColor: "rgba(117, 108, 97, 0.14)",
      studies: [],
    };
  }

  function renderChart(symbol) {
    const market = MARKETS[symbol];
    if (!market) {
      return;
    }

    name.textContent = market.name;
    proxy.textContent = `${market.proxy} · 1D · 5m`;

    tabs.forEach((tab) => {
      const isActive = tab.dataset.marketSymbol === symbol;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", String(isActive));
    });

    chart.innerHTML = `
      <div class="tradingview-widget-container__widget"></div>
      ${getExternalLinksMarkup(symbol)}
    `;

    const script = document.createElement("script");
    script.src = WIDGET_SCRIPT;
    script.async = true;
    script.textContent = JSON.stringify(getWidgetConfig(symbol));
    chart.append(script);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      renderChart(tab.dataset.marketSymbol);
    });
  });

  chart.style.minHeight = `${CHART_HEIGHT}px`;
  renderChart(tabs[0].dataset.marketSymbol);
})();
