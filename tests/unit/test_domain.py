from __future__ import annotations

import pytest

from ai_eval_service.domain.model.dataset import EvalCase, EvalDataset
from ai_eval_service.domain.model.report import EvalReport
from ai_eval_service.domain.model.run import AgentRef, EvalRun, RunStatus, Score
from ai_eval_service.domain.service.aggregation import aggregate
from ai_eval_service.domain.service.state_machine import (
    IllegalStateTransitionError,
    can_transition,
    transition,
)
from ai_eval_service.domain.service.versioning import next_version


def test_next_version():
    assert next_version("v1.2.3") == "v1.2.4"
    assert next_version("v1") == "v1.0.1"
    assert next_version("bad") == "1.0.0"


def test_state_machine_happy_path():
    run = EvalRun(
        dataset_id="d", dataset_version="v1",
        agent_ref=AgentRef(agent_id="a", tenant_id="t"), scorer_set=["x"],
    )
    assert can_transition(RunStatus.pending, RunStatus.running)
    assert not can_transition(RunStatus.pending, RunStatus.done)
    transition(run, RunStatus.running)
    transition(run, RunStatus.scoring)
    transition(run, RunStatus.aggregated)
    transition(run, RunStatus.done)
    assert run.status == RunStatus.done


def test_state_machine_rejects_illegal():
    run = EvalRun(
        dataset_id="d", dataset_version="v1",
        agent_ref=AgentRef(agent_id="a", tenant_id="t"), scorer_set=["x"],
    )
    with pytest.raises(IllegalStateTransitionError):
        transition(run, RunStatus.done)


def test_dataset_version_bump_and_distribution():
    ds = EvalDataset(dataset_id="d", name="n")
    ds.add_case(EvalCase(inputs={"query": "hi"}, tags=["hallucination"]))
    v0 = ds.version
    ds.bump_version()
    assert ds.version != v0
    dist = ds.distribution()
    assert dist["case_count"] == 1
    assert dist["by_tag"].get("hallucination") == 1


def test_aggregate_mean_and_regression():
    run = EvalRun(
        dataset_id="d", dataset_version="v1",
        agent_ref=AgentRef(agent_id="a", tenant_id="t"), scorer_set=[],
    )
    scores = [
        Score(case_id="c1", metric_key="accuracy", value=1.0),
        Score(case_id="c2", metric_key="accuracy", value=0.0),
    ]
    rep = aggregate(run, scores)
    assert rep.metrics_summary["accuracy"] == 0.5
    assert rep.regression_delta is None

    baseline = EvalReport(
        report_id="b", run_id="base", metrics_summary={"accuracy": 1.0}
    )
    rep2 = aggregate(run, scores, baseline)
    assert rep2.regression_delta["accuracy"] == -0.5
