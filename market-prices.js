(function () {
  const LOCAL_QUOTE_ENDPOINT = "data/market-prices.json";
  const QUOTE_TIMEOUT = 6500;
  const QUOTE_REFRESH_INTERVAL = 60 * 1000;
  const LIVE_QUOTE_ENDPOINTS = [
    {
      quoteSymbol: "BTCUSD",
      yahooSymbol: "BTC-USD",
    },
    {
      quoteSymbol: "XAUUSD",
      yahooSymbol: "GC=F",
    },
    {
      quoteSymbol: "SPY.US",
      yahooSymbol: "SPY",
    },
    {
      quoteSymbol: "QQQ.US",
      yahooSymbol: "QQQ",
    },
    {
      quoteSymbol: "DIA.US",
      yahooSymbol: "DIA",
    },
  ];
  const FALLBACK_QUOTES = {
    BTCUSD: {
      available: false,
    },
    XAUUSD: {
      available: false,
    },
    "SPY.US": {
      available: false,
    },
    "QQQ.US": {
      available: false,
    },
    "DIA.US": {
      available: false,
    },
  };
  const MARKETS = {
    "BITSTAMP:BTCUSD": {
      name: "BTC",
      proxy: "BTC/USD",
      summary: "比特币兑美元",
      quoteSymbol: "BTCUSD",
      decimals: 0,
      url: "https://www.tradingview.com/chart/?symbol=BITSTAMP%3ABTCUSD",
    },
    "OANDA:XAUUSD": {
      name: "黄金",
      proxy: "XAU/USD",
      summary: "现货黄金兑美元",
      quoteSymbol: "XAUUSD",
      decimals: 1,
      url: "https://www.tradingview.com/chart/?symbol=OANDA%3AXAUUSD",
    },
    "AMEX:SPY": {
      name: "S&P 500",
      proxy: "SPY ETF",
      summary: "标普 500 代理 ETF",
      quoteSymbol: "SPY.US",
      decimals: 2,
      url: "https://www.tradingview.com/chart/?symbol=AMEX%3ASPY",
    },
    "NASDAQ:QQQ": {
      name: "纳斯达克100",
      proxy: "QQQ ETF",
      summary: "纳斯达克 100 代理 ETF",
      quoteSymbol: "QQQ.US",
      decimals: 2,
      url: "https://www.tradingview.com/chart/?symbol=NASDAQ%3AQQQ",
    },
    "AMEX:DIA": {
      name: "道琼斯",
      proxy: "DIA ETF",
      summary: "道琼斯工业指数代理 ETF",
      quoteSymbol: "DIA.US",
      decimals: 2,
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

  let quotes = {};
  let activeSymbol = tabs[0].dataset.marketSymbol;
  let quoteSource = "载入中";
  let isRefreshing = false;
  let lastRefreshLabel = "";

  function formatNumber(value, decimals) {
    if (!Number.isFinite(value)) {
      return "--";
    }

    return value.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function getQuote(symbol) {
    return quotes[MARKETS[symbol].quoteSymbol];
  }

  function getQuoteMarkup(symbol) {
    const market = MARKETS[symbol];
    const quote = getQuote(symbol);

    if (!quote) {
      return `
        <div class="market-quote pending">
          <span>当前价格</span>
          <strong>载入中</strong>
          <small>正在获取最新行情</small>
        </div>
      `;
    }

    if (!quote.available) {
      return `
        <div class="market-quote unavailable">
          <span>当前价格</span>
          <strong>暂不可用</strong>
          <small>请打开外部行情页查看</small>
        </div>
      `;
    }

    const direction = quote.change >= 0 ? "up" : "down";
    const sign = quote.change >= 0 ? "+" : "";
    const label = quote.fallback ? "参考价格" : "当前价格";
    const changeText = quote.fallback
      ? "实时数据暂未连接"
      : `${sign}${formatNumber(quote.change, market.decimals)} · ${sign}${formatNumber(quote.changePercent, 2)}%`;

    return `
      <div class="market-quote ${direction}">
        <span>${label}</span>
        <strong>${formatNumber(quote.price, market.decimals)}</strong>
        <small>${changeText}</small>
        <em>${quote.date} ${quote.time}</em>
      </div>
    `;
  }

  function getRefreshStatusMarkup() {
    const suffix = lastRefreshLabel ? ` · ${lastRefreshLabel}` : "";

    return `
      <div class="market-refresh-status">
        <span>${quoteSource}${suffix}</span>
        <small>页面每 60 秒自动刷新</small>
      </div>
    `;
  }

  function escapeAttribute(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/"/g, "&quot;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;");
  }

  function getValidPoints(quote) {
    if (!quote || !Array.isArray(quote.points)) {
      return [];
    }

    return quote.points
      .map((point) => ({
        time: point.time || "",
        value: Number(point.value),
      }))
      .filter((point) => Number.isFinite(point.value));
  }

  function getLinePath(points, width, height, padding) {
    if (!points.length) {
      return "";
    }

    const values = points.map((point) => point.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const spread = max - min || 1;
    const innerWidth = width - padding * 2;
    const innerHeight = height - padding * 2;

    return points
      .map((point, index) => {
        const x =
          padding + (points.length === 1 ? innerWidth : (index / (points.length - 1)) * innerWidth);
        const y = padding + ((max - point.value) / spread) * innerHeight;
        return `${index === 0 ? "M" : "L"} ${x.toFixed(2)} ${y.toFixed(2)}`;
      })
      .join(" ");
  }

  function getChartMarkup(symbol) {
    const market = MARKETS[symbol];
    const quote = getQuote(symbol);
    const points = getValidPoints(quote);

    if (!quote || !quote.available || points.length < 2) {
      return `
        <div class="market-line-chart empty">
          <span>折线图载入中</span>
        </div>
      `;
    }

    const width = 640;
    const height = 260;
    const padding = 24;
    const values = points.map((point) => point.value);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const direction = quote.change >= 0 ? "up" : "down";
    const path = getLinePath(points, width, height, padding);
    const areaPath = `${path} L ${width - padding} ${height - padding} L ${padding} ${
      height - padding
    } Z`;
    const firstPoint = points[0];
    const lastPoint = points[points.length - 1];

    return `
      <div class="market-line-chart ${direction}" aria-label="${market.name} 日内折线图">
        <div class="market-chart-scale">
          <span>${formatNumber(max, market.decimals)}</span>
          <span>${formatNumber(min, market.decimals)}</span>
        </div>
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${market.name} price line">
          <path class="market-line-area" d="${areaPath}"></path>
          <path class="market-line-path" d="${path}"></path>
        </svg>
        <div class="market-chart-time">
          <span>${escapeAttribute(firstPoint.time)}</span>
          <span>${escapeAttribute(lastPoint.time)}</span>
        </div>
      </div>
    `;
  }

  function normalizeQuoteRows(data) {
    const symbols = data?.symbols;
    if (!symbols) {
      return [];
    }

    return Array.isArray(symbols) ? symbols : [symbols];
  }

  function formatUtcMoment(timestamp) {
    if (!timestamp) {
      return {
        date: "",
        time: "",
      };
    }

    const moment = new Date(Number(timestamp) * 1000);

    if (Number.isNaN(moment.getTime())) {
      return {
        date: "",
        time: "",
      };
    }

    return {
      date: moment.toISOString().slice(0, 10),
      time: `${moment.toISOString().slice(11, 16)} UTC`,
    };
  }

  function normalizeYahooChart(data, quoteSymbol) {
    const result = data?.chart?.result?.[0];
    const meta = result?.meta;

    if (!result || !meta) {
      return null;
    }

    const timestamps = result.timestamp || [];
    const closes = result.indicators?.quote?.[0]?.close || [];
    const price = Number(meta.regularMarketPrice);
    const open = Number(
      meta.chartPreviousClose ||
        meta.previousClose ||
        meta.regularMarketPreviousClose
    );
    const timestamp =
      meta.regularMarketTime || timestamps[timestamps.length - 1] || null;
    const moment = formatUtcMoment(timestamp);
    const points = timestamps
      .map((pointTimestamp, index) => ({
        time: formatUtcMoment(pointTimestamp).time.replace(" UTC", ""),
        timestamp: pointTimestamp,
        value: closes[index],
      }))
      .filter((point) => Number.isFinite(Number(point.value)))
      .slice(-180);

    if (!Number.isFinite(price) || !Number.isFinite(open)) {
      return null;
    }

    return {
      symbol: quoteSymbol,
      date: moment.date,
      time: moment.time,
      open,
      high: meta.regularMarketDayHigh || price,
      low: meta.regularMarketDayLow || price,
      close: price,
      points,
      sourceSymbol: meta.symbol || quoteSymbol,
    };
  }

  function parseQuote(row) {
    const price = Number(row.close);
    const open = Number(row.open);

    if (!Number.isFinite(price) || !Number.isFinite(open) || open === 0) {
      return {
        available: false,
      };
    }

    const change = price - open;

    return {
      available: true,
      change,
      changePercent: (change / open) * 100,
      date: row.date || "",
      high: Number(row.high),
      low: Number(row.low),
      points: Array.isArray(row.points) ? row.points : [],
      price,
      time: row.time || "",
    };
  }

  function getCacheBustedEndpoint(endpoint) {
    const separator = endpoint.includes("?") ? "&" : "?";
    return `${endpoint}${separator}refresh=${Date.now()}`;
  }

  function fetchJson(endpoint) {
    return fetch(getCacheBustedEndpoint(endpoint), {
      cache: "no-store",
    }).then((response) => {
      if (!response.ok) {
        throw new Error("Quote request failed");
      }

      return response.json();
    });
  }

  function applyQuoteData(data, options = {}) {
    const parsedQuotes = normalizeQuoteRows(data).reduce((nextQuotes, row) => {
      if (row.symbol) {
        nextQuotes[String(row.symbol).toUpperCase()] = parseQuote(row);
      }

      return nextQuotes;
    }, {});

    if (!Object.keys(parsedQuotes).length) {
      throw new Error("Quote response was empty");
    }

    quotes = options.merge ? { ...quotes, ...parsedQuotes } : parsedQuotes;
    quoteSource =
      data.source === "yahoo-live-browser" ? "实时接口" : "站内行情数据";
    lastRefreshLabel = new Date().toLocaleTimeString("zh-CN", {
      hour: "2-digit",
      minute: "2-digit",
    });
  }

  function fetchLiveQuotes() {
    return Promise.allSettled(
      LIVE_QUOTE_ENDPOINTS.map((item) =>
        fetchJson(
          `https://query1.finance.yahoo.com/v8/finance/chart/${encodeURIComponent(
            item.yahooSymbol
          )}?range=1d&interval=1m`
        ).then((data) => normalizeYahooChart(data, item.quoteSymbol))
      )
    ).then((results) => {
      const rows = results
        .filter((result) => result.status === "fulfilled" && result.value)
        .map((result) => result.value);

      if (!rows.length) {
        throw new Error("Live quotes unavailable");
      }

      return {
        source: "yahoo-live-browser",
        symbols: rows,
      };
    });
  }

  function fetchQuotes() {
    if (!window.fetch) {
      quotes = FALLBACK_QUOTES;
      quoteSource = "行情数据不可用";
      return Promise.resolve();
    }

    const timeout = new Promise((_, reject) => {
      window.setTimeout(() => {
        reject(new Error("Quote request timed out"));
      }, QUOTE_TIMEOUT);
    });

    return Promise.race([fetchJson(LOCAL_QUOTE_ENDPOINT), timeout])
      .then((data) => {
        applyQuoteData(data);
        renderChart(activeSymbol);
        return fetchLiveQuotes()
          .then((liveData) => {
            applyQuoteData(liveData, {
              merge: true,
            });
          })
          .catch(() => {});
      })
      .catch(() => {
        return fetchLiveQuotes()
          .then((liveData) => {
            applyQuoteData(liveData);
          })
          .catch(() => {
            quotes = FALLBACK_QUOTES;
            quoteSource = "行情数据不可用";
          });
      });
  }

  function refreshQuotes() {
    if (isRefreshing) {
      return;
    }

    isRefreshing = true;
    fetchQuotes()
      .then(() => {
        renderChart(activeSymbol);
      })
      .finally(() => {
        isRefreshing = false;
      });
  }

  function renderChart(symbol) {
    const market = MARKETS[symbol];
    if (!market) {
      return;
    }

    activeSymbol = symbol;
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
            ${getQuoteMarkup(marketSymbol)}
          </a>
        `;
      })
      .join("");

    chart.innerHTML = `
      <div class="market-asset-panel">
        <div class="market-asset-copy">
          <strong>${market.name}</strong>
          ${getQuoteMarkup(symbol)}
          ${getRefreshStatusMarkup()}
          <p>${market.summary}。页面会自动刷新行情；实时接口不可用时，会回退到站内自动更新数据。</p>
          <a class="market-open-link" href="${market.url}" target="_blank" rel="noreferrer">打开 ${market.name} 行情</a>
        </div>
        ${getChartMarkup(symbol)}
        <div class="market-asset-grid">${cards}</div>
      </div>
    `;
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      renderChart(tab.dataset.marketSymbol);
    });
  });

  renderChart(activeSymbol);
  refreshQuotes();
  window.setInterval(refreshQuotes, QUOTE_REFRESH_INTERVAL);
})();
