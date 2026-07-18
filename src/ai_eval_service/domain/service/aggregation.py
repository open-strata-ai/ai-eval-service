from __future__ import annotations

import uuid
from collections import defaultdict

from ai_eval_service.domain.model.report import EvalReport
from ai_eval_service.domain.model.run import EvalRun, Score


def aggregate(
    run: EvalRun,
    scores: list[Score],
    baseline: EvalReport | None = None,
) -> EvalReport:
    """Aggregate per-case scores into a report (mean per metric_key).

    If a baseline report is supplied, compute the regression delta so callers
    can block releases on key-metric rollbacks (§6.3 / §11.2).
    """
    by_metric: dict[str, list[float]] = defaultdict(list)
    for s in scores:
        by_metric[s.metric_key].append(s.value)

    metrics_summary = {
        key: (sum(vals) / len(vals) if vals else 0.0)
        for key, vals in by_metric.items()
    }

    regression_delta: dict[str, float] | None = None
    if baseline is not None:
        regression_delta = {
            key: round(
                metrics_summary.get(key, 0.0) - baseline.metrics_summary.get(key, 0.0),
                6,
            )
            for key in set(metrics_summary) | set(baseline.metrics_summary)
        }

    return EvalReport(
        report_id=f"report-{uuid.uuid4().hex[:12]}",
        run_id=run.run_id,
        baseline_run_id=run.baseline_run_id,
        metrics_summary=metrics_summary,
        regression_delta=regression_delta,
    )
