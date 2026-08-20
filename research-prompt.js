(function (global) {
  "use strict";

  const CHATGPT_URL = "https://chatgpt.com/";

  function buildResearchPrompt(project) {
    const name = String(project?.name || "").trim();
    const sourceUrl = String(project?.sourceUrl || "").trim();

    if (!name || !sourceUrl) {
      throw new Error("Project name and source URL are required");
    }

    return `请以专业 Web3 / Crypto 项目研究员的身份，对以下项目进行深入研究。

项目名称：${name}
融资信息入口：${sourceUrl}

## 研究原则

1. 先确认项目身份、官网和官方文档；若存在同名项目或无法可靠确认身份，先停止并向我提问。
2. 优先使用项目官网、Docs、Whitepaper、官方 Blog、投资机构公告、GitHub、DefiLlama、RootData、CryptoRank、CoinGecko、链上浏览器及可信媒体。
3. 不使用社交媒体帖子作为资料来源。
4. 禁止编造。无法确认的信息写“未确认”或“未找到可靠来源”。
5. 区分可验证事实、项目方主张和研究员推断；推断必须明确标注。
6. 每项关键事实尽量附可点击来源，数据注明截止时间。
7. 资料相互矛盾时并列展示，不要强行合并；旧版本机制和当前版本机制分开。
8. 使用简单直接的中文，不采用项目方营销话术。

## 1. Research Conclusion：先给结论

- 项目本质：一句话说明它到底是什么。
- 普通用户现在能否参与：能 / 不能 / 只能观察；说明入口、步骤和是否需要真实资金。
- 核心机会：为什么现在值得看。
- 核心风险：项目最可能失败在哪里。
- 初步建议：继续研究 / 小额体验 / 暂不参与 / 重点跟踪。
- 下一步动作：给出具体、低风险、可执行的动作。

## 2. Project Snapshot：项目快照

- 项目 TLDR：它通过什么方式，为谁解决什么问题？
- 赛道。
- 核心产品：用户实际使用什么？
- 运作机制：核心机制如何运转，有什么亮点？
- 目标用户：谁会使用，为什么需要？
- 产品阶段：概念、测试网、主网、正式产品或其他阶段。
- 代币与激励：已有代币、发币确认、积分、任务、Season、排行榜或潜在激励；无官方证据时写“未确认”。

## 3. Evidence & Background：融资、团队、数据

### 3.1 融资情况

用表格输出：时间｜类型/轮次｜金额｜领投方｜参投方｜来源｜可信度。
区分股权融资、SAFT、Grant、加速器、合作和生态支持。

### 3.2 团队背景

用表格输出：成员｜职位｜LinkedIn｜GitHub｜关键经历｜验证来源｜身份可信度。
重点检查相关赛道经验、创业/TGE/退出经验、匿名情况、履历缺失和明显负面记录。

### 3.3 数据快照

用表格输出：指标｜当前数据｜变化趋势｜数据截止时间｜来源｜备注。
按项目类型选择 TVL、活跃地址、交易量、收入、用户数、持有人数等；没有可靠数据时不要用营销数字代替。

## 4. Problem & Solution：真实问题

- 用户当前痛点是什么？
- 现有方案为什么不够好？
- 项目给出的解决方案是什么？
- 该问题是真实需求还是叙事包装？证据是什么？

## 5. Mechanism & Structure：产品与机制

- 核心产品：用户使用后实际得到什么？
- 核心机制：项目成立的关键环节是什么？
- 收益与风险：收益从哪里来，风险由谁承担，价值如何转移？
- 商业模式：谁愿意付钱，协议价值沉淀在哪里？
- 关键依赖：依赖哪些外部条件，哪些部分不透明？
- 风险传导：哪个环节断掉会导致项目失败？
- 无补贴验证：没有积分、空投或补贴时，用户是否仍会使用？

## 6. Competitive Positioning：竞品分析

识别 3–6 个最相关项目，区分直接竞品、间接竞品和替代方案。
用表格比较：项目｜竞品类型｜核心定位｜产品形态｜价值来源｜目标用户｜优势｜劣势｜关键差异｜来源。

随后回答：
- 它真正争夺的核心用户是谁？
- 哪些是真正直接竞品，哪些只是看起来相似？
- 各自护城河是什么？
- 用户只能选一个时，为什么选择 A 而不是 B？
- 原项目最可能靠什么胜出，最可能因为什么失败？

## 7. Timing：现在是窗口期吗？

分析项目自身催化、赛道催化、普通用户参与窗口和反向信号。这里只提供证据和研究草案，不替我做最终决定。

## 8. Thesis & Kill Criteria：判断与证伪

分别列出：
- 已验证事实。
- 研究员推断。
- 哪些数据或事件会证明判断成立。
- 哪些情况会证明判断错误。
- 最值得持续跟踪的 3–5 个变量。

## 9. Personal Strategy：留给我确认

请提供参与策略草案，但把“是否参与、资金投入、时间投入、停止条件和下次检查时间”明确标为待我确认，不要替我最终决定。

## 10. Evidence Ledger：证据账本

用表格列出：来源标题｜URL｜发布日期/访问时间｜支持的结论｜来源类型｜可信度。
最后单列：矛盾信息、过期信息、缺失来源和未确认事项。`;
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
      const prompt = buildResearchPrompt({
        name: button.dataset.projectName,
        sourceUrl: button.dataset.projectUrl,
      });
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
