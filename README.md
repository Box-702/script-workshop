# 剧本智能体 · Script Adaptation Agent

一款用 **LangGraph + LangChain** 重新架构的「剧本改编 Agent」工作台：把原著文本生成结构化剧本，再由一个有状态、可工具调用、可人机协同的 Agent 提出**可审阅、可局部接受、可回滚**的改编建议。

> 技术栈：Python · LangGraph 1.x · LangChain 1.x · FastAPI · PostgreSQL（+ 可选 Milvus 向量库 RAG）
> 定位：面试 / 简历导向的 Agent 开发强化项目 —— 重点讲「状态图、ReAct、结构化输出、人机协同、checkpointer」。

---

## 1. 为什么做这个项目

市面上的「脚本工具」大多是**一次性生成器**：输入小说 → 吐一份剧本 → 结束。它的价值其实很有限，因为：

1. 一次生成的剧本永远需要人继续改；
2. AI 无脑覆盖会毁掉作者已有的结构；
3. 没有版本、没有回滚、没有「这条改动到底改了什么」。

所以本项目把重心从「AI 一次生成」挪到 **AI 如何安全、可控地参与改写**，这正是 **Agent（智能体）** 的核心命题：

> **Agent 的正确位置不是替用户覆盖文本，而是给出可解释、可选择、可回滚的建议。**

这也是为什么用 LangGraph 而不是裸调 LLM：改写不是一个 prompt 就能完成的动作，而是一个**有状态、需要多步推理、中间需要人参与决策**的流程。

---

## 2. 核心闭环

```text
导入原著文本
  -> 线性生成流水线（故事圣经 -> 场景/节拍）-> 结构化剧本
  -> LangGraph Agent 读取选定场景 + 检索相关原文
  -> ReAct 推理 + 工具调用 -> 生成结构化 patch（提议）
  -> review 节点 interrupt 暂停，用户审阅/局部接受/拒绝
  -> 接受 -> 应用 patch -> 校验 -> 生成新版本（可回滚）
```

**核心约束（与旧项目一致的边界，也是 Agent 设计的红线）：**

1. Agent 输出**结构化 patch**，绝不整份覆盖剧本；
2. 接受 patch 前必须校验，接受后必须生成**新版本**；
3. 节拍 id（`beat_数字`）在改写时保持稳定，便于逐条接受与 diff；
4. 运行记录持久化，跨刷新可恢复审阅、拒绝、重试。

---

## 3. 架构总览

```
┌────────────────────────────────────────────────────────────┐
│  Web (单页演示)          REST API (FastAPI)                 │
│  app/web/index.html  <->  app/api.py                       │
└──────────────────────────────┬─────────────────────────────┘
                               │
   ┌───────────────────────────▼───────────────────────────┐
   │  app/agent.py  运行服务：启动运行 / 恢复审阅 / 兜底      │
   │                                                       │
   │  ┌──────────────── LangGraph 图 ─────────────────┐    │
   │  │  context → plan →(ReAct 循环)→ propose →      │    │
   │  │                 plan → tools → plan …     │    │
   │  │  propose → review(interrupt) → apply→finalize │    │
   │  │                    │(拒绝)→ finalize             │    │
   │  └──────────────────────────────────────────────┘    │
   │      app/nodes.py   app/tools.py   app/state.py        │
   │      + app/generation.py （线性生成流水线）            │
   └──────────────────────────┬───────────────────────────┘
                              │
        ┌─────────────────────┼──────────────────────┐
        │  Postgres（业务数据+checkpointer）│  Milvus（可选 RAG）│
        │  app/store.py、graph.py        │  app/vector.py      │
        └────────────────────────────────┴──────────────────┘
```

### 各模块职责

| 文件 | 职责 |
| --- | --- |
| `app/state.py` | 图状态（AgentState）+ 人类决策模型 `HumanDecision`（accept/edit/regenerate/reject） |
| `app/graph.py` | 把节点/边组装成 StateGraph，接入 checkpointer（Postgres/内存） |
| `app/nodes.py` | 图节点实现：context / plan / propose / guard / review / apply / finalize |
| `app/tools.py` | ReAct 工具：剧本概况、场景详情、原文、版本历史、校验、（可选）RAG 检索 |
| `app/patch.py` | patch 引擎：结构化提议 → 操作清单 → 应用 → 校验 / 兜底 |
| `app/domain.py` | 剧本领域模型（Script / Scene / Character / Beat），含 id 与枚举规整 |
| `app/profiles.py` | 改编类型（短剧/电影/剧集/舞台剧）配置 |
| `app/llm.py` | 模型接入（LangChain ChatOpenAI，OpenAI 兼容），无 key 可回退 |
| `app/generation.py` | 线性生成流水线（故事圣经 → 场景/节拍） |
| `app/vector.py` | 可选向量检索：嵌入器（OpenAI/哈希）+ Milvus/内存后端 + RAG |
| `app/store.py` | 业务持久化（SQLAlchemy + Postgres，可回退 SQLite），含运行步骤轨迹 |
| `app/agent.py` | 运行服务：start / resume / get，含线程丢失兜底与步骤采集 |

---

## 4. 关键技术选型与理由

### 4.1 LangGraph —— 为什么用它而不是顺序调 LLM

改编的本质是**多步 + 需要人类决策**的流程，LangGraph 用「状态图」把这种流程表达成一等公民：

- **状态在节点间显式流动**（`AgentState`），每一步都能看到/修改；
- **节点 + 条件边**表达分支：模型要不要调用工具、用户接受还是拒绝；
- **checkpointer** 让图可中断、可恢复 —— 把「人在一起时再继续」变成现实；
- **消息 reducer（`add_messages`）** 天然支持多轮工具调用。

这就是本项目与「一个 prompt 换一段 JSON」的本质区别。

### 4.2 ReAct 推理 + 工具调用

`plan` 节点把模型 `bind_tools` 后作为推理中枢，`ToolNode` 执行工具，结果回流给模型，形成 **ReAct 循环**。模型决定「是否需要查证」—— 例如查看某个场景全文、检索相关原文片段、查看版本历史、校验一致性。这比把整份剧本硬塞进上下文更可控，也更能体现「让 Agent 自己决定用什么工具」。

### 4.3 人机协同（human-in-the-loop）—— 本项目做扎实的地方

`review` 节点调用 `interrupt(...)`，图会**暂停并把提议呈现给用户**。用户提交一个**结构化的 `HumanDecision`**，再经 `Command(resume=decision)` 恢复。它不是简单的"接受/拒绝"，而是完整支持四种决策：

| 动作 | 含义 | 路由 |
| --- | --- | --- |
| `accept` | 接受（可只接受部分 patch，`patch_indexes`） | → `apply` |
| `edit` | 先人工修改操作清单再接受（`decision.patch`） | → `apply` |
| `regenerate` | 带反馈让 Agent 重做（`feedback` 并入指令） | → `propose`（重新提议后再中断） |
| `reject` | 拒绝，结束本轮 | → `finalize` |

在 `propose` 与 `review` 之间，还有一个 **`guard`（自我审阅）节点**：先把当前 patch **dry-run 应用**并校验，若会破坏结构就写回 `critique` 并**回到 `propose` 自纠错**（有迭代上限），否则才交给人类。这是成熟的"Agent 先自我把关、再请人拍板"的坏味道防线。

这套组合体现了 LangGraph 人机协同与状态编辑的最典型用法：
- `interrupt` 暂停 + `Command(resume=...)` 恢复；
- `Command(goto=...)`（通过条件边回到 `propose`）实现**重做循环**，并在状态里带回反馈；
- 人类直接编辑图状态中待应用的数据（`edit` 路径）；
- 整个过程通过 `graph.stream(..., stream_mode="updates")` 采集**节点级执行轨迹**（如 `context → plan → propose → guard → review`），让运行可观测、可演示。

### 4.4 结构化输出

`propose` 节点用 `model.with_structured_output(PatchProposal)`。模型必须输出受约束的结构（计划 + 逐场景改动），再经 `app/patch.py` 规整成**稳定、可逐条接受**的操作清单。这保证了：

- 每一个改动都是一个原子操作（`add / set / remove`）；
- 前端能逐条展示，用户能逐条接受；
- 接受后能安全应用并生成新版本。

### 4.5 PostgreSQL（代替 SQLite）—— 为什么必须

业务数据（项目/版本/运行记录）需要**持久、可并发、可迁移**，SQLite 只适合单机演示。Postgres 是生产级默认，而且这里还把 **LangGraph checkpointer 也放到 Postgres**：让「审阅了一半的图」跨请求、跨重启都能恢复。这是把「人机协同」真正做扎实的关键。

### 4.6 Milvus（可选）—— 为什么做成可选

本项目 Agent 要「读懂原著」，最自然的增强是**按语义检索最相关的原文片段**（RAG）再交给改写，而不是把整本原文塞进上下文。Milvus 是这一能力的向量库载体。

但它是**可选增强**，不是核心：即便没有 Milvus、没有嵌入模型 key，`retrieve_source` 工具不启用或退化为内存向量 + 哈希嵌入，整个主流程依然闭环。这体现了「为需求选型，而不是为炫技堆技术」。

---

## 5. LangGraph 图拓扑

```text
START → context → plan ──(有工具调用)──> tools → plan   (ReAct 循环)
                       └──(无工具调用)──> propose → guard(自纠错)
                                                │(有问题，未超限)└→ propose（重做循环）
                                                │(通过)          └→ review(interrupt)
                                                                   │
                       ┌──(accept/edit)───────┬─┴──────────┬─┐
                       ▼                      │            │ │
                     apply ──> finalize ──> END          │ │
                                                          │ │
                       ┌──(regenerate 带反馈)──> propose ──┘ │（重新提议后再中断）
                       └──(reject)──────────> finalize ──> END
```

- **context**：收集上下文（剧本概况、人物/地点、原文档、版本历史）。
- **plan**：ReAct 推理中枢（绑定工具），决定调用工具还是收尾进入规划。
- **tools**：执行工具，结果回流给 `plan`。
- **propose**：用结构化输出生成 `PatchProposal` → 规整为 patch 操作。
- **guard**：自我审阅（dry-run 应用 + 校验），有结构问题则回 `propose` 重做。
- **review**：`interrupt` 暂停，把提议交给用户（接受/编辑/重新生成/拒绝）。
- **apply**：按用户选择（或人工修订后的 patch）应用 → 生成新版本。
- **finalize**：记录运行终态（接受/拒绝），写回持久化。

---

## 6. 如何运行

### 方式 A：Docker Compose（推荐，Postgres 为核心栈）

```bash
# 准备环境变量
Copy-Item .env.example .env

# 启动（Postgres + API，API 端口 8000）
docker compose up --build
```

- Web（单页演示） + API：http://localhost:8000
- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/healthz

**可选：启用 Milvus RAG**

```bash
# 额外拉起 Milvus 向量栈（etcd + minio + milvus）
docker compose --profile milvus up -d
# 并在 .env 里设置：
#   ENABLE_RAG=true         /  EMBEDDING_PROVIDER=openai  /  EMBEDDING_API_KEY=...
```

### 方式 B：本地（无 Postgres、无模型 key 也能跑）

```bash
# 使用已有的 conda 环境（已装 langchain 1.x / langgraph 1.x）
$env:DATABASE_URL="sqlite:///./data/dev.db"
$env:CHECKPOINTER="memory"
python -m app.cli        # 端到端命令行演示
python -m uvicorn app.main:app --port 8000   # 启动 API + Web
```

`ENABLE_RAG=false`、`OPENAI_API_KEY=` 留空时，全部走本地回退，链路依然闭环（见测试）。

### 运行测试

```bash
python -m pytest tests -q     # patch 引擎 + Agent 人机协同端到端
```

---

## 7. 给面试讲的话（如何把这个项目讲清楚大纲）

1. **痛点**：一次生成的剧本没法安全地后续修改，AI 无脑覆盖会毁掉作者结构。
2. **方案**：用 LangGraph 把「改写」建模成有状态、可中断的 Agent 流程。
3. **亮点 1 · 状态图 + 条件边**：模型是否用工具、用户接受/编辑/重新生成/拒绝，都用边来表达。
4. **亮点 2 · ReAct + 工具**：Agent 自主决定查看场景/检索原文/查版本/校验。
5. **亮点 3 · 人机协同（成熟版）**：`interrupt` 暂停，`Command.resume` 恢复；支持**接受 / 编辑后接受 / 带反馈重新生成 / 拒绝**四种决策。
6. **亮点 4 · 自我审阅**：`guard` 节点先 dry-run 应用并自纠错，再交给人类，形成"先自保障、再人拍板"。
7. **亮点 5 · 结构化输出**：patch 是原子操作，可逐条审、逐条接受、可回滚。
8. **亮点 6 · 持久化 + 可观测**：Postgres 存业务数据 + checkpointer（跨重启恢复审阅态）；`graph.stream` 采集节点级执行轨迹。
9. **亮点 7 · 可选 RAG**：需要时用 Milvus 检索原文，不需要就优雅降级。
10. **取舍**：生成是线性流水线，改编是有状态 Agent；RAG 是增强不是核心。

> 一句话：**我不是写了「一个调用 LLM 的函数」，而是用 LangGraph 编排了一套「会推理、会查证、会停下来等人类决定、并把决定安全落库」的 Agent 工作流。**

---

## 8. 目录结构

```text
langgraph-rebuild/
├── README.md / pyproject.toml / Dockerfile / docker-compose.yml / .env.example
├── app/
│   ├── main.py        FastAPI 入口 + 极简 Web
│   ├── api.py         REST 路由
│   ├── config.py      配置（Postgres/Milvus/模型）
│   ├── deps.py        依赖单例（store/llm/vector/embedder）
│   ├── state.py       LangGraph 状态
│   ├── graph.py       LangGraph 图编排 + checkpointer
│   ├── nodes.py       图节点
│   ├── tools.py       ReAct 工具
│   ├── patch.py       patch 引擎（核心领域逻辑）
│   ├── domain.py      剧本领域模型
│   ├── profiles.py    改编类型
│   ├── llm.py         模型接入
│   ├── generation.py  生成流水线
│   ├── vector.py      可选 RAG（Milvus/内存）
│   ├── store.py       业务持久化（Postgres/SQLite）
│   ├── agent.py       Agent 运行服务
│   ├── cli.py         命令行演示
│   └── web/index.html 单页演示
├── tests/             patch + Agent 端到端测试
└── data/              本地数据（gitignore）
```

## 9. 后续演进方向

- 把生成流水线也升级为 LangGraph 图（与改编 Agent 共享编排思路）；
- 增加角色弧光、时间线一致性等**多场景全局检查**工具；
- 版本 diff 复用 `patch` 的字段级对比，做更细的审阅；
- Milvus 检索支持跨项目、混合检索（语义 + 关键词）。
