# ADR-0003: Coupling of Ragas and VectorStore

- **Status**: Pending (Open)
- **Date**: 2026-07-17
- **Suggested by**: OpenStrata Architecture Group
- **Repository**: ai-eval-service
- **Source**: `docs/DESIGN.md` §13 Open Issue
- **Association**: (within this repository)

##Context

RAG evaluation requires retrieving context (§4.6.2 Fidelity/Context Accuracy), is it mandatory that `vectorStore` be lit? How to declare dependency verification with §12.4 (`rag` depends on `memory`/`vectorStore`, evaluate whether it is the same).

## Decision Options (Options Considered)

1. **Maintain status quo / conservative default**: Maintain current behavior, controlled by configuration switches or explicit parameters, and do not introduce destructive changes.
2. **Unified implementation after cross-repository alignment**: Agree on a clear contract with the relevant service (`corresponding governance service`) before implementation.
3. **Phased introduction**: Leave a placeholder/default switch in the current stage, and solidify it in subsequent stages after the dependent capabilities are ready (see Related Architecture §).

## Recommended decision (Decision)

This ADR solidifies the "coupling of Ragas and VectorStore" into an architectural decision record and incorporates it into `docs/adr/` for continuous tracking. This issue stems from the `docs/DESIGN.md` §13 open issue and is still open.

**Conservative Default Principle**: Before the final decision is made, the "minimum available + explicit configuration switch" shall prevail, maintain the current behavior, and not destroy the existing contract and cross-repository SPI interface; this ADR status will be written back after review by the relevant team.



## To be aligned / Follow-ups (Follow-ups)

- Associated architecture documents §12.4 (as a basis for decision-making and a source of consistency verification).
- Associated architecture documents §4.6.2 (as a basis for decision-making and a source of consistency verification).
- Solidify the decision before the review at the corresponding stage, and write the final conclusion back into this ADR (the status is changed from "Pending" to "Adopted").

## Traceback

- Upstream design: `docs/DESIGN.md` §13 Open issue
- Relevance index: see `docs/adr/README.md`
