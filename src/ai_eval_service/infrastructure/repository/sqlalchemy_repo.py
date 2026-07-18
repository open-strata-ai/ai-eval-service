from __future__ import annotations

import json
from typing import Optional

from sqlalchemy import (
    JSON,
    Column,
    Float,
    MetaData,
    PrimaryKeyConstraint,
    String,
    Table,
    Text,
    create_engine,
    insert,
    select,
)
from sqlalchemy.engine import Engine

from ai_eval_service.domain.model.dataset import EvalCase, EvalDataset
from ai_eval_service.domain.model.report import EvalReport
from ai_eval_service.domain.model.run import EvalRun, Score


def _dump(obj):
    return json.loads(obj.model_dump_json())


class SqlAlchemyEvalRepository:
    """PostgreSQL-backed repository (§8). Reference implementation using
    SQLAlchemy Core with JSON columns; composite PK (dataset_id, version)."""

    def __init__(self, dsn: str, engine: Optional[Engine] = None) -> None:
        self._engine = engine or create_engine(dsn)
        self._meta = MetaData()
        self._dataset = Table(
            "eval_dataset",
            self._meta,
            Column("dataset_id", String, primary_key=True),
            Column("version", String, primary_key=True),
            Column("payload", JSON),
        )
        self._run = Table(
            "eval_run",
            self._meta,
            Column("run_id", String, primary_key=True),
            Column("payload", JSON),
        )
        self._score = Table(
            "eval_score",
            self._meta,
            Column("run_id", String),
            Column("case_id", String),
            Column("metric_key", String),
            Column("value", Float),
            Column("reason", Text),
            PrimaryKeyConstraint("run_id", "case_id", "metric_key"),
        )
        self._report = Table(
            "eval_report",
            self._meta,
            Column("report_id", String, primary_key=True),
            Column("run_id", String),
            Column("payload", JSON),
        )
        self._meta.create_all(self._engine)

    def save_dataset(self, dataset: EvalDataset) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                self._dataset.delete().where(
                    (self._dataset.c.dataset_id == dataset.dataset_id)
                    & (self._dataset.c.version == dataset.version)
                )
            )
            conn.execute(
                insert(self._dataset).values(
                    dataset_id=dataset.dataset_id,
                    version=dataset.version,
                    payload=_dump(dataset),
                )
            )

    def load_dataset(self, dataset_id: str, version: str) -> EvalDataset:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(self._dataset.c.payload).where(
                    (self._dataset.c.dataset_id == dataset_id)
                    & (self._dataset.c.version == version)
                )
            ).first()
        if row is None:
            raise KeyError(f"dataset {dataset_id}@{version} not found")
        return EvalDataset.model_validate(row.payload)

    def load_cases(self, dataset_id: str, version: str, split: str) -> list[EvalCase]:
        ds = self.load_dataset(dataset_id, version)
        if split and split != ds.split.value:
            filtered = [c for c in ds.cases if split in c.tags]
            return filtered or ds.cases
        return list(ds.cases)

    def save_run(self, run: EvalRun) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                self._run.delete().where(self._run.c.run_id == run.run_id)
            )
            conn.execute(
                insert(self._run).values(run_id=run.run_id, payload=_dump(run))
            )

    def load_run(self, run_id: str) -> EvalRun:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(self._run.c.payload).where(self._run.c.run_id == run_id)
            ).first()
        if row is None:
            raise KeyError(f"run {run_id} not found")
        return EvalRun.model_validate(row.payload)

    def save_scores(self, run_id: str, scores: list[Score]) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                self._score.delete().where(self._score.c.run_id == run_id)
            )
            if scores:
                conn.execute(
                    insert(self._score).values(
                        [
                            {
                                "run_id": s.run_id,
                                "case_id": s.case_id,
                                "metric_key": s.metric_key,
                                "value": s.value,
                                "reason": s.reason,
                            }
                            for s in scores
                        ]
                    )
                )

    def save_report(self, report: EvalReport) -> None:
        with self._engine.begin() as conn:
            conn.execute(
                self._report.delete().where(
                    self._report.c.report_id == report.report_id
                )
            )
            conn.execute(
                insert(self._report).values(
                    report_id=report.report_id,
                    run_id=report.run_id,
                    payload=_dump(report),
                )
            )

    def load_report(self, report_id: str) -> EvalReport:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(self._report.c.payload).where(
                    self._report.c.report_id == report_id
                )
            ).first()
        if row is None:
            raise KeyError(f"report {report_id} not found")
        return EvalReport.model_validate(row.payload)

    def load_report_by_run(self, run_id: str) -> EvalReport:
        with self._engine.connect() as conn:
            row = conn.execute(
                select(self._report.c.payload).where(
                    self._report.c.run_id == run_id
                )
            ).first()
        if row is None:
            raise KeyError(f"no report for run {run_id}")
        return EvalReport.model_validate(row.payload)
