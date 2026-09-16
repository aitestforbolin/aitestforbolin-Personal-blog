import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";

const require = createRequire(import.meta.url);
const model = require("../macro-calendar-model.js");
const events = [
  { id: "retail", eventType: "data", country: "US", scheduledAt: "2026-09-16T20:30:00+08:00", dateStatus: "confirmed" },
  { id: "fomc", eventType: "data", country: "US", scheduledAt: "2026-09-17T02:00:00+08:00", dateStatus: "confirmed" },
  { id: "ism", eventType: "data", country: "US", scheduledAt: "2026-09-18T22:00:00+08:00", dateStatus: "confirmed" },
];

test("calendar is U.S.-only and remains sorted by Shanghai display time", () => {
  assert.deepEqual(model.filterByCountry(events, "US").map((event) => event.id), ["retail", "fomc", "ism"]);
  assert.deepEqual(model.sortEvents(events).map((event) => event.id), ["retail", "fomc", "ism"]);
});

test("calendar envelope keeps its source-health fields", () => {
  assert.deepEqual(model.normalizePayload({ status: "healthy", generatedAt: "2026-09-16T10:00:00Z", events }), { status: "healthy", failedSources: [], policyEventsUpdatedAt: null, generatedAt: "2026-09-16T10:00:00Z", events });
});
