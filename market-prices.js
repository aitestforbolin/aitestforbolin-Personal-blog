(function () {
  const WIDGET_SRC =
    "https://s3.tradingview.com/external-embedding/embed-widget-advanced-chart.js";
  const DATE_RANGE = "1D";
  const CHART_HEIGHT = 420;
  const MARKETS = {
    "BITSTAMP:BTCUSD": {
      name: "BTC",
      proxy: "BTC/USD",
    },
    "AMEX:SPY": {
      name: "S&P 500",
      proxy: "SPY ETF",
    },
    "NASDAQ:QQQ": {
      name: "纳斯达克100",
      proxy: "QQQ ETF",
    },
    "AMEX:DIA": {
      name: "道琼斯",
      proxy: "DIA ETF",
    },
    "OANDA:XAUUSD": {
      name: "黄金",
      proxy: "XAU/USD",
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

    const widget = document.createElement("div");
    widget.className = "tradingview-widget-container__widget";
    chart.append(widget);

    const script = document.createElement("script");
    script.type = "text/javascript";
    script.src = WIDGET_SRC;
    script.async = true;
    script.textContent = JSON.stringify({
      autosize: false,
      symbol,
      width: "100%",
      height: CHART_HEIGHT,
      interval: "15",
      timezone: "Asia/Shanghai",
      theme: "light",
      style: "2",
      locale: "zh_CN",
      range: DATE_RANGE,
      backgroundColor: "rgba(255, 253, 248, 0)",
      gridColor: "rgba(117, 108, 97, 0.14)",
      hide_top_toolbar: true,
      hide_legend: false,
      save_image: false,
      calendar: false,
      allow_symbol_change: false,
      support_host: "https://www.tradingview.com",
    });
    chart.append(script);
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      renderChart(tab.dataset.marketSymbol);
    });
  });

  renderChart(tabs[0].dataset.marketSymbol);
})();
