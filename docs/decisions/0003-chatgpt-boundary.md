# ADR 0003: ChatGPT is a handoff target, not a runtime dependency

## Status
Accepted.

## Context
The owner has existing ChatGPT automations. ChatGPT Plus does not include API
access and third-party apps cannot inject messages into a personal conversation.

## Decision
Provide evidence-grounded copy briefs, Markdown/JSON export and optional Sheets
mirror. Store all decisions in DiscMon. Optional API-based AI is off by default
behind a provider adapter with budget caps and no authority over hard gates.

## Consequences
- Core works offline from ChatGPT.
- No fabricated "ChatGPT webhook".
- Users must paste/export explicitly, or use a separately billed API.
