(function () {
  "use strict";

  function normalizeMacroSpacing(text) {
    return String(text || "").replace(
      /^([📉📈—][^：\n]+)：\s*/gm,
      "$1： "
    );
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
          const formatted = normalizeMacroSpacing(text);
          button.copyPayload = formatted;
          return original.call(this, formatted);
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
          // Keep the existing clipboard flow functional if restoration is blocked.
        }
      }, 800);
    },
    true
  );
})();
