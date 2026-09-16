(function () {
  "use strict";
  const waiting = document.querySelector("[data-brief-waiting]");
  const content = document.querySelector("[data-brief-content]");
  let copyText = "";

  function setText(selector, value) {
    const node = document.querySelector(selector);
    if (node) node.textContent = value == null || value === "" ? "暂不可用" : String(value);
  }

  function format(value, unit) {
    if (value == null || value === "") return "暂不可用";
    const number = typeof value === "number" ? value.toLocaleString("zh-CN", { maximumFractionDigits: 3 }) : String(value);
    return unit && !number.includes(unit.trim()) ? `${number}${unit}` : number;
  }

  function card(className, row) {
    const node = document.createElement("div");
    node.className = className;
    const label = document.createElement("small"); label.textContent = row.label || row.id || "—";
    const value = document.createElement("strong"); value.textContent = format(row.value, row.unit || "");
    const meta = document.createElement("span");
    const change = typeof row.changePercent === "number" ? `${row.changePercent >= 0 ? "+" : ""}${row.changePercent.toFixed(2)}%` : "";
    meta.textContent = [change, row.asOf || row.note || "更新时间未知"].filter(Boolean).join(" · ");
    node.append(label, value, meta);
    return node;
  }

  function render(payload) {
    if (!payload || payload.status !== "ready") {
      waiting.hidden = false;
      content.hidden = true;
      setText("[data-waiting-message]", payload && payload.message ? payload.message : "系统会在白名单事件公布前10—30分钟生成。");
      return;
    }
    waiting.hidden = true;
    content.hidden = false;
    copyText = payload.copyText || "";
    setText("[data-event-title]", payload.event.title);
    setText("[data-event-time]", `${payload.event.scheduledAtLabel} · 距公布约${payload.event.minutesUntilRelease}分钟`);
    setText("[data-event-source]", `${payload.event.source || "来源暂不可用"} · ${payload.event.calendarRetrievedAt || "更新时间未知"}`);
    setText("[data-generated-at]", `生成于 ${payload.generatedAt}`);

    const expectations = document.querySelector("[data-expectations]"); expectations.replaceChildren();
    (payload.event.metrics || []).forEach((row) => {
      const item = document.createElement("div"); item.className = "expectation-row";
      [["指标", row.label], ["预期", format(row.forecast)], ["前值", format(row.previous)]].forEach(([labelText, valueText]) => {
        const cell = document.createElement("div"); const label = document.createElement("span"); const value = document.createElement("strong");
        label.textContent = labelText; value.textContent = valueText; cell.append(label, value); item.append(cell);
      });
      expectations.append(item);
    });

    const assets = document.querySelector("[data-market-assets]"); assets.replaceChildren();
    (payload.market.assets || []).forEach((row) => assets.append(card("market-card", row)));
    const rates = document.querySelector("[data-rates]"); rates.replaceChildren();
    (payload.market.treasuries || []).forEach((row) => rates.append(card("rate-card", row)));
    const fedRoot = document.querySelector("[data-fed-watch]"); fedRoot.replaceChildren(card("fed-card-inner", payload.market.fedWatch || {}));
    const watch = document.querySelector("[data-watch-points]"); watch.replaceChildren();
    (payload.watchPoints || []).forEach((value) => { const li = document.createElement("li"); li.textContent = value; watch.append(li); });
  }

  document.querySelector("[data-copy-brief]")?.addEventListener("click", async (event) => {
    if (!copyText) return;
    await navigator.clipboard.writeText(copyText);
    const button = event.currentTarget; button.textContent = "已复制";
    window.setTimeout(() => { button.textContent = "复制给AI"; }, 1600);
  });

  fetch(`../data/macro-brief.json?v=${Date.now()}`, { cache: "no-store" })
    .then((response) => { if (!response.ok) throw new Error("brief unavailable"); return response.json(); })
    .then(render)
    .catch(() => render({ status: "waiting", message: "Macro Brief暂时无法载入。" }));
})();
