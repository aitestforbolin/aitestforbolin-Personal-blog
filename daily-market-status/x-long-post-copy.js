(function () {
  "use strict";

  const THREAD_SEPARATOR = /\n\n──────────\n\n/g;
  const THREAD_COUNTER = /\n\n\d+\/\d+\s*$/;

  function normalizeLongPost(threadText) {
    const joined = String(threadText || "")
      .split(THREAD_SEPARATOR)
      .map((post) => post.replace(THREAD_COUNTER, "").trim())
      .filter(Boolean)
      .join("\n\n");

    const output = [];
    let inMacro = false;
    let inCalendar = false;

    joined.split("\n").forEach((line) => {
      if (line.startsWith("02｜")) {
        inMacro = true;
        inCalendar = false;
        output.push(line);
        return;
      }

      if (line.startsWith("03｜")) {
        inMacro = false;
        inCalendar = true;
        output.push("03｜日历、事件");
        return;
      }

      if (line.startsWith("04｜")) {
        inMacro = false;
        inCalendar = false;
        output.push(line);
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

    // The existing handler builds the complete X payload synchronously before its
    // first await. By the time the event bubbles here, copyPayload is available.
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

    // The original async handler may update the status after this listener.
    // Re-assert the long-post result once that microtask has had a chance to finish.
    setLongPostStatus();
    window.setTimeout(setLongPostStatus, 80);
  });
})();
