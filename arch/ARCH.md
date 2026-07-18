# ai-eval-service · Architecture Document (ARCH)

> Positioning and boundaries, responsibility list, domain model, external integration (Adapter). Source of fact: `design/DESIGN.md`.

## 1. Positioning and boundaries

`ai-eval-service` is OpenStrata's **Evaluation Service**, located in the `ai-native` domain. It is the engineering bearer of the "Evaluation Phase (§6.3)" and "MLOps and Evaluation Layer (§4.6)" in the Agent's full life cycle (§6). Using `Eval` SPI (`bom.yaml` `interface_versions.Eval = 1.0.0`) as a unified port, external evaluation frameworks such as Promptfoo / DeepEval / Ragas are converged into orchestratable and replaceable evaluation capabilities within the platform.

**Single Responsibility**: Assessment data management + Assessment execution + Metric scoring + Report aggregation.

### 1.1 Not responsible

| Dimensions | Responsible party |
| --- | --- |
| Online conversation/reasoning | `ai-gateway-core` (LLMProvider SPI) |
| Agent runtime orchestration | `ai-gateway-core` + AgentRuntime (LangGraph) |
| Online LLM Tracking | Langfuse (Tracing SPI) |
| Evaluation report display UI | `ai-portal-frontend` / `ai-admin-frontend` |
| Model fine-tuning/experiment tracking | MLflow (MLOps SPI, stage 4) |

### 1.2 Hierarchical location

It belongs to the "AI native" application layer capabilities and is adapted to the external evaluation framework through SPI. The evaluation task (`EV` in the figure) is delivered asynchronously by `ai-platform-api`, and the output report is reflowed.

### 1.3 Optional

R1–R7 are all `optional`, lit with the `eval` switch in `openstrata.yaml` (§12.1). Basic risk control of PII scanning (R8) reuse platform.

---
## 2. Responsibilities List

Split by DDD application layer use cases, the following external capabilities are promised:

| # | Responsibilities | Description |
| --- | --- | --- |
| R1 | **Evaluation Dataset Management** | Creation / Versioning / Partition (Train·Eval·Test)/Distribution Analysis/Bad Case Storage |
| R2 | **Evaluation Use Case (Case) Management** | Input/expectation/context/label of a single Case (attribution labels such as illusion/safety/format) |
| R3 | **Evaluation Task Arrangement** | Submit evaluation run, bind target Agent (AgentRuntime), select scorer set, progress tracking |
| R4 | **Evaluation Execution (Run)** | Load data → Call AgentRuntime to execute → Collect trace/output |
| R5 | **Metric Score (Score)** | Score output through pluggable Scorer (Promptfoo/DeepEval/Ragas) |
| R6 | **Result Aggregation and Reporting** | Aggregate indicators, generate Report (accuracy/security/latency/cost, etc.), support regression comparison |
| R7 | **Return/Security/RAG Evaluation** | Return Comparison, Red Team Injection (Promptfoo Red Team), RAG Fidelity Special Evaluation |
| R8 | **PII and data security** | Evaluation data set PII scanning, desensitization, access isolation (reusing platform basic risk control port) |

---
## 3. Domain concepts and models

The domain layer defines aggregations and entities with pure logic and zero external dependencies. Core aggregate roots: `EvalDataset`, `EvalRun`, `EvalReport`.

### 3.1 Domain Glossary

| Concept | Meaning | Key attributes |
| --- | --- | --- |
| **EvalDataset** | A collection of evaluation use cases, with version | `dataset_id`, `name`, `version`, `split` (train/eval/test), `source` (artificial/synthetic/online sampling/BadCase), distribution metadata |
| **EvalCase** | Single evaluation case | `case_id`, `inputs`, optional `expected`/`reference`, RAG `contexts`, attribution `tags` |
| **Metric** | A scoring dimension (such as accuracy/fidelity/illusion rate) | `metric_key`, `scorer`, `direction` (max/min), threshold |
| **Score** | The score of a certain Case under a certain Metric | `case_id`, `metric_key`, `value`, `reason`, `trace_ref` |
| **EvalRun** | An evaluation execution (bound data set + Agent + scorer set) | `run_id`, `agent_ref`, `dataset_version`, `status`, `progress` |
| **EvalReport** | Aggregation results of a Run | `report_id`, `run_id`, each Metric aggregate value, comparison baseline |

### 3.2 Aggregation relationship

```
EvalDataset (1)  *--  (0..*) EvalCase      : contains
EvalRun     (1)  *--  (0..*) Score          : produces
EvalRun     (1)  -->  (1)   EvalReport      : aggregated into
EvalDataset (1)  -->  (0..*) EvalRun        : evaluated by
```

### 3.3 Domain constraints

- `EvalDataset.version` is incremented by the domain service every time the content changes (semantic version, docking with §6.4 version management).
- `EvalRun.status` state machine: `pending → running → scoring → aggregated → done | failed`.
- `Score.value` must fall within the `[min, max]` range declared by the Scorer, otherwise the domain layer rejects and marks the Run as `failed`.
- `tag_categories` Attribution tag enumeration: `hallucination`, `security`, `format`, `toxicity`, `bias`, `factuality`.

### 3.4 Port definition (domain layer port)

```python
# AgentRuntime port —— The domain layer only defines interfaces，Does not depend on implementation
class AgentRuntimePort(Protocol):
    def run_case(self, ref: AgentRef, case: EvalCase) -> CaseResult:
        """Call the target Agent to execute a single evaluation case and return the output and observable trajectory reference."""
        ...

# Scorer port —— Pluggable scorer interface
class ScorerPort(Protocol):
    scorer_key: str
    supported_metrics: list[str]
    def score(self, case: EvalCase, result: CaseResult) -> list[Score]:
        """Score the output of a single Case, returning a score along one or more dimensions."""
        ...

# Repository port —— Data persistence abstraction
class EvalRepositoryPort(Protocol):
    def save_dataset(self, dataset: EvalDataset) -> None: ...
    def load_cases(self, dataset_id: str, version: str, split: str) -> list[EvalCase]: ...
    def save_run(self, run: EvalRun) -> None: ...
    def save_scores(self, run_id: str, scores: list[Score]) -> None: ...
    def load_report(self, report_id: str) -> EvalReport: ...
```

---
## 4. External integration (Adapter anti-corrosion layer)

The evaluation service itself does not hold ** model and vector capabilities, and is all accessed through the corresponding SPI Adapter (ACL anti-corrosion layer) to ensure that multiple implementations of the same type can be switched and external semantics are not leaked.

### 4.1 Dependency capability matrix

| Dependency capabilities | SPI port | Default implementation | Purpose of this service | Adapter class |
| --- | --- | --- | --- | --- |
| Model supply | `LLMProvider` (`1.0.0`) | Qwen/OpenAI/Claude | Agent inference call; synthetic data generation | `LLMProviderAdapter` Unified export via gateway |
| Vector retrieval | `VectorStore` (`1.1.0`) | Qdrant | RAG evaluation (Ragas) retrieval context fidelity | `VectorStoreAdapter` |
| Agent runtime | `AgentRuntime` (`1.3.0`) | LangGraph | Execute the evaluated Agent | `AgentRuntimeAdapter` |
| LLM tracking | `Tracing` | Langfuse (optional) | Evaluation track traces, report correlation | `TracingAdapter` |
| Cache/KV | `Cache` (`1.0.0`) | Redis | Temporary cache of task status and scoring results | `CacheAdapter` |
| Authentication and Authorization | `Auth` (`1.0.0`) | Keycloak | Tenant isolation and access control for datasets/reports | `AuthAdapter` |

### 4.2 Adapter architecture

```
┌──────────────────────────────────────────────┐
│            ai-eval-service internal               │
│  Domain layer: ScorerPort / AgentRuntimePort /     │
│          LLMProviderPort / EvalRepositoryPort │
└────────────┬─────────────────────────────────┘
             │ accomplish Port（dependency inversion DIP）
┌────────────▼─────────────────────────────────┐
│         infrastructure layer Adapter（ACL）              │
│  AgentRuntimeAdapter  →  ai-gateway-core     │
│  LLMProviderAdapter   →  ai-gateway-core     │
│  VectorStoreAdapter   →  Qdrant / Milvus     │
│  TracingAdapter       →  Langfuse            │
│  CacheAdapter         →  Redis               │
│  AuthAdapter          →  Keycloak            │
└──────────────────────────────────────────────┘
```

### 4.3 Adapter registration and DI

The adapter is registered through the dependency injection (DI) container, and the domain layer is called through the port abstraction:

```python
# Infrastructure layer registration
container.register(AgentRuntimePort, AgentRuntimeAdapter, singleton=True)
container.register(LLMProviderPort, LLMProviderAdapter, singleton=True)
container.register(ScorerPort, PromptfooScorer, key="promptfoo")
container.register(ScorerPort, DeepEvalScorer, key="deepeval")
container.register(ScorerPort, RagasScorer, key="ragas")
```

### 4.4 Scorer Registry (ProviderSelector)

```python
class ScorerRegistry:
    """Select a registered adapter instance by scorer_key."""
    def __init__(self, scorers: dict[str, ScorerPort]):
        self._scorers = scorers

    def get(self, scorer_key: str) -> ScorerPort:
        if scorer_key not in self._scorers:
            raise UnknownScorerError(f"Unknown scorer: {scorer_key}")
        return self._scorers[scorer_key]

    def list_enabled(self) -> list[str]:
        return list(self._scorers.keys())
```

### 4.5 GPU Boundary Description

- Phases 1 to 3 are only third-party LLM APIs (no GPU required).
- Self-hosted inference (vLLM) only turns on the full stage four stage, and is always switched via `LLMProvider` SPI, with zero changes to the evaluation use cases.
- The service itself has **no hard dependence on GPU**, and the evaluation execution (running Agent, scoring) is usually **CPU load**.

---
## 5. DDD hierarchical mapping

```
access layer（①）      FastAPI router → Pydantic Schema → Use case layer
Application layer（②）      EvalUseCase（Orchestrate load→run→score→aggregate）
Domain layer（③）      EvalDataset / EvalRun / EvalReport（aggregate root）
                  + port interface（AgentRuntimePort / ScorerPort / EvalRepositoryPort）
infrastructure layer（④）   SQLAlchemy Repository、Adapter accomplish（LangGraph / Promptfoo / Qdrant）
```

- **Pure logic in domain layer**: zero framework dependency, can be separated from DB/FASTAPI single test.
- **Infrastructure layer encapsulates the outside**: Adapter acts as an anti-corruption layer (ACL) to isolate external framework semantic leakage.
- **Application Layer Orchestration Use Case**: Holds port abstraction, schedules domain objects, and does not care about infrastructure details.

### 5.1 Repository directory structure

```
ai-eval-service/
├── src/
│   ├── domain/                    #③ Domain layer (pure logic, zero external dependencies)
│   │   ├── model/                 # EvalDataset / EvalCase / EvalRun / Score / EvalReport
│   │   ├── port/                  #Port interface (AgentRuntimePort/ScorerPort/EvalRepositoryPort)
│   │   └── service/               #Domain services (versioning, state machine, aggregation algorithm)
│   ├── application/               #② Application layer (use case orchestration)
│   │   └── usecase/               # EvalUseCase（load→run→score→aggregate）
│   ├── interface/                 #① Access layer (FastAPI + Pydantic)
│   │   ├── rest/                  #REST routing and middleware
│   │   └── schema/                #Request/Response Pydantic Model
│   ├── infrastructure/            #④ Infrastructure layer
│   │   ├── adapter/               #SPI adapter implementation (ACL anti-corrosion layer)
│   │   ├── repository/            #SQLAlchemy Repository implementation
│   │   └── config/                #Local configuration fragment of this repository
│   └── di/                        #Dependency injection container (Adapter registration, ScorerRegistry)
├── tests/
│   ├── unit/                      #Domain layer pure logic single test (pytest)
│   ├── integration/               #Adapter + DB integration tests (testcontainers)
│   ├── contract/                  #SPI port contract test
│   └── e2e/                       #End-to-end testing (FastAPI TestClient)
├── pyproject.toml  Dockerfile  helm/
└── arch/  design/  skills/  specs/
```

### 5.2 Dependency injection container

```python
# src/di/container.py
class Container:
    """Lightweight DI container that assembles Adapter implementations to ports on demand."""
    def __init__(self, config: EvalConfig):
        self._registry: dict[type, dict[str, object]] = {}

    def register(self, port: type, impl: object, key: str = "default"):
        if port not in self._registry:
            self._registry[port] = {}
        self._registry[port][key] = impl

    def resolve(self, port: type, key: str = "default") -> object:
        return self._registry[port][key]

# Assembly example
container = Container(config)
container.register(AgentRuntimePort, AgentRuntimeAdapter())
container.register(EvalRepositoryPort, SqlAlchemyEvalRepository(session_factory))
container.register(ScorerPort, PromptfooScorer(config), key="promptfoo_accuracy")
container.register(ScorerPort, DeepEvalScorer(config), key="deepeval_hallucination")
container.register(ScorerPort, RagasScorer(config), key="ragas_faithfulness")
```

### 5.3 Technology stack constraints

| Hierarchy | Framework/Library | Version | Description |
| --- | --- | --- | --- |
| Access layer | FastAPI + Pydantic v2 | latest | REST interface + request verification |
| Application layer | Pure Python | — | Use case orchestration, no framework dependencies |
| Domain layer | Pure Python + Protocols | — | Domain model + port abstraction |
| Infrastructure DB | SQLAlchemy 2.0 + asyncpg | latest | PostgreSQL asynchronous access |
| Infrastructure cache | redis-py (async) | latest | Redis task status/cache |
| DI | Self-developed lightweight container or `dependency-injector` | — | Adapter ↔ Port assembly |
| Test | pytest + testcontainers | latest | Three-tier testing (domain/infra/e2e) |

---
## Change record

| Version | Date | Description |
| --- | --- | --- |
| v1.0 | 2026-07-17 | Extract architecture skeleton based on `design/DESIGN.md` §1/§2/§3/§6 |
