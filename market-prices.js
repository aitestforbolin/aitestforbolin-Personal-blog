(function () {
  "use strict";

  const DEFAULT_API_URL =
    "https://cross-asset-pulse.laibocszd.chatgpt.site/api/markets";
  const DISPLAY_TIMEZONE = "Asia/Shanghai";
  const REFRESH_INTERVAL = 60 * 1000;
  const FETCH_TIMEOUT = 10 * 1000;

  const MARKETS = [
    {
      id: "SPX",
      name: "标普 500",
      code: "SPX",
      group: "美股指数",
      session: "美股常规交易时段",
      unit: "price",
      decimals: 2,
      tradingView: "TVC:SPX",
      fallbackSymbol: "AMEX:SPY",
      fallbackLabel: "SPY ETF",
    },
    {
      id: "IXIC",
      name: "纳斯达克",
      code: "IXIC",
      group: "美股指数",
      session: "美股常规交易时段",
      unit: "price",
      decimals: 2,
      tradingView: "NASDAQ:IXIC",
      fallbackSymbol: "AMEX:ONEQ",
      fallbackLabel: "ONEQ ETF",
    },
    {
      id: "DJI",
      name: "道琼斯",
      code: "DJI",
      group: "美股指数",
      session: "美股常规交易时段",
      unit: "price",
      decimals: 2,
      tradingView: "TVC:DJI",
      fallbackSymbol: "AMEX:DIA",
      fallbackLabel: "DIA ETF",
    },
    {
      id: "DXY",
      name: "美元指数",
      code: "DXY",
      group: "美元与利率",
      session: "全球外汇交易时段",
      unit: "price",
      decimals: 2,
      tradingView: "TVC:DXY",
      fallbackSymbol: "TVC:DXY",
      fallbackLabel: "DXY",
    },
    {
      id: "US02Y",
      name: "美债 2 年期",
      code: "US02Y",
      group: "美元与利率",
      session: "美国国债交易时段",
      unit: "yield",
      decimals: 3,
      tradingView: "TVC:US02Y",
      fallbackSymbol: "TVC:US02Y",
      fallbackLabel: "US02Y",
    },
    {
      id: "US10Y",
      name: "美债 10 年期",
      code: "US10Y",
      group: "美元与利率",
      session: "美国国债交易时段",
      unit: "yield",
      decimals: 3,
      tradingView: "TVC:US10Y",
      fallbackSymbol: "TVC:US10Y",
      fallbackLabel: "US10Y",
    },
    {
      id: "GOLD",
      name: "黄金",
      code: "GOLD",
      group: "商品与加密",
      session: "全球贵金属交易时段",
      unit: "price",
      decimals: 2,
      tradingView: "COMEX:GC1!",
      fallbackSymbol: "OANDA:XAUUSD",
      fallbackLabel: "XAU/USD 现货",
    },
    {
      id: "BRN1!",
      name: "布伦特原油",
      code: "BRENT",
      group: "商品与加密",
      session: "全球原油期货交易时段",
      unit: "price",
      decimals: 2,
      tradingView: "NYMEX:BRN1!",
      fallbackSymbol: "TVC:UKOIL",
      fallbackLabel: "Brent 现货",
    },
    {
      id: "BTCUSDT",
      name: "比特币",
      code: "BTC",
      group: "商品与加密",
      session: "24 小时市场",
      unit: "price",
      decimals: 0,
      tradingView: "BINANCE:BTCUSDT",
      fallbackSymbol: "BINANCE:BTCUSDT",
      fallbackLabel: "BTC/USDT",
    },
  ];


  const SECTOR_GROUPS = [
    {
      id: "offense",
      label: "进攻板块",
      markets: [
        { id: "SOX", name: "费城半导体", fullName: "Philadelphia Semiconductor Index", code: "SOX", group: "进攻板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "NASDAQ:SOX", fallbackSymbol: "NASDAQ:SOXX", fallbackLabel: "SOXX ETF" },
        { id: "XLK", name: "科技", fullName: "Technology Select Sector SPDR ETF", code: "XLK", group: "进攻板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLK", fallbackSymbol: "AMEX:XLK", fallbackLabel: "XLK" },
        { id: "XLY", name: "可选消费", fullName: "Consumer Discretionary Select Sector SPDR ETF", code: "XLY", group: "进攻板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLY", fallbackSymbol: "AMEX:XLY", fallbackLabel: "XLY" },
        { id: "XLC", name: "通讯服务", fullName: "Communication Services Select Sector SPDR ETF", code: "XLC", group: "进攻板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLC", fallbackSymbol: "AMEX:XLC", fallbackLabel: "XLC" },
      ],
    },
    {
      id: "defense",
      label: "防御板块",
      markets: [
        { id: "XLV", name: "医疗保健", fullName: "Health Care Select Sector SPDR ETF", code: "XLV", group: "防御板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLV", fallbackSymbol: "AMEX:XLV", fallbackLabel: "XLV" },
        { id: "XLU", name: "公共事业", fullName: "Utilities Select Sector SPDR ETF", code: "XLU", group: "防御板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLU", fallbackSymbol: "AMEX:XLU", fallbackLabel: "XLU" },
        { id: "XLP", name: "必需消费", fullName: "Consumer Staples Select Sector SPDR ETF", code: "XLP", group: "防御板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLP", fallbackSymbol: "AMEX:XLP", fallbackLabel: "XLP" },
      ],
    },
    {
      id: "macro",
      label: "宏观敏感板块",
      markets: [
        { id: "XLE", name: "能源", fullName: "Energy Select Sector SPDR ETF", code: "XLE", group: "宏观敏感板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLE", fallbackSymbol: "AMEX:XLE", fallbackLabel: "XLE" },
        { id: "XLI", name: "工业", fullName: "Industrial Select Sector SPDR ETF", code: "XLI", group: "宏观敏感板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLI", fallbackSymbol: "AMEX:XLI", fallbackLabel: "XLI" },
        { id: "XLF", name: "金融", fullName: "Financial Select Sector SPDR ETF", code: "XLF", group: "宏观敏感板块", session: "美股常规交易时段", unit: "price", decimals: 2, tradingView: "AMEX:XLF", fallbackSymbol: "AMEX:XLF", fallbackLabel: "XLF" },
      ],
    },
  ];
  const SECTOR_MARKETS = SECTOR_GROUPS.flatMap((group) => group.markets);
  const ALL_MARKETS = [...MARKETS, ...SECTOR_MARKETS];

  const RANGE_LABELS = {
    "1d": "盘中",
    "5d": "5 日",
    "1mo": "1 月",
  };

  const root = document.querySelector("[data-market-module]");
  if (!root) {
    return;
  }
  const API_URL = root.dataset.marketApi || DEFAULT_API_URL;
  const previewProvider =
    typeof window.__BOLIN_MARKET_PREVIEW__ === "function"
      ? window.__BOLIN_MARKET_PREVIEW__
      : null;

  const tabsRoot = root.querySelector("[data-market-tabs]");
  const rangesRoot = root.querySelector("[data-market-ranges]");
  const nameElement = root.querySelector("[data-market-name]");
  const codeElement = root.querySelector("[data-market-code]");
  const sessionElement = root.querySelector("[data-market-session]");
  const priceElement = root.querySelector("[data-market-price]");
  const changeElement = root.querySelector("[data-market-change]");
  const statusElement = root.querySelector("[data-market-status]");
  const sourceElement = root.querySelector("[data-market-source]");
  const chartElement = root.querySelector("[data-market-chart]");
  const externalLink = root.querySelector("[data-market-external]");

  if (
    !tabsRoot ||
    !rangesRoot ||
    !nameElement ||
    !codeElement ||
    !sessionElement ||
    !priceElement ||
    !changeElement ||
    !statusElement ||
    !sourceElement ||
    !chartElement ||
    !externalLink
  ) {
    return;
  }

  const overview = new Map();
  const detailCache = new Map();
  let selectedId = "SPX";
  let selectedRange = "1d";
  let loadingOverview = true;
  let loadingDetail = false;
  let lastFetched = null;
  let overviewError = false;
  let requestSequence = 0;
  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function selectedMarket() {
    return ALL_MARKETS.find((market) => market.id === selectedId) || MARKETS[0];
  }

  function selectedData() {
    if (selectedRange === "1d") {
      return overview.get(selectedId);
    }
    return detailCache.get(`${selectedId}:${selectedRange}`);
  }

  function formatNumber(value, market) {
    if (!Number.isFinite(value)) {
      return "—";
    }
    const suffix = market.unit === "yield" ? "%" : "";
    return (
      value.toLocaleString("en-US", {
        minimumFractionDigits: market.decimals,
        maximumFractionDigits: market.decimals,
      }) + suffix
    );
  }

  function formatAxis(value, market) {
    if (!Number.isFinite(value)) {
      return "—";
    }
    if (market.unit === "yield") {
      return `${value.toFixed(2)}%`;
    }
    return value.toLocaleString("en-US", {
      maximumFractionDigits: Math.abs(value) >= 10000 ? 0 : 2,
    });
  }

  function formatPercent(value) {
    if (!Number.isFinite(value)) {
      return "等待行情";
    }
    return `${value >= 0 ? "+" : ""}${value.toFixed(2)}%`;
  }

  function formatClock(timestamp) {
    if (!Number.isFinite(timestamp)) {
      return "";
    }
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(timestamp);
  }

  function formatPointTime(timestamp, range) {
    if (!Number.isFinite(timestamp)) {
      return "";
    }
    const options =
      range === "1mo"
        ? {
            timeZone: DISPLAY_TIMEZONE,
            month: "numeric",
            day: "numeric",
          }
        : {
            timeZone: DISPLAY_TIMEZONE,
            month: "2-digit",
            day: "2-digit",
            hour: "2-digit",
            minute: "2-digit",
            hour12: false,
          };
    return new Intl.DateTimeFormat("zh-CN", options).format(timestamp);
  }

  function periodChange(data) {
    if (!data) {
      return null;
    }
    if (selectedRange === "1d") {
      return {
        value: Number(data.change),
        percent: Number(data.changePercent),
      };
    }
    const first = Number(data.points?.[0]?.value);
    const latest = Number(data.price);
    if (!Number.isFinite(first) || !Number.isFinite(latest) || first === 0) {
      return null;
    }
    return {
      value: latest - first,
      percent: ((latest - first) / first) * 100,
    };
  }

  function samplePoints(points, maximum) {
    if (points.length <= maximum) {
      return points;
    }
    const step = Math.ceil(points.length / maximum);
    const sampled = points.filter((_, index) => index % step === 0);
    const last = points[points.length - 1];
    if (sampled[sampled.length - 1] !== last) {
      sampled.push(last);
    }
    return sampled;
  }

  function renderTabs() {
    const groups = [...new Set(ALL_MARKETS.map((market) => market.group))];
    tabsRoot.innerHTML = groups
      .map(
        (group) => `
          <div class="market-pulse-tab-group">
            <span class="market-pulse-group-label">${escapeHtml(group)}</span>
            <div class="market-pulse-tab-row">
              ${ALL_MARKETS.filter((market) => market.group === group)
                .map(
                  (market) => `
                    <button
                      class="market-chart-tab${
                        market.id === selectedId ? " is-active" : ""
                      }"
                      type="button"
                      data-market-id="${escapeHtml(market.id)}"
                      aria-selected="${market.id === selectedId}"
                      role="tab"
                    >${escapeHtml(market.code)}</button>
                  `
                )
                .join("")}
            </div>
          </div>
        `
      )
      .join("");
  }

  function renderRanges() {
    rangesRoot.innerHTML = Object.entries(RANGE_LABELS)
      .map(
        ([range, label]) => `
          <button
            type="button"
            class="${range === selectedRange ? "is-active" : ""}"
            data-market-range="${range}"
            aria-pressed="${range === selectedRange}"
          >${label}</button>
        `
      )
      .join("");
  }

  function tradingViewUrl(market) {
    return `https://www.tradingview.com/chart/?symbol=${encodeURIComponent(
      market.tradingView
    )}`;
  }

  function fallbackMarkup(market) {
    const interval =
      selectedRange === "1d" ? "5" : selectedRange === "5d" ? "15" : "60";
    const source = new URL("https://s.tradingview.com/widgetembed/");
    source.searchParams.set("symbol", market.fallbackSymbol);
    source.searchParams.set("interval", interval);
    source.searchParams.set("hidesidetoolbar", "1");
    source.searchParams.set("symboledit", "0");
    source.searchParams.set("saveimage", "0");
    source.searchParams.set("theme", "light");
    source.searchParams.set("style", "2");
    source.searchParams.set("timezone", DISPLAY_TIMEZONE);
    source.searchParams.set("withdateranges", "1");
    source.searchParams.set("hideideas", "1");
    source.searchParams.set("locale", "zh_CN");

    return `
      <div class="market-pulse-fallback">
        <span class="market-pulse-fallback-badge">
          TradingView 备用图表 · ${escapeHtml(market.fallbackLabel)}
        </span>
        <iframe
          src="${escapeHtml(source.toString())}"
          title="${escapeHtml(market.name)} TradingView 图表"
          loading="eager"
          allowfullscreen
        ></iframe>
      </div>
    `;
  }

  function loadingMarkup() {
    return `
      <div class="market-pulse-loading">
        <span class="market-pulse-loader" aria-hidden="true"></span>
        <strong>正在连接市场数据</strong>
        <small>若主数据源暂时不可用，将自动显示备用图表</small>
      </div>
    `;
  }

  function renderLineChart(data, market, change) {
    const rawPoints = Array.isArray(data?.points)
      ? data.points
          .map((point) => ({
            time: Number(point.time),
            value: Number(point.value),
          }))
          .filter(
            (point) =>
              Number.isFinite(point.time) && Number.isFinite(point.value)
          )
      : [];
    const points = samplePoints(rawPoints, 720);

    if (points.length < 2) {
      return false;
    }

    const width = 960;
    const height = 360;
    const left = 18;
    const right = 88;
    const top = 16;
    const bottom = 38;
    const plotWidth = width - left - right;
    const plotHeight = height - top - bottom;
    const values = points.map((point) => point.value);
    const rawMin = Math.min(...values);
    const rawMax = Math.max(...values);
    const padding =
      (rawMax - rawMin || Math.max(Math.abs(rawMax) * 0.005, 1)) * 0.08;
    const min = rawMin - padding;
    const max = rawMax + padding;
    const xFor = (index) =>
      left + (index / Math.max(1, points.length - 1)) * plotWidth;
    const yFor = (value) =>
      top + ((max - value) / Math.max(max - min, 1)) * plotHeight;
    const linePath = points
      .map(
        (point, index) =>
          `${index ? "L" : "M"}${xFor(index).toFixed(2)},${yFor(
            point.value
          ).toFixed(2)}`
      )
      .join(" ");
    const areaPath = `${linePath} L${xFor(points.length - 1)},${
      top + plotHeight
    } L${left},${top + plotHeight} Z`;
    const direction = (change?.percent || 0) >= 0 ? "up" : "down";

    const yTicks = [0, 1, 2, 3, 4]
      .map((tick) => {
        const y = top + (tick / 4) * plotHeight;
        const value = max - (tick / 4) * (max - min);
        return `
          <g>
            <line x1="${left}" x2="${left + plotWidth}" y1="${y}" y2="${y}" class="market-pulse-grid-line"></line>
            <text x="${left + plotWidth + 12}" y="${
          y + 4
        }" class="market-pulse-axis-label">${escapeHtml(
          formatAxis(value, market)
        )}</text>
          </g>
        `;
      })
      .join("");

    const xTicks = [0, 1, 2, 3, 4]
      .map((tick) => {
        const index = Math.round((tick / 4) * (points.length - 1));
        const x = xFor(index);
        const anchor = tick === 0 ? "start" : tick === 4 ? "end" : "middle";
        return `
          <text x="${x}" y="${
          height - 13
        }" text-anchor="${anchor}" class="market-pulse-axis-label">
            ${escapeHtml(formatPointTime(points[index].time, selectedRange))}
          </text>
        `;
      })
      .join("");

    chartElement.innerHTML = `
      <div class="market-pulse-line-chart ${direction}">
        <svg
          viewBox="0 0 ${width} ${height}"
          preserveAspectRatio="none"
          role="img"
          aria-label="${escapeHtml(market.name)} ${
      RANGE_LABELS[selectedRange]
    }价格折线图"
          data-market-svg
        >
          <defs>
            <linearGradient id="marketPulseArea" x1="0" x2="0" y1="0" y2="1">
              <stop offset="0%" stop-opacity="0.22"></stop>
              <stop offset="100%" stop-opacity="0"></stop>
            </linearGradient>
          </defs>
          ${yTicks}
          ${xTicks}
          <path d="${areaPath}" class="market-pulse-area"></path>
          <path d="${linePath}" class="market-pulse-path" vector-effect="non-scaling-stroke"></path>
          <g data-market-crosshair style="display:none">
            <line y1="${top}" y2="${
      top + plotHeight
    }" class="market-pulse-crosshair" data-market-crosshair-line></line>
            <circle r="5" class="market-pulse-point" data-market-crosshair-point></circle>
            <g data-market-tooltip>
              <rect width="202" height="54" rx="7" class="market-pulse-tooltip-bg"></rect>
              <text x="12" y="21" class="market-pulse-tooltip-time" data-market-tooltip-time></text>
              <text x="12" y="42" class="market-pulse-tooltip-price" data-market-tooltip-price></text>
            </g>
          </g>
        </svg>
      </div>
    `;

    const svg = chartElement.querySelector("[data-market-svg]");
    const crosshair = chartElement.querySelector("[data-market-crosshair]");
    const crosshairLine = chartElement.querySelector(
      "[data-market-crosshair-line]"
    );
    const crosshairPoint = chartElement.querySelector(
      "[data-market-crosshair-point]"
    );
    const tooltip = chartElement.querySelector("[data-market-tooltip]");
    const tooltipTime = chartElement.querySelector(
      "[data-market-tooltip-time]"
    );
    const tooltipPrice = chartElement.querySelector(
      "[data-market-tooltip-price]"
    );

    if (
      svg &&
      crosshair &&
      crosshairLine &&
      crosshairPoint &&
      tooltip &&
      tooltipTime &&
      tooltipPrice
    ) {
      const showPoint = (event) => {
        const rect = svg.getBoundingClientRect();
        if (!rect.width) {
          return;
        }
        const viewX = ((event.clientX - rect.left) / rect.width) * width;
        const index = Math.max(
          0,
          Math.min(
            points.length - 1,
            Math.round(
              ((viewX - left) / plotWidth) * Math.max(1, points.length - 1)
            )
          )
        );
        const point = points[index];
        const x = xFor(index);
        const y = yFor(point.value);
        const tooltipX = Math.min(Math.max(x + 12, left), width - 214);
        const tooltipY = Math.min(
          Math.max(y - 66, top + 4),
          top + plotHeight - 58
        );

        crosshair.style.display = "";
        crosshairLine.setAttribute("x1", x);
        crosshairLine.setAttribute("x2", x);
        crosshairPoint.setAttribute("cx", x);
        crosshairPoint.setAttribute("cy", y);
        tooltip.setAttribute(
          "transform",
          `translate(${tooltipX},${tooltipY})`
        );
        tooltipTime.textContent = formatPointTime(
          point.time,
          selectedRange
        );
        tooltipPrice.textContent = formatNumber(point.value, market);
      };

      svg.addEventListener("pointermove", showPoint);
      svg.addEventListener("pointerleave", () => {
        crosshair.style.display = "none";
      });
    }

    return true;
  }

  function render() {
    const market = selectedMarket();
    const data = selectedData();
    const change = periodChange(data);
    const isLoading =
      selectedRange === "1d" ? loadingOverview : loadingDetail;

    renderTabs();
    renderRanges();

    nameElement.textContent = market.name;
    codeElement.textContent = market.code;
    sessionElement.textContent =
      data?.contractLabel
        ? `${data.contractLabel} · 单一近月合约 · ${RANGE_LABELS[selectedRange]}`
        : data?.granularity === "daily"
          ? `${data.source === "U.S. Treasury" ? "美国财政部" : "FRED"}官方日线 · 最近可用交易日`
          : market.id === "BTCUSDT" && selectedRange === "1d"
            ? "过去 24 小时 · 5 分钟粒度"
            : `${market.session} · ${RANGE_LABELS[selectedRange]}`;
    priceElement.textContent = data
      ? formatNumber(Number(data.price), market)
      : "—";
    changeElement.textContent = change
      ? formatPercent(change.percent)
      : "等待行情";
    changeElement.classList.toggle(
      "is-positive",
      Boolean(change && change.percent >= 0)
    );
    changeElement.classList.toggle(
      "is-negative",
      Boolean(change && change.percent < 0)
    );

    externalLink.href = tradingViewUrl(market);

    if (data && Array.isArray(data.points) && data.points.length >= 2) {
      renderLineChart(data, market, change);
      sourceElement.textContent =
        data.contractLabel
          ? `Yahoo Finance · ${data.contractLabel} · 单一合约连续取值 · 避免换月断层`
          : data.source === "U.S. Treasury"
            ? "美国财政部 · 2 年期官方收益率日线 · 仅供研究参考"
            : data.source === "FRED"
              ? "FRED · 美联储 H.15 DGS2 官方日线 · 仅供研究参考"
              : "Yahoo Finance · 价格可能延迟 · 仅供研究参考";
    } else if (isLoading) {
      chartElement.innerHTML = loadingMarkup();
      sourceElement.textContent = "正在获取主数据源";
    } else {
      chartElement.innerHTML = fallbackMarkup(market);
      sourceElement.textContent = `主数据源暂不可用 · 已切换 ${market.fallbackLabel}`;
    }

    if (isLoading) {
      statusElement.textContent = "正在更新行情";
    } else if (overviewError && !overview.size) {
      statusElement.textContent = "主数据源暂不可用 · 备用图表已启用";
    } else {
      statusElement.textContent = lastFetched
        ? `自动刷新 · 60 秒 · ${formatClock(lastFetched)} 北京`
        : "自动刷新 · 60 秒";
    }
  }

  async function fetchPayload(range, id) {
    if (previewProvider) {
      return previewProvider(range, id);
    }
    if (!window.fetch) {
      throw new Error("Fetch is unavailable");
    }
    const controller = new AbortController();
    const timeout = window.setTimeout(
      () => controller.abort(),
      FETCH_TIMEOUT
    );
    const url = new URL(API_URL);
    url.searchParams.set("range", range);
    if (id) {
      url.searchParams.set("id", id);
    }

    try {
      const response = await fetch(url.toString(), {
        cache: "no-store",
        credentials: "omit",
        signal: controller.signal,
      });
      if (!response.ok) {
        throw new Error(`Market API ${response.status}`);
      }
      return response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  async function loadOverview() {
    if (!overview.size) {
      loadingOverview = true;
      render();
    }

    try {
      const payload = await fetchPayload("1d");
      const coreIds = new Set(ALL_MARKETS.map((market) => market.id));
      (payload.data || []).forEach((item) => {
        if (coreIds.has(item.id)) {
          overview.set(item.id, item);
        }
      });
      lastFetched = Number(payload.fetchedAt) || Date.now();
      overviewError = false;
    } catch (_error) {
      overviewError = true;
    } finally {
      loadingOverview = false;
      render();
    }
  }

  async function loadDetail() {
    const cacheKey = `${selectedId}:${selectedRange}`;
    if (detailCache.has(cacheKey)) {
      loadingDetail = false;
      render();
      return;
    }

    const currentRequest = ++requestSequence;
    loadingDetail = true;
    render();

    try {
      const payload = await fetchPayload(selectedRange, selectedId);
      if (currentRequest !== requestSequence) {
        return;
      }
      const item = payload.data?.[0];
      if (item) {
        detailCache.set(cacheKey, item);
      }
      lastFetched = Number(payload.fetchedAt) || Date.now();
    } catch (_error) {
      // The renderer will switch this individual asset to TradingView.
    } finally {
      if (currentRequest === requestSequence) {
        loadingDetail = false;
        render();
      }
    }
  }

  tabsRoot.addEventListener("click", (event) => {
    const button = event.target.closest("[data-market-id]");
    if (!button) {
      return;
    }
    selectedId = button.dataset.marketId;
    selectedRange = "1d";
    requestSequence += 1;
    loadingDetail = false;
    render();
  });

  rangesRoot.addEventListener("click", (event) => {
    const button = event.target.closest("[data-market-range]");
    if (!button || button.dataset.marketRange === selectedRange) {
      return;
    }
    selectedRange = button.dataset.marketRange;
    if (selectedRange === "1d") {
      requestSequence += 1;
      loadingDetail = false;
      render();
    } else {
      loadDetail();
    }
  });

  render();
  loadOverview();

  window.setInterval(() => {
    if (document.visibilityState !== "visible") {
      return;
    }
    loadOverview();
    if (selectedRange !== "1d") {
      detailCache.delete(`${selectedId}:${selectedRange}`);
      loadDetail();
    }
  }, REFRESH_INTERVAL);
})();
