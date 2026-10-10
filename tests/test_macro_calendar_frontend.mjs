import assert from "node:assert/strict";
import { createRequire } from "node:module";
import test from "node:test";
import vm from "node:vm";
import fs from "node:fs";

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

test("today status uses the Shanghai calendar day rather than a rolling upcoming window", () => {
  const today = "2026-09-16";
  assert.equal(model.dayDistance(events[0], today), 0);
  assert.equal(model.dayDistance(events[1], today), 1);
});

test("overdue values render a warning and refresh an open calendar without browser cache", async () => {
  const node = () => ({ children: [], dataset: {}, innerHTML: "", textContent: "", append(...children) { this.children.push(...children); }, setAttribute() {} });
  const eventList = node(), status = node(), listeners = {}, requests = [];
  const document = { hidden: false, querySelector(selector) { return selector === "[data-calendar-events]" ? eventList : selector === "[data-calendar-status]" ? status : null; }, querySelectorAll() { return []; }, createElement: node, createDocumentFragment: node, addEventListener(name, handler) { listeners[name] = handler; } };
  let interval;
  class Clock extends Date { constructor(...args) { super(...(args.length ? args : ["2026-10-10T06:00:00Z"])); } static now() { return Date.parse("2026-10-10T06:00:00Z"); } }
  const payload = { status: "partial", events: [{ id: "claims", country: "US", eventType: "data", scheduledAt: "2026-10-08T20:30:00+08:00", title: "初请失业金", actualStatus: "overdue", metrics: [{ label: "初请", actual: null, forecast: "200K", previous: "197K" }] }] };
  vm.runInNewContext(fs.readFileSync(new URL("../macro-calendar.js", import.meta.url), "utf8"), { window: { MacroCalendarModel: model }, document, Date: Clock, Intl, setInterval(fn, ms) { interval = { fn, ms }; }, async fetch(url, options) { requests.push({ url, options }); return { ok: true, async json() { return payload; } }; } });
  await new Promise(setImmediate);
  assert.match(status.textContent, /1 项.*待补全实际值/);
  assert.equal(status.dataset.state, "warning");
  assert.match(JSON.stringify(eventList.children), /实际值待补全/);
  assert.equal(requests[0].options.cache, "no-store");
  assert.match(requests[0].url, /checked=\d+/);
  assert.equal(interval.ms, 300000);
  interval.fn();
  listeners.visibilitychange();
  await new Promise(setImmediate);
  assert.equal(requests.length, 3);
  document.hidden = true;
  interval.fn();
  listeners.visibilitychange();
  assert.equal(requests.length, 3);
});

