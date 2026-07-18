from __future__ import annotations

import uuid
from typing import Optional

from ai_eval_service.domain.model.dataset import (
    DatasetSource,
    EvalCase,
    EvalDataset,
    Split,
)
from ai_eval_service.domain.model.report import EvalReport
from ai_eval_service.domain.model.run import AgentRef, EvalRun, RunStatus, Score
from ai_eval_service.domain.port.agent_runtime import AgentRuntimePort
from ai_eval_service.domain.port.repository import EvalRepositoryPort
from ai_eval_service.domain.port.scorer import ScorerRegistry
from ai_eval_service.domain.service.aggregation import aggregate
from ai_eval_service.domain.service.state_machine import (
    IllegalStateTransitionError,
    transition,
)


class EvalUseCase:
    """Application-layer orchestration (§4): load -> run -> score -> aggregate."""

    def __init__(
        self,
        repository: EvalRepositoryPort,
        agent_runtime: AgentRuntimePort,
        scorer_registry: ScorerRegistry,
    ) -> None:
        self._repo = repository
        self._agent = agent_runtime
        self._scorers = scorer_registry

    # --- R1 Dataset management -------------------------------------------
    def create_dataset(
        self,
        name: str,
        *,
        dataset_id: Optional[str] = None,
        split: Split = Split.eval,
        source: DatasetSource = DatasetSource.human,
        tenant_id: str = "local",
    ) -> EvalDataset:
        ds = EvalDataset(
            dataset_id=dataset_id or f"ds-{uuid.uuid4().hex[:12]}",
            name=name,
            split=split,
            source=source,
            tenant_id=tenant_id,
        )
        self._repo.save_dataset(ds)
        return ds

    def add_case(self, dataset_id: str, version: str, case: EvalCase) -> EvalDataset:
        ds = self._repo.load_dataset(dataset_id, version)
        ds.add_case(case)
        ds.bump_version()
        self._repo.save_dataset(ds)
        return ds

    def get_dataset(self, dataset_id: str, version: str) -> EvalDataset:
        return self._repo.load_dataset(dataset_id, version)

    # --- R3 Submit run ---------------------------------------------------
    def submit_run(
        self,
        dataset_id: str,
        dataset_version: str,
        agent: AgentRef,
        scorer_set: list[str],
        *,
        baseline_run_id: Optional[str] = None,
        split: str = "eval",
        tenant_id: str = "local",
    ) -> EvalRun:
        run = EvalRun(
            dataset_id=dataset_id,
            dataset_version=dataset_version,
            agent_ref=agent,
            scorer_set=scorer_set,
            baseline_run_id=baseline_run_id,
            split=split,
            tenant_id=tenant_id,
        )
        self._repo.save_run(run)
        return run

    def get_run(self, run_id: str) -> EvalRun:
        return self._repo.load_run(run_id)

    def cancel_run(self, run_id: str) -> EvalRun:
        run = self._repo.load_run(run_id)
        if run.status in (RunStatus.done, RunStatus.failed):
            raise IllegalStateTransitionError(
                f"Run {run_id} already terminal ({run.status})"
            )
        transition(run, RunStatus.failed)
        self._repo.save_run(run)
        return run

    # --- R4 + R5 + R6 full pipeline --------------------------------------
    def run_eval(self, run_id: str) -> EvalReport:
        run = self._repo.load_run(run_id)
        if run.status != RunStatus.pending:
            raise IllegalStateTransitionError(
                f"Run {run_id} must be pending to execute (got {run.status})"
            )
        transition(run, RunStatus.running)
        run.progress = 0.1
        self._repo.save_run(run)

        cases = self._repo.load_cases(run.dataset_id, run.dataset_version, run.split)
        total = max(len(cases), 1)
        scored: list[tuple[EvalCase, object]] = []
        for i, case in enumerate(cases):
            res = self._agent.run_case(run.agent_ref, case)
            scored.append((case, res))
            run.progress = round(0.1 + 0.5 * (i + 1) / total, 3)
            self._repo.save_run(run)

        transition(run, RunStatus.scoring)
        run.progress = 0.7
        self._repo.save_run(run)

        scores: list[Score] = []
        for case, res in scored:
            for key in run.scorer_set:
                scorer = self._scorers.get(key)
                scores.extend(scorer.score(case, res))
        self._repo.save_scores(run.run_id, scores)

        transition(run, RunStatus.aggregated)
        run.progress = 0.9
        self._repo.save_run(run)

        baseline = self._load_baseline(run)
        report = aggregate(run, scores, baseline)
        self._repo.save_report(report)

        transition(run, RunStatus.done)
        run.progress = 1.0
        self._repo.save_run(run)
        return report

    def score_run(
        self, run_id: str, scorer_subset: Optional[list[str]] = None
    ) -> EvalReport:
        run = self._repo.load_run(run_id)
        cases = self._repo.load_cases(run.dataset_id, run.dataset_version, run.split)
        keys = scorer_subset or run.scorer_set
        scores: list[Score] = []
        for case in cases:
            res = self._agent.run_case(run.agent_ref, case)
            for key in keys:
                scores.extend(self._scorers.get(key).score(case, res))
        self._repo.save_scores(run.run_id, scores)
        baseline = self._load_baseline(run)
        report = aggregate(run, scores, baseline)
        self._repo.save_report(report)
        run.status = RunStatus.done
        run.progress = 1.0
        self._repo.save_run(run)
        return report

    def get_report(self, report_id: str) -> EvalReport:
        return self._repo.load_report(report_id)

    def get_report_for_run(self, run_id: str) -> EvalReport:
        return self._repo.load_report_by_run(run_id)

    # --- helpers ---------------------------------------------------------
    def _load_baseline(self, run: EvalRun) -> Optional[EvalReport]:
        if not run.baseline_run_id:
            return None
        try:
            return self._repo.load_report_by_run(run.baseline_run_id)
        except Exception:
            return None
