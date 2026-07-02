(function () {
  const WIDGET_ORIGIN = "https://s.tradingview.com";
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

  function getChartUrl(symbol) {
    const params = new URLSearchParams({
      frameElementId: `market-chart-${symbol.replace(/[^a-z0-9]/gi, "-")}`,
      symbol,
      range: "1D",
      interval: "5",
      timezone: "Asia/Shanghai",
      theme: "light",
      style: "1",
      locale: "zh_CN",
      toolbarbg: "fffdf8",
      withdateranges: "1",
      hidesidetoolbar: "0",
      symboledit: "0",
      saveimage: "0",
      hideideas: "1",
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
    proxy.textContent = `${market.proxy} · 1D · 5m`;

    tabs.forEach((tab) => {
      const isActive = tab.dataset.marketSymbol === symbol;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", String(isActive));
    });

    chart.innerHTML = "";

    const frame = document.createElement("iframe");
    frame.className = "market-chart-direct-frame";
    frame.title = `${market.name} TradingView 实时走势图`;
    frame.src = getChartUrl(symbol);
    frame.loading = "lazy";
    frame.allowFullscreen = true;
    frame.style.display = "block";
    frame.style.width = "100%";
    frame.style.height = `${CHART_HEIGHT}px`;
    frame.style.minHeight = `${CHART_HEIGHT}px`;
    frame.style.border = "0";
    frame.style.background = "#f2f2f2";

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
