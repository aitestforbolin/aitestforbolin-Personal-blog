(function () {
  const API_BASES = [
    "https://data-api.binance.vision",
    "https://api1.binance.com",
    "https://api2.binance.com",
    "https://api3.binance.com",
    "https://api.binance.com",
  ];
  const STREAM_BASE = "wss://data-stream.binance.vision/stream";
  const INTERVAL = "5m";
  const LIMIT = 288;
  const FETCH_TIMEOUT = 8000;
  const REFRESH_INTERVAL = 60 * 1000;

  const MARKETS = {
    "BINANCE:BTCUSDT": {
      name: "BTC",
      proxy: "BTC/USDT",
      summary: "比特币兑 USDT",
      liveSymbol: "BTCUSDT",
      decimals: 0,
      url: "https://www.tradingview.com/chart/?symbol=BINANCE%3ABTCUSDT",
    },
    "OANDA:XAUUSD": {
      name: "黄金",
      proxy: "PAXG/USDT",
      summary: "PAX Gold 兑 USDT，作为黄金代理行情",
      liveSymbol: "PAXGUSDT",
      decimals: 1,
      isProxy: true,
      url: "https://www.tradingview.com/chart/?symbol=BINANCE%3APAXGUSDT",
    },
    "BINANCE:ETHUSDT": {
      name: "ETH",
      proxy: "ETH/USDT",
      summary: "以太坊兑 USDT",
      liveSymbol: "ETHUSDT",
      decimals: 1,
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

  const marketList = Object.entries(MARKETS).map(([symbol, market]) => ({
    ...market,
    symbol,
  }));
  const marketByLiveSymbol = marketList.reduce((next, market) => {
    next.set(market.liveSymbol, market);
    return next;
  }, new Map());

  const quotes = new Map();
  let activeSymbol = tabs[0].dataset.marketSymbol;
  let socket = null;
  let reconnectTimer = null;
  let refreshTimer = null;
  let isRefreshing = false;
  let socketConnected = false;
  let lastRefreshLabel = "";
  let sourceLabel = "正在加载行情";

  function formatNumber(value, decimals) {
    if (!Number.isFinite(value)) {
      return "--";
    }

    return value.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function formatPercent(value) {
    if (!Number.isFinite(value)) {
      return "--";
    }

    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  }

  function formatTime(timestamp) {
    if (!Number.isFinite(timestamp)) {
      return "";
    }

    const parts = new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Shanghai",
    })
      .formatToParts(timestamp)
      .reduce((next, part) => {
        next[part.type] = part.value;
        return next;
      }, {});

    return `${parts.month}/${parts.day} ${parts.hour}:${parts.minute}`;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function getQuote(symbol) {
    return quotes.get(symbol);
  }

  function getValidPoints(quote) {
    if (!quote || !Array.isArray(quote.points)) {
      return [];
    }

    return quote.points.filter((point) => Number.isFinite(point.close));
  }

  function withTimeout(promise, timeoutMs) {
    let timeoutId = null;
    const timeout = new Promise((_, reject) => {
      timeoutId = window.setTimeout(() => {
        reject(new Error("Market data request timed out"));
      }, timeoutMs);
    });

    return Promise.race([promise, timeout]).finally(() => {
      window.clearTimeout(timeoutId);
    });
  }

  async function fetchJson(path, params) {
    if (!window.fetch) {
      throw new Error("Fetch is unavailable");
    }

    const query = new URLSearchParams(params).toString();
    let lastError = null;

    for (const apiBase of API_BASES) {
      try {
        const response = await withTimeout(
          fetch(`${apiBase}/api/v3/${path}?${query}`, {
            cache: "no-store",
          }),
          FETCH_TIMEOUT
        );

        if (!response.ok) {
          lastError = new Error(`Market data request failed: ${response.status}`);
          continue;
        }

        return response.json();
      } catch (error) {
        lastError = error;
      }
    }

    throw lastError || new Error("Market data request failed");
  }

  function normalizeKline(row) {
    return {
      time: Number(row[0]),
      open: Number(row[1]),
      high: Number(row[2]),
      low: Number(row[3]),
      close: Number(row[4]),
      volume: Number(row[5]),
    };
  }

  function normalizeRows(rows) {
    if (!Array.isArray(rows)) {
      return [];
    }

    return rows
      .map(normalizeKline)
      .filter((point) => Number.isFinite(point.time) && Number.isFinite(point.close))
      .slice(-LIMIT);
  }

  function makeQuote(market, series, ticker) {
    const points = series.slice(-LIMIT);
    const lastPoint = points[points.length - 1];
    const tickerPrice = Number(ticker?.lastPrice);
    const latestPrice = Number.isFinite(tickerPrice) ? tickerPrice : lastPoint?.close;
    const tickerTime = Number(ticker?.closeTime);
    const latestTime = Number.isFinite(tickerTime) ? tickerTime : lastPoint?.time || Date.now();

    if (!Number.isFinite(latestPrice)) {
      return {
        available: false,
        points,
      };
    }

    if (!lastPoint || latestTime > lastPoint.time) {
      points.push({
        time: latestTime,
        open: latestPrice,
        high: latestPrice,
        low: latestPrice,
        close: latestPrice,
        volume: 0,
      });
    } else {
      points[points.length - 1] = {
        ...lastPoint,
        time: latestTime,
        close: latestPrice,
      };
    }

    while (points.length > LIMIT) {
      points.shift();
    }

    const openFromTicker = Number(ticker?.openPrice);
    const firstPrice = Number.isFinite(openFromTicker)
      ? openFromTicker
      : points[0]?.close || latestPrice;
    const changeFromTicker = Number(ticker?.priceChange);
    const change = Number.isFinite(changeFromTicker)
      ? changeFromTicker
      : latestPrice - firstPrice;
    const percentFromTicker = Number(ticker?.priceChangePercent);
    const changePercent = Number.isFinite(percentFromTicker)
      ? percentFromTicker
      : firstPrice
        ? (change / firstPrice) * 100
        : 0;

    return {
      available: true,
      change,
      changePercent,
      firstPrice,
      market,
      points,
      price: latestPrice,
      time: latestTime,
    };
  }

  async function loadMarket(market) {
    const [klineResult, tickerResult] = await Promise.allSettled([
      fetchJson("klines", {
        symbol: market.liveSymbol,
        interval: INTERVAL,
        limit: String(LIMIT),
      }),
      fetchJson("ticker/24hr", {
        symbol: market.liveSymbol,
      }),
    ]);

    const previous = quotes.get(market.symbol);
    const rows = klineResult.status === "fulfilled" ? klineResult.value : null;
    const ticker = tickerResult.status === "fulfilled" ? tickerResult.value : null;
    const series = rows ? normalizeRows(rows) : previous?.points || [];

    if (!series.length && !ticker) {
      throw new Error(`${market.liveSymbol} data unavailable`);
    }

    quotes.set(market.symbol, makeQuote(market, series, ticker));
  }

  function getQuoteMarkup(symbol, options = {}) {
    const market = MARKETS[symbol];
    const quote = getQuote(symbol);
    const sizeClass = options.prominent ? " prominent" : "";

    if (!quote) {
      return `
        <div class="market-quote pending${sizeClass}">
          <span>当前价格</span>
          <strong>载入中</strong>
          <small>正在获取最新行情</small>
        </div>
      `;
    }

    if (!quote.available) {
      return `
        <div class="market-quote unavailable${sizeClass}">
          <span>当前价格</span>
          <strong>暂不可用</strong>
          <small>公开行情接口暂时不可连接</small>
        </div>
      `;
    }

    const direction = quote.change >= 0 ? "up" : "down";
    const changeText = `${quote.change >= 0 ? "+" : ""}${formatNumber(
      quote.change,
      market.decimals
    )} · ${formatPercent(quote.changePercent)}`;
    const sourceText = market.isProxy ? "黄金代理" : "实时行情";

    return `
      <div class="market-quote ${direction}${sizeClass}">
        <span>当前价格</span>
        <strong>${formatNumber(quote.price, market.decimals)}</strong>
        <small>${changeText}</small>
        <em>${formatTime(quote.time)} · ${sourceText}</em>
      </div>
    `;
  }

  function getRefreshStatusMarkup() {
    const status = socketConnected ? "实时连接中" : sourceLabel;
    const suffix = lastRefreshLabel ? ` · ${lastRefreshLabel}` : "";

    return `
      <div class="market-refresh-status">
        <span>${escapeHtml(status)}${escapeHtml(suffix)}</span>
        <small>WebSocket 实时更新，页面每 60 秒补拉一次</small>
      </div>
    `;
  }

  function getLinePath(points, width, height, padding) {
    if (!points.length) {
      return "";
    }

    const values = points.map((point) => point.close);
    const min = Math.min(...values);
    const max = Math.max(...values);
    const spread = max - min || 1;
    const innerWidth = width - padding * 2;
    const innerHeight = height - padding * 2;

    return points
      .map((point, index) => {
        const x =
          padding +
          (points.length === 1 ? innerWidth : (index / (points.length - 1)) * innerWidth);
        const y = padding + ((max - point.close) / spread) * innerHeight;
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
    const values = points.map((point) => point.close);
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
      <div class="market-line-chart ${direction}" aria-label="${escapeHtml(
        market.name
      )} 24 小时折线图">
        <div class="market-chart-scale">
          <span>${formatNumber(max, market.decimals)}</span>
          <span>${formatNumber(min, market.decimals)}</span>
        </div>
        <svg viewBox="0 0 ${width} ${height}" role="img" aria-label="${escapeHtml(
      market.name
    )} price line">
          <path class="market-line-area" d="${path ? areaPath : ""}"></path>
          <path class="market-line-path" d="${path}"></path>
        </svg>
        <div class="market-chart-time">
          <span>${escapeHtml(formatTime(firstPoint.time))}</span>
          <span>${escapeHtml(formatTime(lastPoint.time))}</span>
        </div>
      </div>
    `;
  }

  function renderChart(symbol) {
    const market = MARKETS[symbol];
    if (!market) {
      return;
    }

    activeSymbol = symbol;
    name.textContent = market.name;
    proxy.textContent = `${market.proxy}${market.isProxy ? " · 黄金代理" : ""} · 24h · 5m`;

    tabs.forEach((tab) => {
      const isActive = tab.dataset.marketSymbol === symbol;
      tab.classList.toggle("is-active", isActive);
      tab.setAttribute("aria-selected", String(isActive));
    });

    const cards = marketList
      .map((item) => {
        const activeClass = item.symbol === symbol ? " is-active" : "";
        return `
          <a class="market-asset-card${activeClass}" href="${item.url}" target="_blank" rel="noreferrer">
            <span>${escapeHtml(item.name)}</span>
            <strong>${escapeHtml(item.proxy)}</strong>
            <small>${escapeHtml(item.summary)}</small>
            ${getQuoteMarkup(item.symbol)}
          </a>
        `;
      })
      .join("");

    chart.innerHTML = `
      <div class="market-asset-panel">
        <div class="market-asset-copy">
          <strong>${escapeHtml(market.name)}</strong>
          ${getQuoteMarkup(symbol, { prominent: true })}
          ${getRefreshStatusMarkup()}
          <p>${escapeHtml(market.summary)}。当前价格来自公开实时行情接口；黄金使用 PAXG/USDT 作为代理，不再伪装成 TradingView 内嵌报价。</p>
          <a class="market-open-link" href="${market.url}" target="_blank" rel="noreferrer">打开 ${escapeHtml(
      market.name
    )} 行情</a>
        </div>
        ${getChartMarkup(symbol)}
        <div class="market-asset-grid">${cards}</div>
      </div>
    `;
  }

  async function refreshMarkets() {
    if (isRefreshing) {
      return;
    }

    isRefreshing = true;
    const results = await Promise.allSettled(marketList.map(loadMarket));
    const hasData = results.some((result) => result.status === "fulfilled");
    sourceLabel = hasData ? "行情已更新" : "行情暂不可用";
    lastRefreshLabel = formatTime(Date.now());
    isRefreshing = false;
    renderChart(activeSymbol);
  }

  function upsertKline(liveSymbol, kline) {
    const market = marketByLiveSymbol.get(liveSymbol);
    if (!market) {
      return;
    }

    const previous = quotes.get(market.symbol);
    const points = previous?.points ? previous.points.slice() : [];
    const point = {
      time: Number(kline.t),
      open: Number(kline.o),
      high: Number(kline.h),
      low: Number(kline.l),
      close: Number(kline.c),
      volume: Number(kline.v),
    };

    if (!Number.isFinite(point.time) || !Number.isFinite(point.close)) {
      return;
    }

    const lastPoint = points[points.length - 1];
    if (lastPoint && lastPoint.time === point.time) {
      points[points.length - 1] = point;
    } else {
      points.push(point);
    }

    while (points.length > LIMIT) {
      points.shift();
    }

    const firstPrice = previous?.firstPrice || points[0]?.close || point.close;
    const change = point.close - firstPrice;
    quotes.set(market.symbol, {
      available: true,
      change,
      changePercent: firstPrice ? (change / firstPrice) * 100 : 0,
      firstPrice,
      market,
      points,
      price: point.close,
      time: point.time,
    });

    renderChart(activeSymbol);
  }

  function connectStream() {
    if (!window.WebSocket) {
      return;
    }

    clearTimeout(reconnectTimer);

    const streams = marketList
      .map((market) => `${market.liveSymbol.toLowerCase()}@kline_${INTERVAL}`)
      .join("/");

    socket = new WebSocket(`${STREAM_BASE}?streams=${streams}`);

    socket.addEventListener("open", () => {
      socketConnected = true;
      renderChart(activeSymbol);
    });

    socket.addEventListener("message", (event) => {
      try {
        const payload = JSON.parse(event.data);
        const data = payload.data;
        if (!data || !data.k) {
          return;
        }

        upsertKline(data.s, data.k);
      } catch (error) {
        sourceLabel = "实时数据解析失败";
        renderChart(activeSymbol);
      }
    });

    socket.addEventListener("close", () => {
      socketConnected = false;
      sourceLabel = "实时连接已断开";
      renderChart(activeSymbol);
      reconnectTimer = window.setTimeout(connectStream, 5000);
    });

    socket.addEventListener("error", () => {
      socketConnected = false;
      sourceLabel = "实时连接已断开";
      renderChart(activeSymbol);
    });
  }

  tabs.forEach((tab) => {
    tab.addEventListener("click", () => {
      renderChart(tab.dataset.marketSymbol);
    });
  });

  renderChart(activeSymbol);
  refreshMarkets().then(connectStream);
  refreshTimer = window.setInterval(refreshMarkets, REFRESH_INTERVAL);
  window.addEventListener("beforeunload", () => {
    window.clearInterval(refreshTimer);
    window.clearTimeout(reconnectTimer);
    if (socket) {
      socket.close();
    }
  });
})();
