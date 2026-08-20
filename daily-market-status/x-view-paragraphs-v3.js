(function () {
  "use strict";

  const VIEW_HEADING = "04｜看法和观点";
  const INTERPRETIVE_SIGNALS = /说明|表明|意味着|更像|而不是|因此|但|仍|若|接下来|关注|有望|警惕|不宜|不能|尚未|主线|风险|修复|分化|压力/;

  function splitSentences(text) {
    return (String(text || "").match(/[^。！？!?]+[。！？!?]?/g) || [])
      .map((sentence) => sentence.trim())
      .filter(Boolean);
  }

  function trimSentence(text, maxLength) {
    const source = String(text || "").replace(/\s+/g, " ").trim();
    if (!source) return "";
    if (source.length <= maxLength) {
      return /[。！？!?]$/.test(source) ? source : source + "。";
    }

    const clipped = source.slice(0, maxLength);
    const boundary = Math.max(
      clipped.lastIndexOf("，"),
      clipped.lastIndexOf("；"),
      clipped.lastIndexOf("。")
    );
    const result = boundary >= Math.floor(maxLength * 0.55)
      ? clipped.slice(0, boundary)
      : clipped;
    return result.replace(/[，；。\s]+$/, "") + "。";
  }

  function sentenceScore(sentence, index) {
    let score = INTERPRETIVE_SIGNALS.test(sentence) ? 12 : 0;
    score += index === 0 ? 2 : 0;
    score -= Math.min((sentence.match(/\d/g) || []).length, 12) * 0.25;
    return score;
  }

  function conciseParagraph(paragraph) {
    const sentences = splitSentences(paragraph);
    if (!sentences.length) return "";
    if (sentences.length === 1) return trimSentence(sentences[0], 125);

    const lead = sentences[0];
    const best = sentences
      .map((sentence, index) => ({ sentence, index, score: sentenceScore(sentence, index) }))
      .sort((a, b) => b.score - a.score || a.index - b.index)[0];

    if (best.index === 0) {
      const second = sentences
        .slice(1)
        .map((sentence, index) => ({ sentence, index: index + 1, score: sentenceScore(sentence, index + 1) }))
        .sort((a, b) => b.score - a.score || a.index - b.index)[0];
      if (second && INTERPRETIVE_SIGNALS.test(second.sentence)) {
        return trimSentence(lead, 72) + trimSentence(second.sentence, 88);
      }
      return trimSentence(lead, 120);
    }

    return trimSentence(lead, 72) + trimSentence(best.sentence, 88);
  }

  function conciseConclusion(text) {
    const source = String(text || "")
      .replace(/^[—–-]\s*/, "")
      .replace(/^(昨日属于|今日属于|结论)[:：]\s*/, "")
      .trim();
    if (!source) return "";

    const sentences = splitSentences(source);
    const chosen = sentences
      .map((sentence, index) => ({ sentence, index, score: sentenceScore(sentence, index) }))
      .sort((a, b) => b.score - a.score || a.index - b.index)[0]?.sentence || source;
    return "结论：" + trimSentence(chosen, 95).replace(/^结论[:：]\s*/, "");
  }

  function buildViewSection() {
    const paragraphs = [...document.querySelectorAll("[data-view] p")]
      .map((node) => node.textContent.replace(/\s+/g, " ").trim())
      .filter(Boolean)
      .map(conciseParagraph)
      .filter(Boolean);

    const verdict = document.querySelector("[data-verdict]")?.textContent?.trim() || "";
    const conclusion = conciseConclusion(verdict);
    const lines = [VIEW_HEADING];

    paragraphs.forEach((paragraph) => {
      lines.push("", paragraph);
    });
    if (conclusion) lines.push("", conclusion);
    return lines.join("\n");
  }

  function replaceViewSection(text) {
    const source = String(text || "");
    const index = source.indexOf(VIEW_HEADING);
    if (index < 0) return source;

    const prefix = source.slice(0, index).replace(/\s+$/, "");
    return prefix + "\n\n" + buildViewSection();
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
          const refined = replaceViewSection(text);
          button.copyPayload = refined;
          return original.call(this, refined);
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
          // Keep the page functional even if the browser prevents restoring the prototype.
        }
      }, 500);
    },
    true
  );
})();
