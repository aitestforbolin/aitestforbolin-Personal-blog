(function () {
  "use strict";

  const root = document.querySelector("[data-x-intelligence-page]");
  if (!root) return;

  const DATA_URL = "../data/x-intelligence.json";
  const RAW_URL = "https://raw.githubusercontent.com/aitestforbolin/aitestforbolin-Personal-blog/main/data/x-intelligence.json";
  const ARCHIVE_BASE_URL = "../data/x-intelligence/archive/";
  const RAW_ARCHIVE_BASE_URL = "https://raw.githubusercontent.com/aitestforbolin/aitestforbolin-Personal-blog/main/data/x-intelligence/archive/";

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
    if (!response.ok) throw new Error("HTTP " + response.status);
    return await response.json();
  }

  async function loadFrom(values) {
    let lastError = null;
    for (const value of values) {
      try {
        return await fetchJson(value);
      } catch (error) {
        lastError = error;
      }
    }
    throw lastError || new Error("No data");
  }

  function loadLatest() {
    return loadFrom([DATA_URL, RAW_URL]);
  }

  function loadArchive(date) {
    const filename = encodeURIComponent(date) + ".json";
    return loadFrom([ARCHIVE_BASE_URL + filename, RAW_ARCHIVE_BASE_URL + filename]);
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "等待首次生成";
    return new Intl.DateTimeFormat("zh-CN", {
      timeZone: "Asia/Shanghai",
      year: "numeric",
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false
    }).format(date);
  }

  function links(urls) {
    if (!Array.isArray(urls) || !urls.length) return "";
    return '<div class="x-topic-sources">' + urls.slice(0, 8).map(function (url, index) {
      return '<a href="' + escapeHtml(url) + '" target="_blank" rel="noreferrer">原帖 ' + (index + 1) + ' ↗</a>';
    }).join("") + '</div>';
  }

  function renderTopics(topics) {
    const node = root.querySelector("[data-x-topics]");
    if (!Array.isArray(topics) || !topics.length) {
      node.innerHTML = '<p class="x-empty">今天没有达到主主题门槛的信息。</p>';
      return;
    }

    node.innerHTML = topics.map(function (topic, index) {
      const facts = Array.isArray(topic.facts) ? topic.facts : [];
      const interpretations = Array.isArray(topic.interpretations) ? topic.interpretations : [];
      const authors = Array.isArray(topic.authors) ? topic.authors : [];

      return '<article class="x-topic" id="topic-' + (index + 1) + '">' +
        '<div class="x-topic-head">' +
          '<h3>' + String(index + 1).padStart(2, "0") + ' · ' + escapeHtml(topic.title || "") + '</h3>' +
          '<div class="x-topic-badges">' +
            '<span class="x-topic-badge">' + escapeHtml(topic.importance === "high" ? "高优先级" : "中优先级") + '</span>' +
            '<span class="x-topic-badge">置信度 ' + escapeHtml(topic.confidence || "—") + '</span>' +
          '</div>' +
        '</div>' +
        '<p class="x-topic-summary">' + escapeHtml(topic.summary || "") + '</p>' +
        (topic.whyItMatters ? '<p class="x-topic-why"><strong>为什么值得看：</strong>' + escapeHtml(topic.whyItMatters) + '</p>' : '') +
        '<div class="x-topic-detail">' +
          (facts.length ? '<div><strong>事实：</strong>' + escapeHtml(facts.join("；")) + '</div>' : '') +
          (interpretations.length ? '<div><strong>KOL 判断：</strong>' + escapeHtml(interpretations.join("；")) + '</div>' : '') +
          (authors.length ? '<div><strong>涉及：</strong>@' + escapeHtml(authors.join(" · @")) + '</div>' : '') +
        '</div>' +
        links(topic.sourceUrls) +
      '</article>';
    }).join("");
  }

  function renderWatchlist(items) {
    const node = root.querySelector("[data-x-watchlist]");
    if (!Array.isArray(items) || !items.length) {
      node.innerHTML = '<p class="x-empty">暂无需要单独保留的弱信号。</p>';
      return;
    }
    node.innerHTML = items.map(function (item) {
      return '<article class="x-compact-card">' +
        '<h3>' + escapeHtml(item.signal || "") + '</h3>' +
        '<p>' + escapeHtml(item.reason || "") + '</p>' +
        links(item.sourceUrls) +
      '</article>';
    }).join("");
  }

  function renderDisagreements(items) {
    const node = root.querySelector("[data-x-disagreements]");
    if (!Array.isArray(items) || !items.length) {
      node.innerHTML = '<p class="x-empty">今天没有明显的观点分歧。</p>';
      return;
    }
    node.innerHTML = items.map(function (item) {
      const positions = Array.isArray(item.positions) ? item.positions : [];
      return '<article class="x-compact-card">' +
        '<h3>' + escapeHtml(item.topic || "") + '</h3>' +
        '<p>' + escapeHtml(positions.join("；")) + '</p>' +
        links(item.sourceUrls) +
      '</article>';
    }).join("");
  }

  function renderNoise(items) {
    const node = root.querySelector("[data-x-noise]");
    if (!Array.isArray(items) || !items.length) {
      node.innerHTML = '<p class="x-empty">无额外噪音摘要。</p>';
      return;
    }
    node.innerHTML = '<ul>' + items.map(function (item) {
      return '<li>' + escapeHtml(item) + '</li>';
    }).join("") + '</ul>';
  }

  const archiveInput = root.querySelector("[data-x-archive-date]");
  const archiveStatus = root.querySelector("[data-x-archive-status]");

  function renderPayload(payload) {
    root.querySelector("[data-x-date]").textContent = formatDate(payload.generatedAt);
    root.querySelector("[data-x-stats]").textContent = payload.status === "success"
      ? "扫描 " + Number(payload.sourcePostCount || 0) + " Posts · " + (payload.topics || []).length + " Topics"
      : "等待 ChatGPT Brief";
    root.querySelector("[data-x-overview]").textContent = payload.overview || "X Intelligence 尚未首次生成。";
    renderTopics(payload.topics);
    renderWatchlist(payload.watchlist);
    renderDisagreements(payload.disagreements);
    renderNoise(payload.noiseSummary);
    if (archiveInput && !archiveInput.value && payload.reportDate) archiveInput.value = payload.reportDate;
  }

  async function showLatest() {
    const payload = await loadLatest();
    renderPayload(payload);
    if (archiveStatus) archiveStatus.textContent = "当前显示最新一期";
  }

  root.querySelector("[data-x-load-date]")?.addEventListener("click", async function () {
    const date = archiveInput?.value;
    if (!date) return;
    if (archiveStatus) archiveStatus.textContent = "正在读取 " + date + "…";
    try {
      const payload = await loadArchive(date);
      renderPayload(payload);
      if (archiveStatus) archiveStatus.textContent = "已载入 " + date + " 存档";
    } catch (error) {
      console.error(error);
      if (archiveStatus) archiveStatus.textContent = date + " 没有可读取的存档";
    }
  });

  root.querySelector("[data-x-latest]")?.addEventListener("click", function () {
    showLatest().catch(function (error) {
      console.error(error);
      if (archiveStatus) archiveStatus.textContent = "最新一期暂时无法载入";
    });
  });

  showLatest().catch(function (error) {
    console.error(error);
    root.querySelector("[data-x-date]").textContent = "数据暂时无法载入";
    root.querySelector("[data-x-stats]").textContent = "";
    root.querySelector("[data-x-overview]").textContent = "X Intelligence 暂时无法载入。";
    renderTopics([]);
    renderWatchlist([]);
    renderDisagreements([]);
    renderNoise([]);
    if (archiveStatus) archiveStatus.textContent = "最新一期暂时无法载入";
  });
})();
