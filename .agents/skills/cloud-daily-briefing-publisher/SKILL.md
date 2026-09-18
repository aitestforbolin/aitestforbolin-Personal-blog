---
name: cloud-daily-briefing-publisher
description: Generate and publish the daily U.S. market briefing from the validated market briefing packet, preserving the existing production schema, immutable archive, status contract, and downstream X/email finalization workflow.
---

# Cloud Daily Briefing Publisher

## Goal

Generate the daily market briefing for the latest complete U.S. trading session and publish it to `aitestforbolin/aitestforbolin-Personal-blog` on `main`.

This workflow is intentionally narrow:

- confirm the target completed U.S. trading session;
- read the validated packet and current status;
- perform only the qualitative research needed to explain the session;
- generate the briefing in the existing production data structure;
- atomically publish the current briefing plus immutable archive when a new briefing is ready;
- otherwise write only the canonical early run status;
- stop after the briefing commit and leave X publication, final run-status finalization, and email notification to the existing GitHub workflow.

Do not modify the existing business logic, data structure, repository paths, packet validation rules, archive rules, or downstream X/email workflow.

## Repository and access contract

Repository: `aitestforbolin/aitestforbolin-Personal-blog`

Production branch: `main`

Packet branch: `market-briefing-data`

Required files:

- `main:data/daily-market-status.json`
- `main:data/run-status.json`
- `market-briefing-data:data/market-briefing-packet.json`

Successful briefing publication writes:

- `main:data/daily-market-status.json`
- `main:data/daily-market-status/archive/YYYY-MM-DD.json`

All repository reads and writes must use the GitHub Connector. Do not use local Git, shell Git, CLI, direct unauthenticated GitHub writes, or any other GitHub write path.

When an atomic commit is required, use the GitHub Connector's Git Data operations so the current briefing and archive are committed together.

## Time and target session

Use `Asia/Shanghai` for the scheduled run and run-date interpretation.

The scheduled production run is Tuesday through Saturday at 07:00 Asia/Shanghai.

Determine the latest complete U.S. trading session. Compare it with the currently published `data/daily-market-status.json`.

If there is no unpublished new complete trading session, do not generate another briefing and do not alter the existing briefing/archive.

## No-new-session status

Before writing a no-new-session status, read the existing `main:data/run-status.json`.

If the existing status has the same `runDate` as the current Asia/Shanghai calendar date and the same `asOf` as the target trading session, and any of the following is true:

- `briefingCommit` is non-null;
- `stage` is a downstream stage such as `x` or `email`;
- `status` is already `success` or `no_new_session`;

then treat this as a repeated execution of an already-started or completed daily run. Do not modify `data/run-status.json`, do not alter the briefing or archive, and stop. Preserve the existing downstream/final status exactly as-is.

This idempotency guard exists only to prevent a repeated/manual rerun from overwriting a real downstream result such as `x_publish_failed`. It does not change the normal first-run behavior at 07:00.

When there is no unpublished new complete trading session and the idempotency guard above does not apply, update only `main:data/run-status.json`:

- `schemaVersion = 1`
- `runDate` = current calendar date in Asia/Shanghai
- `asOf` = current latest complete U.S. trading session
- `status = "no_new_session"`
- `stage = "done"`
- `briefingCommit = null`
- `xPostId = null`
- `xPostUrl = null`
- `reasonCode = "already_current"`

If it can be clearly determined that the U.S. market was closed because of a weekend or market holiday, use `reasonCode = "market_closed"` instead.

`updatedAt` must be an ISO timestamp with `+08:00`.

The commit message must start with:

`Finalize early market briefing status`

Then stop. The ChatGPT result should state the reason briefly.

Do not overwrite an already-existing terminal `success` or `no_new_session` status for the same run date with a failure.

## Packet contract: sole mechanical market-data input

The packet is the sole input for mechanical market data.

Read:

`market-briefing-data:data/market-briefing-packet.json`

Hard gate requirements:

1. the JSON is readable;
2. `tradingDate` equals the target trading session;
3. `validation.complete == true`;
4. `criticalErrors` is empty.

If any hard gate fails, do not rebuild, backfill, infer, splice across dates, or re-scrape packet-covered mechanical market data from Yahoo Finance, U.S. Treasury, Swissquote, TradingView, personal-site APIs, or other quote endpoints.

Instead update only `main:data/run-status.json`:

- `status = "failed"`
- `stage = "packet"`
- use the appropriate `reasonCode`:
  - `packet_missing`
  - `packet_wrong_session`
  - `packet_invalid`

All other status fields follow the canonical status contract above, with the target session in `asOf`, null publication fields, and `updatedAt` in `+08:00`.

The commit message must start with:

`Finalize early market briefing status`

Then stop.

## Existing briefing schema is authoritative

The current production `main:data/daily-market-status.json` is the schema and formatting contract for the generated briefing.

Preserve the existing structure and field semantics. Do not redesign, simplify, rename, remove, or add business fields as part of the scheduled run.

Use the current file only as the structural/template contract and publication-state reference. Do not use stale values from the current file as substitutes for target-session mechanical market data.

The packet supplies the target-session numeric/mechanical facts for indices, breadth, sectors, semiconductor index, macro assets, and other packet-covered market fields.

The new immutable archive must be byte-for-byte identical in JSON content to the newly generated current `data/daily-market-status.json`.

## Research contract

When the packet passes validation, treat its market values as the numeric fact source.

Use web research only for qualitative interpretation and event/company verification needed to write the briefing.

Preferred sources:

- Reuters;
- AP;
- company announcements / investor relations;
- regulators and other first-party official sources.

Use qualitative research to:

- explain the main market drivers;
- verify company-level narratives;
- identify relevant near-term catalysts/events;
- form the written market view.

Do not re-collect packet-covered prices, yields, breadth, gold, indices, sector values, or other mechanical fields from the web.

Do not retry quote APIs that the packet builder already covers.

Skip the old global-news briefing workflow entirely.

## Writing contract

Preserve the established daily market briefing style and current JSON schema.

The field `verdict` beginning with `昨日属于：` must be one naturally readable sentence organized as:

`most important driver → market performance → structural judgment/risk`

Use 2–3 connected clauses rather than a stack of jargon.

The rest of the briefing should remain consistent with the current production structure, including existing driver, event, source-audit, market-view, and supporting fields where present in the current schema.

Do not invent company-specific catalysts. If a move is primarily market/sector driven and no reliable company-specific catalyst is found, say so.

Where qualitative sources and packet values differ because of timing, settlement, proxy, rounding, or methodology, preserve the packet as the production numeric source and disclose the meaningful discrepancy in the existing audit structure rather than silently replacing packet values.

## Successful publication and immutable archive

Only when:

- a new complete U.S. trading session exists;
- the packet passes all hard gates; and
- the briefing is complete,

generate both:

- `main:data/daily-market-status.json`
- `main:data/daily-market-status/archive/YYYY-MM-DD.json`

Before publishing, confirm that the target archive does not already exist.

Never overwrite an existing archive.

Do not create blank, duplicate, speculative, or partially generated briefings.

The current file and archive must contain the same finalized briefing content.

Publish both in one atomic commit through the GitHub Connector Git Data API, then confirm the commit succeeded.

## Handoff to downstream X and email workflow

After the successful atomic briefing commit, stop immediately.

Do not:

- wait for or inspect GitHub Actions;
- read `data/x-publish-log.json`;
- publish to X directly;
- send Gmail/iCloud email directly;
- write `data/run-status.json` again after the successful briefing commit.

The existing GitHub workflow named `Finalize daily market briefing` is responsible for downstream X publication, canonical run-status finalization, and email notification.

The briefing task must not duplicate or compete with that workflow.

## Briefing-generation or commit failure

If writing/generation or the briefing commit unexpectedly fails, and it is still safe to commit only the canonical status file, update only `main:data/run-status.json`:

- `status = "failed"`
- `stage = "briefing"` with `reasonCode = "briefing_generation_failed"`, or
- `stage = "commit"` with `reasonCode = "briefing_commit_failed"`.

The commit message must start with:

`Finalize early market briefing status`

Do not replace an existing `success` or `no_new_session` terminal status for the same run date with `failed`.

If even the status file cannot be safely committed, do not attempt an alternate GitHub write path. Report the failure in ChatGPT; the existing 07:30 watchdog handles missing terminal status.

## Final ChatGPT response

Keep the scheduled-task result short.

State only:

- the target trading session; and
- whether the briefing commit succeeded, or the specific reason it was not published / failed.

Do not report X or email as successful or failed unless that downstream workflow has actually completed; this scheduled task normally stops before that stage.
