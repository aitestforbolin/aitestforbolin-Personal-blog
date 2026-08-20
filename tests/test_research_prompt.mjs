import assert from "node:assert/strict";
import test from "node:test";

await import("../research-prompt.js");

test("builds a complete project-specific research prompt", () => {
  const prompt = globalThis.BolinResearchPrompt.build({
    name: "Botanika",
    sourceUrl: "https://crypto-fundraising.info/projects/botanika/",
  });

  assert.match(prompt, /项目名称：Botanika/);
  assert.match(prompt, /crypto-fundraising\.info\/projects\/botanika/);
  assert.match(prompt, /Research Conclusion/);
  assert.match(prompt, /Competitive Positioning/);
  assert.match(prompt, /Evidence Ledger/);
  assert.match(prompt, /不使用社交媒体帖子作为资料来源/);
  assert.doesNotMatch(prompt, /x\.com|twitter\.com/i);
});

test("requires both project name and source URL", () => {
  assert.throws(
    () => globalThis.BolinResearchPrompt.build({ name: "Missing URL" }),
    /required/,
  );
});
