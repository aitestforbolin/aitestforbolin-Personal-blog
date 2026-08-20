(function () {
  "use strict";

  const THREAD_SEPARATOR = /\n\n──────────\n\n/g;
  const THREAD_COUNTER = /\n\n\d+\/\d+\s*$/;

  function conciseReason(text) {
    const source = String(text || "").replace(/\s+/g, " ").trim();
    if (!source) return "";
    const firstClause = source.split(/[，；。]/).find(Boolean) || source;
    return firstClause
      .replace(/^公司给出的/, "")
      .replace(/^公司/, "")
      .trim() + "。";
  }

  function driverReasonMap() {
    const map = new Map();
    document.querySelectorAll(".driver-row").forEach((row) => {
      const nameNode = row.querySelector(".driver-name");
      const reasonNode = row.querySelector("p");
      if (!nameNode || !reasonNode) return;

      const nameClone = nameNode.cloneNode(true);
      nameClone.querySelectorAll("small").forEach((node) => node.remove());
      const nameText = nameClone.textContent.replace(/\s+/g, " ").trim();
      const ticker = nameText.split("·").at(-1)?.trim();
      if (!ticker) return;

      const reasonClone = reasonNode.cloneNode(true);
      reasonClone.querySelectorAll("a").forEach((node) => node.remove());
      const reason = conciseReason(reasonClone.textContent);
      if (reason) map.set(ticker, reason);
    });
    return map;
  }

  function formatBreadthLine(line) {
    const match = line.match(
      /^•\s*(标普500|Nasdaq交易所)：涨([\d,]+)｜跌([\d,]+)｜平([\d,]+)｜([\d.]+)%上涨$/
    );
    if (!match) return line;
    const [, label, advancers, decliners, unchanged, percent] = match;
    return `· ${label}：${percent}%上涨（涨${advancers}｜跌${decliners}｜平${unchanged}）`;
  }

  function normalizeLongPost(threadText) {
    const joined = String(threadText || "")
      .split(THREAD_SEPARATOR)
      .map((post) => post.replace(THREAD_COUNTER, "").trim())
      .filter(Boolean)
      .join("\n\n");

    const reasons = driverReasonMap();
    const output = [];
    let inMacro = false;
    let inCalendar = false;
    let inDrivers = false;

    joined.split("\n").forEach((rawLine) => {
      let line = rawLine;

      if (line === "01｜核心个股驱动") {
        inDrivers = true;
        inMacro = false;
        inCalendar = false;
        output.push("▍核心个股驱动");
        return;
      }

      if (line.startsWith("02｜")) {
        inDrivers = false;
        inMacro = true;
        inCalendar = false;
        output.push(line);
        return;
      }

      if (line.startsWith("03｜")) {
        inDrivers = false;
        inMacro = false;
        inCalendar = true;
        output.push("03｜日历、事件");
        return;
      }

      if (line.startsWith("04｜")) {
        inDrivers = false;
        inMacro = false;
        inCalendar = false;
        output.push(line);
        return;
      }

      if (line.startsWith("• 标普500：") || line.startsWith("• Nasdaq交易所：")) {
        output.push(formatBreadthLine(line));
        return;
      }

      if (inDrivers && /^•\s*/.test(line)) {
        const displayLine = line.replace(/^•\s*/, "· ");
        output.push(displayLine);
        const ticker = line.match(/（([^）]+)）/)?.[1]?.trim();
        const reason = ticker ? reasons.get(ticker) : "";
        if (reason) output.push(reason, "");
        return;
      }

      if (inCalendar && /^\s*影响[:：]/.test(line)) return;

      if (inMacro && line.includes("｜")) {
        line
          .split("｜")
          .map((item) => item.trim())
          .filter(Boolean)
          .forEach((item) => output.push(item));
        return;
      }

      output.push(line);
    });

    return output.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  function fallbackCopy(text) {
    const textarea = document.createElement("textarea");
    const activeElement = document.activeElement;
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.setAttribute("aria-hidden", "true");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    textarea.style.top = "0";
    document.body.appendChild(textarea);
    textarea.focus();
    textarea.select();
    textarea.setSelectionRange(0, textarea.value.length);
    const copied = document.execCommand("copy");
    textarea.remove();
    if (activeElement && typeof activeElement.focus === "function") {
      activeElement.focus();
    }
    return copied;
  }

  function setLongPostStatus() {
    const status = document.querySelector("[data-copy-status]");
    if (!status) return;
    status.textContent = "已复制 1 篇 X 长帖";
    status.dataset.level = "success";
  }

  document.addEventListener("click", (event) => {
    const button = event.target.closest?.("[data-copy-x]");
    if (!button || button.disabled) return;

    const threadText = button.copyPayload;
    if (!threadText) return;

    const longPost = normalizeLongPost(threadText);
    if (!longPost) return;
    button.copyPayload = longPost;

    const fallbackSucceeded = fallbackCopy(longPost);
    if (navigator.clipboard && typeof navigator.clipboard.writeText === "function") {
      navigator.clipboard.writeText(longPost).catch(() => {
        if (!fallbackSucceeded) setLongPostStatus();
      });
    }

    setLongPostStatus();
    window.setTimeout(setLongPostStatus, 80);
  });
})();
