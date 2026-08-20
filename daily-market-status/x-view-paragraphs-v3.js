(function () {
  "use strict";

  const clipboard = navigator.clipboard;
  if (!clipboard) return;

  const proto = Object.getPrototypeOf(clipboard);
  const originalWriteText = proto && proto.writeText;
  if (typeof originalWriteText !== "function" || originalWriteText.__xFinalFormatter) return;

  const VIEW_HEADING = "04｜看法和观点";
  const DRIVER_HEADING = "▍核心个股驱动";
  const CALENDAR_HEADING = "03｜日历、事件";
  const DISPLAY_TIMEZONE = "Asia/Shanghai";

  function cleanText(value) {
    return String(value || "").replace(/\s+/g, " ").trim();
  }

  function conciseDriverReason(text) {
    let source = cleanText(text)
      .replace(/^公司给出的/, "")
      .replace(/^公司/, "");
    if (!source) return "";

    const firstSentence = source.split(/[。！？!?]/).find(Boolean) || source;
    const clauses = firstSentence
      .split(/[，；]/)
      .map((item) => item.trim())
      .filter(Boolean)
      .filter((item) => !/股价创|单日最大涨幅|直接推动|成为标普.*涨幅|成为.*涨幅个股/.test(item));

    if (!clauses.length) return firstSentence.replace(/[，；。\s]+$/, "") + "。";

    const picked = [];
    let length = 0;
    for (const clause of clauses) {
      const nextLength = length + clause.length + (picked.length ? 1 : 0);
      if (picked.length >= 2 && nextLength > 88) break;
      if (picked.length >= 3) break;
      if (picked.length && nextLength > 96) break;
      picked.push(clause);
      length = nextLength;
    }

    if (picked.length === 1 && clauses.length > 1 && length < 42) {
      picked.push(clauses[1]);
    }

    return picked.join("，").replace(/[，；。\s]+$/, "") + "。";
  }

  function driverReasonMap() {
    const map = new Map();
    document.querySelectorAll(".driver-row").forEach((row) => {
      const nameNode = row.querySelector(".driver-name");
      const reasonNode = row.querySelector("p");
      if (!nameNode || !reasonNode) return;

      const nameClone = nameNode.cloneNode(true);
      nameClone.querySelectorAll("small").forEach((node) => node.remove());
      const ticker = cleanText(nameClone.textContent).split("·").at(-1)?.trim();
      if (!ticker) return;

      const reasonClone = reasonNode.cloneNode(true);
      reasonClone.querySelectorAll("a").forEach((node) => node.remove());
      const reason = conciseDriverReason(reasonClone.textContent);
      if (reason) map.set(ticker, reason);
    });
    return map;
  }

  function replaceDriverReasons(text) {
    const reasons = driverReasonMap();
    if (!reasons.size) return text;

    const lines = String(text || "").split("\n");
    const output = [];
    let inDrivers = false;
    let pendingTicker = "";
    let reasonReplaced = false;

    for (const line of lines) {
      if (line === DRIVER_HEADING) {
        inDrivers = true;
        pendingTicker = "";
        reasonReplaced = false;
        output.push(line);
        continue;
      }
      if (inDrivers && line.startsWith("02｜")) {
        inDrivers = false;
        pendingTicker = "";
        output.push(line);
        continue;
      }

      if (inDrivers) {
        const match = line.match(/^[·•]\s*.+?（([^）]+)）：/);
        if (match) {
          pendingTicker = match[1].trim();
          reasonReplaced = false;
          output.push(line);
          continue;
        }

        if (pendingTicker && line.trim() && !reasonReplaced) {
          const replacement = reasons.get(pendingTicker);
          output.push(replacement || line);
          reasonReplaced = true;
          continue;
        }
      }

      output.push(line);
    }

    return output.join("\n");
  }

  function shanghaiMonthDay() {
    const parts = new Intl.DateTimeFormat("en-US", {
      timeZone: DISPLAY_TIMEZONE,
      month: "numeric",
      day: "numeric",
    }).formatToParts(new Date());
    return {
      month: Number(parts.find((part) => part.type === "month")?.value),
      day: Number(parts.find((part) => part.type === "day")?.value),
    };
  }

  function markTonightCalendar(text) {
    const today = shanghaiMonthDay();
    const lines = String(text || "").split("\n");
    let inCalendar = false;

    return lines.map((line) => {
      if (line === CALENDAR_HEADING) {
        inCalendar = true;
        return line;
      }
      if (inCalendar && line.startsWith("04｜")) {
        inCalendar = false;
        return line;
      }
      if (!inCalendar) return line;

      const match = line.match(/^(?:（今晚）)?(\d{1,2})月(\d{1,2})日｜(.+)$/);
      if (!match) return line;

      const month = Number(match[1]);
      const day = Number(match[2]);
      const label = `${match[1]}月${match[2]}日｜${match[3]}`;
      return month === today.month && day === today.day ? `（今晚）${label}` : label;
    }).join("\n");
  }

  function buildFullViewSection() {
    const paragraphs = [...document.querySelectorAll("[data-view] p")]
      .map((node) => cleanText(node.textContent))
      .filter(Boolean)
      .filter((paragraph) => !/跨资产/.test(paragraph));

    const lines = [VIEW_HEADING];
    paragraphs.forEach((paragraph) => lines.push("", paragraph));
    return lines.join("\n");
  }

  function replaceViewSection(text) {
    const source = String(text || "");
    const index = source.indexOf(VIEW_HEADING);
    if (index < 0) return source;
    const prefix = source.slice(0, index).replace(/\s+$/, "");
    return prefix + "\n\n" + buildFullViewSection();
  }

  function transform(text) {
    return replaceViewSection(markTonightCalendar(replaceDriverReasons(text)));
  }

  function finalWriteText(text) {
    const refined = transform(text);
    const button = document.querySelector("[data-copy-x]");
    if (button) button.copyPayload = refined;
    return originalWriteText.call(this, refined);
  }

  finalWriteText.__xFinalFormatter = true;
  proto.writeText = finalWriteText;
})();
