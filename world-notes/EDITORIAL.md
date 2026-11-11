# 世界切片发布规则

仓库 aitestforbolin/aitestforbolin-Personal-blog，分支 main，日期使用 Asia/Shanghai。每天 07:30 独立执行，目标 08:30 可读。首期五条为初始化样刊，常态每天一两条。

## 选材

读者希望顺手接触国外日常生活，逐渐形成丰富、准确的世界印象。读者无需提供关键词、维护渠道或完成阅读练习。先逛当地媒体社区、教育、交通、人物版与居民办事说明，再顺线索找公开原文。主要入口可从 GroundUp、The Korea Herald、The Kathmandu Post、Mexico News Daily、当地公共机构、Eurostat、OECD 开始。固定入口仅供发现，遇到新的好来源可继续使用。

每日粗筛约 12 条，全文阅读最有潜力的候选，最多精选两条。优先近几个月的慢内容；旧规则与统计确认仍适用。读近 14 天归档，避免相同事件，质量相近时优先少出现的地区、人群和生活领域。留意普通生活、代价和门槛，给平淡但能增进理解的细节机会。无需冷暖、地区、来源类型的每日配额。

标题讲具体发生什么，正文两三句自然中文，末尾地点、材料日期、证据类型及原文。一个日常细节足以说明一个生活问题即可。读感以第001期澡堂镜面广告、南非送水车、育儿津贴为例。勿为罕见或戏剧性而选稿，勿用抽象结论收尾。统计需要解释多个指标才能明白的题目可以留待专题。

## 事实

搜索摘要提供线索。选入的每项说法都必须读到支持它的原文。区分记者所见、当事人判断、经营者自述和官方规定。个人经历只适用于当事人。全国趋势需统计，义务或权利需当前官方规则。规则与医疗等高影响主张核对可靠原始来源。对因果解释标明是谁的判断。不能读到正文就继续找别的材料。

每个来源 evidence 保存关键段落简述、数据表号或条款位置，便于回查。不要复制全文。日期精确到原文可确认的程度，允许 YYYY-MM。不要把收录日写成素材发布日期。

## 发布

全部远端 GitHub 读写使用 GitHub Connector。开始读取本规则、data/world-notes.json 和 data/world-notes/index.json，按索引读近14天归档。当日归档已存在时验读页面，勿重新选稿或覆盖。

生成请求 data/world-notes-publish-request.json。requestId 使用唯一安全字符标识，payload 的 schemaVersion=1，reportDate=上海当天，items 长度1～2。每条包含 id、title、body、location、materialDate、evidenceType、category（数据/规则/报道/个体）、sources。sources 每项包含 publisher、https url、evidence。id 稳定，推荐日期加主题英文短名。不得设置 initialEdition。

提交后等待 Publish World Notes Action 成功，回读当天归档、最新版和索引，确认 requestId 与条目一致。脚本 scripts/publish_world_notes.py 是结构校验依据。Action 一次提交写入三者，近14天按ID和标题去重。语义事实核验由写稿任务负责。

GitHub Actions 的机器人提交可能不会触发分支模式的 Pages 构建。确认归档成功后，通过 Connector 更新 data/world-notes-deploy-trigger.json，内容为 reportDate、requestId、verifiedAt。该正常提交触发站点构建。若重跑，先查是否已经存在同 requestId 的部署触发与成功的公开页面，避免重复写入。

待公开站点 https://aitestforbolin.github.io/aitestforbolin-Personal-blog/ 的 data/world-notes.json 和 data/world-notes/archive/YYYY-MM-DD.json 回读一致，再在会话返回今日标题和 world-notes/?date=YYYY-MM-DD 链接。未核到公开数据，报告部署待确认并继续检查或安全重试。不能用后台归档成功代替上线确认。

素材不足可发一条。无合格稿时保留上一期日期，会话报告本次无新稿。来源大面积打不开时报告采集失败；程序或部署失败报告具体阶段，继续恢复。更正已发布事实需保留更正说明和版本记录。

首周保留实际启动、上线时间、原文可读性、合格条数与失败原因，观察持续可用性。用户读感反馈用于改进下一期。
