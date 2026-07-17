# ai-eval-service · 编码技能（SKILLS）

> 评估流水线、可插拔评分器、可观测性与安全（PII）。事实源：`design/DESIGN.md`。

## 1. 评估流水线（load → run → score → aggregate）

评测执行是应用层的核心用例（`EvalUseCase`），按四阶段串行推进，每阶段可水平扩展（并行评测用 ThreadPool / Ray）。

### 1.1 流水线总览

```
提交 EvalRun ──> ① load ──> ② run ──> ③ score ──> ④ aggregate ──> 产出 EvalReport
  (绑定 AgentRef +      │         │           │            │           (准确率/安全性/
   DatasetVersion +      │         │           │            │            延迟/成本)
   ScorerSet)            │         │           │            │
                    加载数据集    调用Agent   并行打分      聚合+基线对比
                    按split划分   采集trace   各维度指标    生成报告
```

### 1.2 各阶段编码要点

| 阶段 | 输入 | 处理 | 输出 | 编码要点 |
| --- | --- | --- | --- | --- |
| **load** | `dataset_version`、划分规则 | 从 Repository 加载 Case，按 `split` 切分 | `EvalCase[]` | 数据源可插拔（PG/对象存储/合成生成器）；`split` 过滤在仓库层完成 |
| **run** | `EvalCase[]`、`AgentRef` | 经 `AgentRuntimePort` 调用目标 Agent | `CaseResult{output, trace_ref, latency, cost}` | 线程池并发（`concurrency` 配置）；AgentRuntime 适配器注入 |
| **score** | `CaseResult[]`、`ScorerSet` | 对每个 Case 并行调用各 `ScorerPort` | `Score[]` | 评分器注册表按 `scorer_key` 路由；Score.value 范围校验 |
| **aggregate** | `Score[]`、可选 `baseline_run_id` | 按 `metric_key` 聚合（mean/P95/通过率） | `EvalReport` | 基线 diff 计算 `regression_delta`；支持报告导出格式 |

### 1.3 并行执行模式

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

        # Phase run: 并行执行 Agent
        with ThreadPoolExecutor(max_workers=self._concurrency) as pool:
            futures = {pool.submit(self._agent.run_case, run.agent_ref, c): c for c in cases}
            for f in as_completed(futures):
                results.append(f.result())
                self._update_progress(run, len(results), len(cases))

        # Phase score: 每个 Case 经每个 Scorer 打分
        for case, result in zip(cases, results):
            for key in run.scorer_set:
                scorer = self._scorers.get(key)
                scores.extend(scorer.score(case, result))

        # Phase aggregate
        report = self._aggregate(run, scores)
        self._repo.save_report(report)
        return report
```

### 1.4 状态管理

`EvalRun.status` 状态机通过 Redis 缓存 + PG 持久化双写：

```
pending → running → scoring → aggregated → done
           ↘ (任意阶段异常) → failed
```

- 幂等：同一 `run_id` 重复提交通过 Redis 去重。
- 可取消：`POST /v1/runs/{run_id}/cancel` 设置取消标志，各阶段检查并提前退出。

---
## 2. 指标与评分器设计（Pluggable Scorers）

评分器可插拔：领域层定义 `ScorerPort`，每个外部评测框架作为**适配器（Adapter）**实现端口。新增评分维度 = 新增一个 Adapter，领域层与已有用例零改动（依赖倒置 DIP）。

### 2.1 评分器矩阵

| Scorer（Adapter） | BOM 组件 | 版本 | 状态 | SPI | 评测维度 |
| --- | --- | --- | --- | --- | --- |
| `PromptfooScorer` | promptfoo | 0.90.0 | **core**（默认开） | `Eval` | 准确率/安全性/一致性/红队注入 |
| `DeepEvalScorer` | deepeval | 2.0.0 | optional | `Eval` | 幻觉率/毒性/偏见/格式 |
| `RagasScorer` | ragas | 0.2.0 | optional | `Eval` | 忠实度/答案相关性/上下文精度 |

### 2.2 评分器实现模式

```python
class PromptfooScorer:
    """Promptfoo 评分器适配器 —— 封装 promptfoo CLI 为 ScorerPort。"""
    scorer_key = "promptfoo"
    supported_metrics = ["accuracy", "security", "consistency", "redteam"]

    def __init__(self, config: PromptfooConfig):
        self._config = config

    def score(self, case: EvalCase, result: CaseResult) -> list[Score]:
        # 构建 promptfoo 测评配置
        promptfoo_config = self._build_config(case, result)
        # 调用 promptfoo eval（子进程或 SDK）
        raw_scores = promptfoo_evaluate(promptfoo_config)
        # 归一化到 Score 领域对象
        return [
            Score(case_id=case.case_id, metric_key=m.metric, value=m.score, reason=m.reason)
            for m in raw_scores.results
        ]
```

### 2.3 新增评分器步骤

1. 在 `infrastructure/adapters/` 实现 `ScorerPort`，封装对应框架 CLI/SDK。
2. 以 `scorer_key` 注册到 `ScorerRegistry`（经 DI 容器）。
3. 若需新 Metric，在领域层 `Metric` 枚举声明 `metric_key` + 方向 + 阈值。
4. 提供 SPI 契约测试（`Eval: 1.0.0` 端口一致性断言）。

### 2.4 评分器配置

```yaml
# scorer_set 选择示例（对应评测运行请求）
scorer_set:
  - promptfoo_accuracy        # core 默认
  - promptfoo_security        # 红队/注入
  - deepeval_hallucination    # optional，点亮 deepeval 后可用
  - ragas_faithfulness        # optional，RAG 场景
```

---
## 3. 可观测性与安全（PII 数据保护）

### 3.1 可观测性支柱

| 支柱 | 选型 | 本服务落地 |
| --- | --- | --- |
| 基础 Tracing + Audit（**core**） | OpenTelemetry + 不可变审计日志 | 每次 Run/Score 打 OTel Span（含 `run_id`/`tenant_id`/`agent_id`）；所有写操作留痕 |
| Metrics（推荐） | Prometheus + Grafana | 暴露 `eval_runs_total`、`eval_score_latency`、`scorer_errors`；报告可 `export?fmt=grafana` |
| LLM 专项 Tracing（optional） | Langfuse | 经 `TracingAdapter` 关联评测轨迹与线上链路 |

### 3.2 OTel Span 编码规范

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
    # ... 执行流水线
```

### 3.3 安全与 PII 处理

评测数据往往含真实用户语料（线上采样 1%、Bad Case），PII 处理是核心安全项。

| 措施 | 实现 | 性质 |
| --- | --- | --- |
| **PII 扫描 + 脱敏** | 接入平台基础风控 `riskControl.pii_scan` 端口，入库前对 `inputs`/`expected` 做 NER 检测与掩码 | core |
| **注入/越狱检测** | 复用 `riskControl.injection_scan`；评测数据集中的对抗样本经 `promptfoo` 红队打分 | core |
| **频率异常/限流** | `riskControl.rate_limit` 保护评测 API | core |
| **租户隔离** | 所有数据集/报告表带 `tenant_id`，经 `Auth` Port（Keycloak）强制行级隔离 | core |
| **输出敏感信息检测** | 评分后结果经 `pii_scan` 二次校验，避免报告泄露原始 PII | core |
| **高级护栏** | 幻觉检测/合规规则/人工审批，由 `security` 开关启用 | optional |

### 3.4 PII 数据流

```
评测数据入库 ──> PII 扫描 + 脱敏 ──> 脱敏后入库 (tenant_id 隔离)
(人工/合成/线上采样/BadCase)         │
                                      ├──> 评测执行 + 评分
                                      │         │
                                      │    ┌────┘
                                      ▼    ▼
                              报告输出前二次 PII 校验 ──> 安全报告
                              对抗样本 ──> Promptfoo 红队打分 (injection_scan)
```

**设计原则**：本服务**不自研** PII/注入检测，统一经平台基础风控端口（core 基线），避免重复与策略漂移。

### 3.5 Prometheus Metrics 暴露

```python
from prometheus_client import Counter, Histogram

eval_runs_total = Counter("eval_runs_total", "Total eval runs", ["status", "tenant_id"])
eval_score_latency = Histogram("eval_score_latency_seconds", "Score latency")
scorer_errors = Counter("scorer_errors_total", "Scorer errors", ["scorer_key"])
```

---
## 变更记录

| 版本 | 日期 | 说明 |
| --- | --- | --- |
| v1.0 | 2026-07-17 | 基于 `design/DESIGN.md` §4/§5/§11 提取技能骨架 |
