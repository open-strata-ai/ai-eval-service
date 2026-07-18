from __future__ import annotations

from fastapi import APIRouter, HTTPException

from ai_eval_service.di.container import Container
from ai_eval_service.domain.model.dataset import EvalCase
from ai_eval_service.domain.model.run import RunStatus
from ai_eval_service.domain.service.state_machine import IllegalStateTransitionError
from ai_eval_service.interface.schema.views import (
    CaseCreate,
    DatasetCreate,
    ReportView,
    RunCreate,
    RunView,
)


def register_routes(app, container: Container) -> None:
    uc = container.resolve_eval_usecase()
    router = APIRouter(prefix="/v1")

    @router.post("/datasets")
    def create_dataset(body: DatasetCreate):
        ds = uc.create_dataset(
            body.name,
            dataset_id=body.dataset_id,
            split=body.split,
            source=body.source,
            tenant_id=body.tenant_id,
        )
        return ds.model_dump()

    @router.get("/datasets/{dataset_id}")
    def get_dataset(dataset_id: str, version: str = "v1"):
        try:
            return uc.get_dataset(dataset_id, version).model_dump()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/datasets/{dataset_id}/cases")
    def add_case(dataset_id: str, version: str, body: CaseCreate):
        case = EvalCase(
            inputs=body.inputs,
            expected=body.expected,
            contexts=body.contexts,
            tags=body.tags,
        )
        try:
            return uc.add_case(dataset_id, version, case).model_dump()
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/runs", response_model=RunView)
    def create_run(body: RunCreate):
        try:
            run = uc.submit_run(
                body.dataset_id,
                body.dataset_version,
                body.agent,
                body.scorer_set,
                baseline_run_id=body.baseline_run_id,
                split=body.split.value,
                tenant_id=body.agent.tenant_id,
            )
            report = uc.run_eval(run.run_id)
            return _run_view(run, report)
        except IllegalStateTransitionError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=400, detail=str(e))

    @router.get("/runs/{run_id}", response_model=RunView)
    def get_run(run_id: str):
        try:
            return _run_view(uc.get_run(run_id))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/runs/{run_id}/cancel", response_model=RunView)
    def cancel_run(run_id: str):
        try:
            return _run_view(uc.cancel_run(run_id))
        except IllegalStateTransitionError as e:
            raise HTTPException(status_code=409, detail=str(e))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(e))

    @router.post("/runs/{run_id}/score", response_model=ReportView)
    def score_run(run_id: str):
        try:
            return _report_view(uc.score_run(run_id))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/reports/{report_id}", response_model=ReportView)
    def get_report(report_id: str):
        try:
            return _report_view(uc.get_report(report_id))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/runs/{run_id}/report", response_model=ReportView)
    def get_run_report(run_id: str):
        try:
            return _report_view(uc.get_report_for_run(run_id))
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(e))

    @router.get("/reports/{report_id}/export")
    def export_report(report_id: str, fmt: str = "json"):
        try:
            report = uc.get_report(report_id)
        except Exception as e:  # noqa: BLE001
            raise HTTPException(status_code=404, detail=str(e))
        if fmt == "json":
            return report.model_dump()
        if fmt == "md":
            return {"markdown": _to_markdown(report)}
        if fmt == "grafana":
            return {"grafana": report.metrics_summary}
        raise HTTPException(status_code=400, detail=f"unsupported fmt: {fmt}")

    app.include_router(router)


def _run_view(run, report=None) -> RunView:  # type: ignore[no-untyped-def]
    return RunView(
        run_id=run.run_id,
        status=run.status,
        progress=run.progress,
        dataset_id=run.dataset_id,
        dataset_version=run.dataset_version,
        scorer_set=run.scorer_set,
        baseline_run_id=run.baseline_run_id,
    )


def _report_view(report) -> ReportView:  # type: ignore[no-untyped-def]
    return ReportView(
        report_id=report.report_id,
        run_id=report.run_id,
        baseline_run_id=report.baseline_run_id,
        metrics_summary=report.metrics_summary,
        regression_delta=report.regression_delta,
    )


def _to_markdown(report) -> str:  # type: ignore[no-untyped-def]
    lines = [f"# Eval Report `{report.report_id}`", f"- run: {report.run_id}"]
    for k, v in report.metrics_summary.items():
        lines.append(f"- **{k}**: {v}")
    if report.regression_delta:
        lines.append("- regression vs baseline:")
        for k, v in report.regression_delta.items():
            lines.append(f"  - {k}: {v}")
    return "\n".join(lines)
