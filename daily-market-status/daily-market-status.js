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
  const documentSectorConfig = [
    ["进攻和成长板块", [["SOX", "SOX（半导体）"], ["XLK", "XLK（信息技术）"], ["XLY", "XLY（可选消费）"], ["XLC", "XLC（通讯服务）"]]],
    ["防御板块", [["XLV", "XLV（健康医疗）"], ["XLU", "XLU（公共事业）"], ["XLP", "XLP（必需消费）"]]],
    ["宏观敏感板块", [["XLE", "XLE（能源）"], ["XLI", "XLI（工业）"], ["XLF", "XLF（金融）"]]],
  ];

  let snapshot = null;
  let etfData = null;
  let marketMap = new Map();
  let macroHistoryMap = new Map();
  let breadthData = [];
  let marketsFetchedAt = 0;
  let macroHistoryFetchedAt = 0;
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
    if (value === null || value === "" || typeof value === "undefined") return "—";
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
    const historyItem = macroHistoryMap.get(id);
    const referencePoint = (
      Array.isArray(historyItem?.points)
        ? historyItem.points
        : Array.isArray(item?.points)
          ? item.points
          : []
    )
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

  function formatDocumentPercent(value) {
    const number = finiteNumber(value);
    if (number === null) return "—";
    const sign = number > 0 ? "+" : number < 0 ? "−" : "";
    return sign + Math.abs(number).toFixed(2) + "%";
  }

  function visibleEvents() {
    const now = Date.now();
    return (snapshot?.events || [])
      .filter((item) => new Date(item.startAt).getTime() > now)
      .sort((a, b) => new Date(a.startAt) - new Date(b.startAt));
  }

  function formatDocumentEventDay(iso) {
    const date = new Date(iso);
    const weekday = new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      weekday: "short",
    }).format(date);
    return formatEventDay(iso) + " " + weekday;
  }

  function documentAssetLine(label, comparison, decimals, suffix) {
    const previous = comparison.reference;
    const current = comparison.current;
    return (
      directionIcon(previous, current) +
      " " +
      label +
      "：" +
      formatNumber(previous, decimals) +
      (previous === null ? "" : suffix) +
      " → " +
      formatNumber(current, decimals) +
      (current === null ? "" : suffix)
    );
  }

  function buildDocumentCopyText() {
    if (!snapshot) throw new Error("Snapshot is not ready");

    const lines = ["｜美股", "", "三大指数"];
    indexConfig.forEach(([id, label]) => {
      lines.push(label + "：" + formatDocumentPercent(marketMap.get(id)?.changePercent));
    });

    lines.push("", "市场宽度");
    [
      ["SP500", "标普500上涨股票比例"],
      ["NASDAQ", "Nasdaq交易所上涨股票比例"],
    ].forEach(([id, label]) => {
      const item = breadthData.find((entry) => entry?.id === id);
      if (!item) return;
      lines.push(
        label +
          "：" +
          formatNumber(item.advancePercent, 1) +
          "%（涨" +
          formatNumber(item.advancers, 0) +
          "支、跌" +
          formatNumber(item.decliners, 0) +
          "支、平" +
          formatNumber(item.unchanged, 0) +
          "支）"
      );
    });

    documentSectorConfig.forEach(([group, items]) => {
      lines.push("", group);
      items.forEach(([id, label]) => {
        lines.push(label + "：" + formatDocumentPercent(marketMap.get(id)?.changePercent));
      });
    });

    lines.push("", "核心个股驱动");
    const driverGroups = new Map();
    (snapshot.drivers || []).forEach((item) => {
      if (!item?.group || !item?.ticker || !item?.reason) return;
      if (!driverGroups.has(item.group)) driverGroups.set(item.group, []);
      driverGroups.get(item.group).push(item);
    });
    ["半导体", "大型科技", "其他显著个股"].forEach((group) => {
      const items = driverGroups.get(group) || [];
      if (!items.length) return;
      lines.push("", group);
      items.forEach((item) => {
        lines.push(
          item.name +
            "（" +
            item.ticker +
            "）：" +
            formatDocumentPercent(item.changePercent) +
            "，" +
            item.reason
        );
      });
    });

    const comparisons = new Map(
      macroConfig.map(([id]) => [id, rollingComparison(id, marketMap.get(id))])
    );
    lines.push(
      "",
      "｜宏观资产数据",
      "",
      documentAssetLine("美元指数", comparisons.get("DXY"), 3, ""),
      documentAssetLine("2年期美债收益率", comparisons.get("US02Y"), 3, "%"),
      documentAssetLine("10年期美债收益率", comparisons.get("US10Y"), 3, "%"),
      documentAssetLine("30年期美债收益率", comparisons.get("US30Y"), 3, "%")
    );

    const fed = snapshot.fedProbability || {};
    lines.push(
      directionIcon(fed.previous, fed.current) +
        " 美联储加息可能性：" +
        formatNumber(fed.previous, 1) +
        (finiteNumber(fed.previous) === null ? "" : fed.unit || "") +
        " → " +
        formatNumber(fed.current, 1) +
        (finiteNumber(fed.current) === null ? "" : fed.unit || ""),
      documentAssetLine("原油", comparisons.get("BRN1!"), 2, ""),
      documentAssetLine("黄金", comparisons.get("GOLD"), 2, ""),
      documentAssetLine("BTC", comparisons.get("BTCUSDT"), 0, "")
    );

    const etf = etfData?.latest || {
      date: snapshot.etfFlow?.date,
      total: snapshot.etfFlow?.totalMillions,
    };
    const etfTotal = finiteNumber(etf.total);
    lines.push(
      "BTC ETF资金流：" +
        (etf.date || "日期待核验") +
        "，" +
        (etfTotal === null
          ? "数据不可用"
          : (etfTotal >= 0 ? "净流入 " : "净流出 ") +
            "$" +
            formatNumber(Math.abs(etfTotal), 1) +
            "m")
    );

    lines.push("", "｜日历、事件及其影响");
    const eventGroups = new Map();
    visibleEvents().forEach((item) => {
      const day = formatDocumentEventDay(item.startAt);
      if (!eventGroups.has(day)) eventGroups.set(day, []);
      eventGroups.get(day).push(item);
    });
    eventGroups.forEach((items, day) => {
      lines.push("", day);
      items.forEach((item) => {
        lines.push(formatEventTime(item.startAt) + " " + item.name);
        const impact = String(item.impact || "").replace(/^主要影响：?\s*/, "");
        lines.push("主要影响：" + impact);
      });
    });

    lines.push("", "｜看法和观点", "");
    (snapshot.view || []).slice(0, 10).forEach((paragraph, index) => {
      if (index > 0) lines.push("");
      lines.push(String(paragraph).replace(/^[—–-]\s*/, ""));
    });
    if (snapshot.verdict) {
      if ((snapshot.view || []).length) lines.push("");
      lines.push(String(snapshot.verdict).replace(/^[—–-]\s*/, ""));
    }

    return lines.join("\n");
  }

  function setCopyStatus(message, level) {
    const status = root.querySelector("[data-copy-status]");
    if (!status) return;
    status.textContent = message;
    status.dataset.level = level || "";
    window.clearTimeout(setCopyStatus.timer);
    setCopyStatus.timer = window.setTimeout(() => {
      status.textContent = "";
      status.dataset.level = "";
    }, level === "error" ? 5000 : 2400);
  }

  function fallbackCopy(text) {
    const textarea = document.createElement("textarea");
    const activeElement = document.activeElement;
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.setAttribute("aria-hidden", "true");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.top = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    let copied = false;
    try {
      copied = document.execCommand("copy");
    } finally {
      textarea.remove();
      if (activeElement && typeof activeElement.focus === "function") {
        activeElement.focus();
      }
    }
    if (!copied) throw new Error("Fallback copy failed");
  }

  async function copyDocumentBody(text) {
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        await navigator.clipboard.writeText(text);
        return;
      } catch (error) {
        fallbackCopy(text);
        return;
      }
    }
    fallbackCopy(text);
  }

  async function handleCopyBody() {
    const button = root.querySelector("[data-copy-body]");
    if (!button || button.disabled) return;
    button.disabled = true;
    try {
      const text = buildDocumentCopyText();
      button.copyPayload = text;
      await copyDocumentBody(text);
      setCopyStatus("已复制", "success");
    } catch (error) {
      setCopyStatus("复制失败，请手动选择", "error");
    } finally {
      button.disabled = false;
      button.focus();
    }
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
    const events = visibleEvents();
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
    const copyButton = root.querySelector("[data-copy-body]");
    if (copyButton) copyButton.disabled = false;
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
      const refreshHistory =
        !macroHistoryFetchedAt ||
        Date.now() - macroHistoryFetchedAt >= 5 * 60 * 1000;
      const [marketsResponse, breadthResponse, historyResponse] = await Promise.all([
        fetchJson(`${MARKETS_API}?range=1d`),
        fetchJson(BREADTH_API),
        refreshHistory
          ? fetchJson(`${MARKETS_API}?range=5d`)
          : Promise.resolve(null),
      ]);
      const liveMarkets = Array.isArray(marketsResponse.data)
        ? marketsResponse.data
        : [];
      marketsFetchedAt = Number(marketsResponse.fetchedAt) || Date.now();
      if (Array.isArray(historyResponse?.data)) {
        macroHistoryMap = new Map(
          historyResponse.data.map((item) => [item.id, item])
        );
        macroHistoryFetchedAt =
          Number(historyResponse.fetchedAt) || Date.now();
      }
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

  root.querySelector("[data-copy-body]")?.addEventListener("click", handleCopyBody);

  loadStatic()
    .then(() => refreshLive())
    .catch(() => {
      setState("equities", "页面数据载入失败，请稍后刷新", "error");
      setState("macro", "页面数据载入失败，请稍后刷新", "error");
      setState("events", "页面数据载入失败，请稍后刷新", "error");
      root.querySelector("[data-page-state]").textContent = "载入失败";
    });
})();
