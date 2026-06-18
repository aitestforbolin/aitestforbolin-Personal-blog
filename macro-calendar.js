(function () {
  const DATA_URL = "data/us-macro-calendar.json";
  const FILTER_LABELS = {
    inflation: "通胀",
    jobs: "就业",
    growth: "增长/消费",
    consumption: "增长/消费",
    fed: "美联储",
  };
  const HORIZON_DAYS = 14;

  const state = {
    events: [],
  };

  const eventList = document.querySelector("[data-calendar-events]");
  const status = document.querySelector("[data-calendar-status]");

  if (!eventList || !status) {
    return;
  }

  function parseDate(dateText) {
    const [year, month, day] = dateText.split("-").map(Number);
    return new Date(year, month - 1, day);
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

  function getEventDateForWindow(event) {
    return event.date_shanghai || event.date;
  }

  function normalizeCategory(event) {
    return event.category === "consumption" ? "growth" : event.category;
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
      return `${monthMatch[2]}年${months[monthMatch[1]]}`;
    }

    const quarterMatch = period.match(/^Q([1-4])\s+(\d{4})$/);
    if (quarterMatch) {
      return `${quarterMatch[2]}年${quarterMatch[1]}季度`;
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
      return `${meetingMatch[2]}年${months[meetingMatch[1]]}会议`;
    }

    return period;
  }

  function formatEventName(event) {
    const title = event.title_cn.replace(/\s+/g, "");
    const period = formatPeriod(event.period);
    return period ? `${title} ${period}` : title;
  }

  function filterEvents() {
    return state.events
      .filter((event) => {
        const distance = dateDistance(getEventDateForWindow(event));
        return distance >= 0 && distance <= HORIZON_DAYS;
      })
      .sort((a, b) => {
        const aStamp = `${getEventDateForWindow(a)} ${a.time_shanghai || ""}`;
        const bStamp = `${getEventDateForWindow(b)} ${b.time_shanghai || ""}`;
        return aStamp.localeCompare(bStamp);
      });
  }

  function renderStatus(events) {
    if (!state.events.length) {
      status.textContent = "暂时没有可显示的宏观事件。";
      return;
    }

    status.textContent = events.length ? "" : "未来 14 天暂无重点事件。";
  }

  function renderEvents() {
    const events = filterEvents();
    eventList.innerHTML = "";
    renderStatus(events);

    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "macro-empty";
      empty.textContent = "未来 14 天暂无重点事件。";
      eventList.append(empty);
      return;
    }

    const fragment = document.createDocumentFragment();

    events.forEach((event) => {
      const item = document.createElement("article");
      item.className = `macro-event macro-event-${normalizeCategory(event)}`;

      const chinaDate = getEventDateForWindow(event);
      const sourceUrl = event.url || "#";
      const category =
        FILTER_LABELS[event.category] ||
        FILTER_LABELS[normalizeCategory(event)] ||
        "宏观";

      item.innerHTML = `
        <div class="macro-date">
          <span>${formatCnDate(chinaDate)}</span>
          <strong>${event.time_shanghai || "待定"}</strong>
        </div>
        <div class="macro-event-body">
          <div class="macro-event-meta">
            <span class="macro-category">${category}</span>
          </div>
          <a class="macro-event-name" href="${sourceUrl}" target="_blank" rel="noreferrer">
            ${formatEventName(event)}
          </a>
        </div>
      `;

      fragment.append(item);
    });

    eventList.append(fragment);
  }

  fetch(DATA_URL)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Calendar request failed: ${response.status}`);
      }
      return response.json();
    })
    .then((events) => {
      state.events = Array.isArray(events) ? events : [];
      renderEvents();
    })
    .catch(() => {
      status.textContent = "日历数据暂时无法载入，请检查 data/us-macro-calendar.json。";
    });
})();
