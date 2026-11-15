# ADR 0003 — Visual identity: signal orange, status families, IBM Plex

- Status: accepted
- Date: 2026-11-15

## Context
The original amber `#D97732` reads as brown next to deep slate. The product must avoid generic AI-dashboard styling (gradients, purple, emoji, icon-in-a-square KPI cards). It must also meet WCAG 2.2 AA.

## Decision
- Primary action colour `#F07C1F`, with **deep slate text** on it (5.3:1). White on this orange is 2.8:1 and fails AA, so it is not allowed. Orange is never used as a text colour or for statuses.
- Five fixed status families (neutral, active, waiting, success, danger). Each badge is a tint background, a solid dot and slate text, rendered only through `StatusBadge`.
- IBM Plex Sans / Mono, self-hosted via `next/font`. Mono is used for identifiers and numbers.
- The full do-not-use list lives in `CLAUDE.md` §9 "Visual anti-patterns".

## Consequences
- Status meaning never depends on colour alone (label text is always present), which supports colour-blind users.
- Any new status must map to one of the five families. A sixth family needs a new ADR.
