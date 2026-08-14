(function () {
  const DATA_URL = "data/macro-calendar.json?v=20260814-cpi-ppi-1";
  const MODEL = window.MacroCalendarModel;
  const HORIZON_DAYS = 7;
  const RELEASE_LOOKBACK_HOURS = 48;
  const RELEASE_LOOKBACK_DAYS = 2;
  const POLICY_LOOKBACK_DAYS = RELEASE_LOOKBACK_DAYS;
  const UPCOMING_DAYS = 3;
  const CATEGORY_LABELS = {
    inflation: "通胀",
    prices: "价格",
    jobs: "就业",
    growth: "增长/消费",
    consumption: "增长/消费",
    fed: "美联储",
    manufacturing: "景气",
    external: "外贸",
    credit: "货币信贷",
    activity: "经济活动",
    housing: "房地产",
    monetary_policy: "利率",
    reserves: "外储",
    fiscal: "财政",
    profits: "工业利润",
    policy_meeting: "经济政策会议",
    party_plenum: "中央全会",
  };
  const COUNTRY_LABELS = {
    CN: "中国",
    US: "美国",
  };
  const SOURCE_STATUS_LABELS = {
    nbs: "国家统计局",
    pbc_credit: "人民银行金融统计",
    pbc_lpr: "人民银行LPR",
    gacc: "海关总署",
    safe: "国家外汇管理局",
    mof: "财政部",
  };
  const FOMC_MEETINGS = [
    { start: "2026-01-27", end: "2026-01-28" },
    { start: "2026-03-17", end: "2026-03-18" },
    { start: "2026-04-28", end: "2026-04-29" },
    { start: "2026-06-16", end: "2026-06-17" },
    { start: "2026-07-28", end: "2026-07-29" },
    { start: "2026-09-15", end: "2026-09-16" },
    { start: "2026-10-27", end: "2026-10-28" },
    { start: "2026-12-08", end: "2026-12-09" },
    { start: "2027-01-26", end: "2027-01-27" },
    { start: "2027-03-16", end: "2027-03-17" },
    { start: "2027-04-27", end: "2027-04-28" },
    { start: "2027-06-08", end: "2027-06-09" },
    { start: "2027-07-27", end: "2027-07-28" },
    { start: "2027-09-14", end: "2027-09-15" },
    { start: "2027-10-26", end: "2027-10-27" },
    { start: "2027-12-07", end: "2027-12-08" },
    { start: "2028-01-25", end: "2028-01-26", tentative: true },
  ];

  const state = {
    events: [],
    country: "ALL",
    dataStatus: "unknown",
    failedSources: [],
    policyEventsUpdatedAt: null,
  };

  const eventList = document.querySelector("[data-calendar-events]");
  const status = document.querySelector("[data-calendar-status]");
  const nextFomcDate = document.querySelector("[data-next-fomc-date]");
  const filterButtons = Array.from(
    document.querySelectorAll("[data-macro-country]")
  );

  if (!eventList || !status || !MODEL) {
    return;
  }

  function todayShanghai() {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }

  function formatCnDate(day) {
    const date = MODEL.parseShanghaiDay(day);
    if (!date) {
      return "日期待定";
    }
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "long",
      day: "numeric",
      weekday: "short",
    }).format(date);
  }

  function formatShortDay(day) {
    const date = MODEL.parseShanghaiDay(day);
    if (!date) {
      return "待定";
    }
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "numeric",
      day: "numeric",
    }).format(date);
  }

  function formatExpectedWindow(windowValue) {
    if (!windowValue || !windowValue.start) {
      return "日期待定";
    }
    const start = formatShortDay(windowValue.start);
    const end = windowValue.end ? formatShortDay(windowValue.end) : start;
    return start === end ? `预计 ${start}` : `预计 ${start}—${end}`;
  }

  function parseDate(dateText) {
    const [year, month, day] = dateText.split("-").map(Number);
    return new Date(year, month - 1, day);
  }

  function getNextFomcMeeting() {
    const today = parseDate(todayShanghai());
    return FOMC_MEETINGS.find((meeting) => {
      const meetingEnd = parseDate(meeting.end || meeting.start);
      meetingEnd.setHours(23, 59, 59, 999);
      return meetingEnd >= today;
    });
  }

  function formatFomcMeeting(meeting) {
    const start = parseDate(meeting.start);
    const end = parseDate(meeting.end || meeting.start);
    const sameYear = start.getFullYear() === end.getFullYear();
    const sameMonth = sameYear && start.getMonth() === end.getMonth();
    let dateText = "";
    if (sameMonth) {
      dateText = `${start.getFullYear()}年${
        start.getMonth() + 1
      }月${start.getDate()}-${end.getDate()}日`;
    } else if (sameYear) {
      dateText = `${start.getFullYear()}年${
        start.getMonth() + 1
      }月${start.getDate()}日-${end.getMonth() + 1}月${end.getDate()}日`;
    } else {
      dateText = `${start.getFullYear()}年${
        start.getMonth() + 1
      }月${start.getDate()}日-${end.getFullYear()}年${
        end.getMonth() + 1
      }月${end.getDate()}日`;
    }
    return `${dateText}${meeting.tentative ? "（暂定）" : ""}`;
  }

  function renderNextFomcDate() {
    if (!nextFomcDate) {
      return;
    }
    const meeting = getNextFomcMeeting();
    nextFomcDate.textContent = meeting
      ? `下次 FOMC：${formatFomcMeeting(meeting)}`
      : "下次 FOMC：见美联储日历";
  }

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = String(value == null ? "" : value);
    return node.innerHTML;
  }

  function getImportanceStars(event) {
    const stars = Number(event.stars);
    if (Number.isInteger(stars) && stars >= 1 && stars <= 5) {
      return stars;
    }
    return {
      critical: 5,
      high: 4,
      medium: 3,
      low: 2,
      background: 1,
    }[event.importance] || 3;
  }

  function renderImportanceStars(event) {
    const stars = getImportanceStars(event);
    const symbols = `${"★".repeat(stars)}${"☆".repeat(5 - stars)}`;
    return `<span class="macro-importance" data-stars="${stars}" role="img" aria-label="重要性 ${stars} 星，满分 5 星" title="重要性 ${stars}/5">${symbols}</span>`;
  }

  function formatPeriod(period) {
    if (!period) {
      return "";
    }
    const isoMonth = period.match(/^(\d{4})-(\d{2})$/);
    if (isoMonth) {
      return `${isoMonth[1]}年${Number(isoMonth[2])}月`;
    }
    const cumulative = period.match(/^(\d{4})-01\/(\d{2})$/);
    if (cumulative) {
      return `${cumulative[1]}年1—${Number(cumulative[2])}月`;
    }
    const englishMonth = period.match(
      /^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})$/
    );
    if (englishMonth) {
      const monthNumber = [
        "January",
        "February",
        "March",
        "April",
        "May",
        "June",
        "July",
        "August",
        "September",
        "October",
        "November",
        "December",
      ].indexOf(englishMonth[1]);
      return `${englishMonth[2]}年${monthNumber + 1}月`;
    }
    const quarter = period.match(/^Q([1-4])\s+(\d{4})$/);
    if (quarter) {
      return `${quarter[2]}年${quarter[1]}季度`;
    }
    return period;
  }

  function formatMetricValue(value, unit) {
    if (value === null || value === undefined || value === "") {
      return "";
    }
    const text = String(value);
    if (!unit || text.includes(unit)) {
      return text;
    }
    return `${text}${unit}`;
  }

  function splitCompositeMetric(value) {
    if (typeof value !== "string" || !value.includes(" · ")) {
      return null;
    }
    const entries = value.split(" · ").map((part) => {
      const match = part.trim().match(/^(.+?)\s+([-+−]?\d[\d,.]*%?|—)$/u);
      return match ? [match[1].trim(), match[2].trim()] : null;
    });
    return entries.every(Boolean) ? new Map(entries) : null;
  }

  function displayMetrics(event) {
    const metrics = Array.isArray(event.metrics) ? event.metrics : [];
    if (metrics.length !== 1 || (metrics[0].label || "综合值") !== "综合值") {
      return metrics;
    }
    const metric = metrics[0];
    const parts = {
      actual: splitCompositeMetric(metric.actual),
      forecast: splitCompositeMetric(metric.forecast),
      previous: splitCompositeMetric(metric.previous),
    };
    const labels = [...new Set(Object.values(parts).flatMap((values) =>
      values ? [...values.keys()] : []
    ))];
    if (labels.length < 2) {
      return metrics;
    }
    return labels.map((label) => ({
      label,
      actual: parts.actual?.get(label) || null,
      forecast: parts.forecast?.get(label) || null,
      previous: parts.previous?.get(label) || null,
      unit: "",
    }));
  }

  function renderMetrics(event) {
    const displayRows = displayMetrics(event);
    if (!displayRows.length) {
      return "";
    }
    const showForecast = event.country !== "CN" && displayRows.some(
      (metric) => metric.forecast !== null && metric.forecast !== undefined && metric.forecast !== ""
    );
    const columnClass = showForecast ? "macro-metric-columns-4" : "macro-metric-columns-3";
    const metricHeader = `<div class="macro-metric-table-head ${columnClass}"><span>指标</span><span>实际</span>${showForecast ? "<span>预期</span>" : ""}<span>前值</span></div>`;
    const metrics = displayRows
      .map((metric) => {
        if (![metric.actual, metric.forecast, metric.previous].some(
          (value) => value !== null && value !== undefined && value !== ""
        )) {
          return "";
        }
        const value = (value, className) => `<strong class="${className}">${escapeHtml(
          value === null || value === undefined || value === "" ? "—" : formatMetricValue(value, metric.unit)
        )}</strong>`;
        return `<div class="macro-metric ${columnClass}"><span class="macro-metric-label">${escapeHtml(metric.label || "综合值")}</span>${value(metric.actual, "macro-result-actual")}${showForecast ? value(metric.forecast, "macro-result-forecast") : ""}${value(metric.previous, "macro-result-previous")}</div>`;
      })
      .filter(Boolean);
    if (!metrics.length) {
      return "";
    }
    return `<div class="macro-event-results" aria-label="数据公布结果">${metricHeader}${metrics.join(
      ""
    )}</div>`;
  }

  function eventDatePresentation(event) {
    if (event.dateStatus === "date_tbd" && !event.expectedWindow) {
      return { date: "日期待定", time: "—" };
    }
    if (event.dateStatus === "expected_window" && event.expectedWindow) {
      return {
        date: formatExpectedWindow(event.expectedWindow),
        time: "窗口",
      };
    }
    const day = MODEL.eventDisplayDay(event);
    const time = event.scheduledAt
      ? event.scheduledAt.slice(11, 16)
      : event.eventType === "policy_event"
      ? "时间未公开"
      : "待定";
    return { date: formatCnDate(day), time };
  }

  function isWindowEvent(event) {
    return Boolean(
      event &&
        event.dateStatus === "expected_window" &&
        event.expectedWindow &&
        event.expectedWindow.start
    );
  }

  function releasedWithin48Hours(event) {
    const releasedAt = event.releasedAt || event.scheduledAt;
    let releasedTimestamp = releasedAt ? Date.parse(releasedAt) : NaN;

    if (Number.isNaN(releasedTimestamp)) {
      const releaseDay = MODEL.eventDisplayDay(event);
      releasedTimestamp = releaseDay
        ? Date.parse(`${releaseDay}T23:59:59+08:00`)
        : NaN;
    }

    if (Number.isNaN(releasedTimestamp)) {
      return false;
    }

    const ageMs = Date.now() - releasedTimestamp;
    return ageMs >= 0 && ageMs <= RELEASE_LOOKBACK_HOURS * 60 * 60 * 1000;
  }

  function eventStatusBadge(event) {
    const distance = MODEL.dayDistance(event, todayShanghai());
    const released = event.releaseStatus === "released" || Boolean(event.releasedAt);
    const policyEvent = event.eventType === "policy_event";
    const recentlyReleased = policyEvent
      ? distance >= -POLICY_LOOKBACK_DAYS && distance <= 0
      : releasedWithin48Hours(event);
    if (released && recentlyReleased) {
      return `<small class="macro-released-badge">${
        policyEvent ? "已举行" : "已公布"
      }</small>`;
    }
    if (!released && distance >= 0 && distance <= UPCOMING_DAYS) {
      return `<small class="macro-upcoming-badge">${
        policyEvent ? "即将举行" : "即将发布"
      }</small>`;
    }
    if (event.dateStatus === "expected_window") {
      return '<small class="macro-window-badge">预计窗口</small>';
    }
    return "";
  }

  function visibleEvents(country, eventType) {
    const events = MODEL.visibleEvents(state.events, {
      country,
      eventType,
      today: todayShanghai(),
      lookbackDays:
        eventType === "policy_event" ? POLICY_LOOKBACK_DAYS : RELEASE_LOOKBACK_DAYS,
      horizonDays: HORIZON_DAYS,
    });
    return events.filter((event) => {
      const released = event.releaseStatus === "released" || Boolean(event.releasedAt);
      return eventType === "policy_event" || !released || releasedWithin48Hours(event);
    });
  }

  function updateFilterCounts() {
    const allWindowEvents = MODEL.sortEvents([
      ...visibleEvents("ALL", "data"),
      ...visibleEvents("ALL", "policy_event"),
    ]);
    const counts = {
      ALL: allWindowEvents.length,
      CN: allWindowEvents.filter((event) => event.country === "CN").length,
      US: allWindowEvents.filter((event) => event.country === "US").length,
    };
    filterButtons.forEach((button) => {
      const country = button.dataset.macroCountry;
      const count = button.querySelector("[data-filter-count]");
      button.setAttribute("aria-pressed", String(country === state.country));
      button.classList.toggle("is-active", country === state.country);
      if (count) {
        count.textContent = String(counts[country] || 0);
      }
    });
  }

  function renderStatus(dataEvents, policyEvents) {
    const events = [...dataEvents, ...policyEvents];
    if (!state.events.length) {
      status.textContent = "暂时没有可显示的宏观事件。";
      status.dataset.state = "empty";
      return;
    }
    if (state.dataStatus === "partial" || state.dataStatus === "stale") {
      const sourceText = state.failedSources.length
        ? `（${state.failedSources
            .map((source) => SOURCE_STATUS_LABELS[source] || source)
            .join("、")}）`
        : "";
      status.textContent = `部分中国官方源暂时不可用${sourceText}，当前保留上一份有效数据。`;
      status.dataset.state = "warning";
      return;
    }
    if (state.dataStatus === "static_sample") {
      status.textContent = "中国数据为已核对的官方静态样本；政策会议来自官方通稿，未公开时刻不会被推测。";
      status.dataset.state = "notice";
      return;
    }
    status.textContent = events.length
      ? ""
      : `最近 ${RELEASE_LOOKBACK_HOURS} 小时已公布的数据、最近 ${POLICY_LOOKBACK_DAYS} 天已举行的政策事件及未来 ${HORIZON_DAYS} 天暂无重点事项。`;
    status.dataset.state = events.length ? "ready" : "empty";
  }

  function renderPolicyDetails(event) {
    const summary = event.summary
      ? `<p class="macro-policy-summary">${escapeHtml(event.summary)}</p>`
      : "";
    const scheduleNote = event.scheduleNote
      ? `<small class="macro-policy-schedule">${escapeHtml(event.scheduleNote)}</small>`
      : "";
    const outcomeUrl = event.outcomeUrl || event.sourceUrl;
    const outcomeLink = outcomeUrl
      ? `<a class="macro-policy-outcome" href="${escapeHtml(
          outcomeUrl
        )}" target="_blank" rel="noreferrer">${escapeHtml(
          event.outcomeLabel || "查看官方通稿"
        )}</a>`
      : "";
    return `<div class="macro-policy-details">${summary}${scheduleNote}${outcomeLink}</div>`;
  }

  function directOfficialReportUrl(event) {
    const scheduledDay = event.scheduledAt && event.scheduledAt.slice(0, 10);
    const isReleased =
      event.releaseStatus === "released" ||
      (scheduledDay && scheduledDay < todayShanghai());
    if (!isReleased) return null;

    const blsArchives = {
      "美国CPI / 核心CPI": "cpi",
      "美国PPI": "ppi",
      "美国就业报告": "empsit",
    };
    const archive = blsArchives[event.title];
    if (archive && scheduledDay) {
      return `https://www.bls.gov/news.release/archives/${archive}_${scheduledDay.replaceAll("-", "")}.htm`;
    }
    if (event.title === "美国零售销售") {
      return "https://www.census.gov/retail/sales.html";
    }
    return null;
  }

  function renderCalendarItem(event) {
    const item = document.createElement("article");
    const eventType = event.eventType || "data";
    item.className = `macro-event macro-event-${escapeHtml(
      event.category || "macro"
    )} macro-event-type-${escapeHtml(eventType)} macro-country-${String(
      event.country || ""
    ).toLowerCase()}`;
    const date = eventDatePresentation(event);
    const sourceUrl = event.sourceUrl || "#";
    const reportUrl = directOfficialReportUrl(event);
    const primaryUrl = reportUrl || sourceUrl;
    const sourceLabel = reportUrl
      ? `${event.source || "官方"} 报告 ↗`
      : `${event.source || "官方"} 日程 ↗`;
    const fallbackLink = event.fallbackSourceUrl
      ? `<a class="macro-fallback-link" href="${escapeHtml(
          event.fallbackSourceUrl
        )}" target="_blank" rel="noreferrer">${escapeHtml(
          event.fallbackSourceLabel || "备用官方源"
        )}</a>`
      : "";
    const period = formatPeriod(event.period);
    const title = period ? `${event.title} ${period}` : event.title;
    const content =
      eventType === "policy_event"
        ? renderPolicyDetails(event)
        : renderMetrics(event);
    item.innerHTML = `
      <div class="macro-date">
        <span>${escapeHtml(date.date)}</span>
        <strong>${escapeHtml(date.time)}</strong>
        ${eventStatusBadge(event)}
      </div>
      <div class="macro-event-body">
        <div class="macro-event-summary">
          <a class="macro-event-name" href="${escapeHtml(
            primaryUrl
          )}" target="_blank" rel="noreferrer">${escapeHtml(title)}</a>
          <div class="macro-event-meta">
            <span class="macro-country-badge macro-country-badge-${String(
              event.country || ""
            ).toLowerCase()}">${escapeHtml(COUNTRY_LABELS[event.country] || event.country)}</span>
            <span class="macro-category">${escapeHtml(
              CATEGORY_LABELS[event.category] || (eventType === "policy_event" ? "政策事件" : "宏观")
            )}</span>
            ${renderImportanceStars(event)}
            ${event.source ? `<a class="macro-source-link" href="${escapeHtml(primaryUrl)}" target="_blank" rel="noreferrer">${escapeHtml(sourceLabel)}</a>` : ""}
            ${fallbackLink}
          </div>
        </div>
        <div class="macro-event-main">
          ${content}
        </div>
      </div>
    `;
    return item;
  }

  function renderEventGroup(fragment, title, events, eventType) {
    const group = document.createElement("section");
    group.className = `macro-calendar-group macro-calendar-group-${eventType}`;
    const heading = document.createElement("div");
    heading.className = "macro-calendar-group-head";
    heading.innerHTML = `<h3>${escapeHtml(title)}</h3><span>${events.length} 项</span>`;
    const list = document.createElement("div");
    list.className = "macro-calendar-group-list";
    if (events.length) {
      events.forEach((event) => list.append(renderCalendarItem(event)));
    } else {
      const empty = document.createElement("p");
      empty.className = "macro-group-empty";
      empty.textContent =
        eventType === "policy_event"
          ? "当前窗口暂无可确认的重要会议或政策事件。"
          : "当前窗口暂无重点宏观数据。";
      list.append(empty);
    }
    group.append(heading, list);
    fragment.append(group);
  }

  function renderEvents() {
    const dataEvents = visibleEvents(state.country, "data");
    const scheduledDataEvents = dataEvents.filter((event) => !isWindowEvent(event));
    const windowDataEvents = dataEvents.filter(isWindowEvent);
    const policyEvents = visibleEvents(state.country, "policy_event");
    const events = MODEL.sortEvents([...scheduledDataEvents, ...policyEvents, ...windowDataEvents]);
    eventList.innerHTML = "";
    renderStatus(dataEvents, policyEvents);
    updateFilterCounts();

    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "macro-empty";
      empty.textContent = `最近 ${RELEASE_LOOKBACK_HOURS} 小时已公布的数据、最近 ${POLICY_LOOKBACK_DAYS} 天的政策事件及未来 ${HORIZON_DAYS} 天暂无重点事项。`;
      eventList.append(empty);
      return;
    }

    const fragment = document.createDocumentFragment();
    renderEventGroup(fragment, "宏观数据", scheduledDataEvents, "data");
    renderEventGroup(
      fragment,
      "重要会议与政策事件",
      policyEvents,
      "policy_event"
    );
    if (windowDataEvents.length) {
      renderEventGroup(
        fragment,
        "发布时间窗口待定",
        windowDataEvents,
        "expected-window"
      );
    }
    eventList.append(fragment);
  }

  filterButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.country = button.dataset.macroCountry || "ALL";
      renderEvents();
    });
  });

  renderNextFomcDate();
  fetch(DATA_URL)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Calendar request failed: ${response.status}`);
      }
      return response.json();
    })
    .then((payload) => {
      const normalized = MODEL.normalizePayload(payload);
      state.events = normalized.events;
      state.dataStatus = normalized.status;
      state.failedSources = normalized.failedSources || [];
      state.policyEventsUpdatedAt = normalized.policyEventsUpdatedAt;
      renderEvents();
    })
    .catch(() => {
      status.textContent = "日历数据暂时无法载入，请检查 data/macro-calendar.json。";
      status.dataset.state = "warning";
    });
})();
