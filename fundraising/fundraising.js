(function () {
  const DATA_URL = "../data/crypto-fundraising.json";
  const root = document.querySelector("[data-fundraising-page]");
  const list = document.querySelector("[data-fundraising-list]");
  const updated = document.querySelector("[data-fundraising-updated]");

  if (!root || !list || !updated) {
    return;
  }

  function escapeHtml(value) {
    return String(value)
      .replace(/&/g, "&amp;")
      .replace(/</g, "&lt;")
      .replace(/>/g, "&gt;")
      .replace(/"/g, "&quot;");
  }

  function formatUpdated(value) {
    const date = new Date(value);
    if (Number.isNaN(date.getTime())) {
      return "更新时间暂不可用";
    }
    return `更新：${new Intl.DateTimeFormat("zh-CN", {
      month: "2-digit",
      day: "2-digit",
      hour: "2-digit",
      minute: "2-digit",
      hour12: false,
      timeZone: "Asia/Shanghai",
    }).format(date)}`;
  }

  function formatMonth(value) {
    const match = /^(\d{4})-(\d{2})$/.exec(String(value));
    if (!match) {
      return "日期未披露";
    }
    return `${match[1]}年${Number(match[2])}月`;
  }

  function trimZeros(value, digits) {
    return value.toFixed(digits).replace(/\.?0+$/, "");
  }

  function formatAmount(value) {
    const amount = Number(value);
    if (!Number.isFinite(amount) || amount <= 0) {
      return "金额未披露";
    }
    if (amount >= 100_000_000) {
      return `${trimZeros(amount / 100_000_000, 2)}亿美元`;
    }
    if (amount >= 10_000) {
      return `${trimZeros(amount / 10_000, 1)}万美元`;
    }
    return `${new Intl.NumberFormat("zh-CN").format(amount)}美元`;
  }

  function formatRound(value) {
    if (!value) {
      return "轮次未披露";
    }
    const labels = {
      "Pre-Seed": "种子前轮",
      Seed: "种子轮",
      "Series A": "A轮",
      "Series B": "B轮",
      "Series C": "C轮",
      Strategic: "战略融资",
      "Private Sale": "私募轮",
    };
    return labels[value] || value;
  }

  function validDetailUrl(value) {
    try {
      const url = new URL(value);
      return (
        url.protocol === "https:" &&
        ["crypto-fundraising.info", "www.crypto-fundraising.info"].includes(url.hostname) &&
        url.pathname.startsWith("/projects/")
      );
    } catch (_error) {
      return false;
    }
  }

  function render(projects) {
    list.innerHTML = projects
      .map((project, index) => {
        const detailUrl = validDetailUrl(project.detail_url)
          ? project.detail_url
          : "https://crypto-fundraising.info/";
        return `
          <a
            class="fundraising-project"
            href="${escapeHtml(detailUrl)}"
            target="_blank"
            rel="noreferrer"
            aria-label="查看 ${escapeHtml(project.name)} 的 Crypto-Fundraising 项目详情"
          >
            <span class="fundraising-project-name">
              <span class="fundraising-rank">${String(index + 1).padStart(2, "0")}</span>
              <strong>${escapeHtml(project.name)}</strong>
            </span>
            <span class="fundraising-field fundraising-field-date">
              <small>公布月份</small>
              <strong>${escapeHtml(formatMonth(project.announced_month))}</strong>
            </span>
            <span class="fundraising-field fundraising-field-round">
              <small>融资轮次</small>
              <strong>${escapeHtml(formatRound(project.round))}</strong>
            </span>
            <span class="fundraising-field fundraising-amount">
              <small>融资金额</small>
              <strong>${escapeHtml(formatAmount(project.amount_usd))}</strong>
            </span>
            <span class="fundraising-arrow" aria-hidden="true">↗</span>
          </a>
        `;
      })
      .join("");
  }

  function renderError() {
    root.classList.add("is-error");
    updated.textContent = "数据暂时无法载入";
    list.innerHTML = '<p class="fundraising-error">融资项目暂时无法载入，请稍后重试或查看原始数据。</p>';
  }

  fetch(DATA_URL, { cache: "no-store" })
    .then((response) => {
      if (!response.ok) {
        throw new Error(`Fundraising request failed: ${response.status}`);
      }
      return response.json();
    })
    .then((data) => {
      const projects = Array.isArray(data.projects) ? data.projects.slice(0, 5) : [];
      if (projects.length !== 5 || projects.some((project) => !project.name)) {
        renderError();
        return;
      }
      updated.textContent = formatUpdated(data.updated_at);
      render(projects);
    })
    .catch(renderError);
})();
