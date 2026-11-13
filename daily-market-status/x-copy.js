(function (global) {
  "use strict";

  const TIMEZONE = "Asia/Shanghai";
  const WINDOW_MS = 48 * 60 * 60 * 1000;
  const clean = (text) => String(text || "").replace(/\s+/g, " ").trim();

  function conciseDriverReason(text) {
    const source = clean(text).replace(/^公司给出的/, "").replace(/^公司/, "");
    if (!source) return "";
    const sentence = source.split(/[。！？!?]/).find(Boolean) || source;
    const clauses = sentence.split(/[，；]/).map(clean).filter(Boolean)
      .filter((clause) => !/股价创|单日最大涨幅|直接推动|成为标普.*涨幅|成为.*涨幅个股/.test(clause));
    if (!clauses.length) return sentence.replace(/[，；。\s]+$/, "") + "。";
    const picked = [];
    let length = 0;
    for (const clause of clauses) {
      const next = length + clause.length + (picked.length ? 1 : 0);
      if ((picked.length >= 2 && next > 88) || picked.length >= 3 || (picked.length && next > 96)) break;
      picked.push(clause);
      length = next;
    }
    if (picked.length === 1 && clauses.length > 1 && length < 42) picked.push(clauses[1]);
    return picked.join("，").replace(/[，；。\s]+$/, "") + "。";
  }

  function formatMacroLine(line) {
    return String(line).replace(
      /^(📉|📈|—)(.+?)(?:：)?\s*([+−-]?\d[\d,.]*%?)\s*→\s*([+−-]?\d[\d,.]*%?)\s*$/u,
      (_, icon, label, from, to) => `${icon}${label.trim()}： ${from} → ${to}`
    );
  }

  function formatBreadthLine(line) {
    const match = String(line).match(/^•\s*(标普500|Nasdaq交易所)：涨([\d,]+)｜跌([\d,]+)｜平([\d,]+)｜([\d.]+)%上涨$/);
    if (!match) return line;
    const [, label, up, down, flat, percent] = match;
    return `· ${label}：${percent}%上涨（涨${up}｜跌${down}｜平${flat}）`;
  }

  function calendarLines(events, now) {
    const dayFormat = new Intl.DateTimeFormat("zh-CN", {timeZone: TIMEZONE, month: "long", day: "numeric"});
    const weekFormat = new Intl.DateTimeFormat("zh-CN", {timeZone: TIMEZONE, weekday: "short"});
    const clockFormat = new Intl.DateTimeFormat("zh-CN", {timeZone: TIMEZONE, hour: "2-digit", minute: "2-digit", hour12: false});
    const today = dayFormat.format(now);
    const selected = (events || []).map((event) => ({...event, time: new Date(event.startAt).getTime()}))
      .filter((event) => Number.isFinite(event.time) && event.time > now && event.time <= now + WINDOW_MS)
      .sort((a, b) => a.time - b.time);
    if (!selected.length) return ["未来48小时暂无重点事件。"];
    const lines = [];
    let previousDay = "";
    for (const event of selected) {
      const day = dayFormat.format(event.time);
      if (day !== previousDay) {
        lines.push("", `${day === today ? "（今晚）" : ""}${day}｜${weekFormat.format(event.time)}`);
        previousDay = day;
      }
      lines.push(`· ${clockFormat.format(event.time)}｜${event.name}`);
    }
    return lines;
  }

  function build(input) {
    const now = Number(input.now ?? Date.now());
    const lines = [input.title, "", "01｜美股", "", "▍三大核心指数", ...(input.indexLines || []),
      "", "▍市场宽度", ...(input.breadthLines || []).map(formatBreadthLine)];
    if (input.drivers?.length) {
      lines.push("", "▍核心个股驱动", "");
      for (const driver of input.drivers) {
        lines.push(`· ${driver.name}（${driver.ticker}）：${driver.change}`);
        const reason = conciseDriverReason(driver.reason);
        if (reason) lines.push(reason);
        lines.push("");
      }
    }
    lines.push("", "02｜宏观资产数据（美股交易时段变化）", "", ...(input.macroLines || []).map(formatMacroLine),
      "", "03｜日历、事件", ...calendarLines(input.events, now));
    const view = (input.view || []).map(clean).filter(Boolean).filter((paragraph) => !/跨资产/.test(paragraph));
    if (view.length || input.verdict) {
      lines.push("", "04｜看法和观点");
      for (const paragraph of view.length ? view : [clean(input.verdict)]) lines.push("", paragraph);
    }
    return lines.join("\n").replace(/\n{3,}/g, "\n\n").trim();
  }

  async function copy(text, environment = global) {
    if (environment.navigator?.clipboard?.writeText) {
      try {
        await environment.navigator.clipboard.writeText(text);
        return;
      } catch (error) {
        // Clipboard permissions can be unavailable in embedded or local pages.
      }
    }
    const document = environment.document;
    const active = document.activeElement;
    const textarea = document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.setAttribute("aria-hidden", "true");
    textarea.style.position = "fixed";
    textarea.style.left = "-9999px";
    document.body.appendChild(textarea);
    try {
      textarea.focus();
      textarea.select();
      textarea.setSelectionRange(0, text.length);
      if (!document.execCommand("copy")) throw new Error("Clipboard copy failed");
    } finally {
      textarea.remove();
      active?.focus?.();
    }
  }

  global.BolinXCopy = Object.freeze({build, copy, conciseDriverReason, formatMacroLine});
})(globalThis);
