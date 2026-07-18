from __future__ import annotations

from ai_eval_service.domain.model.dataset import EvalDataset, EvalCase
from ai_eval_service.domain.model.report import EvalReport
from ai_eval_service.domain.model.run import EvalRun, Score
from ai_eval_service.domain.port.repository import EvalRepositoryPort


class InMemoryEvalRepository:
    """Offline reference repository (no external store). Used for tests/e2e."""

    def __init__(self) -> None:
        self._datasets: dict[tuple[str, str], EvalDataset] = {}
        self._runs: dict[str, EvalRun] = {}
        self._scores: dict[str, list[Score]] = {}
        self._reports: dict[str, EvalReport] = {}
        self._run_to_report: dict[str, str] = {}

    def save_dataset(self, dataset: EvalDataset) -> None:
        self._datasets[(dataset.dataset_id, dataset.version)] = dataset

    def load_dataset(self, dataset_id: str, version: str) -> EvalDataset:
        ds = self._datasets.get((dataset_id, version))
        if ds is None:
            raise KeyError(f"dataset {dataset_id}@{version} not found")
        return ds

    def load_cases(self, dataset_id: str, version: str, split: str) -> list[EvalCase]:
        ds = self.load_dataset(dataset_id, version)
        if split and split != ds.split.value:
            # Logical split filter (no physical copy, §4.6.3).
            filtered = [c for c in ds.cases if split in c.tags]
            return filtered or ds.cases
        return list(ds.cases)

    def save_run(self, run: EvalRun) -> None:
        self._runs[run.run_id] = run

    def load_run(self, run_id: str) -> EvalRun:
        r = self._runs.get(run_id)
        if r is None:
            raise KeyError(f"run {run_id} not found")
        return r

    def save_scores(self, run_id: str, scores: list[Score]) -> None:
        self._scores[run_id] = scores

    def save_report(self, report: EvalReport) -> None:
        self._reports[report.report_id] = report
        self._run_to_report[report.run_id] = report.report_id

    def load_report(self, report_id: str) -> EvalReport:
        r = self._reports.get(report_id)
        if r is None:
            raise KeyError(f"report {report_id} not found")
        return r

    def load_report_by_run(self, run_id: str) -> EvalReport:
        rid = self._run_to_report.get(run_id)
        if rid is None:
            raise KeyError(f"no report for run {run_id}")
        return self._reports[rid]
