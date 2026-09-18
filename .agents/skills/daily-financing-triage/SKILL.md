---
name: daily-financing-triage
description: Research newly surfaced Web3/Crypto financing projects and classify each as ACTION, WATCH, or STOP for a concise daily review. Use for daily financing triage, not for a full deep-dive investment report.
---

# Daily Financing Triage

## Goal

Turn a newly surfaced Web3/Crypto financing event into a concise, evidence-backed decision on whether it deserves action now, continued monitoring, or no further attention.

This skill is intentionally narrower than a full Web3 research workflow. Do not run full competitive research, full team diligence, or a long-form final report unless explicitly requested.

## Input

Expect at minimum:

- project name;
- financing event URL or source URL;
- any feed metadata already available, such as round, amount, announced month, and `feed_is_new`.

Treat feed metadata as a discovery hint, not as verified truth.

Important: `feed_is_new` means only that the financing item is newly seen in the feed. It does **not** prove that the underlying project is new, unlaunched, untokenized, or not renamed.

## Core questions

For each project, answer only what is necessary to decide whether it deserves the user's attention:

1. What is the project, in plain Chinese?
2. What did it raise, and who led or participated?
3. What does the product actually do? Explain the core mechanism simply, without jargon stacking.
4. Is this truly a new project, or an existing/renamed/already-tokenized project?
5. Can an ordinary user do anything meaningful now?
6. Is there a recent official incentive: points, season, testnet, campaign, rewards, token/airdrop confirmation, or another participation program?
7. Is there a real user need or a credible low-cost early-participation opportunity?
8. Based on utility, timing, cost, risk, and participation quality, should the result be ACTION, WATCH, or STOP?

## Evidence rules

Prefer sources in this order:

1. project website, docs, whitepaper, official blog or product app;
2. project financing announcement and investor/lead-investor announcement;
3. GitHub, chain explorers, DefiLlama, RootData, CryptoRank, CoinGecko, Token Terminal, Crunchbase or similarly relevant structured sources;
4. official X account only for: confirming the official account, very recent launches, points/seasons/testnets/campaigns, token/airdrop announcements, and other time-sensitive official updates.

Do not use community speculation, influencer claims, reply threads, or unofficial X accounts as evidence of an incentive or token plan.

If a material fact cannot be confirmed, mark it `unconfirmed` rather than guessing.

If project identity is ambiguous, stop and return `needs_identity_confirmation` instead of researching the wrong project.

## Research depth

Keep research shallow but sufficient.

Use only the lightweight parts of a normal project-research workflow:

- Project snapshot: what it is, core product, target user, simple mechanism.
- Funding: amount, round, lead/major investors, and confidence.
- Participation: what an ordinary user can do now, whether real funds are required, and approximate friction/risk.
- Timing: current incentive or a concrete reason to act now.

Do not perform a 3-6 competitor matrix, exhaustive team background check, token valuation, or long-form thesis unless the user explicitly asks for a deep dive.

## Decision policy

### ACTION

Use `ACTION` when there is a concrete action worth considering now and the reason is strong enough to justify attention.

A valid ACTION can come from either of two paths:

- **Real utility:** the product solves a real problem for the user and can be tried or used now at acceptable cost/risk.
- **Early-participation asymmetry:** there is a credible early participation window, ecosystem catalyst, or official incentive where small/controlled effort or capital can create meaningful optionality.

ACTION does not require an airdrop. Do not downgrade a useful product merely because token incentives are weak.

ACTION also does not mean "invest heavily". Recommend the smallest sensible validation step, such as trying the app, connecting a read-only wallet, making a small test deposit, or running one complete user flow.

### WATCH

Use `WATCH` when the project is worth retaining but action now is not compelling.

Typical reasons:

- product or mechanism is interesting but PMF is not proven;
- participation exists but reward/cost ratio is weak;
- meaningful participation requires too much capital or risk;
- incentives are late, weak, unclear, or not token-linked;
- an upcoming product launch, chain integration, V2, token milestone, or other catalyst could materially change the decision.

Every WATCH must include a concrete `recheck_trigger`. Avoid vague triggers such as "see how it develops".

### STOP

Use `STOP` when continued attention is not justified at present.

Typical reasons:

- no meaningful ordinary-user participation and no clear future catalyst;
- product is primarily for builders, merchants, institutions, or another audience with no relevant user path;
- it is an old/already-tokenized/renamed project and the new financing event does not create a new opportunity;
- the only thesis is prestige investors, financing size, marketing activity, or vague airdrop speculation;
- the product has no clear user value and no credible early-participation asymmetry.

STOP means "do not spend more research attention now", not "the project is bad".

## Judgment principles learned from historical decisions

Apply these principles consistently:

- Funding size and famous VCs are discovery signals, not decision rules.
- Ask "what can an ordinary user meaningfully do now?" before being impressed by narrative.
- Real personal utility can outweigh weak token expectations.
- Airdrop potential can justify ACTION only when the participation path is credible and cost/risk is controlled.
- High APY alone is weak evidence. Trace where yield comes from and whether the extra risk is worth it.
- Penalize large capital requirements, poor liquidity, opaque incentives, excessive marketing, and crowded/late participation windows.
- Prefer low-friction tests that reveal product quality quickly.
- If the right move is "wait", identify exactly what event would make the project worth checking again.

## Project status classification

Do not use feed freshness as project age. Set one of:

- `new_unlaunched`
- `new_live_no_token`
- `existing_no_token`
- `existing_token`
- `renamed_existing`
- `unclear`

Also record `token_status` separately as `no_token_found`, `token_announced`, `token_live`, or `unconfirmed`.

## Required output

Return one JSON object per project. Do not wrap it in Markdown fences.

Required shape:

{
  "project_name": "string",
  "decision": "ACTION | WATCH | STOP | NEEDS_IDENTITY_CONFIRMATION",
  "financing": {
    "amount_usd": "number|null",
    "round": "string|null",
    "lead_investors": ["string"],
    "announcement_date": "YYYY-MM-DD|null",
    "confidence": "high|medium|low"
  },
  "plain_explanation": "1-2 short Chinese sentences",
  "mechanism_simple": "1-3 short Chinese sentences",
  "project_status": {
    "category": "new_unlaunched|new_live_no_token|existing_no_token|existing_token|renamed_existing|unclear",
    "token_status": "no_token_found|token_announced|token_live|unconfirmed",
    "note": "short Chinese sentence"
  },
  "participation": {
    "available_now": true,
    "what_user_can_do": "string|null",
    "requires_real_funds": true,
    "friction_or_risk": "short Chinese sentence"
  },
  "incentives": {
    "status": "confirmed|none_found|unconfirmed",
    "types": ["points|season|testnet|campaign|airdrop|token|other"],
    "details": "short Chinese sentence"
  },
  "why": ["2-4 concise Chinese reasons"],
  "next_step": "smallest sensible action for ACTION; otherwise null",
  "recheck_trigger": "concrete trigger for WATCH; otherwise null",
  "website_url": "https://...|null",
  "x_url": "https://x.com/...|null",
  "evidence": [
    {
      "claim": "what this source supports",
      "url": "https://...",
      "source_type": "official_site|docs|official_blog|investor|database|official_x|other",
      "confidence": "high|medium|low"
    }
  ]
}

## Output quality checks

Before finalizing:

- Confirm that project identity is correct.
- Confirm financing amount/round/lead investor against at least one credible source when possible.
- Confirm that "new project", "already tokenized", and "renamed" are independent research judgments, not copied from `feed_is_new`.
- For any claimed points/season/testnet/airdrop/token activity, require an official source or mark it unconfirmed.
- Keep `plain_explanation` and `mechanism_simple` understandable to a non-specialist.
- Do not let funding prestige alone produce ACTION.
- ACTION must contain a concrete, controlled next step.
- WATCH must contain a concrete recheck trigger.
- STOP should be concise and should not trigger deeper research automatically.
