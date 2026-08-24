(function () {
  const root = document.querySelector("[data-home-fundraising]");
  const list = document.querySelector("[data-home-fundraising-list]");
  const updated = document.querySelector("[data-home-fundraising-updated]");

  if (!root || !list || !updated) return;

  const DATA_URL = "data/crypto-fundraising.json";
  const RAW_DATA_URL = "https://raw.githubusercontent.com/aitestforbolin/aitestforbolin-Personal-blog/main/data/crypto-fundraising.json";
  const CACHE_KEY = "bolin.cryptoFundraising.payload.v1";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function validatePayload(data) {
    if (!data || typeof data !== "object") throw new Error("Invalid fundraising payload");
    const projects = Array.isArray(data.projects) ? data.projects.slice(0, 5) : [];
    if (projects.length !== 5 || projects.some((project) => !String(project?.name || "").trim())) {
      throw new Error("Fundraising payload does not contain five valid projects");
    }
    return { ...data, projects };
  }

  async function fetchPayload(value) {
    const url = new URL(value, window.location.href);
    url.searchParams.set("_", Date.now().toString());
    const response = await fetch(url, { cache: "no-store" });
    if (!response.ok) throw new Error(`Fundraising request failed: ${response.status}`);
    return validatePayload(await response.json());
  }

  function saveCache(payload) {
    try {
      localStorage.setItem(CACHE_KEY, JSON.stringify(payload));
    } catch (_error) {
      // Storage can be unavailable in privacy modes; network loading still works.
    }
  }

  function readCache() {
    try {
      const raw = localStorage.getItem(CACHE_KEY);
      return raw ? validatePayload(JSON.parse(raw)) : null;
    } catch (_error) {
      return null;
    }
  }

  async function loadData() {
    const attempts = [
      { url: DATA_URL, mode: "site" },
      { url: RAW_DATA_URL, mode: "github" },
    ];
    const errors = [];

    for (const attempt of attempts) {
      try {
        const payload = await fetchPayload(attempt.url);
        saveCache(payload);
        return { payload, mode: attempt.mode };
      } catch (error) {
        errors.push(error);
      }
    }

    const cached = readCache();
    if (cached) return { payload: cached, mode: "cache" };
    throw new Error(errors.map((error) => error?.message || String(error)).join("; "));
  }

  function formatUpdated(value, mode) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "更新时间暂不可用";
    const suffix = mode === "cache" ? " · 使用上次缓存" : mode === "github" ? " · 备用数据通道" : "";
    return `更新：${new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      hour12: false, timeZone: "Asia/Shanghai",
    }).format(date)}${suffix}`;
  }

  function formatAmount(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) return "金额未披露";
    if (amount >= 100000000) return `${(amount / 100000000).toFixed(2).replace(/\.?0+$/, "")}亿美元`;
    if (amount >= 10000) return `${(amount / 10000).toFixed(1).replace(/\.?0+$/, "")}万美元`;
    return `${new Intl.NumberFormat("zh-CN").format(amount)}美元`;
  }

  function formatRound(value) {
    const labels = { "Pre-Seed": "种子前轮", Seed: "种子轮", "Series A": "A轮", "Series B": "B轮", "Series C": "C轮", Strategic: "战略融资", "Private Sale": "私募轮" };
    return value ? (labels[value] || value) : "轮次未披露";
  }

  function validDetailUrl(value) {
    try {
      const url = new URL(value);
      return url.protocol === "https:" &&
        ["crypto-fundraising.info", "www.crypto-fundraising.info"].includes(url.hostname) &&
        url.pathname.startsWith("/projects/");
    } catch (_error) {
      return false;
    }
  }

  function render(projects) {
    list.innerHTML = projects.map((project, index) => {
      const href = validDetailUrl(project.detail_url) ? project.detail_url : "fundraising/";
      const isNew = project.is_new === true;
      return `<article class="home-fundraising-item">
        <span class="home-fundraising-rank">${String(index + 1).padStart(2, "0")}</span>
        <span class="home-fundraising-project">
          <strong><a href="${escapeHtml(href)}" ${href.startsWith("http") ? 'target="_blank" rel="noreferrer"' : ""}>${escapeHtml(project.name)}</a></strong>
          ${isNew ? '<em class="home-fundraising-new">新！</em>' : ""}
          <small>${escapeHtml(formatRound(project.round))} · ${escapeHtml(formatAmount(project.amount_usd))}</small>
        </span>
        <span class="home-fundraising-actions">
          <button class="home-fundraising-research" type="button" data-research-copy data-prompt-type="initial" data-project-name="${escapeHtml(project.name)}" data-project-url="${escapeHtml(href)}">初筛</button>
          <button class="home-fundraising-research" type="button" data-research-copy data-prompt-type="research" data-project-name="${escapeHtml(project.name)}" data-project-url="${escapeHtml(href)}">研究</button>
        </span>
      </article>`;
    }).join("");

    list.querySelectorAll("[data-research-copy]").forEach((button) => {
      button.addEventListener("click", (event) => {
        event.preventDefault();
        window.BolinResearchPrompt.copyFromButton(button);
      });
    });
  }

  loadData()
    .then(({ payload, mode }) => {
      updated.textContent = formatUpdated(payload.updated_at, mode);
      render(payload.projects);
    })
    .catch((error) => {
      console.error(error);
      updated.textContent = "数据暂时无法载入";
      list.innerHTML = '<p class="home-fundraising-error">融资项目暂时无法载入，请前往融资追踪页查看。</p>';
    });
})();
