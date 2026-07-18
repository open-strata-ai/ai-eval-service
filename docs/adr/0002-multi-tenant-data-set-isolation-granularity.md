# ADR-0002: Multi-tenant dataset isolation granularity

- **Status**: Pending Alignment
- **Date**: 2026-07-17
- **Suggested by**: OpenStrata Architecture Group
- **Repository**: ai-eval-service
- **Source**: `docs/DESIGN.md` §13 Open Issue
- **Association**: `ai-platform-api`

##Context

When sharing `advanced` files across multiple teams, is the data set "tenant-level isolated" or "team/project-level"? Needs to be aligned with the tenant model (§8.1 / §14) of `ai-platform-api`.

## Decision Options (Options Considered)

1. **Maintain status quo / conservative default**: Maintain current behavior, controlled by configuration switches or explicit parameters, and do not introduce destructive changes.
2. **Unified implementation after cross-repository alignment**: Make a clear contract with the relevant service (`ai-platform-api`) before implementation.
3. **Phased introduction**: Leave a placeholder/default switch in the current stage, and solidify it in subsequent stages after the dependent capabilities are ready (see Related Architecture §).

## Recommended decision (Decision)

This ADR solidifies the "multi-tenant data set isolation granularity" into an architectural decision record and incorporates it into `docs/adr/` for continuous tracking. This issue stems from the `docs/DESIGN.md` §13 open issue and is still open.

**Conservative Default Principle**: Before the final decision is made, the "minimum available + explicit configuration switch" shall prevail, maintain the current behavior, and not destroy the existing contract and cross-repository SPI interface; this ADR status will be written back after review by the relevant team.



## To be aligned / Follow-ups (Follow-ups)

- Alignment confirmation with `ai-platform-api`: clarify responsibility boundaries/interface contracts/data flow direction to avoid double writing or semantic drift.
- Associated architecture documents §14 (as a basis for decision-making and a source of consistency verification).
- Associated architecture documents §8.1 (as a basis for decision-making and a source of consistency verification).
- Solidify the decision before the review at the corresponding stage, and write the final conclusion back into this ADR (the status is changed from "Pending" to "Adopted").

## Traceback

- Upstream design: `docs/DESIGN.md` §13 Open issue
- Relevance index: see `docs/adr/README.md`
