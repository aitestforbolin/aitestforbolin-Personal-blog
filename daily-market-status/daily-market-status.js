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
    ["IXIC", "Nasdaq"],
    ["DJI", "道琼斯"],
  ];
  const sectorConfig = [
    ["进攻和成长", [["SOX", "SOX"], ["XLK", "XLK"], ["XLY", "XLY"], ["XLC", "XLC"]]],
    ["防御", [["XLV", "XLV"], ["XLU", "XLU"], ["XLP", "XLP"]]],
    ["宏观敏感", [["XLE", "XLE"], ["XLI", "XLI"], ["XLF", "XLF"]]],
  ];
  const macroConfig = [
    ["DXY", "美元指数", 3, ""],
    ["US02Y", "2Y 美债收益率", 3, "%"],
    ["US10Y", "10Y 美债收益率", 3, "%"],
    ["US30Y", "30Y 美债收益率", 3, "%"],
    ["BRN1!", "Brent", 2, ""],
    ["GOLD", "黄金", 2, ""],
    ["BTCUSDT", "BTC", 0, ""],
  ];

  let snapshot = null;
  let etfData = null;
  let marketMap = new Map();
  let breadthData = [];
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

  function formatEventTime(iso) {
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      month: "2-digit",
      day: "2-digit",
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
            <strong>${escapeHtml(item.label)}</strong>
            <span>
              <span class="is-up">涨 ${formatNumber(item.advancers, 0)} 支</span>｜
              <span class="is-down">跌 ${formatNumber(item.decliners, 0)} 支</span>｜
              <span class="is-up">${formatNumber(item.advancePercent, 1)}% 上涨</span>
              ${Number(item.unchanged) ? `｜平 ${formatNumber(item.unchanged, 0)} 支` : ""}
            </span>
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

  function macroRow(label, previous, current, decimals, suffix, time, extra) {
    const change = Number(current) - Number(previous);
    return `
      <div class="macro-row">
        <span>${escapeHtml(label)}</span>
        <strong class="macro-value ${directionClass(change)}">
          ${formatNumber(previous, decimals)}${suffix} → ${formatNumber(current, decimals)}${suffix}
          ${extra ? `<small>｜${escapeHtml(extra)}</small>` : ""}
        </strong>
        <span class="macro-time">${escapeHtml(time)}</span>
      </div>`;
  }

  function renderMacro() {
    const rows = macroConfig.map(([id, label, decimals, suffix]) => {
      const item = marketMap.get(id);
      return macroRow(
        label,
        item?.previousClose,
        item?.price,
        decimals,
        suffix,
        item?.updatedAt ? `口径 ${formatClock(item.updatedAt)}` : "快照时间待核验",
        id === "BRN1!" ? item?.contractLabel : ""
      );
    });
    const fed = snapshot.fedProbability;
    rows.splice(
      4,
      0,
      macroRow(
        fed.label,
        fed.previous,
        fed.current,
        0,
        fed.unit,
        `快照 ${fed.asOf}｜${fed.source}`,
        ""
      )
    );
    const etf = etfData?.latest || {
      date: snapshot.etfFlow.date,
      total: snapshot.etfFlow.totalMillions,
    };
    const total = Number(etf.total);
    rows.push(`
      <div class="macro-row">
        <span>BTC ETF 资金流</span>
        <strong class="macro-value ${directionClass(total)}">
          ${total >= 0 ? "净流入" : "净流出"} $${formatNumber(Math.abs(total), 1)}m
        </strong>
        <span class="macro-time">${escapeHtml(etf.date)}｜Farside Investors</span>
      </div>`);
    root.querySelector("[data-macro]").innerHTML = rows.join("");
  }

  function renderEvents() {
    const now = Date.now();
    const events = (snapshot.events || [])
      .filter((item) => new Date(item.startAt).getTime() > now)
      .sort((a, b) => new Date(a.startAt) - new Date(b.startAt));
    root.querySelector("[data-events]").innerHTML = events.length
      ? events
          .map(
            (item) => `
              <div class="event-row">
                <time class="event-time" datetime="${escapeHtml(item.startAt)}">${formatEventTime(item.startAt)} 北京</time>
                <strong class="event-name"><a href="${escapeHtml(item.sourceUrl)}" target="_blank" rel="noreferrer">${escapeHtml(item.name)} ↗</a></strong>
                <span class="event-impact">${escapeHtml(item.impact)}</span>
              </div>`
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
        fetchJson(MARKETS_API),
        fetchJson(BREADTH_API),
      ]);
      const liveMarkets = Array.isArray(marketsResponse.data)
        ? marketsResponse.data
        : [];
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
      setState("macro", "实时接口正常｜盘中资产按各自口径更新", "fresh");
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
