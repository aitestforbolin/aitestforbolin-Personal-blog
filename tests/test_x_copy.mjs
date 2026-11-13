import assert from "node:assert/strict";
import fs from "node:fs";
import test from "node:test";
await import("../daily-market-status/x-copy.js");

const {build, copy} = globalThis.BolinXCopy;
const fixture = JSON.parse(fs.readFileSync(new URL("fixtures/x-copy-long-post.json", import.meta.url), "utf8"));

test("direct long post preserves the final output of all three retired formatters", () => {
  assert.equal(build(fixture.input), fixture.expected);
});

test("long analysis paragraphs remain complete without thread splitting or counters", () => {
  const paragraph = "这是需要完整保留的研究判断，不能因为短帖字数限制而截断。".repeat(40);
  const text = build({...fixture.input, view: [paragraph]});
  assert.ok(text.includes(paragraph));
  assert.doesNotMatch(text, /──────────|\n\d+\/\d+(?:\n|$)/);
});

test("48-hour calendar handles the Beijing year boundary, sorting and expired events", () => {
  const text = build({...fixture.input, now: Date.parse("2026-12-31T20:00:00+08:00"), events: [
    {name: "明年事件", startAt: "2027-01-01T21:30:00+08:00"},
    {name: "今晚事件", startAt: "2026-12-31T21:30:00+08:00"},
    {name: "已经发生", startAt: "2026-12-31T19:30:00+08:00"},
    {name: "超出窗口", startAt: "2027-01-02T20:01:00+08:00"},
  ]});
  assert.match(text, /（今晚）12月31日/);
  assert.match(text, /1月1日/);
  assert.ok(text.indexOf("今晚事件") < text.indexOf("明年事件"));
  assert.doesNotMatch(text, /已经发生|超出窗口/);
});

test("empty calendar and unverified gold anchors retain their explicit notices", () => {
  const text = build({...fixture.input, events: []});
  assert.match(text, /未来48小时暂无重点事件。/);
  assert.match(text, /黄金 最新 4,000.00（锚点缺失/);
});

function fallbackEnvironment(success = true) {
  const calls = [];
  const textarea = {style: {}, setAttribute() {}, focus() {}, select() {}, setSelectionRange() {}, remove() {calls.push("remove");}};
  const environment = {navigator: {}, document: {
    activeElement: {focus() {calls.push("restore-focus");}},
    createElement() {return textarea;}, body: {appendChild() {}},
    execCommand(command) {calls.push(command); return success;},
  }};
  return {environment, calls, textarea};
}

test("native copying writes the supplied body once without changing clipboard methods", async () => {
  const {environment, calls} = fallbackEnvironment();
  const writes = [];
  const writeText = async (text) => writes.push(text);
  environment.navigator.clipboard = {writeText};
  await copy("普通正文保持原样\n04｜看法和观点", environment);
  assert.deepEqual(writes, ["普通正文保持原样\n04｜看法和观点"]);
  assert.deepEqual(calls, []);
  assert.equal(environment.navigator.clipboard.writeText, writeText);
});

test("fallback copies the same payload and restores focus after a permission failure", async () => {
  const {environment, calls, textarea} = fallbackEnvironment();
  environment.navigator.clipboard = {writeText: async () => {throw new Error("denied");}};
  await copy("完整长帖", environment);
  assert.equal(textarea.value, "完整长帖");
  assert.deepEqual(calls, ["copy", "remove", "restore-focus"]);
});

test("fallback failure is reported and still removes its temporary element", async () => {
  const {environment, calls} = fallbackEnvironment(false);
  await assert.rejects(copy("payload", environment), /Clipboard copy failed/);
  assert.deepEqual(calls, ["copy", "remove", "restore-focus"]);
});
