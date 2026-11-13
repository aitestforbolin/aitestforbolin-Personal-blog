---
name: cloud-daily-briefing-publisher
description: Generate and publish the daily U.S. market briefing from the market briefing packet with source-verified repair of missing or invalid data when needed, preserving the existing production schema, immutable archive, status contract, and downstream X/email finalization workflow.
---

# Cloud Daily Briefing Publisher

## Goal

Generate the daily market briefing for the latest complete U.S. trading session and publish it to `aitestforbolin/aitestforbolin-Personal-blog` on `main`.

This workflow is intentionally narrow:

- confirm the target completed U.S. trading session;
- read the packet and current status; use a complete packet directly or repair only missing/invalid data from verified sources;
- perform the qualitative research needed to explain the session;
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

The scheduled production task runs once per U.S. trading day, Tuesday through Saturday, at 08:30 Asia/Shanghai. There are no 10:00 or 11:00 scheduled retries. The hard end-to-end deadline is 09:30 Asia/Shanghai: the website briefing and archive must be committed by 09:15 so the existing X publication workflow has time to validate and publish. The automatic X workflow must reach its publish step before 09:25; if it misses that start cutoff, it must fail closed rather than publish late. The canonical run status must show success, including a confirmed X post, before 09:30. Use the latest complete U.S. trading session and the latest valid packet available at execution time.

Determine the latest complete U.S. trading session. Compare it with the currently published `data/daily-market-status.json`.

If there is no unpublished new complete trading session, do not generate another briefing and do not alter the existing briefing/archive.

## No-new-session status

Before writing a no-new-session status, read the existing `main:data/run-status.json`.

If the existing status has the same `runDate` as the current Asia/Shanghai calendar date and the same `asOf` as the target trading session, and any of the following is true:

- `briefingCommit` is non-null;
- `stage` is a downstream stage such as `x` or `email`;
- `status` is already `success` or `no_new_session`;

then treat this as a repeated execution of an already-started or completed daily run. Do not modify `data/run-status.json`, do not alter the briefing or archive, and stop. Preserve the existing downstream/final status exactly as-is.

This idempotency guard exists only to prevent a repeated/manual rerun from overwriting a real downstream result such as `x_publish_failed`. A failed status with `stage = "packet"` and no `briefingCommit` does not authorize later scheduled retries. Complete any targeted repair within the current production run before its publication cutoff.

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

## Packet contract: primary data input with targeted repair

GitHub Actions continues collecting and generating the canonical packet independently. Read:

`market-briefing-data:data/market-briefing-packet.json`

Check the JSON, target `tradingDate`, `validation.complete`, `validation.criticalErrors`, row-level dates, instrument identities and `sourceAudit` timestamps.

### Complete packet: use directly

If the packet matches the latest completed session, is complete, has no critical errors and its required rows pass the data checks, copy its mechanical rows unchanged and proceed to research and writing. Do not recollect good data merely because a newer quote exists: completed-session closes and fixed-time anchors retain their specified observation times.

### Missing, invalid or wrong-session packet: repair within this GPT run

Do not stop merely because the canonical packet is missing, unreadable, stale or incomplete. In the same scheduled GPT run:

1. Make a working copy called the **effective packet**. Keep the original canonical packet and its validation result unchanged. Record the canonical blob/commit SHA when available, generation time and original errors.
2. Identify each missing, erroneous, wrong-date or incompatible row/field using `scripts/build_market_briefing_packet.py` and `scripts/validate_x_snapshot.py` as the data contract (read these files on the repair path). Reuse every independently valid target-session row unchanged. An invalid packet does not make all its rows unusable; an old-session packet does not authorize reuse of old-session numbers for the target session.
3. Actively retrieve only the missing or invalid data through available web research/data tools. Open the underlying source; a search snippet or model memory is not evidence for a numeric field. For a missing/unreadable packet or wrong-session rows, retrieve all required target-session values instead of relabelling old data. GitHub reads/writes still use only the GitHub Connector.
4. Build complete replacement rows in the same schema, keeping provider, symbol, currency/unit, observation time, target date, previous actual trading date and comparison basis. Only deterministic arithmetic (such as change = close - previous close) may be calculated from verified observations. Never infer a quote, breadth count, timestamp or source identity.
5. Recheck all effective-packet requirements and the candidate briefing's pre-commit gate before publication. Unresolved required data remains a failure, not an exception to the quality gate.

Retrieval and comparison rules:

- For the 15 session index/sector rows and candidate stocks, retrieve Yahoo Finance daily history for the same symbols and the target and preceding actual trading sessions. The existing publisher requires `comparisonBasis = "yahoo_daily_history"`; use it only when that history was actually verified. Do not substitute an ETF for an index, a futures contract for a cash index, an intraday quote for a close, or another provider's values under a Yahoo label.
- For DXY, Brent and BTC fixed comparisons, verify both observations at the required 16:00 America/New_York anchors, accounting for daylight saving time. Preserve the same instrument/provider across the pair. A latest quote or futures settlement is not a replacement for that anchor.
- For Treasury yields, use U.S. Treasury official daily observations and the previous available official date, including bond-market holidays; preserve their real dates.
- For breadth, retrieve the same target-session universe and methodology as the packet. A different exchange/universe or an unsupported reconstruction is not a replacement.
- For gold, preserve the established spot/proxy identity and available comparison contract. An explicitly labelled latest quote is allowed only under the existing gold rule and downstream validator; do not invent a fixed-time pair.
- FedWatch still requires its separate paired-observation verification. BTC ETF and future-event fields retain their own observation dates; their informational status must not be presented as a current-session data guarantee. Research a required stale or missing event/ETF field when used, without inventing unpublished source data.

In the briefing's existing `sourceAudit` fields:

- keep the original packet SHA, generation time and trading date truthful;
- record a targeted-repair summary in `fallbackReason`/`note`;
- add every repair source URL to `evidenceUrls`;
- describe each repaired row/field, original problem, replacement values, provider/symbol, observation dates/times and retrieval time in `inconsistencies`;
- use `missingAnchors` truthfully, and disclose approved gold/proxy or source-lag limitations.

The effective packet is a working input for this briefing, not an overwrite of the Actions packet. Do not change the original packet's `validation.complete` flag, write repaired values back to the shared packet branch, or assert that Actions supplied/revalidated model-retrieved values.

Do not use a temporary failure-status commit to request another Actions run as the default repair path. GPT performs targeted retrieval directly. If a newer independently generated canonical packet becomes available, it may be read and checked; do not depend on cron recovery or postpone the work to another GPT invocation.

Complete data retrieval, research, validation and the atomic briefing/archive commit by 09:15 Asia/Shanghai. If the effective packet still cannot satisfy the required checks in time, write only the canonical final failed status, with null publication fields:

- `status = "failed"`;
- `stage = "packet"`;
- `reasonCode = "packet_missing"`, `"packet_wrong_session"` or `"packet_invalid"`, as applicable;
- an actual `updatedAt` in `+08:00`;
- commit prefix `Finalize early market briefing status`.

Preserve any already-started downstream/terminal result under the idempotency rules. The existing 09:30 watchdog and X/email finalization remain unchanged.

## Existing briefing schema is authoritative

Below, **effective packet** means the unchanged canonical packet on the complete path, or its working copy with individually verified repairs on the repair path. Mechanical rows always come from this effective packet; original packet provenance remains distinct from repair provenance.

The current production `main:data/daily-market-status.json` is the schema and formatting contract for the generated briefing. At the start of the run, inspect the packet's `generatedAt` and `sourceAudit` timestamps as well as its `tradingDate`; never silently fall back to an older packet or reuse stale source observations. Qualitative news research must use the latest relevant reporting and official updates available at run time, with publication timestamps checked.

Preserve the existing structure and field semantics. Do not redesign, simplify, rename, remove, or add business fields as part of the scheduled run.

Use the current file only as the structural/template contract and publication-state reference. Do not use stale values from the current file as substitutes for target-session mechanical market data.

The effective packet supplies the target-session numeric/mechanical facts for indices, breadth, sectors, semiconductor index, macro assets, and other packet-covered market fields.

The new immutable archive must be byte-for-byte identical in JSON content to the newly generated current `data/daily-market-status.json`.

## Mechanical data preservation and pre-commit gate

Valid mechanical data must never be summarized, selectively copied, or simplified by the model. Replace missing/invalid fields only through the targeted-repair contract above; preserve all other fields.

For every successful briefing generation:

- build `fallback.markets` by copying the target-session effective-packet rows, preserving every field and value present in the packet;
- for session assets (`SPX`, `IXIC`, `DJI`, `SOX`, `XLK`, `XLY`, `XLC`, `XLV`, `XLU`, `XLP`, `XLE`, `XLI`, `XLB`, `XLRE`, `XLF`), use the corresponding `effectivePacket.markets` row without dropping fields;
- for `DXY`, `BTCUSDT`, `BRN1!`, `US02Y`, `US10Y`, `US30Y`, and `GOLD`, use the corresponding `effectivePacket.macroAssets` row without dropping fields;
- copy `effectivePacket.breadth` into `fallback.breadth` without dropping fields;
- derive `macro24h` and `macroAnchors` only from the effective packet's verified comparison objects and preserve their timing/provenance fields.

The model may add or update qualitative fields such as `drivers`, `events`, `fedProbability`, `view`, `verdict`, and qualitative source-audit notes. It must not rewrite packet-covered mechanical rows into a shorter shape.

`fedProbability` is the single structured source of truth for the briefing's FedWatch probability comparison. Populate its `previous` and `current` values from the same cited research observation. Both values must be finite numbers; `null`, blank, non-numeric, NaN, or infinite values are not allowed. If `view` explicitly states a FedWatch before/after probability transition, those numbers must match `fedProbability.previous` and `fedProbability.current` apart from display rounding. Do not independently retype a different FedWatch pair in prose. Do not publish the briefing/archive until both values and their shared observation/source have been verified. A final failure-status-only commit remains permitted. If a reliable paired observation cannot be verified, fail the pre-commit gate and do not publish a partial briefing or archive.

Gold instrument identity must also be preserved. If the packet uses Yahoo `GC=F` / `GC_FUTURES`, treat it as a COMEX gold-futures proxy for XAU/USD and never label it as XAU/USD spot. Only Swissquote/XAU/USD spot data may be labelled as XAU/USD spot.

Before publishing the briefing/archive, perform a pre-commit structural check on the candidate briefing:

1. all 15 session rows exist;
2. every session row has numeric `price`, `previousClose`, `change`, and `changePercent`;
3. every session row has `priceDate == asOf`;
4. every session row has a string `previousCloseDate` earlier than `priceDate`;
5. every session row has `comparisonBasis == "yahoo_daily_history"`;
6. the candidate's mechanical values and provenance fields match the effective-packet rows; unchanged rows match the canonical packet and every repair has the source audit required above;
7. `fedProbability` is an object with finite numeric `previous` and `current` values from the same cited observation;
8. any explicit FedWatch before/after transition in `view` matches `fedProbability.previous/current`;
9. gold provider/symbol identity is preserved so a futures proxy cannot be presented as spot;
10. the current file and archive candidate are identical.

If any check fails, do not commit the briefing or archive. Write only the canonical failed run status with `stage = "briefing"` and `reasonCode = "briefing_generation_failed"`.

This gate is mandatory even when the visible page would still render correctly from live APIs.

## Research contract

Once the effective packet passes all required data checks, treat its market values as the numeric fact source.

Use web research for qualitative interpretation and event/company verification. On the repair path, also retrieve the specific missing/invalid mechanical data under the targeted-repair contract.

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

Do not re-collect valid packet-covered mechanical data. Targeted retrieval for missing/invalid fields is explicitly permitted; do not repeatedly retry a failing endpoint or let repair consume the publication deadline.

Skip the old global-news briefing workflow entirely.

## Writing contract

Preserve the established daily market briefing style and current JSON schema.

The field `verdict` beginning with `昨日属于：` must be one naturally readable sentence organized as:

`most important driver → market performance → structural judgment/risk`

Use 2–3 connected clauses rather than a stack of jargon.

The rest of the briefing should remain consistent with the current production structure, including existing driver, event, source-audit, market-view, and supporting fields where present in the current schema.

Do not invent company-specific catalysts. If a move is primarily market/sector driven and no reliable company-specific catalyst is found, say so.

Where qualitative sources and effective-packet values differ because of timing, settlement, proxy, rounding, or methodology, preserve the effective packet as the production numeric source and disclose the meaningful discrepancy in the existing audit structure rather than silently replacing packet values.

## Successful publication and immutable archive

Only when:

- a new complete U.S. trading session exists;
- the effective packet passes all required data checks, with verified repair provenance when applicable; and
- the briefing is complete,

generate both:

- `main:data/daily-market-status.json`
- `main:data/daily-market-status/archive/YYYY-MM-DD.json`

Before publishing, confirm that the target archive does not already exist.

Never overwrite an existing archive.

Do not create blank, duplicate, speculative, or partially generated briefings.

The current file and archive must contain the same finalized briefing content.

The atomic website commit must complete no later than 09:15 Asia/Shanghai. Do not publish a partial or stale briefing after this cutoff and describe it as on time.

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

This is a terminal failure for the current daily run and triggers the existing failure notification. There is no later 10:00 or 11:00 scheduled retry. Do not publish a stale, partial, or late briefing to make the run appear successful. Never overwrite an existing archive or a real downstream/final status.

Do not replace an existing `success` or `no_new_session` terminal status for the same run date with `failed`.

If even the status file cannot be safely committed, do not attempt an alternate GitHub write path. Report the failure in ChatGPT; the existing 09:30 watchdog handles missing terminal status.

## Final ChatGPT response

Keep the scheduled-task result short.

State only:

- the target trading session; and
- whether the briefing commit succeeded, or the specific reason it was not published / failed.

Do not report X or email as successful or failed unless that downstream workflow has actually completed; this scheduled task normally stops before that stage.
