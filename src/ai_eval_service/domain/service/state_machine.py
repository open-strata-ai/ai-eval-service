from __future__ import annotations

from ai_eval_service.domain.model.run import EvalRun, RunStatus


class IllegalStateTransitionError(Exception):
    pass


_ALLOWED: dict[RunStatus, set[RunStatus]] = {
    RunStatus.pending: {RunStatus.running, RunStatus.failed},
    RunStatus.running: {RunStatus.scoring, RunStatus.failed},
    RunStatus.scoring: {RunStatus.aggregated, RunStatus.failed},
    RunStatus.aggregated: {RunStatus.done, RunStatus.failed},
    RunStatus.done: set(),
    RunStatus.failed: set(),
}


def can_transition(current: RunStatus, target: RunStatus) -> bool:
    return target in _ALLOWED.get(current, set())


def transition(run: EvalRun, target: RunStatus) -> None:
    if not can_transition(run.status, target):
        raise IllegalStateTransitionError(
            f"Cannot transition EvalRun {run.run_id} from {run.status} to {target}"
        )
    run.status = target
