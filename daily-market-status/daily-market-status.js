(function () {
  "use strict";

  const root = document.querySelector("[data-daily-status]");
  if (!root) return;

  const MARKETS_API =
    "https://cross-asset-pulse.laibocszd.chatgpt.site/api/markets";
  const BREADTH_API =
    "https://cross-asset-pulse.laibocszd.chatgpt.site/api/breadth";
  const SNAPSHOT_URL = "../data/daily-market-status.json";
  const ETF_URL = "../data/btc-etf-flow.json";
  const DISPLAY_TIMEZONE = "Asia/Shanghai";
  const FETCH_TIMEOUT = 10000;
  const RETRY_DELAYS = [60000, 120000, 300000, 900000];

  const indexConfig = [
    ["SPX", "标普500"],
    ["IXIC", "纳斯达克"],
    ["DJI", "道琼斯"],
  ];
  const sectorConfig = [
    ["进攻和成长", [["SOX", "SOX（半导体指数）"], ["XLK", "XLK（信息技术）"], ["XLY", "XLY（可选消费）"], ["XLC", "XLC（通信服务）"]]],
    ["防御", [["XLV", "XLV（医疗保健）"], ["XLU", "XLU（公共事业）"], ["XLP", "XLP（必需消费）"]]],
    ["宏观敏感", [["XLE", "XLE（能源）"], ["XLI", "XLI（工业）"], ["XLF", "XLF（金融）"]]],
  ];
  const macroConfig = [
    ["DXY", "美元指数", 3, "", "Yahoo Finance · DX-Y.NYB"],
    ["US02Y", "2年期美债收益率", 3, "%", "TradingView · TVC:US02Y"],
    ["US10Y", "10年期美债收益率", 3, "%", "Yahoo Finance · ^TNX"],
    ["US30Y", "30年期美债收益率", 3, "%", "Yahoo Finance · ^TYX"],
    ["BRN1!", "Brent期货", 2, "", "TradingView · ICEEUR:BRN1!"],
    ["GOLD", "黄金", 2, "", "TradingView · OANDA:XAUUSD"],
    ["BTCUSDT", "BTC", 0, "", "Yahoo Finance · BTC-USD"],
  ];

  let snapshot = null;
  let etfData = null;
  let marketMap = new Map();
  let breadthData = [];
  let marketsFetchedAt = 0;
  let retryIndex = 0;
  let timer = null;

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  async function fetchJson(url) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT);
    try {
      const response = await fetch(url, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.json();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function formatDate(dateValue) {
    if (!dateValue) return "日期待核验";
    const date = new Date(`${dateValue}T12:00:00+08:00`);
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      year: "numeric",
      month: "long",
      day: "numeric",
    }).format(date);
  }

  function formatClock(timestamp) {
    const numeric = Number(timestamp);
    if (!Number.isFinite(numeric)) return "时间待核验";
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(numeric));
  }

  function formatEventDay(iso) {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      month: "2-digit",
      day: "2-digit",
    }).format(new Date(iso));
  }

  function formatEventTime(iso) {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(new Date(iso));
  }

  function formatPercent(value) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return `${number > 0 ? "+" : ""}${number.toFixed(2)}%`;
  }

  function directionClass(value) {
    const number = Number(value);
    if (number > 0) return "is-up";
    if (number < 0) return "is-down";
    return "is-flat";
  }

  function formatNumber(value, decimals) {
    const number = Number(value);
    if (!Number.isFinite(number)) return "—";
    return number.toLocaleString("en-US", {
      minimumFractionDigits: decimals,
      maximumFractionDigits: decimals,
    });
  }

  function setState(name, text, level) {
    const element = root.querySelector(`[data-state="${name}"]`);
    if (!element) return;
    element.textContent = text;
    element.dataset.level = level || "fresh";
  }

  function fallbackMap() {
    return new Map(
      (snapshot?.fallback?.markets || []).map((item) => [item.id, item])
    );
  }

  function renderIndices() {
    const target = root.querySelector("[data-indices]");
    target.innerHTML = indexConfig
      .map(([id, label]) => {
        const item = marketMap.get(id);
        return `<span class="pipe-item ${directionClass(item?.changePercent)}">${label} ${formatPercent(item?.changePercent)}</span>`;
      })
      .join("");
  }

  function renderBreadth() {
    const target = root.querySelector("[data-breadth]");
    target.innerHTML = breadthData
      .filter((item) => item && Number.isFinite(Number(item.advancers)))
      .map(
        (item) => `
          <div class="breadth-row">
            <strong>${escapeHtml(item.id === "SP500" ? "标普500" : "纳斯达克交易所")}：</strong>
            <span>涨${formatNumber(item.advancers, 0)}支、跌${formatNumber(item.decliners, 0)}支、平${formatNumber(item.unchanged, 0)}支（${formatNumber(item.advancePercent, 1)}%上涨）</span>
          </div>`
      )
      .join("");
    const latest = Math.max(
      0,
      ...breadthData.map((item) => Number(item?.updatedAt) || 0)
    );
    root.querySelector("[data-breadth-time]").textContent =
      latest > 0 ? `对应最新完成交易日｜更新 ${formatClock(latest)}` : "快照时间待核验";
  }

  function renderSectors() {
    root.querySelector("[data-sectors]").innerHTML = sectorConfig
      .map(
        ([group, items]) => `
          <div class="sector-group">
            <h4>${escapeHtml(group)}</h4>
            <div class="sector-line">
              ${items
                .map(([id, label]) => {
                  const item = marketMap.get(id);
                  return `<span class="pipe-item ${directionClass(item?.changePercent)}">${label} ${formatPercent(item?.changePercent)}</span>`;
                })
                .join("")}
            </div>
          </div>`
      )
      .join("");
  }

  function renderDrivers() {
    const target = root.querySelector("[data-drivers]");
    const groups = new Map();
    (snapshot.drivers || []).forEach((item) => {
      if (!item || !item.ticker || !item.reason) return;
      if (!groups.has(item.group)) groups.set(item.group, []);
      groups.get(item.group).push(item);
    });
    target.innerHTML = [...groups.entries()]
      .filter(([, items]) => items.length)
      .map(
        ([group, items]) => `
          <div class="driver-group">
            <h4>${escapeHtml(group)}</h4>
            ${items
              .map(
                (item) => `
                  <div class="driver-row">
                    <div class="driver-name">
                      ${escapeHtml(item.name)} · ${escapeHtml(item.ticker)}
                      <small class="${directionClass(item.changePercent)}">${formatPercent(item.changePercent)}</small>
                    </div>
                    <p>${escapeHtml(item.reason)}
                      <a href="${escapeHtml(item.sourceUrl)}" target="_blank" rel="noreferrer">${escapeHtml(item.sourceLabel)} ↗</a>
                    </p>
                  </div>`
              )
              .join("")}
          </div>`
      )
      .join("");
    root.querySelector("[data-driver-date]").textContent =
      `${formatDate(snapshot.asOf)} 收盘筛选`;
  }

  function finiteNumber(value) {
    const number = Number(value);
    return value !== null && value !== "" && Number.isFinite(number)
      ? number
      : null;
  }

  function snapshotComparison(id) {
    return (snapshot?.macro24h || []).find((item) => item.id === id) || null;
  }

  function rollingComparison(id, item) {
    const stored = snapshotComparison(id);
    const current = finiteNumber(item?.price) ?? finiteNumber(stored?.current);
    const currentTime =
      finiteNumber(item?.updatedAt) ?? finiteNumber(stored?.currentTime);
    if (current === null || currentTime === null) {
      return {
        current,
        currentTime,
        reference: null,
        referenceTime: null,
        status: "数据不可用",
      };
    }

    const targetTime = currentTime - 24 * 60 * 60 * 1000;
    const referencePoint = (Array.isArray(item?.points) ? item.points : [])
      .filter(
        (point) =>
          finiteNumber(point?.time) !== null &&
          finiteNumber(point?.value) !== null &&
          Number(point.time) <= targetTime
      )
      .sort((a, b) => Number(a.time) - Number(b.time))
      .at(-1);
    const storedReference =
      stored &&
      finiteNumber(stored.reference) !== null &&
      finiteNumber(stored.referenceTime) !== null &&
      Number(stored.referenceTime) <= targetTime
        ? stored
        : null;
    const reference =
      finiteNumber(referencePoint?.value) ??
      finiteNumber(storedReference?.reference);
    const referenceTime =
      finiteNumber(referencePoint?.time) ??
      finiteNumber(storedReference?.referenceTime);
    const age = Math.max(0, (marketsFetchedAt || Date.now()) - currentTime);
    const availability =
      age > 45 * 60 * 1000 ? "最近可用" : "当前";

    return {
      current,
      currentTime,
      reference,
      referenceTime,
      targetTime,
      status:
        reference === null
          ? `${availability}｜同源24小时序列不可用`
          : availability,
    };
  }

  function directionIcon(previous, current) {
    const before = finiteNumber(previous);
    const now = finiteNumber(current);
    if (before === null || now === null || before === now) return "—";
    return now > before ? "📈" : "📉";
  }

  function macroRow(label, previous, current, decimals, suffix, source, status, iconOverride) {
    return `
      <div class="macro-row">
        <span>${iconOverride || directionIcon(previous, current)} ${escapeHtml(label)}</span>
        <div class="macro-reading">
          <strong class="macro-value">${formatNumber(previous, decimals)}${previous === null ? "" : suffix} → ${formatNumber(current, decimals)}${current === null ? "" : suffix}</strong>
          <span class="macro-source">${escapeHtml(source)}｜${escapeHtml(status)}</span>
        </div>
      </div>`;
  }

  function renderMacro() {
    const comparisons = macroConfig.map(([id, label, decimals, suffix, source]) => {
      const comparison = rollingComparison(id, marketMap.get(id));
      return { id, label, decimals, suffix, source, ...comparison };
    });
    const rows = comparisons.map((item) =>
      macroRow(
        item.label,
        item.reference,
        item.current,
        item.decimals,
        item.suffix,
        item.source,
        item.status
      )
    );
    const timed = comparisons.filter(
      (item) => item.currentTime && item.referenceTime
    );
    const latestCurrent = Math.max(
      0,
      ...comparisons.map((item) => item.currentTime || 0)
    );
    const commonTarget = latestCurrent
      ? latestCurrent - 24 * 60 * 60 * 1000
      : 0;
    root.querySelector("[data-macro-clock]").textContent = latestCurrent
      ? `当前更新时间 ${formatClock(latestCurrent)}｜24小时前目标 ${formatClock(commonTarget)}｜${timed.length}/${comparisons.length} 项取得同源滚动参照`
      : "当前时间与24小时前参照时间待核验";

    const fed = snapshot.fedProbability;
    rows.splice(
      4,
      0,
      macroRow(
        fed.label,
        fed.previous,
        fed.current,
        1,
        fed.unit,
        fed.source,
        `上次核验 ${fed.previousAsOf}｜当前核验 ${fed.currentAsOf}`,
        "—"
      )
    );
    const etf = etfData?.latest || {
      date: snapshot.etfFlow.date,
      total: snapshot.etfFlow.totalMillions,
    };
    const total = Number(etf.total);
    rows.push(`
      <div class="macro-row">
        <span>— BTC ETF资金流</span>
        <div class="macro-reading">
          <strong class="macro-value">${total >= 0 ? "净流入" : "净流出"} $${formatNumber(Math.abs(total), 1)}m</strong>
          <span class="macro-source">${escapeHtml(etf.date)}｜Farside Investors｜最新已完成统计日</span>
        </div>
      </div>`);
    root.querySelector("[data-macro]").innerHTML = rows.join("");
  }

  function renderEvents() {
    const now = Date.now();
    const events = (snapshot.events || [])
      .filter((item) => new Date(item.startAt).getTime() > now)
      .sort((a, b) => new Date(a.startAt) - new Date(b.startAt));
    const groups = new Map();
    events.forEach((item) => {
      const day = formatEventDay(item.startAt);
      if (!groups.has(day)) groups.set(day, []);
      groups.get(day).push(item);
    });
    root.querySelector("[data-events]").innerHTML = events.length
      ? [...groups.entries()]
          .map(
            ([day, items]) => `
              <section class="event-group">
                <h3 class="event-day">${escapeHtml(day)}</h3>
                ${items
                  .map(
                    (item) => `
                      <div class="event-row">
                        <time class="event-time" datetime="${escapeHtml(item.startAt)}">${formatEventTime(item.startAt)}</time>
                        <strong class="event-name"><a href="${escapeHtml(item.sourceUrl)}" target="_blank" rel="noreferrer">${escapeHtml(item.name)} ↗</a></strong>
                        <span class="event-impact">${escapeHtml(item.impact)}</span>
                      </div>`
                  )
                  .join("")}
              </section>`
          )
          .join("")
      : '<p class="module-state">当前快照内没有尚未发生的重点事件。</p>';
    setState(
      "events",
      events.length ? `已隐藏过期事件｜未来 ${events.length} 项` : "当前无待发生重点事件",
      "fresh"
    );
  }

  function renderView() {
    root.querySelector("[data-view]").innerHTML = (snapshot.view || [])
      .slice(0, 10)
      .map((paragraph) => `<p>${escapeHtml(paragraph)}</p>`)
      .join("");
    root.querySelector("[data-verdict]").textContent = snapshot.verdict || "";
  }

  function renderAll() {
    renderIndices();
    renderBreadth();
    renderSectors();
    renderDrivers();
    renderMacro();
    renderEvents();
    renderView();
    root.querySelector("[data-page-date]").textContent =
      `${formatDate(snapshot.asOf)}｜最新完成交易日`;
  }

  async function loadStatic() {
    [snapshot, etfData] = await Promise.all([
      fetchJson(SNAPSHOT_URL),
      fetchJson(ETF_URL).catch(() => null),
    ]);
    marketMap = fallbackMap();
    breadthData = snapshot.fallback.breadth || [];
    renderAll();
  }

  async function refreshLive() {
    if (document.hidden) {
      scheduleRefresh(RETRY_DELAYS[0]);
      return;
    }
    try {
      const [marketsResponse, breadthResponse] = await Promise.all([
        fetchJson(`${MARKETS_API}?range=5d`),
        fetchJson(BREADTH_API),
      ]);
      const liveMarkets = Array.isArray(marketsResponse.data)
        ? marketsResponse.data
        : [];
      marketsFetchedAt = Number(marketsResponse.fetchedAt) || Date.now();
      const merged = fallbackMap();
      liveMarkets
        .filter((item) => item?.status === "ok" && Number.isFinite(Number(item.price)))
        .forEach((item) => merged.set(item.id, { ...merged.get(item.id), ...item }));
      marketMap = merged;
      if (Array.isArray(breadthResponse.data) && breadthResponse.data.length) {
        breadthData = breadthResponse.data;
      }
      renderIndices();
      renderBreadth();
      renderSectors();
      renderMacro();
      const liveCount = liveMarkets.filter((item) => item?.status === "ok").length;
      setState("equities", `实时接口正常｜${liveCount} 项行情｜每 60 秒刷新`, "fresh");
      const comparableCount = macroConfig.filter(([id]) => {
        const comparison = rollingComparison(id, marketMap.get(id));
        return comparison.reference !== null;
      }).length;
      setState(
        "macro",
        `统一接口正常｜${comparableCount}/${macroConfig.length} 项取得同源滚动24小时参照`,
        comparableCount === macroConfig.length ? "fresh" : "stale"
      );
      root.querySelector("[data-page-state]").textContent = "实时数据已连接";
      retryIndex = 0;
      scheduleRefresh(RETRY_DELAYS[0]);
    } catch (error) {
      const delay = RETRY_DELAYS[Math.min(retryIndex, RETRY_DELAYS.length - 1)];
      retryIndex += 1;
      setState("equities", "实时接口暂不可用｜显示已核验快照", "stale");
      setState("macro", "部分数据为已核验快照｜自动退避重试", "stale");
      root.querySelector("[data-page-state]").textContent = "快照模式";
      scheduleRefresh(delay);
    }
  }

  function scheduleRefresh(delay) {
    window.clearTimeout(timer);
    timer = window.setTimeout(refreshLive, delay);
  }

  document.addEventListener("visibilitychange", () => {
    if (!document.hidden) {
      window.clearTimeout(timer);
      refreshLive();
    }
  });

  loadStatic()
    .then(() => refreshLive())
    .catch(() => {
      setState("equities", "页面数据载入失败，请稍后刷新", "error");
      setState("macro", "页面数据载入失败，请稍后刷新", "error");
      setState("events", "页面数据载入失败，请稍后刷新", "error");
      root.querySelector("[data-page-state]").textContent = "载入失败";
    });
})();
