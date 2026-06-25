(function () {
  const WIDGET_ORIGIN = "https://s.tradingview.com";
  const DATE_RANGE = "1D";
  const CHART_HEIGHT = 420;
  const MARKETS = {
    "BITSTAMP:BTCUSD": {
      name: "BTC",
      proxy: "BTC/USD",
      url: "https://www.tradingview.com/chart/?symbol=BITSTAMP%3ABTCUSD",
    },
    "OANDA:XAUUSD": {
      name: "黄金",
      proxy: "XAU/USD",
      url: "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD",
    },
    "AMEX:SPY": {
      name: "S&P 500",
      proxy: "SPY ETF",
      url: "https://www.tradingview.com/chart/?symbol=AMEX%3ASPY",
    },
    "NASDAQ:QQQ": {
      name: "纳斯达克100",
      proxy: "QQQ ETF",
      url: "https://www.tradingview.com/chart/?symbol=NASDAQ%3AQQQ",
    },
    "AMEX:DIA": {
      name: "道琼斯",
      proxy: "DIA ETF",
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

  function getExternalLinksMarkup(activeSymbol) {
    const assetLinks = Object.entries(MARKETS)
      .map(([symbol, market]) => {
        const activeClass = symbol === activeSymbol ? " is-active" : "";
        return `<a class="market-fallback-link${activeClass}" href="${market.url}" target="_blank" rel="noreferrer">${market.name}</a>`;
      })
      .join("");

    return `
      <div class="market-chart-fallback" aria-label="外部行情链接">
        <p>如果图表加载较慢，可直接打开对应资产页面。</p>
        <div class="market-fallback-links">${assetLinks}</div>
      </div>
    `;
  }

  function getChartUrl(symbol) {
    const params = new URLSearchParams({
      frameElementId: `market-chart-${symbol.replace(/[^a-z0-9]/gi, "-")}`,
      symbol,
      interval: "15",
      range: DATE_RANGE,
      timezone: "Asia/Shanghai",
      theme: "light",
      style: "2",
      locale: "zh_CN",
      hidesidetoolbar: "1",
      symboledit: "0",
      saveimage: "0",
      toolbarbg: "fffdf8",
      hideideas: "1",
      withdateranges: "1",
      studies: "[]",
      studies_overrides: "{}",
      overrides: JSON.stringify({
        "paneProperties.background": "#fffdf8",
        "paneProperties.vertGridProperties.color": "rgba(117, 108, 97, 0.14)",
        "paneProperties.horzGridProperties.color": "rgba(117, 108, 97, 0.14)",
      }),
      enabled_features: "[]",
      disabled_features: "[]",
      utm_source: window.location.hostname || "localhost",
      utm_medium: "widget",
      utm_campaign: "chart",
      utm_term: symbol,
    });

    return `${WIDGET_ORIGIN}/widgetembed/?${params.toString()}`;
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

    const frame = document.createElement("iframe");
    frame.className = "market-chart-direct-frame";
    frame.title = `${market.name} TradingView 走势图`;
    frame.src = getChartUrl(symbol);
    frame.loading = "lazy";
    frame.allowFullscreen = true;

    chart.append(frame);
    chart.insertAdjacentHTML("beforeend", getExternalLinksMarkup(symbol));
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      renderChart(tab.dataset.marketSymbol);
    });
  });

  chart.style.minHeight = `${CHART_HEIGHT}px`;
  renderChart(tabs[0].dataset.marketSymbol);
})();
