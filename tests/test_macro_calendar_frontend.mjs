import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const model = require("../macro-calendar-model.js");

const events = [
  {
    id: "cn-window",
    country: "CN",
    scheduledAt: null,
    dateStatus: "expected_window",
    expectedWindow: { start: "2026-08-09", end: "2026-08-15" },
  },
  {
    id: "us-exact",
    country: "US",
    scheduledAt: "2026-08-08T20:30:00+08:00",
    dateStatus: "confirmed",
  },
  {
    id: "cn-exact",
    country: "CN",
    scheduledAt: "2026-08-08T09:30:00+08:00",
    dateStatus: "confirmed",
  },
  {
    id: "cn-tbd",
    country: "CN",
    scheduledAt: null,
    dateStatus: "date_tbd",
  },
];

test("country filters support all, China and United States", () => {
  assert.equal(model.filterByCountry(events, "ALL").length, 4);
  assert.deepEqual(
    model.filterByCountry(events, "CN").map((event) => event.id),
    ["cn-window", "cn-exact", "cn-tbd"]
  );
  assert.deepEqual(
    model.filterByCountry(events, "US").map((event) => event.id),
    ["us-exact"]
  );
});

test("confirmed events and expected windows sort by Asia Shanghai display time", () => {
  assert.deepEqual(
    model.sortEvents(events).map((event) => event.id),
    ["cn-exact", "us-exact", "cn-window", "cn-tbd"]
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
    ["cn-window", "us-exact", "cn-exact", "cn-tbd"]
  );
  const narrow = model.filterWindow(events, {
    today: "2026-08-02",
    lookbackDays: 3,
    horizonDays: 5,
  });
  assert.deepEqual(narrow.map((event) => event.id), ["cn-tbd"]);

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
    events,
  });
});
