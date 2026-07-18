# ADR-0001: GPU bounds

- **Status**: Pending (Open)
- **Date**: 2026-07-17
- **Suggested by**: OpenStrata Architecture Group
- **Repository**: ai-eval-service
- **Source**: `docs/DESIGN.md` §13 Open Issue
- **Association**: `ai-gateway-core`

##Context

GPU scheduling/quota attribution when benchmarking a local self-hosted model (vLLM) - does the service hold the GPU load directly, or is it always called remotely via `modelServing` from `ai-gateway-core`? (Incline towards the latter, keep this service without GPU hard dependency, §10.2)

## Decision Options (Options Considered)

1. **Maintain status quo / conservative default**: Maintain current behavior, controlled by configuration switches or explicit parameters, and do not introduce destructive changes.
2. **Unified implementation after cross-repository alignment**: Make a clear contract with the relevant service (`ai-gateway-core`) before implementation.
3. **Phased introduction**: Leave a placeholder/default switch in the current stage, and solidify it in subsequent stages after the dependent capabilities are ready (see Related Architecture §).

## Recommended decision (Decision)

This ADR solidifies "GPU boundaries" into architectural decision records and incorporates them into `docs/adr/` for continuous tracking. This issue stems from the `docs/DESIGN.md` §13 open issue and is still open.

**Conservative Default Principle**: Before the final decision is made, the "minimum available + explicit configuration switch" shall prevail, maintain the current behavior, and not destroy the existing contract and cross-repository SPI interface; this ADR status will be written back after review by the relevant team.



## To be aligned / Follow-ups (Follow-ups)

- Alignment confirmation with `ai-gateway-core`: clarify responsibility boundaries/interface contracts/data flow direction to avoid double writing or semantic drift.
- Associated architecture documents §10.2 (as a basis for decision-making and a source of consistency verification).
- Solidify the decision before the review at the corresponding stage, and write the final conclusion back into this ADR (the status is changed from "Pending" to "Adopted").

## Traceback

- Upstream design: `docs/DESIGN.md` §13 Open issue
- Relevance index: see `docs/adr/README.md`
