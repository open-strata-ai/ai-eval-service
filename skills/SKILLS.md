# ai-eval-service · Coding skills (SKILLS)

> Assessment pipeline, pluggable scorers, observability and security (PII). Source of fact: `design/DESIGN.md`.

## 1. Evaluation pipeline (load → run → score → aggregate)

Evaluation execution is the core use case of the application layer (`EvalUseCase`), which is promoted serially in four stages, and each stage can be expanded horizontally (ThreadPool/Ray is used for parallel evaluation).

### 1.1 Pipeline Overview

```
submit EvalRun ──> ① load ──> ② run ──> ③ score ──> ④ aggregate ──> output EvalReport
  (binding AgentRef +      │         │           │            │           (Accuracy/security/
   DatasetVersion +      │         │           │            │            Delay/cost)
   ScorerSet)            │         │           │            │
                    Load dataset    callAgent   Parallel scoring      polymerization+baseline comparison
                    according tosplitdivide   collectiontrace   Indicators of each dimension    Generate report
```

### 1.2 Key points of coding at each stage

| Stages | Input | Processing | Output | Coding Essentials |
| --- | --- | --- | --- | --- |
| **load** | `dataset_version`, partitioning rules | Load Case from Repository, split by `split` | `EvalCase[]` | Data source is pluggable (PG/Object Storage/Synthetic Generator); `split` filtering is completed at the repository layer |
| **run** | `EvalCase[]`, `AgentRef` | Call the target Agent via `AgentRuntimePort` | `CaseResult{output, trace_ref, latency, cost}` | Thread pool concurrency (`concurrency` configuration); AgentRuntime adapter injection |
| **score** | `CaseResult[]`, `ScorerSet` | Call each `ScorerPort` in parallel for each Case | `Score[]` | Scorer registry routed by `scorer_key`; Score.value range check |
| **aggregate** | `Score[]`, optional `baseline_run_id` | Aggregate by `metric_key` (mean/P95/pass rate) | `EvalReport` | Baseline diff calculation `regression_delta`; support report export format |

### 1.3 Parallel execution mode

```python
from concurrent.futures import ThreadPoolExecutor, as_completed

class EvalUseCase:
    def __init__(self, agent_port: AgentRuntimePort, scorer_registry: ScorerRegistry,
                 repo: EvalRepositoryPort, concurrency: int = 16):
        self._agent = agent_port
        self._scorers = scorer_registry
        self._repo = repo
        self._concurrency = concurrency

    def execute(self, run: EvalRun) -> EvalReport:
        cases = self._repo.load_cases(run.dataset_id, run.dataset_version, run.split)
        results: list[CaseResult] = []
        scores: list[Score] = []

        #Phase run: execute Agent in parallel
        with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
            futures = {pool.submit(self._agent.run_case, run.agent_ref, c): c for c in cases}
            for f in as_completed(futures):
                results.append(f.result())
                self._update_progress(run, len(results), len(cases))

        #Phase score: Each Case is scored by each Scorer
        for case, result in zip(cases, results):
            for key in run.scorer_set:
                scorer = self._scorers.get(key)
                scores.extend(scorer.score(case, result))

        # Phase aggregate
        report = self._aggregate(run, scores)
        self._repo.save_report(report)
        return report
```

### 1.4 Status Management

`EvalRun.status` state machine is dual-written through Redis cache + PG persistence:

```
pending → running → scoring → aggregated → done
           ↘ (Abnormality at any stage) → failed
```

- Idempotent: Duplicate submissions with the same `run_id` are deduplicated through Redis.
- Cancelable: `POST /v1/runs/{run_id}/cancel` sets the cancellation flag, checks each stage and exits early.

---
## 2. Indicator and scorer design (Pluggable Scorers)

The scorer is pluggable: the domain layer defines `ScorerPort`, and each external evaluation framework implements the port as an Adapter. New scoring dimension = Add a new Adapter, zero changes to the domain layer and existing use cases (dependency inversion DIP).

### 2.1 Scorer Matrix

| Scorer (Adapter) | BOM component | Version | Status | SPI | Evaluation dimensions |
| --- | --- | --- | --- | --- | --- |
| `PromptfooScorer` | promptfoo | 0.90.0 | **core** (on by default) | `Eval` | Accuracy/security/consistency/red team injection |
| `DeepEvalScorer` | deepeval | 2.0.0 | optional | `Eval` | hallucination rate/toxicity/bias/format |
| `RagasScorer` | ragas | 0.2.0 | optional | `Eval` | Fidelity/Answer Relevance/Context Accuracy |

### 2.2 Scorer implementation mode

```python
class PromptfooScorer:
    """Promptfoo Scorer Adapter - wraps the promptfoo CLI as a ScorerPort."""
    scorer_key = "promptfoo"
    supported_metrics = ["accuracy", "security", "consistency", "redteam"]

    def __init__(self, config: PromptfooConfig):
        self._config = config

    def score(self, case: EvalCase, result: CaseResult) -> list[Score]:
        #Build promptfoo evaluation configuration
        promptfoo_config = self._build_config(case, result)
        #Call promptfoo eval (child process or SDK)
        raw_scores = promptfoo_evaluate(promptfoo_config)
        #Normalize to Score domain object
        return [
            Score(case_id=case.case_id, metric_key=m.metric, value=m.score, reason=m.reason)
            for m in raw_scores.results
        ]
```

### 2.3 Steps to add a new grader

1. Implement `ScorerPort` in `infrastructure/adapters/` and encapsulate the corresponding framework CLI/SDK.
2. Register to `ScorerRegistry` (via DI container) with `scorer_key`.
3. If a new metric is required, declare `metric_key` + direction + threshold in the `Metric` enumeration at the domain layer.
4. Provide SPI contract testing (`Eval: 1.0.0` port consistency assertion).

### 2.4 Scorer configuration

```yaml
# scorer_set Select example（Corresponding to evaluation run request）
scorer_set:
  - promptfoo_accuracy        #core default
  - promptfoo_security        #Red Team/Injection
  - deepeval_hallucination    #optional, available after lighting deepeval
  - ragas_faithfulness        #optional, RAG scenario
```

---
## 3. Observability and Security (PII Data Protection)

### 3.1 Observability Pillar

| Pillars | Selection | Implementation of this service |
| --- | --- | --- |
| Basic Tracing + Audit (**core**) | OpenTelemetry + immutable audit log | Every Run/Score hits OTel Span (including `run_id`/`tenant_id`/`agent_id`); all write operations leave traces |
| Metrics (recommended) | Prometheus + Grafana | Expose `eval_runs_total`, `eval_score_latency`, `scorer_errors`; reportable `export?fmt=grafana` |
| LLM Special Tracing (optional) | Langfuse | Associating evaluation tracks and online links via `TracingAdapter` |

### 3.2 OTel Span coding specification

```python
from opentelemetry import trace

tracer = trace.get_tracer("ai-eval-service")

@tracer.start_as_current_span("eval.run")
def execute_run(run: EvalRun):
    span = trace.get_current_span()
    span.set_attributes({
        "run_id": run.run_id,
        "tenant_id": run.tenant_id,
        "agent_id": run.agent_ref.agent_id,
        "dataset_version": run.dataset_version,
    })
    #... execution pipeline
```

### 3.3 Security and PII Handling

Evaluation data often contains real user corpus (1% online sampling, Bad Case), and PII processing is a core security item.

| Measures | Implementation | Nature |
| --- | --- | --- |
| **PII scanning + desensitization** | Access the basic risk control `riskControl.pii_scan` port of the platform, and perform NER detection and masking on `inputs`/`expected` before entering the database | core |
| **Injection/Jailbreak Detection** | Reuse `riskControl.injection_scan`; the adversarial samples in the evaluation data set were scored by the red team with `promptfoo` | core |
| **Frequency Abnormality/Current Limitation** | `riskControl.rate_limit` Protection Evaluation API | core |
| **Tenant Isolation** | All datasets/report tables with `tenant_id`, enforce row level isolation via `Auth` Port (Keycloak) | core |
| **Output sensitive information detection** | After scoring, the results are verified twice by `pii_scan` to avoid the report leaking the original PII | core |
| **Advanced Guardrails** | Illusion detection/compliance rules/human approval, enabled by `security` switch | optional |

### 3.4 PII data flow

```
Evaluation data storage ──> PII scanning + Desensitization ──> Storage after desensitization (tenant_id isolation)
(Artificial/synthesis/Online sampling/BadCase)         │
                                      ├──> Evaluation execution + score
                                      │         │
                                      │    ┌────┘
                                      ▼    ▼
                              Report output first two times PII check ──> security report
                              Adversarial examples ──> Promptfoo Red team scores (injection_scan)
```

**Design Principle**: This service **does not self-develop** PII/injection detection, and unifies the basic risk control port (core baseline) of the platform to avoid duplication and policy drift.

### 3.5 Prometheus Metrics Exposure

```python
from prometheus_client import Counter, Histogram

eval_runs_total = Counter("eval_runs_total", "Total eval runs", ["status", "tenant_id"])
eval_score_latency = Histogram("eval_score_latency_seconds", "Score latency")
scorer_errors = Counter("scorer_errors_total", "Scorer errors", ["scorer_key"])
```

---
## Change record

| Version | Date | Description |
| --- | --- | --- |
| v1.0 | 2026-07-17 | Extract skill skeleton based on `design/DESIGN.md` §4/§5/§11 |
