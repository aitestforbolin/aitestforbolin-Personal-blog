(function () {
  "use strict";

  const DATA_URL = "../../data/web3-daily-triage.json";
  const RAW_DATA_URL =
    "https://raw.githubusercontent.com/aitestforbolin/aitestforbolin-Personal-blog/main/data/web3-daily-triage.json";

  const root = document.querySelector("[data-triage-page]");
  if (!root) return;

  function escapeHtml(value) {
    return String(value ?? "")
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function validUrl(value) {
    try {
      const url = new URL(value);
      return ["http:", "https:"].includes(url.protocol) ? url.href : null;
    } catch (_error) {
      return null;
    }
  }

  function formatDate(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "日期待核验";
    return new Intl.DateTimeFormat("zh-CN", {
      year: "numeric",
      month: "long",
      day: "numeric",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Shanghai",
    }).format(date);
  }

  function formatWindow(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) return "时间待核验";
    return new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Shanghai",
    }).format(date);
  }

  function formatAmount(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) return "金额未披露";
    if (amount >= 100000000) return `${(amount / 100000000).toFixed(2).replace(/\.?0+$/, "")} 亿美元`;
    if (amount >= 10000) return `${(amount / 10000).toFixed(1).replace(/\.?0+$/, "")} 万美元`;
    return `${new Intl.NumberFormat("zh-CN").format(amount)} 美元`;
  }

  function financingLine(project) {
    const parts = [formatAmount(project?.financing?.amount_usd)];
    if (project?.financing?.round) parts.push(project.financing.round);
    const leads = Array.isArray(project?.financing?.lead_investors)
      ? project.financing.lead_investors.filter(Boolean)
      : [];
    if (leads.length) parts.push(`领投：${leads.join("、")}`);
    else parts.push("领投：未确认");
    return parts.join(" · ");
  }

  function projectStatus(project) {
    const category = {
      new_unlaunched: "新项目 / 尚未上线",
      new_live_no_token: "新项目 / 已上线未发币",
      existing_no_token: "已有项目 / 未发现已发币",
      existing_token: "已有项目 / 已发币",
      renamed_existing: "改名后的已有项目",
      unclear: "状态不明确",
    }[project?.project_status?.category] || "状态不明确";
    return category;
  }

  function sourceLinks(project) {
    const links = [];
    const website = validUrl(project.website_url);
    const x = validUrl(project.x_url);
    const detail = validUrl(project.source_detail_url);
    if (website) links.push(`<a href="${escapeHtml(website)}" target="_blank" rel="noreferrer">官网 ↗</a>`);
    if (x) links.push(`<a href="${escapeHtml(x)}" target="_blank" rel="noreferrer">官方 X ↗</a>`);
    if (detail) links.push(`<a href="${escapeHtml(detail)}" target="_blank" rel="noreferrer">融资来源 ↗</a>`);
    return links.join("");
  }

  function evidenceLinks(project) {
    const evidence = Array.isArray(project.evidence) ? project.evidence : [];
    return evidence
      .filter((item) => validUrl(item?.url))
      .map((item) => `<a href="${escapeHtml(validUrl(item.url))}" target="_blank" rel="noreferrer">${escapeHtml(item.claim || "来源")} ↗</a>`)
      .join("");
  }

  function renderDetailed(project) {
    const participation = project.participation || {};
    const incentives = project.incentives || {};
    const reasons = Array.isArray(project.why) ? project.why : [];
    const actionLabel = project.decision === "ACTION" ? "建议动作" : "重新检查节点";
    const actionValue =
      project.decision === "ACTION" ? project.next_step : project.recheck_trigger;

    return `<article class="triage-project-card">
      <div class="triage-project-heading">
        <div>
          <span class="triage-badge triage-badge-${escapeHtml(project.decision.toLowerCase())}">${escapeHtml(project.decision)}</span>
          <h3>${escapeHtml(project.project_name)}</h3>
        </div>
        <span class="triage-financing">${escapeHtml(financingLine(project))}</span>
      </div>
      <div class="triage-project-grid">
        <div class="triage-copy-block">
          <small>项目是什么</small>
          <p>${escapeHtml(project.plain_explanation || "未确认")}</p>
        </div>
        <div class="triage-copy-block">
          <small>简单机制</small>
          <p>${escapeHtml(project.mechanism_simple || "未确认")}</p>
        </div>
        <div class="triage-copy-block">
          <small>项目状态</small>
          <p>${escapeHtml(projectStatus(project))}。 ${escapeHtml(project?.project_status?.note || "")}</p>
        </div>
        <div class="triage-copy-block">
          <small>参与机会</small>
          <p>${escapeHtml(participation.what_user_can_do || "当前没有明确的普通用户参与入口。")}
          ${participation.requires_real_funds ? "需要真实资金。" : "当前不要求真实资金。"}
          ${escapeHtml(participation.friction_or_risk || "")}</p>
        </div>
        <div class="triage-copy-block triage-copy-block-wide">
          <small>官方激励</small>
          <p>${escapeHtml(incentives.details || "截至检索时未发现已确认的官方激励。")}</p>
        </div>
        <div class="triage-copy-block triage-copy-block-wide">
          <small>为什么这样判断</small>
          <ul>${reasons.map((reason) => `<li>${escapeHtml(reason)}</li>`).join("")}</ul>
        </div>
      </div>
      ${actionValue ? `<div class="triage-next-step"><small>${actionLabel}</small><strong>${escapeHtml(actionValue)}</strong></div>` : ""}
      <div class="triage-links">${sourceLinks(project)}${evidenceLinks(project)}</div>
    </article>`;
  }

  function renderStop(project) {
    const reasons = Array.isArray(project.why) ? project.why : [];
    const tokenLive = project?.project_status?.token_status === "token_live";
    const reason = reasons[0] || (tokenLive
      ? "原生代币已经正式上线并可交易，按当前规则直接跳过。"
      : "当前没有值得继续投入注意力的普通用户机会。");
    return `<article class="triage-stop-row">
      <div>
        <span class="triage-badge triage-badge-stop">STOP</span>
        <h3>${escapeHtml(project.project_name)}</h3>
      </div>
      <p>${escapeHtml(reason)}</p>
      <div class="triage-links">${sourceLinks(project)}</div>
    </article>`;
  }

  function validate(data) {
    if (!data || data.schemaVersion !== 1 || !Array.isArray(data.projects)) {
      throw new Error("Invalid Web3 Daily Triage payload");
    }
    return data;
  }

  async function fetchPayload(url) {
    const target = new URL(url, window.location.href);
    target.searchParams.set("_", Date.now().toString());
    const response = await fetch(target, { cache: "no-store" });
    if (!response.ok) throw new Error(`HTTP ${response.status}`);
    return validate(await response.json());
  }

  async function load() {
    try {
      return await fetchPayload(DATA_URL);
    } catch (_siteError) {
      return await fetchPayload(RAW_DATA_URL);
    }
  }

  function render(data) {
    const counts = data.counts || {};
    root.querySelector("[data-triage-date]").textContent =
      `发布：${formatDate(data.publishedAt)}`;
    root.querySelector("[data-triage-window]").textContent =
      `候选窗口：${formatWindow(data.windowStart)} → ${formatWindow(data.windowEnd)}`;
    root.querySelector("[data-triage-total]").textContent = Number(counts.new ?? data.projects.length);
    root.querySelector("[data-triage-action]").textContent = Number(counts.action ?? 0);
    root.querySelector("[data-triage-watch]").textContent = Number(counts.watch ?? 0);
    root.querySelector("[data-triage-stop]").textContent = Number(counts.stop ?? 0);
    root.querySelector("[data-triage-note]").textContent = data.deduplicationNote || "";

    const groups = { ACTION: [], WATCH: [], STOP: [] };
    data.projects.forEach((project) => {
      if (groups[project.decision]) groups[project.decision].push(project);
    });

    Object.entries(groups).forEach(([decision, projects]) => {
      const section = root.querySelector(`[data-section="${decision}"]`);
      const list = root.querySelector(`[data-list="${decision}"]`);
      if (!projects.length) {
        section.hidden = true;
        return;
      }
      section.hidden = false;
      list.innerHTML = projects
        .map((project) => decision === "STOP" ? renderStop(project) : renderDetailed(project))
        .join("");
    });

    root.querySelector("[data-triage-empty]").hidden = data.projects.length !== 0;
  }

  load()
    .then(render)
    .catch((error) => {
      console.error(error);
      root.querySelector("[data-triage-error]").hidden = false;
      root.querySelectorAll(".triage-section, .triage-summary, .triage-note").forEach((item) => {
        item.hidden = true;
      });
    });
})();
