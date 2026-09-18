(function () {
  "use strict";

  const root = document.querySelector("[data-home-x-intelligence]");
  if (!root) return;

  const updated = root.querySelector("[data-home-x-updated]");
  const stats = root.querySelector("[data-home-x-stats]");
  const overview = root.querySelector("[data-home-x-overview]");
  const list = root.querySelector("[data-home-x-list]");

  const DATA_URL = "data/x-intelligence.json";
  const RAW_URL = "https://raw.githubusercontent.com/aitestforbolin/aitestforbolin-Personal-blog/main/data/x-intelligence.json";
  const CACHE_KEY = "bolin.xIntelligence.latest.v1";

  function escapeHtml(value) {
    return String(value == null ? "" : value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

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

  function render(payload) {
    updated.textContent = formatUpdated(payload.generatedAt);
    stats.textContent = payload.status === "success"
      ? "扫描 " + Number(payload.sourcePostCount || 0) + " Posts · " + (payload.topics || []).length + " Topics"
      : "等待 ChatGPT Brief";

    overview.textContent = payload.overview || "X Intelligence 尚未首次生成。";

    const topics = Array.isArray(payload.topics) ? payload.topics.slice(0, 5) : [];
    if (!topics.length) {
      list.innerHTML = '<p class="x-intelligence-home-empty">暂无已发布的重点主题。</p>';
      return;
    }

    list.innerHTML = topics.map(function (topic, index) {
      const authors = Array.isArray(topic.authors) ? topic.authors.slice(0, 4) : [];
      const meta = authors.length ? "@" + authors.join(" · @") : "";
      return '<article class="x-intelligence-home-item">' +
        '<span class="x-intelligence-home-rank">' + String(index + 1).padStart(2, "0") + '</span>' +
        '<div>' +
          '<h4><a href="x-intelligence/#topic-' + (index + 1) + '">' + escapeHtml(topic.title || "未命名主题") + '</a></h4>' +
          '<p>' + escapeHtml(topic.summary || "") + '</p>' +
          (meta ? '<small>' + escapeHtml(meta) + '</small>' : '') +
        '</div>' +
      '</article>';
    }).join("");
  }

  load().then(render).catch(function (error) {
    console.error(error);
    updated.textContent = "数据暂时无法载入";
    stats.textContent = "";
    overview.textContent = "X Intelligence 暂时无法载入。";
    list.innerHTML = "";
  });
})();
