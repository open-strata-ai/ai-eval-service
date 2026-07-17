# ai-eval-service · 架构文档（ARCH）

> 定位与边界、职责清单、领域模型、外部集成（Adapter）。事实源：`design/DESIGN.md`。

## 1. 定位与边界

`ai-eval-service` 是 OpenStrata 的**评测服务（Evaluation Service）**，位于 `ai-native` 域，是 Agent 全生命周期（§6）中"评测阶段（§6.3）"与"MLOps 与评测层（§4.6）"的工程承载者。以 `Eval` SPI（`bom.yaml` `interface_versions.Eval = 1.0.0`）为统一端口，将 Promptfoo / DeepEval / Ragas 等外部评测框架收敛为平台内可编排、可替换的评测能力。

**单一职责**：评估数据管理 + 评测执行 + 指标评分 + 报告聚合。

### 1.1 不负责

| 维度 | 负责方 |
| --- | --- |
| 在线对话 / 推理 | `ai-gateway-core`（LLMProvider SPI） |
| Agent 运行时编排 | `ai-gateway-core` + AgentRuntime（LangGraph） |
| 线上 LLM 追踪 | Langfuse（Tracing SPI） |
| 评测报告展示 UI | `ai-portal-frontend` / `ai-admin-frontend` |
| 模型微调 / 实验追踪 | MLflow（MLOps SPI，阶段四） |

### 1.2 分层位置

属于"AI 原生"应用层能力，经 SPI 适配外部评测框架。被 `ai-platform-api` 异步投递评测任务（图中 `EV`），产出报告回流。

### 1.3 可选性

R1–R7 全部 `optional`，随 `openstrata.yaml` 的 `eval` 开关点亮（§12.1）。PII 扫描（R8）复用平台基础风控。

---
## 2. 职责清单

按 DDD 应用层用例拆分，对外承诺以下能力：

| # | 职责 | 说明 |
| --- | --- | --- |
| R1 | **评估数据集管理** | 创建 / 版本化 / 划分（Train·Eval·Test）/ 分布分析 / Bad Case 入库 |
| R2 | **评测用例（Case）管理** | 单条 Case 的输入 / 期望 / 上下文 / 标签（幻觉/安全/格式等归因标签） |
| R3 | **评测任务编排** | 提交评测运行、绑定目标 Agent（AgentRuntime）、选择评分器集合、进度追踪 |
| R4 | **评测执行（Run）** | 加载数据 → 调用 AgentRuntime 执行 → 采集轨迹/输出 |
| R5 | **指标评分（Score）** | 通过可插拔 Scorer（Promptfoo/DeepEval/Ragas）对输出打分 |
| R6 | **结果聚合与报告** | 聚合指标、生成 Report（准确率/安全性/延迟/成本等），支持回归对比 |
| R7 | **回归/安全/RAG 评测** | 回归对比、红队注入（Promptfoo Red Team）、RAG 忠实度专项评测 |
| R8 | **PII 与数据安全** | 评测数据集 PII 扫描、脱敏、访问隔离（复用平台基础风控端口） |

---
## 3. 领域概念与模型

领域层以**纯逻辑、零外部依赖**定义聚合与实体。核心聚合根：`EvalDataset`、`EvalRun`、`EvalReport`。

### 3.1 领域词汇表

| 概念 | 含义 | 关键属性 |
| --- | --- | --- |
| **EvalDataset** | 一组评测用例的集合，带版本 | `dataset_id`、`name`、`version`、`split`（train/eval/test）、`source`（人工/合成/线上采样/BadCase）、分布元数据 |
| **EvalCase** | 单条评测用例 | `case_id`、`inputs`、可选 `expected`/`reference`、RAG `contexts`、归因 `tags` |
| **Metric** | 一个评分维度（如准确率/忠实度/幻觉率） | `metric_key`、`scorer`、`direction`（max/min）、阈值 |
| **Score** | 某 Case 在某 Metric 下的得分 | `case_id`、`metric_key`、`value`、`reason`、`trace_ref` |
| **EvalRun** | 一次评测执行（绑定数据集+Agent+评分器集） | `run_id`、`agent_ref`、`dataset_version`、`status`、`progress` |
| **EvalReport** | 一次 Run 的聚合结果 | `report_id`、`run_id`、各 Metric 聚合值、对比基线 |

### 3.2 聚合关系

```
EvalDataset (1)  *--  (0..*) EvalCase      : contains
EvalRun     (1)  *--  (0..*) Score          : produces
EvalRun     (1)  -->  (1)   EvalReport      : aggregated into
EvalDataset (1)  -->  (0..*) EvalRun        : evaluated by
```

### 3.3 领域约束

- `EvalDataset.version` 由领域服务在每次内容变更时自增（语义化版本，对接 §6.4 版本管理）。
- `EvalRun.status` 状态机：`pending → running → scoring → aggregated → done | failed`。
- `Score.value` 必须落在 Scorer 声明的 `[min, max]` 范围，否则领域层拒绝并标记 Run 为 `failed`。
- `tag_categories` 归因标签枚举：`hallucination`（幻觉）、`security`（安全/注入）、`format`（格式错误）、`toxicity`（毒性）、`bias`（偏见）、`factuality`（事实性）。

### 3.4 端口定义（领域层端口）

```python
# AgentRuntime 端口 —— 领域层仅定义接口，不依赖实现
class AgentRuntimePort(Protocol):
    def run_case(self, ref: AgentRef, case: EvalCase) -> CaseResult:
        """调用目标 Agent 执行单条评测用例，返回输出与可观测轨迹引用。"""
        ...

# Scorer 端口 —— 可插拔评分器接口
class ScorerPort(Protocol):
    scorer_key: str
    supported_metrics: list[str]
    def score(self, case: EvalCase, result: CaseResult) -> list[Score]:
        """对单个 Case 的输出进行评分，返回一个或多个维度的得分。"""
        ...

# Repository 端口 —— 数据持久化抽象
class EvalRepositoryPort(Protocol):
    def save_dataset(self, dataset: EvalDataset) -> None: ...
    def load_cases(self, dataset_id: str, version: str, split: str) -> list[EvalCase]: ...
    def save_run(self, run: EvalRun) -> None: ...
    def save_scores(self, run_id: str, scores: list[Score]) -> None: ...
    def load_report(self, report_id: str) -> EvalReport: ...
```

---
## 4. 外部集成（Adapter 防腐层）

评测服务本身**不持有**模型与向量能力，全部经对应 SPI 的 Adapter（ACL 防腐层）接入，保证同类多实现可切换、外部语义不泄漏。

### 4.1 依赖能力矩阵

| 依赖能力 | SPI 端口 | 默认实现 | 本服务用途 | 适配器类 |
| --- | --- | --- | --- | --- |
| 模型供给 | `LLMProvider` (`1.0.0`) | Qwen/OpenAI/Claude | Agent 推理调用；合成数据生成 | `LLMProviderAdapter` 经网关统一出口 |
| 向量检索 | `VectorStore` (`1.1.0`) | Qdrant | RAG 评测（Ragas）检索上下文忠实度 | `VectorStoreAdapter` |
| Agent 运行时 | `AgentRuntime` (`1.3.0`) | LangGraph | 执行被评 Agent | `AgentRuntimeAdapter` |
| LLM 追踪 | `Tracing` | Langfuse（optional） | 评测轨迹留痕、报告关联 | `TracingAdapter` |
| 缓存/KV | `Cache` (`1.0.0`) | Redis | 任务状态、评分结果临时缓存 | `CacheAdapter` |
| 认证授权 | `Auth` (`1.0.0`) | Keycloak | 数据集/报告的租户隔离与访问控制 | `AuthAdapter` |

### 4.2 适配器架构

```
┌──────────────────────────────────────────────┐
│            ai-eval-service 内部               │
│  领域层: ScorerPort / AgentRuntimePort /     │
│          LLMProviderPort / EvalRepositoryPort │
└────────────┬─────────────────────────────────┘
             │ 实现 Port（依赖倒置 DIP）
┌────────────▼─────────────────────────────────┐
│         基础设施层 Adapter（ACL）              │
│  AgentRuntimeAdapter  →  ai-gateway-core     │
│  LLMProviderAdapter   →  ai-gateway-core     │
│  VectorStoreAdapter   →  Qdrant / Milvus     │
│  TracingAdapter       →  Langfuse            │
│  CacheAdapter         →  Redis               │
│  AuthAdapter          →  Keycloak            │
└──────────────────────────────────────────────┘
```

### 4.3 适配器注册与 DI

适配器通过依赖注入（DI）容器注册，领域层通过端口抽象调用：

```python
# 基础设施层注册
container.register(AgentRuntimePort, AgentRuntimeAdapter, singleton=True)
container.register(LLMProviderPort, LLMProviderAdapter, singleton=True)
container.register(ScorerPort, PromptfooScorer, key="promptfoo")
container.register(ScorerPort, DeepEvalScorer, key="deepeval")
container.register(ScorerPort, RagasScorer, key="ragas")
```

### 4.4 Scorer 注册表（ProviderSelector）

```python
class ScorerRegistry:
    """按 scorer_key 选择已注册的适配器实例。"""
    def __init__(self, scorers: dict[str, ScorerPort]):
        self._scorers = scorers

    def get(self, scorer_key: str) -> ScorerPort:
        if scorer_key not in self._scorers:
            raise UnknownScorerError(f"Unknown scorer: {scorer_key}")
        return self._scorers[scorer_key]

    def list_enabled(self) -> list[str]:
        return list(self._scorers.keys())
```

### 4.5 GPU 边界说明

- 阶段一~三仅第三方 LLM API（无需 GPU）。
- 自托管推理（vLLM）仅阶段四 full 档点亮，且始终经 `LLMProvider` SPI 切换，对评测用例零改动。
- 本服务本身**无 GPU 硬依赖**，评测执行（跑 Agent、打分）通常为 **CPU 负载**。

---
## 5. DDD 分层映射

```
接入层（①）      FastAPI router → Pydantic Schema → 用例层
应用层（②）      EvalUseCase（编排 load→run→score→aggregate）
领域层（③）      EvalDataset / EvalRun / EvalReport（聚合根）
                  + 端口接口（AgentRuntimePort / ScorerPort / EvalRepositoryPort）
基础设施层（④）   SQLAlchemy Repository、Adapter 实现（LangGraph / Promptfoo / Qdrant）
```

- **领域层纯逻辑**：零框架依赖，可脱离 DB/FASTAPI 单测。
- **基础设施层封装外部**：Adapter 作为防腐层（ACL），隔离外部框架语义泄漏。
- **应用层编排用例**：持有端口抽象、调度领域对象，不关心基础设施细节。

### 5.1 Repository 目录结构

```
ai-eval-service/
├── src/
│   ├── domain/                    # ③ 领域层（纯逻辑，零外部依赖）
│   │   ├── model/                 # EvalDataset / EvalCase / EvalRun / Score / EvalReport
│   │   ├── port/                  # 端口接口（AgentRuntimePort / ScorerPort / EvalRepositoryPort）
│   │   └── service/               # 领域服务（版本化、状态机、聚合算法）
│   ├── application/               # ② 应用层（用例编排）
│   │   └── usecase/               # EvalUseCase（load→run→score→aggregate）
│   ├── interface/                 # ① 接入层（FastAPI + Pydantic）
│   │   ├── rest/                  # REST 路由与中间件
│   │   └── schema/                # 请求/响应 Pydantic 模型
│   ├── infrastructure/            # ④ 基础设施层
│   │   ├── adapter/               # SPI 适配器实现（ACL 防腐层）
│   │   ├── repository/            # SQLAlchemy Repository 实现
│   │   └── config/                # 本仓局部配置片段
│   └── di/                        # 依赖注入容器（Adapter 注册、ScorerRegistry）
├── tests/
│   ├── unit/                      # 领域层纯逻辑单测（pytest）
│   ├── integration/               # Adapter + DB 集成测试（testcontainers）
│   ├── contract/                  # SPI 端口契约测试
│   └── e2e/                       # 端到端测试（FastAPI TestClient）
├── pyproject.toml  Dockerfile  helm/
└── arch/  design/  skills/  specs/
```

### 5.2 依赖注入容器

```python
# src/di/container.py
class Container:
    """轻量 DI 容器，按需装配 Adapter 实现到端口。"""
    def __init__(self, config: EvalConfig):
        self._registry: dict[type, dict[str, object]] = {}

    def register(self, port: type, impl: object, key: str = "default"):
        if port not in self._registry:
            self._registry[port] = {}
        self._registry[port][key] = impl

    def resolve(self, port: type, key: str = "default") -> object:
        return self._registry[port][key]

# 装配示例
container = Container(config)
container.register(AgentRuntimePort, AgentRuntimeAdapter())
container.register(EvalRepositoryPort, SqlAlchemyEvalRepository(session_factory))
container.register(ScorerPort, PromptfooScorer(config), key="promptfoo_accuracy")
container.register(ScorerPort, DeepEvalScorer(config), key="deepeval_hallucination")
container.register(ScorerPort, RagasScorer(config), key="ragas_faithfulness")
```

### 5.3 技术栈约束

| 层级 | 框架/库 | 版本 | 说明 |
| --- | --- | --- | --- |
| 接入层 | FastAPI + Pydantic v2 | latest | REST 接口 + 请求校验 |
| 应用层 | 纯 Python | — | 用例编排，无框架依赖 |
| 领域层 | 纯 Python + Protocols | — | 领域模型 + 端口抽象 |
| 基础设施 DB | SQLAlchemy 2.0 + asyncpg | latest | PostgreSQL 异步访问 |
| 基础设施缓存 | redis-py (async) | latest | Redis 任务状态/缓存 |
| DI | 自研轻量容器 或 `dependency-injector` | — | Adapter ↔ Port 装配 |
| 测试 | pytest + testcontainers | latest | 三层测试（domain/infra/e2e） |

---
## 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0 | 2026-07-17 | 基于 `design/DESIGN.md` §1/§2/§3/§6 提取架构骨架 |
