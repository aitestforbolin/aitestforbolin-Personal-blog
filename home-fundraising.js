(function () {
  const root = document.querySelector("[data-home-fundraising]");
  const list = document.querySelector("[data-home-fundraising-list]");
  const updated = document.querySelector("[data-home-fundraising-updated]");

  if (!root || !list || !updated) return;

  const DATA_URL = "data/crypto-fundraising.json";

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatUpdated(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "更新时间暂不可用";
    return `更新：${new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit",
      hour12: false, timeZone: "Asia/Shanghai",
    }).format(date)}`;
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
      return `<a class="home-fundraising-item" href="${escapeHtml(href)}" ${href.startsWith("http") ? 'target="_blank" rel="noreferrer"' : ""}>
        <span class="home-fundraising-rank">${String(index + 1).padStart(2, "0")}</span>
        <span class="home-fundraising-project">
          <strong>${escapeHtml(project.name)}</strong>
          ${isNew ? '<em class="home-fundraising-new">新！</em>' : ""}
          <small>${escapeHtml(formatRound(project.round))} · ${escapeHtml(formatAmount(project.amount_usd))}</small>
        </span>
        <span class="home-fundraising-arrow" aria-hidden="true">↗</span>
      </a>`;
    }).join("");
  }

  fetch(DATA_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) throw new Error("Unable to load fundraising data");
      return response.json();
    })
    .then((data) => {
      const projects = Array.isArray(data.projects) ? data.projects.slice(0, 3) : [];
      if (projects.length !== 3 || projects.some((project) => !project.name)) throw new Error("Invalid fundraising data");
      updated.textContent = formatUpdated(data.updated_at);
      render(projects);
    })
    .catch(() => {
      updated.textContent = "数据暂时无法载入";
      list.innerHTML = '<p class="home-fundraising-error">融资项目暂时无法载入，请前往融资追踪页查看。</p>';
    });
})();
