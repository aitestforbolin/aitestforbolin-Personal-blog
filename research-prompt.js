(function (global) {
  "use strict";

  const CHATGPT_URL = "https://chatgpt.com/";

  function buildResearchPrompt(project, promptType = "research") {
    const name = String(project?.name || "").trim();
    const sourceUrl = String(project?.sourceUrl || "").trim();
    const type = String(promptType || "research").trim();

    if (!name || !sourceUrl) {
      throw new Error("Project name and source URL are required");
    }

    if (type === "initial") {
      return `初步筛选 ${name}：\n${sourceUrl}\n按 \`01-initial-screening.md\` 执行。`;
    }

    return `深入研究 ${name}：\n${sourceUrl}\n按本项目完整 Web3 Research SOP 执行。`;
  }

  async function copyText(text) {
    if (global.navigator?.clipboard?.writeText) {
      try {
        await global.navigator.clipboard.writeText(text);
        return;
      } catch (_error) {
        // Some embedded browsers expose Clipboard API but block writes.
        // Fall back to the selection-based copy path below.
      }
    }

    const textarea = global.document.createElement("textarea");
    textarea.value = text;
    textarea.setAttribute("readonly", "");
    textarea.style.position = "fixed";
    textarea.style.opacity = "0";
    global.document.body.appendChild(textarea);
    textarea.select();
    const copied = global.document.execCommand("copy");
    textarea.remove();
    if (!copied) throw new Error("Unable to copy research prompt");
  }

  async function handleCopy(button) {
    const originalLabel = button.textContent;
    button.disabled = true;

    try {
      const prompt = buildResearchPrompt(
        {
          name: button.dataset.projectName,
          sourceUrl: button.dataset.projectUrl,
        },
        button.dataset.promptType || "research"
      );
      await copyText(prompt);
      button.textContent = "已复制";
      button.dataset.copyState = "success";
    } catch (error) {
      console.error(error);
      button.textContent = "复制失败，请重试";
      button.dataset.copyState = "error";
    }

    global.setTimeout(() => {
      button.textContent = originalLabel;
      button.disabled = false;
      delete button.dataset.copyState;
    }, 2200);
  }

  global.BolinResearchPrompt = {
    build: buildResearchPrompt,
    chatGptUrl: CHATGPT_URL,
    copyFromButton: handleCopy,
  };
})(globalThis);
