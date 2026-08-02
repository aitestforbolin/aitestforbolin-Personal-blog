(function (root, factory) {
  const api = factory();
  if (typeof module === "object" && module.exports) {
    module.exports = api;
  }
  root.MacroCalendarModel = api;
})(typeof globalThis !== "undefined" ? globalThis : this, function () {
  const DAY_MS = 86400000;

  function normalizePayload(payload) {
    if (Array.isArray(payload)) {
      return { status: "legacy", events: payload };
    }
    return {
      status: payload && payload.status ? payload.status : "unknown",
      failedSources:
        payload && Array.isArray(payload.failedSources)
          ? payload.failedSources
          : [],
      events:
        payload && Array.isArray(payload.events) ? payload.events : [],
    };
  }

  function parseShanghaiDay(day) {
    if (!day) {
      return null;
    }
    const date = new Date(`${day}T00:00:00+08:00`);
    return Number.isNaN(date.getTime()) ? null : date;
  }

  function eventDisplayDay(event) {
    if (event.scheduledAt) {
      return event.scheduledAt.slice(0, 10);
    }
    if (event.expectedWindow && event.expectedWindow.start) {
      return event.expectedWindow.start;
    }
    const legacy = event.legacy || event;
    return legacy.date_shanghai || legacy.date || null;
  }

  function eventSortTimestamp(event) {
    if (event.scheduledAt) {
      const parsed = Date.parse(event.scheduledAt);
      if (!Number.isNaN(parsed)) {
        return parsed;
      }
    }
    if (event.expectedWindow && event.expectedWindow.start) {
      const parsed = Date.parse(`${event.expectedWindow.start}T23:59:59+08:00`);
      if (!Number.isNaN(parsed)) {
        return parsed;
      }
    }
    const day = eventDisplayDay(event);
    const parsedDay = parseShanghaiDay(day);
    return parsedDay ? parsedDay.getTime() : Number.POSITIVE_INFINITY;
  }

  function sortEvents(events) {
    return [...events].sort((a, b) => {
      const timeDifference = eventSortTimestamp(a) - eventSortTimestamp(b);
      if (timeDifference !== 0) {
        return timeDifference;
      }
      const countryDifference = String(a.country || "").localeCompare(
        String(b.country || "")
      );
      if (countryDifference !== 0) {
        return countryDifference;
      }
      return String(a.id || "").localeCompare(String(b.id || ""));
    });
  }

  function filterByCountry(events, country) {
    if (!country || country === "ALL") {
      return [...events];
    }
    return events.filter((event) => event.country === country);
  }

  function dayDistance(event, today) {
    const day = eventDisplayDay(event);
    const eventDate = parseShanghaiDay(day);
    const todayDate = parseShanghaiDay(today);
    if (!eventDate || !todayDate) {
      return Number.POSITIVE_INFINITY;
    }
    return Math.round((eventDate.getTime() - todayDate.getTime()) / DAY_MS);
  }

  function filterWindow(events, options) {
    const today = options.today;
    const lookbackDays = Number(options.lookbackDays || 0);
    const horizonDays = Number(options.horizonDays || 0);
    const todayDate = parseShanghaiDay(today);
    if (!todayDate) {
      return [];
    }
    const earliest = todayDate.getTime() - lookbackDays * DAY_MS;
    const latest = todayDate.getTime() + horizonDays * DAY_MS;
    return events.filter((event) => {
      if (event.dateStatus === "date_tbd" && !event.expectedWindow) {
        return true;
      }
      if (event.expectedWindow) {
        const start = parseShanghaiDay(event.expectedWindow.start);
        const end = parseShanghaiDay(
          event.expectedWindow.end || event.expectedWindow.start
        );
        return Boolean(
          start &&
            end &&
            start.getTime() <= latest &&
            end.getTime() >= earliest
        );
      }
      const distance = dayDistance(event, today);
      return distance >= -lookbackDays && distance <= horizonDays;
    });
  }

  function visibleEvents(events, options) {
    return sortEvents(
      filterWindow(filterByCountry(events, options.country), options)
    );
  }

  return {
    normalizePayload,
    parseShanghaiDay,
    eventDisplayDay,
    eventSortTimestamp,
    sortEvents,
    filterByCountry,
    dayDistance,
    filterWindow,
    visibleEvents,
  };
});
