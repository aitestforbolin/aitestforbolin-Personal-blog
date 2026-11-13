# Bolin Brief 个人网站

网站：[aitestforbolin.github.io/aitestforbolin-Personal-blog](https://aitestforbolin.github.io/aitestforbolin-Personal-blog/)

这是一个由静态 HTML、CSS、JavaScript 和 JSON 组成的网站，通过 GitHub Pages 从 `main` 分支根目录发布。前端读取已发布的数据；Python 脚本、GitHub Actions 和 GPT 定时任务负责不同的数据采集与内容生产步骤。

## 页面与数据

| 功能 | 页面或入口 | 主要数据 |
|---|---|---|
| 每日市场早报 | `daily-market-status/` | `data/daily-market-status.json` |
| 盘前宏观简报 | `macro-brief/` | `data/macro-brief.json` |
| 美国宏观基本面 | `us-macro/`，首页 | `data/us-macro-dashboard.json`、`data/us-macro-history.json` |
| 美国宏观日历 | 首页 | `data/macro-calendar.json`，由 `data/us-macro-calendar.json` 转换 |
| AI、云与半导体财报追踪 | 首页 | `data/tech-company-events.json`，公司名单在 `data/tech-company-event-sources.json` |
| BTC ETF 资金流 | 首页、早报 | `data/btc-etf-flow.json` |
| X Intelligence | `x-intelligence/` | `data/x-intelligence.json` |
| 融资追踪与初筛 | `fundraising/`、`fundraising/daily-triage/` | `data/crypto-fundraising.json`、`data/web3-daily-triage.json` |
| 世界切片 | `world-notes/` | `data/world-notes.json` |

首页行情由 `home-market-snapshot.js` 读取现有行情 API。`scripts/update_market_prices.py` 和 `data/market-prices.json` 则服务后台采样、早报 packet 和宏观简报，两者用途不同。

## 生产链路

- **每日早报**：Actions 构建 packet，写入 `market-briefing-data` 分支。GPT 定时任务读取 `.agents/skills/cloud-daily-briefing-publisher/SKILL.md`，使用有效 packet，并按规则补齐、生成和发布早报。下游工作流核验并完成 X / 邮件发布状态。
- **X Intelligence**：GPT 按 `.agents/skills/x-intelligence-publisher/SKILL.md` 写 trigger，collector 收集输入，GPT 生成发布请求，由 `publish-intelligence-request.yml` 原子写入当前内容和当天归档。
- **融资初筛**：遵循 `.agents/skills/daily-financing-triage/SKILL.md`；采集、窗口延续、分级和原子发布相互衔接。直连采集脚本是 bridge 故障时的兜底。
- **世界切片**：GPT 按 `world-notes/EDITORIAL.md` 核验来源和图片，提交发布请求，由 `publish-world-notes.yml` 校验发布。
- **宏观日历**：`fetch_forex_factory_calendar.py` 采集正式数据并核验 FOMC，`merge_macro_calendars.py` 生成前端格式，`update_us_macro_dashboard.py` 更新基本面。旧日历影子对照流程已退役。
- **财报**：只追踪配置中的 21 家公司。更新器仅发现财报链接，区分事件日期、公告日期和回放截止日期，统一换算北京时间，并保留确认级别、日期变化和有效旧数据。Nasdaq 提供补充日程，已核实日程保存在 curated 配置中。

当前计划时间以 `.github/workflows/` 的配置和各 GPT 定时任务设置为准。不要从旧文章日期推断任务时间。

## 日常维护

1. 修改前读取当前 `main`；使用隔离副本验证，通过后提交到 GitHub。
2. 涉及内容发布时遵循对应业务规则，保留当前内容、不可变归档和本次请求的执行回执之间的一致性。
3. 通过 GitHub Pages 的部署结果核验实际上线；部署任务的事件 SHA 与实际 checkout SHA 可能不同，必要时检查构建日志。
4. 保留 `market-briefing-data` 分支。其他旧开发分支应先核对提交关系和开放 PR，再清理。
5. 早报页的“复制正文”和“X 发布”共用一次复制流程；`daily-market-status/x-copy.js` 直接生成长帖，不能再通过改写浏览器剪贴板原型叠加补丁。

## 本地检查

```bash
python -m unittest discover -s tests -p 'test_*.py'
python -m pytest -q tests/test_web3_triage_site.py tests/test_update_market_prices.py
node --test tests/test_macro_calendar_frontend.mjs tests/test_x_copy.mjs
python scripts/update_tech_company_events.py --validate-only
python scripts/merge_macro_calendars.py --validate-only
```

运行线上采集脚本会访问外部来源并更新本地 JSON；普通代码验证应优先使用现有测试和 `--validate-only`。

## 归档与退役记录

- `data/*/archive/` 和 `run-receipts/` 仍参与历史阅读、重复发布检查及执行核验，不能作为无用文件批量删除。
- `briefings/`、`markets/` 是旧版文章归档，保留已有链接。
- `archive/experiments/` 保存退役的联合调度与定时执行测试结果，只作历史记录。
- “欧洲观察”及其采集工作流、旧行情图表、旧 ETF 图表和逐项目研究按钮已退役。
