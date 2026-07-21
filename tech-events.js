(function () {
  const DATA_URL = "data/tech-company-events.json";
  const SHANGHAI_OFFSET = "+08:00";
  const DEFAULT_HORIZON_DAYS = 35;
  const DAY_MS = 86400000;

  const CATEGORY_LABELS = {
    earnings: "财报与指引",
    operating_data: "经营数据",
    product_event: "产品活动",
    investor_event: "投资者日",
    regulatory_legal: "监管法律",
  };

  const CONFIRMATION_LABELS = {
    confirmed: "日期确认",
    guided: "官方窗口",
    inferred: "待确认",
  };

  const IMPORTANCE_LABELS = {
    core: "核心",
    important: "重要",
  };

  const MARKET_LABELS = {
    before_open: "盘前",
    after_close: "盘后",
    scheduled_time: "定时发布",
    time_tbd: "时间待公布",
  };

  const root = document.querySelector("[data-tech-events]");
  if (!root) {
    return;
  }

  const eventList = root.querySelector("[data-tech-events-list]");
  const status = root.querySelector("[data-tech-events-status]");
  const updated = root.querySelector("[data-tech-events-updated]");
  const companySelect = root.querySelector("[data-tech-events-company]");
  const categoryButtons = Array.from(root.querySelectorAll("[data-event-category]"));

  const state = {
    category: "all",
    company: "all",
    companies: [],
    events: [],
    horizonDays: DEFAULT_HORIZON_DAYS,
    updatedAt: "",
  };

  function shanghaiToday() {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
    }).formatToParts(new Date());
    const values = Object.fromEntries(parts.map((part) => [part.type, part.value]));
    return `${values.year}-${values.month}-${values.day}`;
  }

  function dateAtShanghaiMidnight(dateText) {
    return new Date(`${dateText}T00:00:00${SHANGHAI_OFFSET}`);
  }

  function dayDistance(dateText) {
    return Math.round(
      (dateAtShanghaiMidnight(dateText) - dateAtShanghaiMidnight(shanghaiToday())) / DAY_MS
    );
  }

  function eventStartDate(event) {
    return event.date_bjt || event.window_start;
  }

  function eventEndDate(event) {
    return event.window_end || event.date_bjt || event.window_start;
  }

  function isInHorizon(event) {
    const startDistance = dayDistance(eventStartDate(event));
    const endDistance = dayDistance(eventEndDate(event));
    return endDistance >= 0 && startDistance <= state.horizonDays;
  }

  function formatDate(dateText, includeYear) {
    const date = dateAtShanghaiMidnight(dateText);
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: includeYear ? "numeric" : undefined,
      month: "long",
      day: "numeric",
      weekday: "short",
    }).format(date);
  }

  function formatWindow(event) {
    const start = event.window_start;
    const end = event.window_end;
    if (!start || !end) {
      return "日期待确认";
    }
    if (start === end) {
      return formatDate(start, false);
    }
    const [startYear, startMonth] = start.split("-").map(Number);
    const [, endMonth, endDay] = end.split("-").map(Number);
    const endYear = Number(end.slice(0, 4));
    const sameMonth = startYear === endYear && startMonth === endMonth;
    if (sameMonth) {
      return `${formatDate(start, false).replace(/星期.|周./, "").trim()}—${endDay}日`;
    }
    return `${formatDate(start, false)}—${formatDate(end, false)}`;
  }

  function countdownText(event) {
    const startDistance = dayDistance(eventStartDate(event));
    const endDistance = dayDistance(eventEndDate(event));
    if (event.date_type === "window" && startDistance <= 0 && endDistance >= 0) {
      return "当前处于待确认窗口";
    }
    if (startDistance === 0) {
      return "今天";
    }
    if (startDistance === 1) {
      return "明天";
    }
    if (startDistance > 1) {
      return `${startDistance} 天后`;
    }
    return "已发生";
  }

  function displayTime(event) {
    if (event.date_type === "window") {
      return "具体时间待确认";
    }
    if (event.time_bjt) {
      return `北京时间 ${event.time_bjt}`;
    }
    return "具体北京时间待公布";
  }

  function filteredEvents() {
    return state.events
      .filter(isInHorizon)
      .filter((event) => state.category === "all" || event.event_category === state.category)
      .filter((event) => state.company === "all" || event.company_id === state.company)
      .sort((a, b) => {
        const first = `${eventStartDate(a)} ${a.time_bjt || "99:99"}`;
        const second = `${eventStartDate(b)} ${b.time_bjt || "99:99"}`;
        return first.localeCompare(second) || a.company.localeCompare(b.company);
      });
  }

  function createBadge(text, className) {
    const badge = document.createElement("span");
    badge.className = className;
    badge.textContent = text;
    return badge;
  }

  function renderEvent(event) {
    const item = document.createElement("article");
    item.className = `tech-event tech-event-${event.event_category}`;
    if (event.importance === "core") {
      item.classList.add("tech-event-core");
    }

    const dateBlock = document.createElement("div");
    dateBlock.className = "tech-event-date";
    const dateLabel = document.createElement("strong");
    dateLabel.textContent =
      event.date_type === "window" ? formatWindow(event) : formatDate(event.date_bjt, false);
    const timeLabel = document.createElement("span");
    timeLabel.textContent = displayTime(event);
    const countdown = document.createElement("small");
    countdown.textContent = countdownText(event);
    dateBlock.append(dateLabel, timeLabel, countdown);

    const body = document.createElement("div");
    body.className = "tech-event-body";

    const companyRow = document.createElement("div");
    companyRow.className = "tech-event-company-row";
    const company = document.createElement("strong");
    company.textContent = event.company;
    const ticker = document.createElement("span");
    ticker.textContent = event.ticker;
    companyRow.append(company, ticker);

    const title = document.createElement("a");
    title.className = "tech-event-name";
    title.href = event.source_url;
    title.target = "_blank";
    title.rel = "noreferrer";
    title.textContent = event.event_name;
    title.setAttribute("aria-label", `${event.event_name}，打开${event.source_label}官方来源`);

    const badges = document.createElement("div");
    badges.className = "tech-event-badges";
    badges.append(
      createBadge(CATEGORY_LABELS[event.event_category] || "公司事件", "tech-event-category"),
      createBadge(
        IMPORTANCE_LABELS[event.importance] || "重要",
        `tech-event-importance tech-event-importance-${event.importance}`
      ),
      createBadge(
        CONFIRMATION_LABELS[event.confirmation] || "待确认",
        `tech-event-confirmation tech-event-confirmation-${event.confirmation}`
      )
    );
    if (event.date_changed) {
      badges.append(createBadge("日期有变", "tech-event-change"));
    }

    const details = document.createElement("div");
    details.className = "tech-event-details";
    const market = document.createElement("span");
    market.textContent = MARKET_LABELS[event.market_timing] || "时间待公布";
    const source = document.createElement("a");
    source.href = event.source_url;
    source.target = "_blank";
    source.rel = "noreferrer";
    source.textContent = `官方来源：${event.source_label}`;
    details.append(market, source);

    body.append(companyRow, title, badges, details);
    item.append(dateBlock, body);
    return item;
  }

  function renderStatus(events) {
    const total = state.events.filter(isInHorizon).length;
    if (!events.length) {
      status.textContent = `当前筛选下，未来 ${state.horizonDays} 天暂无关键事件。`;
      return;
    }
    const confirmed = events.filter((event) => event.confirmation === "confirmed").length;
    const inferred = events.filter((event) => event.confirmation !== "confirmed").length;
    status.textContent = `显示 ${events.length} 项（全部 ${total} 项）：${confirmed} 项日期已确认${
      inferred ? `，${inferred} 项仍待确认` : ""
    }。`;
  }

  function render() {
    const events = filteredEvents();
    eventList.replaceChildren();
    renderStatus(events);
    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "tech-events-empty";
      empty.textContent = "可尝试切换事件类型或选择其他公司。";
      eventList.append(empty);
      return;
    }
    const fragment = document.createDocumentFragment();
    events.forEach((event) => fragment.append(renderEvent(event)));
    eventList.append(fragment);
  }

  function populateCompanies() {
    const fragment = document.createDocumentFragment();
    state.companies.forEach((company) => {
      const option = document.createElement("option");
      option.value = company.id;
      option.textContent = `${company.name} · ${company.ticker}`;
      fragment.append(option);
    });
    companySelect.append(fragment);
  }

  function formatUpdatedAt(value) {
    if (!value) {
      return "更新时间暂不可用";
    }
    const date = new Date(value);
    return `数据变更于 ${new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "numeric",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
    }).format(date)}`;
  }

  categoryButtons.forEach((button) => {
    button.addEventListener("click", () => {
      state.category = button.dataset.eventCategory;
      categoryButtons.forEach((candidate) => {
        const active = candidate === button;
        candidate.classList.toggle("is-active", active);
        candidate.setAttribute("aria-pressed", String(active));
      });
      render();
    });
  });

  companySelect.addEventListener("change", () => {
    state.company = companySelect.value;
    render();
  });

  fetch(DATA_URL)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Technology event request failed: ${response.status}`);
      }
      return response.json();
    })
    .then((payload) => {
      state.companies = Array.isArray(payload.companies) ? payload.companies : [];
      state.events = Array.isArray(payload.events) ? payload.events : [];
      state.horizonDays = Number(payload.horizon_days) || DEFAULT_HORIZON_DAYS;
      state.updatedAt = payload.updated_at || "";
      updated.textContent = formatUpdatedAt(state.updatedAt);
      populateCompanies();
      render();
    })
    .catch(() => {
      status.textContent = "科技事件暂时无法载入，请稍后刷新。";
      updated.textContent = "数据载入失败";
    });
})();
