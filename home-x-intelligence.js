(function () {
  "use strict";

  const root = document.querySelector("[data-home-x-intelligence]");
  if (!root) return;

  const updated = root.querySelector("[data-home-x-updated]");
  const stats = root.querySelector("[data-home-x-stats]");
  const highlightsNode = root.querySelector("[data-home-x-highlights]");

  const DATA_URL = "data/x-intelligence.json";
  const RAW_URL = "https://raw.githubusercontent.com/aitestforbolin/aitestforbolin-Personal-blog/main/data/x-intelligence.json";
  const CACHE_KEY = "bolin.xIntelligence.latest.v2";

  async function fetchJson(value) {
    const url = new URL(value, window.location.href);
    url.searchParams.set("_", String(Date.now()));
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error("X intelligence request failed: " + response.status);
    return await response.json();
  }

  function validate(data) {
    if (!data || typeof data !== "object") throw new Error("Invalid X intelligence payload");
    if (Number(data.schemaVersion) !== 1) throw new Error("Unsupported X intelligence schema");
    return data;
  }

  function saveCache(data) {
    try { localStorage.setItem(CACHE_KEY, JSON.stringify(data)); } catch (_error) {}
  }

  function readCache() {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      return raw ? validate(JSON.parse(raw)) : null;
    } catch (_error) {
      return null;
    }
  }

  async function load() {
    for (const value of [DATA_URL, RAW_URL]) {
      try {
        const payload = validate(await fetchJson(value));
        saveCache(payload);
        return payload;
      } catch (_error) {}
    }
    const cached = readCache();
    if (cached) return cached;
    throw new Error("No X intelligence payload available");
  }

  function formatUpdated(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "等待首次生成";
    return "更新：" + new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    }).format(date);
  }

  function fallbackHighlights(payload) {
    if (!payload.overview) return [];
    return String(payload.overview)
      .split(/(?<=[。！？])/)
      .map(function (item) { return item.trim(); })
      .filter(Boolean)
      .slice(0, 5);
  }

  function renderHighlights(items) {
    highlightsNode.innerHTML = "";
    if (!items.length) {
      const empty = document.createElement("p");
      empty.className = "x-intelligence-home-empty";
      empty.textContent = "X Intelligence 尚未首次生成。";
      highlightsNode.appendChild(empty);
      return;
    }

    items.slice(0, 5).forEach(function (item) {
      const row = document.createElement("p");
      row.className = "x-intelligence-home-highlight";

      const marker = document.createElement("span");
      marker.className = "x-intelligence-home-marker";
      marker.setAttribute("aria-hidden", "true");
      marker.textContent = "•";

      const text = document.createElement("span");
      text.textContent = item;

      row.appendChild(marker);
      row.appendChild(text);
      highlightsNode.appendChild(row);
    });
  }

  function render(payload) {
    updated.textContent = formatUpdated(payload.generatedAt);
    stats.textContent = payload.status === "success"
      ? "扫描 " + Number(payload.sourcePostCount || 0) + " Posts · " + (payload.topics || []).length + " Topics"
      : "等待 ChatGPT Brief";

    const highlights = Array.isArray(payload.homeHighlights) && payload.homeHighlights.length
      ? payload.homeHighlights
      : fallbackHighlights(payload);

    renderHighlights(highlights);
  }

  load().then(render).catch(function (error) {
    console.error(error);
    updated.textContent = "数据暂时无法载入";
    stats.textContent = "";
    renderHighlights(["X Intelligence 暂时无法载入。"]);
  });
})();
