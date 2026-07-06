(function () {
  const DATA_URL = "data/us-macro-calendar.json";
  const FEDWATCH_URL = "data/fedwatch-probabilities.json";
  const FILTER_LABELS = {
    inflation: "通胀",
    jobs: "就业",
    growth: "增长/消费",
    consumption: "增长/消费",
    fed: "美联储",
  };
  const HORIZON_DAYS = 35;
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
  };

  const eventList = document.querySelector("[data-calendar-events]");
  const status = document.querySelector("[data-calendar-status]");
  const nextFomcDate = document.querySelector("[data-next-fomc-date]");
  const fedwatchCard = document.querySelector("[data-fedwatch-probability]");
  const fedwatchMeeting = document.querySelector("[data-fedwatch-meeting]");
  const fedwatchCurrent = document.querySelector("[data-fedwatch-current]");
  const fedwatchProbabilities = document.querySelector("[data-fedwatch-probabilities]");
  const fedwatchUpdated = document.querySelector("[data-fedwatch-updated]");

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

  function getToday() {
    const today = new Date();
    today.setHours(0, 0, 0, 0);
    return today;
  }

  function getNextFomcMeeting() {
    const today = getToday();

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

  function formatFedwatchDate(dateText) {
    if (!dateText) {
      return "";
    }

    const date = parseDate(dateText);
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
    }).format(date);
  }

  function renderFedwatchProbability(data) {
    if (
      !fedwatchCard ||
      !fedwatchMeeting ||
      !fedwatchCurrent ||
      !fedwatchProbabilities ||
      !fedwatchUpdated
    ) {
      return;
    }

    const probabilities = Array.isArray(data.probabilities)
      ? data.probabilities
      : [];

    fedwatchMeeting.textContent =
      data.meeting_label ||
      (data.meeting_date
        ? `${formatFedwatchDate(data.meeting_date)} FOMC`
        : "下一次 FOMC");
    fedwatchCurrent.textContent = data.current_target_rate
      ? `当前 ${data.current_target_rate}`
      : "当前目标利率";
    fedwatchProbabilities.innerHTML = probabilities
      .map((item) => {
        const value = Number(item.probability) || 0;
        const width = Math.max(2, Math.min(value, 100));
        const target = item.target_rate ? `<em>${item.target_rate}</em>` : "";

        return `
          <div class="fedwatch-probability-item fedwatch-probability-${item.kind || "base"}">
            <div>
              <span>${item.label || "概率"}</span>
              ${target}
            </div>
            <strong>${value.toFixed(1)}%</strong>
            <i style="width: ${width}%"></i>
          </div>
        `;
      })
      .join("");
    fedwatchUpdated.textContent = data.updated_at
      ? `${data.source || "CME FedWatch"} · 更新于 ${formatFedwatchDate(data.updated_at)}`
      : `${data.source || "CME FedWatch"} · 点击查看实时概率`;
  }

  function renderFedwatchFallback() {
    if (
      !fedwatchMeeting ||
      !fedwatchCurrent ||
      !fedwatchProbabilities ||
      !fedwatchUpdated
    ) {
      return;
    }

    fedwatchMeeting.textContent = "点击查看 CME FedWatch";
    fedwatchCurrent.textContent = "概率暂不可用";
    fedwatchProbabilities.innerHTML = "";
    fedwatchUpdated.textContent = "CME FedWatch API 需要单独权限，当前仅保留入口。";
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

    status.textContent = events.length ? "" : `未来 ${HORIZON_DAYS} 天暂无重点事件。`;
  }

  function renderEvents() {
    const events = filterEvents();
    eventList.innerHTML = "";
    renderStatus(events);

    if (!events.length) {
      const empty = document.createElement("p");
      empty.className = "macro-empty";
      empty.textContent = `未来 ${HORIZON_DAYS} 天暂无重点事件。`;
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

  renderNextFomcDate();

  fetch(FEDWATCH_URL)
    .then((response) => {
      if (!response.ok) {
        throw new Error(`FedWatch request failed: ${response.status}`);
      }
      return response.json();
    })
    .then(renderFedwatchProbability)
    .catch(renderFedwatchFallback);

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
