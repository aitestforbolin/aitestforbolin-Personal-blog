# 新发现

《新发现》显示在 Bolin Brief 首页最末。正文、原文与往期入口位于 `new-findings/`。所有已公开期次存于 `data/new-findings.json`。首页自动读取首项，数据文件只需更新一次。

## 手动发布

1. 从 `main` 读取当前 `data/new-findings.json`，保存一份作为 `previous.json`。它是公开往期的完整记录。
2. 使用公开来源独立选题。先按实际用途、路径和适用条件查全部往期。同一路径沿用原条目键，无实质变化则跳过。每个条目至少附一条可读原文。活动或机会链接指向官方公告。
3. 在 `editions` 数组最前新增一期。期号用 `YYYY-MM-DD-NN`，同日从 `01` 开始。按阅读顺序放一条主发现和最多四条短讯。原有期次完整保留。
4. 执行 `python3 new-findings/check.py draft.json --previous previous.json`。检查覆盖重复主题键、重复标题、含跟踪参数的同源链接、续报关系和旧期改写。同一来源可支撑不同用途，添加 `why_distinct` 说明。检查工具基于条目键和文字，定稿前继续对照内容的实际用途。
5. 把核实后的草稿写回 `data/new-findings.json`。提交前确认 `main` 上的文件仍与之前读取的版本一致，若有更新先重查。发布后验证首页与详情使用同一期，同时能打开至少一个历史期次。

每条至少包含 `id`、`category`、`title`、`summary`、`evidence` 和 `sources`。原文项使用 `title` 和 `url`。详情为可选的 `details` 文本数组。证据写「官方确认」「多人独立实测」或「单一报告」。有实质变化时，复用条目 `id`，使用 `update_of` 指向该主题上次入选的期号，写清 `what_changed`。

```json
{
  "editions": [
    {
      "id": "2026-01-01-01",
      "date": "2026-01-01",
      "items": [
        {
          "id": "example-new-capability",
          "category": "服务与工具",
          "title": "虚构示例标题",
          "summary": "简述新多了什么选择",
          "evidence": "官方确认",
          "details": ["写明适用条件、成本或期限"],
          "sources": [{"title": "虚构示例来源", "url": "https://example.com/notice"}]
        }
      ]
    }
  ]
}
```

公开数据使用通用适用条件。个人资源和私有试刊仅在各自私有环境中读取。栏目采用手动更新。
