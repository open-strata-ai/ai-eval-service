# ADR-0006: Relationship between Eval SPI and OpenCompass

- **Status**: Pending (Open)
- **Date**: 2026-07-17
- **Suggested by**: OpenStrata Architecture Group
- **Repository**: ai-eval-service
- **Source**: `design/DESIGN.md` §13 Open Issue
- **Association**: (within this repository)

##Context

§10.3 I8 enumerates `EvalEngine → Promptfoo/DeepEval/OpenCompass`, but the `eval` capability of §4.6.2/bom.yaml only contains promptfoo/deepEval/ragas. Whether OpenCompass (model-level evaluation) is included in the Scorer system of this service or is only a `modelServing` side capability requires a decision by the architecture team. ---

## Decision Options (Options Considered)

1. **Maintain status quo / conservative default**: Maintain current behavior, controlled by configuration switches or explicit parameters, and do not introduce destructive changes.
2. **Unified implementation after cross-repository alignment**: Agree on a clear contract with the relevant service (`corresponding governance service`) before implementation.
3. **Phased introduction**: Leave a placeholder/default switch in the current stage, and solidify it in subsequent stages after the dependent capabilities are ready (see Related Architecture §).

## Recommended decision (Decision)

This ADR solidifies the "relationship between Eval SPI and OpenCompass" into an architectural decision record and incorporates it into `design/adr/` for continuous tracking. This issue stems from the `design/DESIGN.md` §13 open issue and is still open.

**Conservative Default Principle**: Before the final decision is made, the "minimum available + explicit configuration switch" shall prevail, maintain the current behavior, and not destroy the existing contract and cross-repository SPI interface; this ADR status will be written back after review by the relevant team.



## To be aligned / Follow-ups (Follow-ups)

- Associated architecture documents §10.3 (as a basis for decision-making and a source of consistency verification).
- Associated architecture documents §4.6.2 (as a basis for decision-making and a source of consistency verification).
- Solidify the decision before the review at the corresponding stage, and write the final conclusion back into this ADR (the status is changed from "Pending" to "Adopted").

## Traceback

- Upstream design: `design/DESIGN.md` §13 Open issue
- Relevance index: see `design/adr/README.md`
