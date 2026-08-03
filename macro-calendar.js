(function () {
  const DATA_URL = "data/macro-calendar.json";
  const FILTER_LABELS = {
    inflation: "通胀",
    jobs: "就业",
    growth: "增长/消费",
    consumption: "增长/消费",
    fed: "美联储",
    pmi: "景气",
    trade: "外贸",
    credit: "金融",
    housing: "房地产",
    profits: "企业利润",
    policy: "政策会议",
    rates: "利率",
  };
  const COUNTRY_LABELS = {
    CN: "中国",
    US: "美国",
  };
  const HORIZON_DAYS = 35;
  const LOOKBACK_DAYS = 7;
  const UPCOMING_DAYS = 3;
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
    country: "all",
    highOnly: false,
  };

  const eventList = document.querySelector("[data-calendar-events]");
  const status = document.querySelector("[data-calendar-status]");
  const nextFomcDate = document.querySelector("[data-next-fomc-date]");
  const countryButtons = Array.from(
    document.querySelectorAll("[data-calendar-country]")
  );
  const highOnlyButton = document.querySelector("[data-calendar-high-only]");

  if (!eventList || !status) {
    return;
  }

  function parseDate(dateText) {
    const parts = String(dateText).split("-").map(Number);
    return new Date(parts[0], parts[1] - 1, parts[2]);
  }

  function formatCnDate(dateText) {
    const date = parseDate(dateText);
    return new Intl.DateTimeFormat("zh-CN", {
      month: "long",
      day: "numeric",
      weekday: "short",
    }).format(date);
  }

  function dateDistance(dateText) {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    const eventDate = parseDate(dateText);
    eventDate.setHours(0, 0, 0, 0);
    return Math.round((eventDate - today) / 86400000);
  }

  function getToday() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  }

  function getNextFomcMeeting() {
    const today = getToday();
    return FOMC_MEETINGS.find(function (meeting) {
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
      dateText =
        start.getFullYear() +
        "年" +
        (start.getMonth() + 1) +
        "月" +
        start.getDate() +
        "-" +
        end.getDate() +
        "日";
    } else if (sameYear) {
      dateText =
        start.getFullYear() +
        "年" +
        (start.getMonth() + 1) +
        "月" +
        start.getDate() +
        "日-" +
        (end.getMonth() + 1) +
        "月" +
        end.getDate() +
        "日";
    } else {
      dateText =
        start.getFullYear() +
        "年" +
        (start.getMonth() + 1) +
        "月" +
        start.getDate() +
        "日-" +
        end.getFullYear() +
        "年" +
        (end.getMonth() + 1) +
        "月" +
        end.getDate() +
        "日";
    }

    return dateText + (meeting.tentative ? "（暂定）" : "");
  }

  function renderNextFomcDate() {
    if (!nextFomcDate) {
      return;
    }
    const meeting = getNextFomcMeeting();
    nextFomcDate.textContent = meeting
      ? "下次 FOMC：" + formatFomcMeeting(meeting)
      : "下次 FOMC：见美联储日历";
  }

  function getEventDateForWindow(event) {
    return event.date_shanghai || event.date;
  }

  function getEventEndDate(event) {
    return event.date_end || event.dateEnd || getEventDateForWindow(event);
  }

  function getDateStatus(event) {
    return event.dateStatus || event.date_status || "confirmed";
  }

  function isUpcomingEvent(event) {
    const startDistance = dateDistance(getEventDateForWindow(event));
    const endDistance = dateDistance(getEventEndDate(event));
    return (
      event.release_status !== "released" &&
      endDistance >= 0 &&
      startDistance <= UPCOMING_DAYS
    );
  }

  function isRecentEvent(event) {
    const endDistance = dateDistance(getEventEndDate(event));
    return endDistance < 0 && endDistance >= -LOOKBACK_DAYS;
  }

  function normalizeCategory(event) {
    return event.category === "consumption" ? "growth" : event.category;
  }

  function getImportanceStars(event) {
    const stars = Number(event.stars);
    if (Number.isInteger(stars) && stars >= 1 && stars <= 5) {
      return stars;
    }
    const legacyImportance = {
      critical: 5,
      high: 4,
      medium: 3,
      low: 2,
      background: 1,
    };
    return legacyImportance[event.importance] || 3;
  }

  function renderImportanceStars(event) {
    const stars = getImportanceStars(event);
    const symbols = "★".repeat(stars) + "☆".repeat(5 - stars);
    return (
      '<span class="macro-importance" data-stars="' +
      stars +
      '" role="img" aria-label="重要性 ' +
      stars +
      ' 星，满分 5 星" title="重要性 ' +
      stars +
      '/5">' +
      symbols +
      "</span>"
    );
  }

  function formatPeriod(period) {
    if (!period) {
      return "";
    }
    const monthMatch = period.match(
      /^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})$/
    );
    if (monthMatch) {
      const months = {
        January: "1月",
        February: "2月",
        March: "3月",
        April: "4月",
        May: "5月",
        June: "6月",
        July: "7月",
        August: "8月",
        September: "9月",
        October: "10月",
        November: "11月",
        December: "12月",
      };
      return monthMatch[2] + "年" + months[monthMatch[1]];
    }
    const quarterMatch = period.match(/^Q([1-4])\s+(\d{4})$/);
    if (quarterMatch) {
      return quarterMatch[2] + "年" + quarterMatch[1] + "季度";
    }
    const meetingMatch = period.match(
      /^(January|February|March|April|May|June|July|August|September|October|November|December)\s+(\d{4})\s+meeting$/
    );
    if (meetingMatch) {
      const months = {
        January: "1月",
        February: "2月",
        March: "3月",
        April: "4月",
        May: "5月",
        June: "6月",
        July: "7月",
        August: "8月",
        September: "9月",
        October: "10月",
        November: "11月",
        December: "12月",
      };
      return meetingMatch[2] + "年" + months[meetingMatch[1]] + "会议";
    }
    return period;
  }

  function formatEventName(event) {
    const title = String(event.title_cn || event.title || "").replace(/\s+/g, "");
    const period = formatPeriod(event.period);
    return period ? title + " " + period : title;
  }

  function escapeHtml(value) {
    const node = document.createElement("span");
    node.textContent = String(value);
    return node.innerHTML;
  }

  function formatEventResults(event) {
    const fields = [
      ["actual", "公布"],
      ["forecast", "预期"],
      ["previous", "前值"],
    ];
    const values = fields.filter(function (entry) {
      const value = event[entry[0]];
      return value !== undefined && value !== null && value !== "";
    });
    if (!values.length) {
      return "";
    }
    return (
      '<div class="macro-event-results" aria-label="数据公布结果">' +
      values
        .map(function (entry) {
          const field = entry[0];
          const label = entry[1];
          return (
            '<span class="macro-result macro-result-' +
            field +
            '"><small>' +
            label +
            "</small><strong>" +
            escapeHtml(event[field]) +
            "</strong></span>"
          );
        })
        .join("") +
      "</div>"
    );
  }

  function formatDateLabel(event) {
    const start = getEventDateForWindow(event);
    const end = getEventEndDate(event);
    if (end && end !== start) {
      return formatCnDate(start) + "—" + formatCnDate(end);
    }
    return formatCnDate(start);
  }

  function getStatusBadge(event) {
    const dateStatus = getDateStatus(event);
    if (dateStatus === "after_confirmed") {
      return '<small class="macro-released-badge">会后确认</small>';
    }
    if (dateStatus === "window") {
      return '<small class="macro-window-badge">观察窗口</small>';
    }
    if (dateStatus === "tentative") {
      return '<small class="macro-tentative-badge">待定</small>';
    }
    if (event.release_status === "released" || isRecentEvent(event)) {
      return '<small class="macro-released-badge">已公布</small>';
    }
    if (isUpcomingEvent(event)) {
      return '<small class="macro-upcoming-badge">即将发布</small>';
    }
    return "";
  }

  function filterEvents() {
    return state.events
      .filter(function (event) {
        const startDistance = dateDistance(getEventDateForWindow(event));
        const endDistance = dateDistance(getEventEndDate(event));
        const inWindow =
          endDistance >= -LOOKBACK_DAYS && startDistance <= HORIZON_DAYS;
        const matchesCountry =
          state.country === "all" || event.country === state.country;
        const matchesImportance =
          !state.highOnly || getImportanceStars(event) >= 4;
        return inWindow && matchesCountry && matchesImportance;
      })
      .sort(function (a, b) {
        const aStamp =
          getEventDateForWindow(a) + " " + (a.time_shanghai || "99:99");
        const bStamp =
          getEventDateForWindow(b) + " " + (b.time_shanghai || "99:99");
        return aStamp.localeCompare(bStamp);
      });
  }

  function renderStatus(events) {
    if (!state.events.length) {
      status.textContent = "暂时没有可显示的宏观事件。";
      return;
    }
    status.textContent = events.length
      ? ""
      : "当前筛选下，最近 7 天及未来 35 天暂无重点事件。";
  }

  function renderEvents() {
    const events = filterEvents();
    eventList.innerHTML = "";
    renderStatus(events);

    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "macro-empty";
      empty.textContent = "当前筛选下，最近 7 天及未来 35 天暂无重点事件。";
      eventList.append(empty);
      return;
    }

    const fragment = document.createDocumentFragment();
    events.forEach(function (event) {
      const isUpcoming = isUpcomingEvent(event);
      const isRecent =
        isRecentEvent(event) || event.release_status === "released";
      const item = document.createElement("article");
      item.className =
        "macro-event macro-event-" +
        normalizeCategory(event) +
        (isUpcoming ? " macro-event-upcoming" : "") +
        (isRecent ? " macro-event-recent" : "");

      const sourceUrl = event.sourceUrl || event.url || "#";
      const category =
        FILTER_LABELS[event.category] ||
        FILTER_LABELS[normalizeCategory(event)] ||
        "宏观";
      const country = event.country || "US";
      const sourceBadge = event.source
        ? '<span class="macro-source">' + escapeHtml(event.source) + "</span>"
        : "";
      const fallbackLink = event.fallback_url
        ? '<a class="macro-fallback-link" href="' +
          escapeHtml(event.fallback_url) +
          '" target="_blank" rel="noreferrer">' +
          escapeHtml(event.fallback_label || "备用链接") +
          "</a>"
        : "";
      const timeText =
        getDateStatus(event) === "window" || !event.time_shanghai
          ? "时间待定"
          : event.time_shanghai;

      item.innerHTML =
        '<div class="macro-date"><span class="macro-date-range">' +
        formatDateLabel(event) +
        "</span><strong>" +
        escapeHtml(timeText) +
        "</strong>" +
        getStatusBadge(event) +
        '</div><div class="macro-event-body"><div class="macro-event-meta">' +
        '<span class="macro-event-country" data-country="' +
        escapeHtml(country) +
        '">' +
        escapeHtml(COUNTRY_LABELS[country] || country) +
        "</span>" +
        '<span class="macro-category">' +
        escapeHtml(category) +
        "</span>" +
        renderImportanceStars(event) +
        sourceBadge +
        fallbackLink +
        '</div><div class="macro-event-main"><a class="macro-event-name" href="' +
        escapeHtml(sourceUrl) +
        '" target="_blank" rel="noreferrer">' +
        escapeHtml(formatEventName(event)) +
        "</a>" +
        formatEventResults(event) +
        "</div></div>";

      fragment.append(item);
    });
    eventList.append(fragment);
  }

  countryButtons.forEach(function (button) {
    button.addEventListener("click", function () {
      state.country = button.dataset.calendarCountry || "all";
      countryButtons.forEach(function (candidate) {
        const active = candidate === button;
        candidate.classList.toggle("is-active", active);
        candidate.setAttribute("aria-pressed", String(active));
      });
      renderEvents();
    });
  });

  if (highOnlyButton) {
    highOnlyButton.addEventListener("click", function () {
      state.highOnly = !state.highOnly;
      highOnlyButton.classList.toggle("is-active", state.highOnly);
      highOnlyButton.setAttribute("aria-pressed", String(state.highOnly));
      renderEvents();
    });
  }

  renderNextFomcDate();

  fetch(DATA_URL)
    .then(function (response) {
      if (!response.ok) {
        throw new Error("Calendar request failed: " + response.status);
      }
      return response.json();
    })
    .then(function (events) {
      state.events = Array.isArray(events) ? events : [];
      renderEvents();
    })
    .catch(function () {
      status.textContent =
        "日历数据暂时无法载入，请检查 data/macro-calendar.json。";
    });
})();

