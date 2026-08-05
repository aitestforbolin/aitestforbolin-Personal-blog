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
  const BRIEFING_ARCHIVE_URL = "../briefings/global.html";
  const COPY_NEWS_LIMIT = 5;
  const DISPLAY_TIMEZONE = "Asia/Shanghai";
  const MARKET_TIMEZONE = "America/New_York";
  const CLOSE_ANCHOR_MINUTES = 16 * 60;
  const CLOSE_ANCHOR_LOOKBACK_MINUTES = 60;
  const FETCH_TIMEOUT = 10000;
  const RETRY_DELAYS = [60000, 120000, 300000, 900000];
  const treasuryIds = new Set(["US02Y", "US10Y", "US30Y"]);
  const closeAnchorIds = new Set(["DXY", "BRN1!", "GOLD", "BTCUSDT"]);

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
    ["BRN1!", "Brent期货", 2, "", "Yahoo Finance · BZ=F"],
    ["GOLD", "COMEX黄金期货", 2, "", "Yahoo Finance · GC=F"],
    ["BTCUSDT", "BTC", 0, "", "Yahoo Finance · BTC-USD"],
    ["DXY", "美元指数", 3, "", "Yahoo Finance · DX-Y.NYB"],
    ["US02Y", "2年期美债收益率", 3, "%", "美国财政部 · 2-Year Par Yield"],
    ["US10Y", "10年期美债收益率", 3, "%", "美国财政部 · 10-Year Par Yield"],
    ["US30Y", "30年期美债收益率", 3, "%", "美国财政部 · 30-Year Par Yield"],
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
  let latestBriefingCopyPromise = null;

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

  async function fetchText(url) {
    const controller = new AbortController();
    const timeout = window.setTimeout(() => controller.abort(), FETCH_TIMEOUT);
    try {
      const response = await fetch(url, {
        cache: "no-store",
        signal: controller.signal,
      });
      if (!response.ok) throw new Error(`HTTP ${response.status}`);
      return await response.text();
    } finally {
      window.clearTimeout(timeout);
    }
  }

  function compactCopyText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function extractBriefingItem(article) {
    const title = compactCopyText(article.querySelector("h2, h3")?.textContent);
    return title ? { title } : null;
  }

  async function loadLatestBriefingCopyData() {
    if (latestBriefingCopyPromise) return latestBriefingCopyPromise;

    latestBriefingCopyPromise = (async () => {
      const archiveHtml = await fetchText(BRIEFING_ARCHIVE_URL);
      const parser = new DOMParser();
      const archiveDocument = parser.parseFromString(archiveHtml, "text/html");
      const latestLink = archiveDocument.querySelector(
        '.archive-card a[href*="global-daily-brief-"]'
      );
      if (!latestLink) throw new Error("Latest briefing link is unavailable");

      const archiveUrl = new URL(BRIEFING_ARCHIVE_URL, window.location.href);
      const briefingUrl = new URL(latestLink.getAttribute("href"), archiveUrl);
      const briefingHtml = await fetchText(briefingUrl.href);
      const briefingDocument = parser.parseFromString(briefingHtml, "text/html");
      const date = briefingDocument.querySelector("main time[datetime]")?.getAttribute(
        "datetime"
      );
      const featureItems = Array.from(
        briefingDocument.querySelectorAll(".briefing-item-feature")
      )
        .map((article) => extractBriefingItem(article))
        .filter(Boolean);
      const compactItems = Array.from(
        briefingDocument.querySelectorAll(".briefing-item-compact")
      )
        .map((article) => extractBriefingItem(article))
        .filter(Boolean);
      const items = [...featureItems, ...compactItems].slice(0, COPY_NEWS_LIMIT);

      if (!date || !items.length) {
        throw new Error("Latest briefing content is incomplete");
      }
      return { date, items };
    })().catch((error) => {
      latestBriefingCopyPromise = null;
      throw error;
    });

    return latestBriefingCopyPromise;
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

  function snapshotAnchor(id) {
    return (snapshot?.macroAnchors || []).find((item) => item.id === id) || null;
  }

  function trustedMacroSource(id, item) {
    if (!item) return false;
    if (treasuryIds.has(id)) return item.source === "U.S. Treasury";
    if (closeAnchorIds.has(id)) return item.source === "Yahoo Finance";
    return true;
  }

  function marketClockParts(timestamp) {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: MARKET_TIMEZONE,
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).formatToParts(timestamp);
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return {
      date: `${values.year}-${values.month}-${values.day}`,
      minutes: Number(values.hour) * 60 + Number(values.minute),
    };
  }

  function historyCloseAnchors(id) {
    const historyItem = macroHistoryMap.get(id);
    if (!trustedMacroSource(id, historyItem)) return null;
    const points = Array.isArray(historyItem?.points) ? historyItem.points : [];
    const byDate = new Map();
    points.forEach((point) => {
      const time = finiteNumber(point?.time);
      const value = finiteNumber(point?.value);
      if (time === null || value === null) return;
      const clock = marketClockParts(time);
      const ageMinutes = CLOSE_ANCHOR_MINUTES - clock.minutes;
      if (
        ageMinutes < 0 ||
        ageMinutes > CLOSE_ANCHOR_LOOKBACK_MINUTES
      ) {
        return;
      }
      const existing = byDate.get(clock.date);
      if (!existing || time > existing.observedAt) {
        byDate.set(clock.date, {
          value,
          observedAt: time,
          anchorTime: time + ageMinutes * 60 * 1000,
          ageMinutes,
        });
      }
    });
    const anchors = [...byDate.entries()]
      .sort(([dateA], [dateB]) => dateA.localeCompare(dateB))
      .map(([date, value]) => ({ ...value, date }));
    if (anchors.length < 2) return null;
    const previous = anchors.at(-2);
    const current = anchors.at(-1);
    if (snapshot?.asOf && current.date !== snapshot.asOf) return null;
    return {
      previous: previous.value,
      previousAnchorTime: previous.anchorTime,
      previousObservedAt: previous.observedAt,
      anchor: current.value,
      anchorTime: current.anchorTime,
      anchorObservedAt: current.observedAt,
      status:
        current.ageMinutes > 30
          ? `16:00 ET前最后报价；距锚点${current.ageMinutes}分钟`
          : current.ageMinutes > 0
            ? `16:00 ET前${current.ageMinutes}分钟最后报价`
            : "16:00 ET完整锚点",
    };
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

    if (item?.source === "U.S. Treasury") {
      const historyItem = macroHistoryMap.get(id);
      const referencePoint = (
        historyItem?.source === "U.S. Treasury" && Array.isArray(historyItem?.points)
          ? historyItem.points
          : Array.isArray(item?.points)
            ? item.points
            : []
      )
        .filter(
          (point) =>
            finiteNumber(point?.time) !== null &&
            finiteNumber(point?.value) !== null &&
            Number(point.time) < currentTime
        )
        .sort((a, b) => Number(a.time) - Number(b.time))
        .at(-1);
      const reference =
        finiteNumber(referencePoint?.value) ?? finiteNumber(stored?.reference);
      const referenceTime =
        finiteNumber(referencePoint?.time) ?? finiteNumber(stored?.referenceTime);
      return {
        current,
        currentTime,
        reference,
        referenceTime,
        targetTime: null,
        status:
          reference === null
            ? "美国财政部官方前一交易日数据不可用"
            : "美国财政部官方前一交易日",
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

  function percentageChange(previous, current) {
    const before = finiteNumber(previous);
    const now = finiteNumber(current);
    if (before === null || now === null || before === 0) return null;
    return ((now - before) / before) * 100;
  }

  function anchorComparison(id, item) {
    if (treasuryIds.has(id)) {
      const officialItem = trustedMacroSource(id, item)
        ? item
        : (snapshot?.fallback?.markets || []).find(
            (candidate) => candidate.id === id && candidate.source === "U.S. Treasury"
          );
      const official = rollingComparison(id, officialItem);
      const change =
        finiteNumber(official.current) !== null &&
        finiteNumber(official.reference) !== null
          ? Number(official.current) - Number(official.reference)
          : null;
      return {
        id,
        previous: official.reference,
        previousTime: official.referenceTime,
        anchor: official.current,
        anchorTime: official.currentTime,
        latest: official.current,
        latestTime: official.currentTime,
        dailyChange: change,
        liveChange: null,
        kind: "official",
        status: official.status,
      };
    }

    const stored = snapshotAnchor(id);
    const history = historyCloseAnchors(id);
    const anchors = history || stored || {};
    const storedLatestTime = finiteNumber(stored?.latestTime);
    const itemLatestTime = trustedMacroSource(id, item)
      ? finiteNumber(item?.updatedAt)
      : null;
    const useLiveItem =
      itemLatestTime !== null &&
      (storedLatestTime === null || itemLatestTime >= storedLatestTime);
    const latest = useLiveItem
      ? finiteNumber(item?.price)
      : finiteNumber(stored?.latest);
    const latestTime = useLiveItem ? itemLatestTime : storedLatestTime;
    const previous = finiteNumber(anchors.previous);
    const anchor = finiteNumber(anchors.anchor);
    return {
      id,
      previous,
      previousTime: finiteNumber(anchors.previousAnchorTime),
      anchor,
      anchorTime: finiteNumber(anchors.anchorTime),
      latest,
      latestTime,
      dailyChange: percentageChange(previous, anchor),
      liveChange: percentageChange(anchor, latest),
      kind: "price",
      status: anchors.status || "16:00 ET锚点待核验",
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
    const day = new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      month: "long",
      day: "numeric",
    }).format(date);
    const weekday = new Intl.DateTimeFormat("zh-CN", {
      timeZone: DISPLAY_TIMEZONE,
      weekday: "short",
    }).format(date);
    return day + "｜" + weekday;
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

  function buildDocumentCopyText(briefing) {
    if (!snapshot) throw new Error("Snapshot is not ready");
    if (!briefing?.items?.length) throw new Error("Briefing is not ready");

    const lines = ["今日关键新闻｜" + formatDate(briefing.date), ""];
    briefing.items.forEach((item, index) => {
      const sentence = /[。！？!?]$/.test(item.title)
        ? item.title
        : item.title + "。";
      lines.push(index + 1 + "/" + briefing.items.length + "｜" + sentence);
    });

    lines.push(
      "",
      "每日市场状态｜" + formatDate(snapshot.asOf),
      "",
      "01｜美股",
      "",
      "▍三大核心指数"
    );
    indexConfig.forEach(([id, label]) => {
      lines.push(
        "• " +
          label +
          "：" +
          formatDocumentPercent(marketMap.get(id)?.changePercent)
      );
    });

    lines.push("", "▍市场宽度");
    [
      ["SP500", "标普500"],
      ["NASDAQ", "Nasdaq交易所"],
    ].forEach(([id, label]) => {
      const item = breadthData.find((entry) => entry?.id === id);
      if (!item) return;
      const advancingPercent = finiteNumber(
        item.advancePercent ?? item.advancingPercent
      );
      lines.push(
        "• " +
          label +
          "：涨" +
          formatNumber(item.advancers, 0) +
          "｜跌" +
          formatNumber(item.decliners, 0) +
          "｜平" +
          formatNumber(item.unchanged, 0) +
          "｜" +
          (advancingPercent === null
            ? "上涨比例待核验"
            : formatNumber(advancingPercent, 1) + "%上涨")
      );
    });

    documentSectorConfig.forEach(([group, items]) => {
      lines.push("", "▍" + group);
      items.forEach(([id, label]) => {
        lines.push(
          "• " +
            label +
            "：" +
            formatDocumentPercent(marketMap.get(id)?.changePercent)
        );
      });
    });

    lines.push("", "▍核心个股驱动");
    const driverGroups = new Map();
    (snapshot.drivers || []).forEach((item) => {
      if (!item?.group || !item?.ticker || !item?.reason) return;
      const normalizedGroup =
        {
          semiconductor: "半导体",
          semiconductors: "半导体",
          megacap: "大型科技",
          mega_cap: "大型科技",
          large_tech: "大型科技",
          other: "其他显著个股",
        }[item.group] || item.group;
      if (!driverGroups.has(normalizedGroup)) driverGroups.set(normalizedGroup, []);
      driverGroups.get(normalizedGroup).push(item);
    });
    ["半导体", "大型科技", "其他显著个股"].forEach((group) => {
      const items = driverGroups.get(group) || [];
      if (!items.length) return;
      lines.push("", "【" + group + "】");
      items.forEach((item) => {
        lines.push(
          "• " +
            item.name +
            "（" +
            item.ticker +
            "）：" +
            formatDocumentPercent(item.changePercent)
        );
        lines.push("  驱动：" + item.reason);
      });
    });

    const comparisons = new Map(
      macroConfig.map(([id]) => {
        const comparison = anchorComparison(id, marketMap.get(id));
        return [
          id,
          {
            reference: comparison.previous,
            referenceTime: comparison.previousTime,
            current: comparison.anchor,
            currentTime: comparison.anchorTime,
            status: comparison.status,
          },
        ];
      })
    );
    lines.push(
      "",
      "02｜宏观资产数据",
      "",
      "• " + documentAssetLine("美元指数", comparisons.get("DXY"), 3, ""),
      "• " + documentAssetLine("2年期美债收益率", comparisons.get("US02Y"), 3, "%"),
      "• " + documentAssetLine("10年期美债收益率", comparisons.get("US10Y"), 3, "%"),
      "• " + documentAssetLine("30年期美债收益率", comparisons.get("US30Y"), 3, "%")
    );

    const fed = snapshot.fedProbability || {};
    lines.push(
      "• " +
        directionIcon(fed.previous, fed.current) +
        " 美联储加息可能性：" +
        formatNumber(fed.previous, 1) +
        (finiteNumber(fed.previous) === null ? "" : fed.unit || "") +
        " → " +
        formatNumber(fed.current, 1) +
        (finiteNumber(fed.current) === null ? "" : fed.unit || ""),
      "• " + documentAssetLine("原油", comparisons.get("BRN1!"), 2, ""),
      "• " + documentAssetLine("COMEX黄金期货", comparisons.get("GOLD"), 2, ""),
      "• " + documentAssetLine("BTC", comparisons.get("BTCUSDT"), 0, "")
    );

    const etf = etfData?.latest || {
      date: snapshot.etfFlow?.date,
      total: snapshot.etfFlow?.totalMillions,
    };
    const etfTotal = finiteNumber(etf.total);
    lines.push(
      "• BTC ETF资金流：" +
        (etf.date || "日期待核验") +
        "，" +
        (etfTotal === null
          ? "数据不可用"
          : (etfTotal >= 0 ? "净流入 " : "净流出 ") +
            "$" +
            formatNumber(Math.abs(etfTotal), 1) +
            "m")
    );

    lines.push("", "03｜日历、事件及其影响");
    const eventGroups = new Map();
    visibleEvents().forEach((item) => {
      const day = formatDocumentEventDay(item.startAt);
      if (!eventGroups.has(day)) eventGroups.set(day, []);
      eventGroups.get(day).push(item);
    });
    eventGroups.forEach((items, day) => {
      lines.push("", "📅 " + day);
      items.forEach((item) => {
        lines.push("• " + formatEventTime(item.startAt) + "｜" + item.name);
        const impact = String(item.impact || "").replace(/^主要影响：?\s*/, "");
        lines.push("  影响：" + impact);
      });
    });

    lines.push("", "04｜看法和观点", "");
    (snapshot.view || []).slice(0, 10).forEach((paragraph, index) => {
      if (index > 0) lines.push("");
      lines.push(
        index +
          1 +
          ". " +
          String(paragraph).replace(/^[—–-]\s*/, "")
      );
    });
    if (snapshot.verdict) {
      if ((snapshot.view || []).length) lines.push("");
      lines.push(
        "结论｜" + String(snapshot.verdict).replace(/^[—–-]\s*/, "")
      );
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
    let nativeWrite = null;
    let fallbackSucceeded = false;
    let fallbackError = null;

    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      try {
        nativeWrite = navigator.clipboard.writeText(text);
      } catch (error) {
        nativeWrite = null;
      }
    }

    try {
      fallbackCopy(text);
      fallbackSucceeded = true;
    } catch (error) {
      fallbackError = error;
    }

    if (nativeWrite) {
      try {
        await nativeWrite;
        return;
      } catch (error) {
        if (fallbackSucceeded) return;
        throw fallbackError || error;
      }
    }

    if (fallbackSucceeded) return;
    throw fallbackError || new Error("Clipboard copy failed");
  }

  async function handleCopyBody() {
    const button = root.querySelector("[data-copy-body]");
    if (!button || button.disabled) return;
    button.disabled = true;
    try {
      const briefing = await loadLatestBriefingCopyData();
      const text = buildDocumentCopyText(briefing);
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

  function signedChange(value, decimals, suffix) {
    const number = finiteNumber(value);
    if (number === null) return "—";
    const sign = number > 0 ? "+" : number < 0 ? "−" : "";
    return `${sign}${Math.abs(number).toFixed(decimals)}${suffix}`;
  }

  function changeTone(value) {
    const number = finiteNumber(value);
    if (number === null || number === 0) return "is-flat";
    return number > 0 ? "is-up" : "is-down";
  }

  function formatMarketAnchor(timestamp) {
    const number = finiteNumber(timestamp);
    if (number === null) return "锚点待核验";
    return `${new Intl.DateTimeFormat("zh-CN", {
      timeZone: MARKET_TIMEZONE,
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(number)} ET`;
  }

  function macroLayer(label, previous, current, decimals, suffix, change, changeLabel, className, valueTone) {
    return `
      <div class="macro-layer ${className || ""}">
        <span class="macro-layer-label">${escapeHtml(label)}</span>
        <strong class="macro-layer-value"><span class="macro-layer-start">${formatNumber(previous, decimals)}${finiteNumber(previous) === null ? "" : suffix}</span><span class="macro-layer-arrow"> → </span><span class="macro-layer-end ${valueTone || ""}">${formatNumber(current, decimals)}${finiteNumber(current) === null ? "" : suffix}</span></strong>
        <span class="macro-change ${changeTone(change)}">${escapeHtml(changeLabel)}</span>
      </div>`;
  }

  function layeredMacroRow(item) {
    const dailyValue =
      item.kind === "official"
        ? finiteNumber(item.dailyChange) === null
          ? null
          : Number(item.dailyChange) * 100
        : item.dailyChange;
    const dailyLabel =
      item.kind === "official"
        ? signedChange(dailyValue, 1, " bp")
        : signedChange(dailyValue, 2, "%");
    const liveLayer =
      item.kind === "official"
        ? `
          <div class="macro-layer macro-layer-live macro-layer-muted">
            <span class="macro-layer-label">实时状态</span>
            <span class="macro-layer-message">官方日频，不提供伪实时</span>
            <span class="macro-change is-flat">—</span>
          </div>`
        : macroLayer(
            "收盘锚点后",
            item.anchor,
            item.latest,
            item.decimals,
            item.suffix,
            item.liveChange,
            signedChange(item.liveChange, 2, "%"),
            "macro-layer-live",
            changeTone(item.liveChange)
          );
    const timing =
      item.kind === "official"
        ? `${item.status}｜官方数据日 ${formatMarketAnchor(item.anchorTime)}`
        : `${item.status}｜实时截至 ${formatClock(item.latestTime)} 北京`;
    return `
      <div class="macro-row macro-row-layered">
        <div class="macro-identity">
          <span class="macro-name">${directionIcon(item.previous, item.anchor)} ${escapeHtml(item.label)}</span>
        </div>
        <div class="macro-reading">
          <div class="macro-layer-grid">
            ${macroLayer(
              item.kind === "official" ? "官方日度" : "完整交易日",
              item.previous,
              item.anchor,
              item.decimals,
              item.suffix,
              dailyValue,
              dailyLabel,
              "macro-layer-primary"
            )}
            ${liveLayer}
          </div>
          <span class="macro-source">${escapeHtml(item.source)}｜${escapeHtml(timing)}</span>
        </div>
      </div>`;
  }

  function fixedSnapshotRow(label, previous, current, unit, source, status) {
    const change =
      finiteNumber(previous) !== null && finiteNumber(current) !== null
        ? Number(current) - Number(previous)
        : null;
    return `
      <div class="macro-row macro-row-layered">
        <div class="macro-identity">
          <span class="macro-name">${directionIcon(previous, current)} ${escapeHtml(label)}</span>
        </div>
        <div class="macro-reading">
          <div class="macro-layer-grid">
            ${macroLayer(
              "固定快照",
              previous,
              current,
              1,
              unit,
              change,
              signedChange(change, 1, " pp"),
              "macro-layer-primary"
            )}
            <div class="macro-layer macro-layer-live macro-layer-muted">
              <span class="macro-layer-label">实时状态</span>
              <span class="macro-layer-message">等待下一次同一时点快照</span>
              <span class="macro-change is-flat">—</span>
            </div>
          </div>
          <span class="macro-source">${escapeHtml(source)}｜${escapeHtml(status)}</span>
        </div>
      </div>`;
  }

  function renderMacro() {
    const comparisons = macroConfig.map(([id, label, decimals, suffix, source]) => {
      const comparison = anchorComparison(id, marketMap.get(id));
      return { id, label, decimals, suffix, source, ...comparison };
    });
    const rows = comparisons.map(layeredMacroRow);
    const fixedCount = comparisons.filter(
      (item) => item.previous !== null && item.anchor !== null
    ).length;
    const latestAnchor = Math.max(
      0,
      ...comparisons
        .filter((item) => item.kind === "price")
        .map((item) => item.anchorTime || 0)
    );
    const latestQuote = Math.max(
      0,
      ...comparisons.map((item) => item.latestTime || 0)
    );
    root.querySelector("[data-macro-clock]").innerHTML = latestAnchor
      ? `<strong>日度锚点 ${escapeHtml(formatMarketAnchor(latestAnchor))}</strong><span>实时截至 ${escapeHtml(formatClock(latestQuote))} 北京</span><span>${fixedCount}/${comparisons.length} 项完成固定比较</span>`
      : "正在建立美股收盘锚点…";

    const fed = snapshot.fedProbability;
    rows.splice(
      7,
      0,
      fixedSnapshotRow(
        fed.label,
        fed.previous,
        fed.current,
        fed.unit,
        fed.source,
        `上次 ${fed.previousAsOf}｜本次 ${fed.currentAsOf}`
      )
    );
    const etf = etfData?.latest || {
      date: snapshot.etfFlow.date,
      total: snapshot.etfFlow.totalMillions,
    };
    const total = Number(etf.total);
    rows.splice(3, 0, `
      <div class="macro-row macro-row-layered macro-row-static">
        <div class="macro-identity">
          <span class="macro-name">${directionIcon(0, total)} BTC ETF资金流</span>
        </div>
        <div class="macro-reading">
          <div class="macro-layer-grid macro-layer-grid-single">
            <div class="macro-layer macro-layer-primary macro-layer-muted">
              <span class="macro-layer-label">最新统计日</span>
              <span class="macro-layer-message">${escapeHtml(etf.date)} · ${total >= 0 ? "净流入" : "净流出"} $${formatNumber(Math.abs(total), 1)}m</span>
              <span class="macro-change ${total >= 0 ? "is-up" : "is-down"}">${total >= 0 ? "流入" : "流出"}</span>
            </div>
          </div>
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
        .filter(
          (item) =>
            item?.status === "ok" &&
            Number.isFinite(Number(item.price)) &&
            (!treasuryIds.has(item.id) && !closeAnchorIds.has(item.id)
              ? true
              : trustedMacroSource(item.id, item))
        )
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
        const comparison = anchorComparison(id, marketMap.get(id));
        return comparison.previous !== null && comparison.anchor !== null;
      }).length;
      setState(
        "macro",
        `双层口径正常｜${comparableCount}/${macroConfig.length} 项完成固定比较`,
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
