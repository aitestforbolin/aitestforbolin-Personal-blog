(function () {
  const LOCAL_QUOTE_ENDPOINT = "data/market-prices.json";
  const REMOTE_QUOTE_ENDPOINT =
    "https://api.allorigins.win/raw?url=https%3A%2F%2Fstooq.com%2Fq%2Fl%2F%3Fs%3Dbtcusd%2Cxauusd%2Cspy.us%2Cqqq.us%2Cdia.us%26f%3Dsd2t2ohlcv%26h%26e%3Djson";
  const QUOTE_TIMEOUT = 6500;
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

  function normalizeQuoteRows(data) {
    const symbols = data?.symbols;
    if (!symbols) {
      return [];
    }

    return Array.isArray(symbols) ? symbols : [symbols];
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
      price,
      time: row.time || "",
    };
  }

  function fetchQuotes() {
    if (!window.fetch) {
      quotes = FALLBACK_QUOTES;
      return Promise.resolve();
    }

    function fetchQuoteData(endpoint) {
      return fetch(endpoint, {
        cache: "no-store",
      }).then((response) => {
        if (!response.ok) {
          throw new Error("Quote request failed");
        }

        return response.json();
      });
    }

    const timeout = new Promise((_, reject) => {
      window.setTimeout(() => {
        reject(new Error("Quote request timed out"));
      }, QUOTE_TIMEOUT);
    });

    const request = fetchQuoteData(LOCAL_QUOTE_ENDPOINT).catch(() =>
      fetchQuoteData(REMOTE_QUOTE_ENDPOINT)
    );

    return Promise.race([request, timeout])
      .then((data) => {
        quotes = normalizeQuoteRows(data).reduce((nextQuotes, row) => {
          if (row.symbol) {
            nextQuotes[String(row.symbol).toUpperCase()] = parseQuote(row);
          }

          return nextQuotes;
        }, {});

        if (!Object.keys(quotes).length) {
          throw new Error("Quote response was empty");
        }
      })
      .catch(() => {
        quotes = FALLBACK_QUOTES;
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
          <p>${market.summary}。当前网络环境下 TradingView 内嵌图表不可用，页面会尽量显示最新价格和日内涨跌幅。</p>
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

  renderChart(activeSymbol);
  fetchQuotes().then(() => {
    renderChart(activeSymbol);
  });
})();
