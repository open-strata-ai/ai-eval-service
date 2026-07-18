from __future__ import annotations

from ai_eval_service.domain.model.dataset import EvalCase
from ai_eval_service.domain.model.run import AgentRef, RunStatus


def test_full_pipeline(container):
    uc = container.resolve_eval_usecase()
    ds = uc.create_dataset("qa", dataset_id="qa-golden")
    uc.add_case(
        "qa-golden", ds.version,
        EvalCase(
            inputs={"query": "What is 2+2?"},
            expected={"answer": "What is 2+2?"},
        ),
    )
    run = uc.submit_run(
        "qa-golden", ds.version,
        AgentRef(agent_id="cs", tenant_id="t"),
        scorer_set=["promptfoo_accuracy", "promptfoo_security"],
    )
    report = uc.run_eval(run.run_id)
    assert report.metrics_summary["accuracy"] == 1.0
    assert report.metrics_summary["security"] == 1.0
    assert uc.get_run(run.run_id).status == RunStatus.done


def test_regression_compare(container):
    uc = container.resolve_eval_usecase()
    ds = uc.create_dataset("qa", dataset_id="qa-golden")
    uc.add_case(
        "qa-golden", ds.version,
        EvalCase(inputs={"query": "hi"}, expected={"answer": "hi"}),
    )
    base = uc.submit_run(
        "qa-golden", ds.version,
        AgentRef(agent_id="cs", tenant_id="t"), scorer_set=["promptfoo_accuracy"],
    )
    base_report = uc.run_eval(base.run_id)

    cand = uc.submit_run(
        "qa-golden", ds.version,
        AgentRef(agent_id="cs", tenant_id="t"),
        scorer_set=["promptfoo_accuracy"], baseline_run_id=base.run_id,
    )
    cand_report = uc.run_eval(cand.run_id)
    assert cand_report.baseline_run_id == base.run_id
    assert cand_report.regression_delta is not None
    assert cand_report.regression_delta["accuracy"] == 0.0


def test_cancel_terminal_run_rejected(container):
    from ai_eval_service.domain.service.state_machine import IllegalStateTransitionError

    uc = container.resolve_eval_usecase()
    ds = uc.create_dataset("qa", dataset_id="qa-golden")
    run = uc.submit_run(
        "qa-golden", ds.version,
        AgentRef(agent_id="cs", tenant_id="t"), scorer_set=["promptfoo_accuracy"],
    )
    uc.run_eval(run.run_id)
    try:
        uc.cancel_run(run.run_id)
        assert False, "expected IllegalStateTransitionError"
    except IllegalStateTransitionError:
        pass
