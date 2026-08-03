import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const model = require("../macro-calendar-model.js");

const events = [
  {
    id: "cn-window",
    eventType: "data",
    country: "CN",
    scheduledAt: null,
    dateStatus: "expected_window",
    expectedWindow: { start: "2026-08-09", end: "2026-08-15" },
  },
  {
    id: "us-exact",
    eventType: "data",
    country: "US",
    scheduledAt: "2026-08-08T20:30:00+08:00",
    dateStatus: "confirmed",
  },
  {
    id: "cn-exact",
    eventType: "data",
    country: "CN",
    scheduledAt: "2026-08-08T09:30:00+08:00",
    dateStatus: "confirmed",
  },
  {
    id: "cn-tbd",
    eventType: "data",
    country: "CN",
    scheduledAt: null,
    dateStatus: "date_tbd",
  },
  {
    id: "cn-policy",
    eventType: "policy_event",
    country: "CN",
    scheduledAt: null,
    eventDate: "2026-07-30",
    dateStatus: "confirmed_date",
  },
];

test("country filters support all, China and United States", () => {
  assert.equal(model.filterByCountry(events, "ALL").length, 5);
  assert.deepEqual(
    model.filterByCountry(events, "CN").map((event) => event.id),
    ["cn-window", "cn-exact", "cn-tbd", "cn-policy"]
  );
  assert.deepEqual(
    model.filterByCountry(events, "US").map((event) => event.id),
    ["us-exact"]
  );
});

test("confirmed events and expected windows sort by Asia Shanghai display time", () => {
  assert.deepEqual(
    model.sortEvents(events).map((event) => event.id),
    ["cn-policy", "cn-exact", "us-exact", "cn-window", "cn-tbd"]
  );
});

test("event type filters keep policy events separate from macro data", () => {
  assert.deepEqual(
    model.filterByType(events, "data").map((event) => event.id),
    ["cn-window", "us-exact", "cn-exact", "cn-tbd"]
  );
  assert.deepEqual(
    model.filterByType(events, "policy_event").map((event) => event.id),
    ["cn-policy"]
  );
  assert.deepEqual(
    model.visibleEvents(events, {
      country: "CN",
      eventType: "policy_event",
      today: "2026-08-03",
      lookbackDays: 30,
      horizonDays: 35,
    }).map((event) => event.id),
    ["cn-policy"]
  );
});

test("window filter keeps date-tbd events visible and applies lookback horizon", () => {
  const visible = model.filterWindow(events, {
    today: "2026-08-02",
    lookbackDays: 3,
    horizonDays: 7,
  });
  assert.deepEqual(
    visible.map((event) => event.id),
    ["cn-window", "us-exact", "cn-exact", "cn-tbd", "cn-policy"]
  );
  const narrow = model.filterWindow(events, {
    today: "2026-08-02",
    lookbackDays: 3,
    horizonDays: 5,
  });
  assert.deepEqual(narrow.map((event) => event.id), ["cn-tbd", "cn-policy"]);

  const duringWindow = model.filterWindow(events, {
    today: "2026-08-14",
    lookbackDays: 0,
    horizonDays: 0,
  });
  assert.deepEqual(
    duringWindow.map((event) => event.id),
    ["cn-window", "cn-tbd"]
  );
});

test("payload normalizer accepts the unified envelope", () => {
  assert.deepEqual(model.normalizePayload({ status: "partial", events }), {
    status: "partial",
    failedSources: [],
    policyEventsUpdatedAt: null,
    events,
  });
});
