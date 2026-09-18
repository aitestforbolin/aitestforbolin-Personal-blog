---
name: x-intelligence-publisher
description: Read the canonical 24h X List packet, cluster it into a concise research brief, publish the structured result to the Bolin Brief website, and send a short completion email.
---

# X Intelligence Publisher

## Goal

Generate the weekday X Intelligence briefing from data/x-intelligence-input.json in aitestforbolin/aitestforbolin-Personal-blog main.
Publish the finalized structured briefing to data/x-intelligence.json on main.
GitHub Actions is the collection layer; the scheduled Chat task is the reasoning and publishing layer. Do not re-scrape X or call SocialData from the Chat task.

## Repository and access contract

Repository: aitestforbolin/aitestforbolin-Personal-blog
Branch: main
Required reads: data/x-intelligence-input.json and current data/x-intelligence.json.
Required write: data/x-intelligence.json.
All GitHub reads and writes must use the connected GitHub Connector. Do not use local Git, CLI, shell Git, or another GitHub write path.

## Time contract

Scheduled run: Monday through Friday at 13:00 Asia/Shanghai.
Interpret reportDate in Asia/Shanghai.

## Input hard gates

Require: readable JSON; schemaVersion == 1; listsRequested == 4; listsCompleted == 4; stoppedForBudget == false; posts is an array; stats.uniqueTweetsInWindow == posts.length; generatedAt is present and no more than 6 hours old.
If any gate fails, do not overwrite data/x-intelligence.json. Report the failure in ChatGPT. If Gmail is connected and available, send a short failure email with subject "X Intelligence 未更新" and the specific reason. Never substitute stale data.
An empty posts array is valid only if every other hard gate passes; publish an empty-day briefing rather than inventing topics.

## Evidence contract

Use only the supplied X packet as evidence. Do not browse the web to fill gaps or add outside facts during the scheduled run.
Treat the packet as an information-monitoring feed, not a verified-news database.
Keep source statements, KOL interpretations, and propagation/attention signals distinct. Do not turn an unverified KOL claim into a verified fact.
Interpret Quote Posts together with quoted context when available. Retweets are primarily propagation signals and must not be counted as independent factual sources.
Replies are not automatically noise; keep meaningful new information, disagreement, evidence, or interpretation.
If image/video/link content lacks enough textual context, mark it context-insufficient rather than guessing.

## Analysis contract

Do not summarize tweet by tweet. Cluster Posts into the same underlying events/topics.
Prioritize genuinely new information; multi-account discussion; project/protocol/product changes; financing, partnership, governance, security, token, chain, market-structure and on-chain developments; explicit new KOL theses; macro/market information materially relevant to Web3; weak signals; and meaningful disagreements.
Avoid routine price chatter, generic promotion, repetitive reposts, engagement bait, greetings, and low-information memes unless repetition itself is the signal.

## Output limits

Main topics: 5 to 10 when evidence supports them; never invent topics to reach five.
Watchlist: at most 8.
Disagreements: at most 6.
Noise summary: at most 8 short items.
Order topics by practical research importance. The homepage no longer renders topic cards; it uses homeHighlights only.

## Output JSON contract

Top-level fields must be exactly: schemaVersion, status, reportDate, generatedAt, sourceGeneratedAt, sourcePostCount, sourceListCount, overview, homeHighlights, topics, watchlist, disagreements, noiseSummary.
schemaVersion = 1; status = "success"; reportDate = current Asia/Shanghai YYYY-MM-DD; generatedAt = ISO timestamp with +08:00; sourceGeneratedAt copied from input; sourcePostCount = posts.length; sourceListCount = 4.\nhomeHighlights must be an array of 3 to 5 concise Chinese sentences for the homepage. Each item must contain one distinct information point, with no numeric prefix, no bullet character in the text, and no duplicated wording. Prefer one line each: major regulatory/market shift, major project/ecosystem development, important emerging narrative, and any key counter-signal or divergence. Keep each item compact enough to scan quickly.
Each topics item contains: title, importance (high or medium), summary, whyItMatters, facts, interpretations, authors, sourceUrls, sourceCount, confidence (high, medium, or low).
Each watchlist item contains: signal, reason, authors, sourceUrls.
Each disagreements item contains: topic, positions, sourceUrls.
noiseSummary is an array of short Chinese strings.
All sourceUrls must come from the packet only. Do not write hidden reasoning, credentials, API details, or raw private configuration.

## Publication contract

Read current data/x-intelligence.json only as publication state, not evidence.
Publish only the complete finalized JSON through the GitHub Connector.
After writing, read the remote file back and confirm status == "success", reportDate is today, sourceGeneratedAt equals input generatedAt, and sourcePostCount equals posts.length.
If the GitHub write fails, do not use another write path.

## Chat output

The scheduled Chat result is also a reading surface. Present the same briefing in compact Chinese: date and scan count, overview, numbered main topics, watchlist, disagreements when present, and source links for important topics. Do not reproduce all raw Posts.

## Email notification

After and only after GitHub publication and read-back verification succeed, if Gmail is connected and available, send one short notification email to the user connected Gmail account.
Subject: X Intelligence 已更新｜YYYY-MM-DD
Body: say the briefing is complete, include source Post count and main topic count, and ask the user to open ChatGPT or Bolin Brief. Do not copy the full briefing.
If Gmail is unavailable, do not fail publication; say in Chat that the site update succeeded but email was skipped.
If the briefing fails before publication, send a short failure email when Gmail is available.
