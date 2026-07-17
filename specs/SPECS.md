# ai-eval-service · 规格契约（SPECS）

> API 设计（REST/SDK）、数据模型（存储）、配置与部署。事实源：`design/DESIGN.md`。

## 1. API 设计（REST / SDK 契约）

接入层（DDD ①）用 FastAPI 暴露 REST，Pydantic v2 作 Schema 与校验。所有写接口经 `Auth` Port 注入租户上下文（`tenant_id` 来自 Keycloak Token）。

### 1.1 REST 端点契约

| 方法 | 路径 | 用例 | 说明 |
| --- | --- | --- | --- |
| `POST` | `/v1/datasets` | R1 | 创建数据集 |
| `GET` | `/v1/datasets/{id}?version=` | R1 | 获取数据集（含版本） |
| `POST` | `/v1/datasets/{id}/cases` | R2 | 新增评测用例 |
| `POST` | `/v1/runs` | R3/R4 | 提交评测运行（绑定 AgentRef + 数据集版本 + scorer_set） |
| `GET` | `/v1/runs/{run_id}` | R3 | 查询运行进度 |
| `POST` | `/v1/runs/{run_id}/cancel` | R3 | 取消运行 |
| `POST` | `/v1/runs/{run_id}/score` | R5 | 触发/重跑评分（可指定 scorer 子集） |
| `GET` | `/v1/reports/{report_id}` | R6 | 获取聚合报告（支持 `?baseline=run_id` 回归对比） |
| `GET` | `/v1/reports/{report_id}/export?fmt=md\|json\|grafana` | R6 | 报告导出 |

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
    version: str | None = None          # 不填则取当前线上版本

class RunCreate(BaseModel):
    dataset_id: str
    dataset_version: str
    agent: AgentRef
    scorer_set: list[str] = Field(..., min_length=1)
    split: Split = Split.eval
    baseline_run_id: str | None = None  # 回归对比基线

class RunView(BaseModel):
    run_id: str
    status: RunStatus
    progress: float = Field(ge=0, le=1)
    metrics_summary: dict = {}

class ReportView(BaseModel):
    report_id: str
    run_id: str
    baseline_run_id: str | None
    metrics_summary: dict[str, float]       # metric_key -> 聚合值
    regression_delta: dict[str, float] | None
```

### 1.3 FastAPI 路由骨架

```python
from fastapi import APIRouter, Depends, HTTPException

router = APIRouter(prefix="/v1", tags=["eval"])

@router.post("/runs", response_model=RunView, status_code=202)
async def create_run(body: RunCreate, tenant_id: str = Depends(get_tenant_id)):
    """提交评测运行，异步执行。"""
    ...

@router.get("/runs/{run_id}", response_model=RunView)
async def get_run(run_id: str, tenant_id: str = Depends(get_tenant_id)):
    """查询评测运行进度。"""
    ...

@router.get("/reports/{report_id}", response_model=ReportView)
async def get_report(report_id: str, baseline: str | None = None,
                     tenant_id: str = Depends(get_tenant_id)):
    """获取聚合报告，支持回归对比。"""
    ...
```

### 1.4 SDK 消费契约

```python
# 面向 ai-sdk-python 消费方
from openstrata.sdk import EvalClient
client = EvalClient(base_url="http://ai-eval-service", token="<keycloak-token>")
run = client.runs.create(
    dataset_id="qa-golden", dataset_version="v3",
    agent={"agent_id": "customer-service", "tenant_id": "t-b"},
    scorer_set=["promptfoo_accuracy", "deepeval_hallucination"],
)
report = client.reports.wait(run.run_id)      # 轮询至 done
print(report.metrics_summary)
```

### 1.5 兼容性承诺

REST 前缀 `/v1`、SPI `Eval: 1.0.0`。破坏性变更须 bump `MAJOR` 并附 ADR。

---
## 2. 数据模型与存储

存储遵循 §4.9 底座：`PostgreSQL 16`（关系/结构化）+ `Redis 7.4`（任务状态/缓存）。领域层定义 `EvalRepositoryPort`，基础设施层以 SQLAlchemy 实现。

### 2.1 核心表 DDL

```sql
-- 评估数据集（版本化复合主键）
CREATE TABLE eval_dataset (
    dataset_id   TEXT,
    version      TEXT,
    name         TEXT,
    source       TEXT,            -- human|synthetic|online_sample|badcase
    split        TEXT,
    dist_meta    JSONB,           -- 类别/长度/难度分布
    tenant_id    TEXT NOT NULL,
    created_at   TIMESTAMPTZ DEFAULT now(),
    PRIMARY KEY (dataset_id, version)
);

-- 评测用例
CREATE TABLE eval_case (
    case_id    TEXT PRIMARY KEY,
    dataset_id TEXT NOT NULL,
    version    TEXT NOT NULL,
    inputs     JSONB NOT NULL,
    expected   JSONB,
    contexts   JSONB,            -- RAG 场景检索上下文
    tags       TEXT[],           -- 归因标签：hallucination|security|format|...
    FOREIGN KEY (dataset_id, version) REFERENCES eval_dataset(dataset_id, version)
);

-- 评测运行
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

-- 单条得分
CREATE TABLE eval_score (
    run_id     TEXT NOT NULL,
    case_id    TEXT NOT NULL,
    metric_key TEXT NOT NULL,
    value      REAL NOT NULL,
    reason     TEXT,
    PRIMARY KEY (run_id, case_id, metric_key)
);

-- 聚合报告
CREATE TABLE eval_report (
    report_id        TEXT PRIMARY KEY,
    run_id           TEXT NOT NULL UNIQUE,
    baseline_run_id  TEXT,
    metrics_summary  JSONB NOT NULL DEFAULT '{}',
    regression_delta JSONB
);
```

### 2.2 存储分工

| 数据类型 | 存储 | 说明 |
| --- | --- | --- |
| 数据集/用例/运行/得分/报告 | PostgreSQL | 持久化事实源；版本化靠复合主键 |
| 运行进度/评分中间结果缓存 | Redis | 高并发读写、幂等去重 |
| 大规模合成数据/轨迹附件 | 对象存储（MinIO，optional） | 大体积不落 PG |
| 实验指标历史（可选） | MLflow（阶段四 MLOps） | 跨版本趋势 |

### 2.3 SQLAlchemy ORM 模型骨架

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

### 2.4 划分策略

数据集划分（Train/Eval/Test）为**逻辑划分**（按 `split` 列 + 配置化规则），不物理复制，降低存储成本。`split` 枚举：`train | eval | test`。

---
## 3. 配置与部署

### 3.1 配置片段

本仓只持有**局部配置片段**，全局由元仓 `openstrata-meta/dependencies/config/` 渲染。

```yaml
# ai-eval-service/infrastructure/config/eval.yaml
eval:
  enabled: true
  # 评分器开关：core 默认开 promptfoo，optional 按需点亮
  scorers:
    promptfoo:  { enabled: true,  version: "0.90.0" }
    deepeval:   { enabled: false, version: "2.0.0" }
    ragas:      { enabled: false, version: "0.2.0" }
  execution:
    concurrency: 16            # 并行评测线程数
    backend: threadpool        # threadpool | ray（大数据集）
  storage:
    postgres: { dsn_env: PGDSN }
    redis:    { enabled: true }
  integrations:
    agentRuntime: langgraph
    llmProvider:  [qwen-cloud, openai]
    vectorStore:  qdrant
    tracing:      langfuse
```

### 3.2 部署形态（四档预制）

| Profile | 阶段 | 是否含本服务 | 资源 |
| --- | --- | --- | --- |
| `starter` | 一·尝鲜 | 默认关 | N/A |
| `standard` | 二·增强 | 可选（点亮 `eval`） | K8s 单租户，CPU 为主 |
| `advanced` | 三·规模化治理 | 含（`eval: [promptfoo, deepeval, ragas]`） | 多团队共享，CPU |
| `full` | 四·工程化与自治 | 含（全量 Eval） | + 自托管推理需 GPU 节点（仅评测本地模型时） |

### 3.3 资源定性

评测执行（跑 Agent、打分）通常为 **CPU 负载**；仅当被评对象使用**自托管模型（local-qwen-vllm）** 时，才经 `LLMProvider` 触发 GPU 推理——本服务本身无 GPU 硬依赖。

### 3.4 容器与交付物

- `Dockerfile`：`python:3.12-slim` 基础镜像，Poetry 安装依赖；无状态优先，配置外置。
- `helm/`：Deployment + Service +（可选）HPA；与 `profiles/*.yaml` 联动渲染。
- 调度：`advanced/full` 下可配 Kueue 队列，与自托管推理共享 GPU 池（仅 full）。

### 3.5 依赖校验

`eval` 点亮需 `agentRuntime` 与 `modelProvider` 已开。校验逻辑在元仓 `profiles/*.yaml` 中声明，部署时做前置检查。

---
## 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0 | 2026-07-17 | 基于 `design/DESIGN.md` §7/§8/§10 提取规格骨架 |
