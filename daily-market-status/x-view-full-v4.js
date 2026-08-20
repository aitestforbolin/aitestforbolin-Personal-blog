(function () {
  "use strict";

  const VIEW_HEADING = "04｜看法和观点";

  function buildFullViewSection() {
    const paragraphs = [...document.querySelectorAll("[data-view] p")]
      .map((node) => node.textContent.replace(/\s+/g, " ").trim())
      .filter(Boolean);
    const verdict = document.querySelector("[data-verdict]")?.textContent?.trim() || "";

    const lines = [VIEW_HEADING];
    paragraphs.forEach((paragraph) => lines.push("", paragraph));
    if (verdict) lines.push("", verdict.replace(/^[—–-]\s*/, ""));
    return lines.join("\n");
  }

  function replaceViewSection(text) {
    const source = String(text || "");
    const index = source.indexOf(VIEW_HEADING);
    if (index < 0) return source;
    const prefix = source.slice(0, index).replace(/\s+$/, "");
    return prefix + "\n\n" + buildFullViewSection();
  }

  document.addEventListener(
    "click",
    (event) => {
      const button = event.target.closest?.("[data-copy-x]");
      if (!button || button.disabled) return;

      const clipboard = navigator.clipboard;
      if (!clipboard) return;

      const proto = Object.getPrototypeOf(clipboard);
      const original = proto && proto.writeText;
      if (typeof original !== "function") return;

      let restored = false;
      try {
        proto.writeText = function (text) {
          const fullText = replaceViewSection(text);
          button.copyPayload = fullText;
          return original.call(this, fullText);
        };
      } catch (error) {
        return;
      }

      window.setTimeout(() => {
        if (restored) return;
        restored = true;
        try {
          proto.writeText = original;
        } catch (error) {
          // Keep the page functional if the browser prevents prototype restoration.
        }
      }, 500);
    },
    true
  );
})();
