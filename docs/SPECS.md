# ai-eval-service · Specification Contract (SPECS)

> API design (REST/SDK), data model (storage), configuration and deployment. Source of fact: `docs/DESIGN.md`.

## 1. API design (REST/SDK contract)

The access layer (DDD ①) uses FastAPI to expose REST, and Pydantic v2 for Schema and verification. All write interfaces are injected into the tenant context via the `Auth` Port (`tenant_id` comes from Keycloak Token).

### 1.1 REST Endpoint Contract

| Method | Path | Use Case | Description |
| --- | --- | --- | --- |
| `POST` | `/v1/datasets` | R1 | Create dataset |
| `GET` | `/v1/datasets/{id}?version=` | R1 | Get the data set (including version) |
| `POST` | `/v1/datasets/{id}/cases` | R2 | New evaluation case |
| `POST` | `/v1/runs` | R3/R4 | Submit evaluation run (bind AgentRef + dataset version + scorer_set) |
| `GET` | `/v1/runs/{run_id}` | R3 | Query the running progress |
| `POST` | `/v1/runs/{run_id}/cancel` | R3 | Cancel run |
| `POST` | `/v1/runs/{run_id}/score` | R5 | Trigger/rerun scoring (scorer subset can be specified) |
| `GET` | `/v1/reports/{report_id}` | R6 | Get aggregate report (supports `?baseline=run_id` regression comparison) |
| `GET` | `/v1/reports/{report_id}/export?fmt=md\|json\|grafana` | R6 | Report export |

### 1.2 Pydantic v2 Schema

```python
from pydantic import BaseModel, Field
from enum import Enum

class Split(str, Enum):
    train = "train"; eval = "eval"; test = "test"

class RunStatus(str, Enum):
    pending = "pending"; running = "running"; scoring = "scoring"
    aggregated = "aggregated"; done = "done"; failed = "failed"

class AgentRef(BaseModel):
    agent_id: str
    tenant_id: str
    version: str | None = None          #If left blank, the current online version will be taken.

class RunCreate(BaseModel):
    dataset_id: str
    dataset_version: str
    agent: AgentRef
    scorer_set: list[str] = Field(..., min_length=1)
    split: Split = Split.eval
    baseline_run_id: str | None = None  #regression vs. baseline

class RunView(BaseModel):
    run_id: str
    status: RunStatus
    progress: float = Field(ge=0, le=1)
    metrics_summary: dict = {}

class ReportView(BaseModel):
    report_id: str
    run_id: str
    baseline_run_id: str | None
    metrics_summary: dict[str, float]       #metric_key -> aggregate value
    regression_delta: dict[str, float] | None
```

### 1.3 FastAPI routing skeleton

```python
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/v1", tags=["eval"])

@router.post("/runs", response_model=RunView, status_code=202)
async def create_run(body: RunCreate, tenant_id: str = Depends(get_tenant_id)):
    """Submit the evaluation and run it asynchronously."""
    ...

@router.get("/runs/{run_id}", response_model=RunView)
async def get_run(run_id: str, tenant_id: str = Depends(get_tenant_id)):
    """Query the evaluation running progress."""
    ...

@router.get("/reports/{report_id}", response_model=ReportView)
async def get_report(report_id: str, baseline: str | None = None,
                     tenant_id: str = Depends(get_tenant_id)):
    """Get aggregated reports and support regression comparison."""
    ...
```

### 1.4 SDK consumption contract

```python
# For ai-sdk-python consumer side
from openstrata.sdk import EvalClient
client = EvalClient(base_url="http://ai-eval-service", token="<keycloak-token>")
run = client.runs.create(
    dataset_id="qa-golden", dataset_version="v3",
    agent={"agent_id": "customer-service", "tenant_id": "t-b"},
    scorer_set=["promptfoo_accuracy", "deepeval_hallucination"],
)
report = client.reports.wait(run.run_id)      #poll to done
print(report.metrics_summary)
```

### 1.5 Compatibility Commitment

REST prefix `/v1`, SPI `Eval: 1.0.0`. Breaking changes must bump `MAJOR` and be accompanied by ADR.

---
## 2. Data model and storage

Storage follows §4.9 Base: `PostgreSQL 16` (relational/structured) + `Redis 7.4` (task state/cache). The domain layer defines `EvalRepositoryPort`, and the infrastructure layer is implemented in SQLAlchemy.

### 2.1 Core table DDL

```sql
-- Evaluation dataset（Versioned composite primary key）
CREATE TABLE eval_dataset (
    dataset_id   TEXT,
    version      TEXT,
    name         TEXT,
    source       TEXT,            -- human|synthetic|online_sample|badcase
    split        TEXT,
    dist_meta    JSONB,           -- category/length/Difficulty distribution
    tenant_id    TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (dataset_id, version)
);

-- Evaluation use case
CREATE TABLE eval_case (
    case_id    TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    version    TEXT NOT NULL,
    inputs     JSONB NOT NULL,
    expected   JSONB,
    contexts   JSONB,            -- RAG scene retrieval context
    tags       TEXT[],           -- attribution tag：hallucination|security|format|...
    FOREIGN KEY (dataset_id, version) REFERENCES eval_dataset(dataset_id, version)
);

-- Evaluation run
CREATE TABLE eval_run (
    run_id           TEXT PRIMARY KEY,
    agent_ref        JSONB NOT NULL,
    dataset_id       TEXT NOT NULL,
    dataset_version  TEXT NOT NULL,
    scorer_set       TEXT[] NOT NULL,
    status           TEXT NOT NULL DEFAULT 'pending',
    progress         REAL DEFAULT 0,
    tenant_id        TEXT NOT NULL,
    baseline_run_id  TEXT
);

-- Single score
CREATE TABLE eval_score (
    run_id     TEXT NOT NULL,
    case_id    TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    value      REAL NOT NULL,
    reason     TEXT,
    PRIMARY KEY (run_id, case_id, metric_key)
);

-- Aggregation reporting
CREATE TABLE eval_report (
    report_id        TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL UNIQUE,
    baseline_run_id  TEXT,
    metrics_summary  JSONB NOT NULL DEFAULT '{}',
    regression_delta JSONB
);
```

### 2.2 Storage division of labor

| Data type | Storage | Description |
| --- | --- | --- |
| Dataset/Usecase/Run/Score/Report | PostgreSQL | Persistent source of truth; versioned by composite primary key |
| Running progress/scoring intermediate result cache | Redis | High concurrent reading and writing, idempotent deduplication |
| Large-scale synthetic data/trajectory attachment | Object storage (MinIO, optional) | Large volume does not fall into PG |
| Experiment metric history (optional) | MLflow (Phase 4 MLOps) | Cross-version trends |

### 2.3 SQLAlchemy ORM model skeleton

```python
from sqlalchemy import Column, String, Float, JSON, ARRAY, TIMESTAMP, ForeignKeyConstraint
from sqlalchemy.orm import declarative_base

Base = declarative_base()

class EvalDatasetModel(Base):
    __tablename__ = "eval_dataset"
    dataset_id = Column(String, primary_key=True)
    version = Column(String, primary_key=True)
    name = Column(String)
    source = Column(String)
    split = Column(String)
    dist_meta = Column(JSON)
    tenant_id = Column(String, nullable=False, index=True)
    created_at = Column(TIMESTAMP(timezone=True))

class EvalCaseModel(Base):
    __tablename__ = "eval_case"
    case_id = Column(String, primary_key=True)
    dataset_id = Column(String, nullable=False)
    version = Column(String, nullable=False)
    inputs = Column(JSON, nullable=False)
    expected = Column(JSON)
    contexts = Column(JSON)
    tags = Column(ARRAY(String))

class EvalRunModel(Base):
    __tablename__ = "eval_run"
    run_id = Column(String, primary_key=True)
    agent_ref = Column(JSON, nullable=False)
    dataset_id = Column(String, nullable=False)
    dataset_version = Column(String, nullable=False)
    scorer_set = Column(ARRAY(String), nullable=False)
    status = Column(String, default="pending")
    progress = Column(Float, default=0)
    tenant_id = Column(String, nullable=False, index=True)
    baseline_run_id = Column(String)
```

### 2.4 Division strategy

Data set division (Train/Eval/Test) is **logical division** (by `split` columns + configuration rules), without physical replication, reducing storage costs. `split` enum: `train | eval | test`.

---
## 3. Configuration and deployment

### 3.1 Configuration fragment

This repository only holds **local configuration fragments**, and the global configuration is rendered by the meta repository `openstrata-meta/dependencies/config/`.

```yaml
# ai-eval-service/infrastructure/config/eval.yaml
eval:
  enabled: true
  #Scorer switch: core is on by default promptfoo, optional is on as needed
  scorers:
    promptfoo:  { enabled: true,  version: "0.90.0" }
    deepeval:   { enabled: false, version: "2.0.0" }
    ragas:      { enabled: false, version: "0.2.0" }
  execution:
    concurrency: 16            #Number of parallel evaluation threads
    backend: threadpool        #threadpool | ray (large data set)
  storage:
    postgres: { dsn_env: PGDSN }
    redis:    { enabled: true }
  integrations:
    agentRuntime: langgraph
    llmProvider:  [qwen-cloud, openai]
    vectorStore:  qdrant
    tracing:      langfuse
```

### 3.2 Deployment form (four levels of prefabrication)

| Profile | Stage | Whether this service is included | Resources |
| --- | --- | --- | --- |
| `starter` | 1. Early adopters | Default off | N/A |
| `standard` | 2·Enhancement | Optional (light on `eval`) | K8s single tenant, CPU-based |
| `advanced` | 3. Scaled governance | Contains (`eval: [promptfoo, deepeval, ragas]`) | Multi-team sharing, CPU |
| `full` | 4. Engineering and Autonomy | Included (full Eval) | + Self-hosted inference requires GPU nodes (only when evaluating local models) |

### 3.3 Resource Qualification

Evaluation execution (running Agent, scoring) is usually **CPU load**; only when the object being evaluated uses **self-hosted model (local-qwen-vllm)**, GPU inference is triggered through `LLMProvider` - this service itself has no hard dependence on GPU.

### 3.4 Containers and Deliverables

- `Dockerfile`: `python:3.12-slim` base image, Poetry installation dependency; stateless priority, external configuration.
- `helm/`: Deployment + Service + (optional) HPA; rendered in conjunction with `profiles/*.yaml`.
- Scheduling: Kueue queue can be configured under `advanced/full` to share the GPU pool with self-hosted inference (full only).

### 3.5 Dependency verification

`eval` needs to be turned on if `agentRuntime` and `modelProvider` are turned on. The verification logic is declared in the metacang `profiles/*.yaml` and is pre-checked during deployment.

---
## Change record

| Version | Date | Description |
| --- | --- | --- |
| v1.0 | 2026-07-17 | Extract specification skeleton based on `docs/DESIGN.md` §7/§8/§10 |
