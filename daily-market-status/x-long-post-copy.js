(function () {
  "use strict";

  const THREAD_SEPARATOR = /\n\n──────────\n\n/g;
  const THREAD_COUNTER = /\n\n\d+\/\d+\s*$/;
  const DISPLAY_TIMEZONE = "Asia/Shanghai";
  const CALENDAR_WINDOW_MS = 48 * 60 * 60 * 1000;

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

  function shanghaiYear() {
    const parts = new Intl.DateTimeFormat("en-CA", {
      timeZone: DISPLAY_TIMEZONE,
      year: "numeric",
    }).formatToParts(new Date());
    return Number(parts.find((part) => part.type === "year")?.value);
  }

  function calendarEventTime(month, day, hour, minute, now) {
    let year = shanghaiYear();
    const build = (targetYear) =>
      new Date(
        `${targetYear}-${String(month).padStart(2, "0")}-${String(day).padStart(2, "0")}T${String(hour).padStart(2, "0")}:${String(minute).padStart(2, "0")}:00+08:00`
      ).getTime();

    let timestamp = build(year);
    if (timestamp < now - 180 * 24 * 60 * 60 * 1000) {
      year += 1;
      timestamp = build(year);
    }
    return timestamp;
  }

  function splitSentences(text) {
    return (String(text || "").match(/[^。！？!?]+[。！？!?]?/g) || [])
      .map((sentence) => sentence.trim())
      .filter(Boolean);
  }

  function sentenceScore(sentence) {
    const strongSignals = sentence.match(/说明|表明|意味着|更像|而不是|因此|主线|结构性|并不|不能|尚未/g) || [];
    const weakSignals = sentence.match(/但|仍|若|接下来|关注|有望|警惕/g) || [];
    let score = strongSignals.length * 8 + weakSignals.length * 2;
    score -= Math.min((sentence.match(/\d/g) || []).length, 10) * 0.5;
    if (sentence.length > 150) score -= 2;
    return score;
  }

  function bestSentence(paragraph) {
    const sentences = splitSentences(paragraph);
    if (!sentences.length) return "";
    return sentences
      .map((sentence, index) => ({ sentence, index, score: sentenceScore(sentence) }))
      .sort((a, b) => b.score - a.score || a.index - b.index)[0].sentence;
  }

  function bestInterpretiveUnit(paragraph) {
    const units = splitSentences(paragraph).flatMap((sentence) => {
      const clauses = sentence
        .split(/；/)
        .map((item) => item.trim())
        .filter(Boolean);
      return clauses.length > 1 ? [sentence, ...clauses] : [sentence];
    });
    if (!units.length) return "";
    return units
      .map((unit, index) => ({ unit, index, score: sentenceScore(unit) }))
      .sort((a, b) => b.score - a.score || a.unit.length - b.unit.length || a.index - b.index)[0].unit
      .replace(/[；\s]+$/, "")
      .replace(/([^。！？!?])$/, "$1。");
  }

  function trimSentence(text, maxLength) {
    const source = String(text || "").trim();
    if (source.length <= maxLength) return source;
    const clipped = source.slice(0, maxLength);
    const boundary = Math.max(
      clipped.lastIndexOf("，"),
      clipped.lastIndexOf("；"),
      clipped.lastIndexOf("。")
    );
    return (boundary >= maxLength * 0.55 ? clipped.slice(0, boundary) : clipped).replace(/[，；。\s]+$/, "") + "。";
  }

  function uniqueNonEmpty(items) {
    const seen = new Set();
    return items.filter((item) => {
      const value = String(item || "").trim();
      if (!value || seen.has(value)) return false;
      seen.add(value);
      return true;
    });
  }

  function conciseConclusion(text) {
    const source = String(text || "")
      .replace(/^[—–-]\s*/, "")
      .replace(/^(昨日属于|今日属于|结论)[:：]\s*/, "")
      .trim();
    if (!source) return "";

    const clauses = source.split(/；/).map((item) => item.trim()).filter(Boolean);
    let chosen = clauses.find((item) => /(更像|而不是|尚未|不能|仍需|警惕)/.test(item));
    if (!chosen) chosen = bestInterpretiveUnit(source) || clauses.at(-1) || source;
    chosen = chosen.replace(/，若.+$/, "").replace(/[。；\s]+$/, "");
    return "结论：" + trimSentence(chosen, 90);
  }

  function buildXViewSummary() {
    const paragraphs = [...document.querySelectorAll("[data-view] p")]
      .map((node) => node.textContent.replace(/\s+/g, " ").trim())
      .filter(Boolean);
    const verdict = document.querySelector("[data-verdict]")?.textContent?.trim() || "";
    if (!paragraphs.length && !verdict) return [];

    const overall = paragraphs.find((text) => /(三大指数|市场宽度|风险偏好|结构性)/.test(text));
    const macroParagraphs = paragraphs.filter((text) => /(财政部|收益率|FOMC|加息|利率|长债)/.test(text));
    const structureParagraphs = paragraphs.filter((text) => /(板块|医疗|科技|芯片|美元|黄金|BTC|油价)/.test(text));
    const outlook = [...paragraphs].reverse().find((text) => /(接下来|Walmart|PMI|若|关注)/.test(text));

    const macroSummary = uniqueNonEmpty(macroParagraphs.slice(0, 2).map(bestInterpretiveUnit)).join("");
    const structureSummary = bestInterpretiveUnit(
      structureParagraphs
        .slice()
        .sort((a, b) => sentenceScore(bestInterpretiveUnit(b)) - sentenceScore(bestInterpretiveUnit(a)))[0] || ""
    );

    const summary = uniqueNonEmpty([
      trimSentence(bestInterpretiveUnit(overall || paragraphs[0]), 125),
      trimSentence(macroSummary, 180),
      trimSentence(structureSummary, 135),
      trimSentence(bestSentence(outlook || paragraphs.at(-1)), 145),
    ]);

    const conclusion = conciseConclusion(verdict);
    if (conclusion) summary.push(conclusion);
    return summary;
  }

  function normalizeLongPost(threadText) {
    const joined = String(threadText || "")
      .split(THREAD_SEPARATOR)
      .map((post) => post.replace(THREAD_COUNTER, "").trim())
      .filter(Boolean)
      .join("\n\n");

    const reasons = driverReasonMap();
    const viewSummary = buildXViewSummary();
    const output = [];
    const now = Date.now();
    const calendarDeadline = now + CALENDAR_WINDOW_MS;
    let inMacro = false;
    let inCalendar = false;
    let inDrivers = false;
    let inView = false;
    let calendarDate = null;
    let calendarDateShown = false;
    let calendarEventCount = 0;
    let calendarHeaderIndex = -1;

    joined.split("\n").forEach((rawLine) => {
      let line = rawLine;

      if (line === "▍细分板块如下") return;

      if (line === "01｜核心个股驱动") {
        inDrivers = true;
        inMacro = false;
        inCalendar = false;
        inView = false;
        output.push("▍核心个股驱动");
        return;
      }

      if (line.startsWith("02｜")) {
        inDrivers = false;
        inMacro = true;
        inCalendar = false;
        inView = false;
        output.push(line);
        return;
      }

      if (line.startsWith("03｜")) {
        inDrivers = false;
        inMacro = false;
        inCalendar = true;
        inView = false;
        calendarHeaderIndex = output.length;
        output.push("03｜日历、事件");
        return;
      }

      if (line.startsWith("04｜")) {
        if (inCalendar && calendarEventCount === 0 && calendarHeaderIndex >= 0) {
          output.push("未来48小时暂无重点事件。");
        }
        inDrivers = false;
        inMacro = false;
        inCalendar = false;
        inView = true;
        output.push("04｜看法和观点");
        if (viewSummary.length) {
          output.push("", ...viewSummary.flatMap((paragraph, index) =>
            index < viewSummary.length - 1 ? [paragraph, ""] : [paragraph]
          ));
        }
        return;
      }

      if (inView) return;

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

      if (inCalendar) {
        if (/^\s*影响[:：]/.test(line)) return;
        const dateMatch = line.replace(/^📅\s*/, "").match(/^(\d{1,2})月(\d{1,2})日｜(.+)$/);
        if (dateMatch) {
          calendarDate = {
            month: Number(dateMatch[1]),
            day: Number(dateMatch[2]),
            label: `${dateMatch[1]}月${dateMatch[2]}日｜${dateMatch[3]}`,
          };
          calendarDateShown = false;
          return;
        }

        const eventMatch = line.match(/^•\s*(\d{1,2}):(\d{2})｜(.+)$/);
        if (eventMatch && calendarDate) {
          const eventTime = calendarEventTime(
            calendarDate.month,
            calendarDate.day,
            Number(eventMatch[1]),
            Number(eventMatch[2]),
            now
          );
          if (eventTime > now && eventTime <= calendarDeadline) {
            if (!calendarDateShown) {
              output.push("", calendarDate.label);
              calendarDateShown = true;
            }
            output.push(`· ${eventMatch[1].padStart(2, "0")}:${eventMatch[2]}｜${eventMatch[3]}`);
            calendarEventCount += 1;
          }
          return;
        }

        if (!line.trim()) return;
      }

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

    if (inCalendar && calendarEventCount === 0 && calendarHeaderIndex >= 0) {
      output.push("未来48小时暂无重点事件。");
    }

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
