# 剧本智能体（Script Adaptation Agent）

基于 LangGraph 的剧本改编 Agent 工作台。它不是一次性生成工具，而是一套有状态、可调用工具、可人机协同的改写系统：AI 给出可解释、可逐条选择、可回滚的修改建议，由人来决定接受、编辑或拒绝。

- Python 3.12+ / LangGraph 1.x / LangChain 1.x / FastAPI
- 后端 FastAPI（REST + 流式对话），前端 Vue 3 + Vite
- 可选 Postgres（业务库 + checkpointer）与 Milvus（RAG 向量库）

## 为什么做这个项目

市面上常见的剧本工具大多是「一次性生成」：输入小说，吐出一份剧本，结束。这类工具价值有限，因为：

1. 一次生成的剧本仍需要人工继续修改；
2. AI 无脑覆盖会破坏作者已有的结构；
3. 没有版本、没有回滚，也说不清「这条改动到底改了什么」。

这个项目把重心从「AI 一次生成」移到「AI 如何安全、可控地参与改写」，这才是 Agent 的核心命题。

## 功能

- **状态图编排**：LangGraph StateGraph + 条件边，模型是否用工具、用户是否接受都用边来表达。
- **ReAct 工具调用**：Agent 自主决定查看场景详情、检索原文、查版本历史、校验。
- **人机协同**：`interrupt` 暂停图执行，`Command.resume` 恢复；支持接受 / 编辑 / 重新生成 / 拒绝四种决策。
- **自我审阅**：`guard` 节点先 dry-run 应用并自纠错，再交给人类。
- **评审打分 + 一致性保障**：guard 之上再跑一次 LLM 审阅，对提议按「忠实度 / 一致性 / 冲突 / 风格 / 结构」五维打分（0-100）；总分低于阈值或存在 error 级一致性问题（人物 OOC、设定 / 时间线冲突、结构断裂、风格偏离）时自动回炉重做。评审结果以「评审卡片」在审阅抽屉展示。
- **接地气的混合检索**：RAG 检索以「改编需求 + 场景 / 题材」为 query，联动向量 + 关键词 + 正文覆盖三类信号做重排，并可按 kind 均衡覆盖知识库，让命中的原文与同类剧本知识真正服务于本次改编目标。
- **结构化输出**：patch 是原子操作，可逐条审、逐条接受、可回滚。
- **对话式交互**：用自然语言完成从导入、改编到审阅的整套流程。
- **项目级知识 RAG**：每个项目维护「同类走向 / 写作手法 / 作者风格」三类记忆。
- **剧本导出**：一键导出为 `.txt / .md / .docx`。
- **剧本编辑器**：直接改台词、动作、场景，保存成新版本（复用 patch 引擎）。
- **编剧设定**：项目面板维护人物小传、时间线、伏笔清单。
- **版本里程碑**：给版本打「草稿 / 候选 / 终稿」标记，一键定为终稿。
- **工作目录**：默认落盘，或指定真实磁盘文件夹，或仅应用内不落盘。
- **本地文件浏览**：直接查看 / 下载 `data/<剧名>/` 下的剧本文件。
- **持久化 + 可观测**：Postgres 存业务数据与 checkpointer；`graph.stream` 采集节点级执行轨迹。

## 架构

- `app/api.py`：REST 路由 + SSE 流式对话，对外提供 `/api/*`。
- `app/chat.py`：对话式 Agent（ChatConductor），持有工具集并编排对话。
- `app/agent.py`：运行服务，负责启动运行、恢复审阅与兜底。
- `app/graph.py` + `app/nodes.py` + `app/tools.py` + `app/state.py`：把节点和边组装成 LangGraph StateGraph，接入 checkpointer 实现中断与恢复。
- `app/store.py`：业务持久化（SQLAlchemy，Postgres / SQLite）。
- `app/vector.py`：向量检索层（Milvus，不可用时退化为内存向量 + 哈希嵌入）。
- `frontend/`：Vue 3 + Vite 单页，`/api` 请求代理到后端。

### LangGraph 图拓扑

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
                       ┌──(regenerate 带反馈)──> propose ──┘ │
                       └──(reject)──────────> finalize ──> END
```

## 快速开始

应用在本机直接运行（uvicorn / vite）。Docker 只用来提供基础设施：Postgres（业务库 + checkpointer）与可选的 Milvus 向量库。不插数据库也能跑通演示链路。

### 方式一：本机运行（零基础设施）

```bash
# 1. 安装依赖（建议先 conda activate langgraph）
pip install -e ".[dev]"

# 2. 配置环境变量（可选，不配也能跑通演示）
export DATABASE_URL="sqlite:///./data/dev.db"
export CHECKPOINTER="memory"

# 3. 运行命令行演示
python -m app.cli

# 4. 启动 API（后端，托管 REST + 前端构建产物）
uvicorn app.main:app --port 8000 --reload

# 5. 启动前端（Vue 3 + Vite，开发模式 /api 自动代理到 8000）
cd frontend && npm install && npm run dev
# 打开 http://localhost:5173

# （可选）构建前端产物，之后 FastAPI 会直接在 http://localhost:8000 托管
npm run build
```

`ENABLE_RAG=false`、`OPENAI_API_KEY=` 留空时，全部走本地回退，链路依然闭环。

### 方式二：用 Docker 提供基础设施（Postgres / 可选 Milvus）

应用仍在本机跑，Docker 只负责数据库。适合要用 Postgres checkpointer 实现跨重启恢复，或启用 Milvus RAG 的场景。

```bash
# 1. 准备环境变量
cp .env.example .env

# 2. 启动 Postgres（默认）
docker compose up -d

# （可选）额外拉起 Milvus 向量栈
docker compose --profile milvus up -d
# 并在 .env 里设置：ENABLE_RAG=true、EMBEDDING_PROVIDER=openai、EMBEDDING_API_KEY=your_key

# 3. 本机安装依赖并连 Postgres 启动
pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg://script:script@localhost:5432/script_agent"
export CHECKPOINTER="postgres"
export CHECKPOINT_DSN="postgresql://script:script@localhost:5432/script_agent"
uvicorn app.main:app --port 8000

# 4. 前端：构建产物由 FastAPI 托管（:8000），或用 Vite 开发模式
cd frontend && npm install && npm run build
```

两种方式访问入口相同：

- Web：http://localhost:8000
- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/healthz

## 项目结构

```
Script Workshop/
├── README.md                 # 项目说明
├── pyproject.toml            # Python 包配置
├── docker-compose.yml        # 基础设施编排（Postgres + 可选 Milvus）
├── .env.example              # 环境变量模板
├── LICENSE                   # MIT 许可证
│
├── app/                      # 核心应用
│   ├── main.py               # FastAPI 入口 + 托管前端
│   ├── api.py                # REST 路由（对话 / SSE / 文件导入）
│   ├── chat.py               # 对话式 Agent（ChatConductor）
│   ├── knowledge.py          # 项目级改编知识 RAG
│   ├── importer.py           # 原著文件导入（.txt/.md/.docx）
│   ├── config.py             # 配置管理
│   ├── deps.py               # 依赖单例
│   ├── state.py              # LangGraph 状态定义
│   ├── graph.py              # LangGraph 图编排
│   ├── nodes.py              # 图节点实现
│   ├── tools.py              # ReAct 工具集
│   ├── patch.py              # patch 引擎（核心领域逻辑）
│   ├── domain.py             # 剧本领域模型
│   ├── export.py             # 剧本导出（.txt / .md / .docx 渲染）
│   ├── workspace.py          # 工作目录（真实磁盘文件夹 + 结构化分格）
│   ├── profiles.py           # 改编类型配置
│   ├── llm.py                # 模型接入层
│   ├── generation.py         # 生成流水线
│   ├── vector.py             # 可选 RAG（Milvus/内存）
│   ├── store.py              # 业务持久化
│   ├── agent.py              # Agent 运行服务
│   └── cli.py                # 命令行演示
│
├── frontend/                 # Vue 3 前端（Vite 构建）
│   ├── index.html            # 入口 HTML
│   ├── vite.config.js        # Vite 配置（/api 代理到后端）
│   └── src/
│       ├── main.js           # 应用入口
│       ├── style.css         # 全局样式（暗色主题变量）
│       ├── api.js            # 后端接口封装（JSON / 上传 / SSE）
│       ├── App.vue           # 根组件：三栏布局
│       ├── stores/app.js     # 全局状态 + 业务动作（单例 store）
│       ├── utils/            # markdown 渲染 / 版本 diff / 格式化
│       └── components/       # 顶栏、项目树、对话流、查看面板、弹窗等
│
├── tests/                    # 测试套件
│   ├── conftest.py           # 测试公共夹具
│   ├── test_agent.py         # Agent 端到端测试
│   ├── test_patch.py         # patch 引擎测试
│   ├── test_chat.py          # 对话工具层测试
│   ├── test_importer.py      # 文件导入测试
│   └── test_knowledge.py     # 知识 RAG 测试
│
└── data/                     # 本地数据（gitignore）
```

### 主要模块职责

| 文件 | 职责 |
|------|------|
| `app/chat.py` | 对话式 Agent：ChatConductor 图 + 工具集 + SSE 流式对话 |
| `app/knowledge.py` | 项目级改编知识 RAG：题材识别、作者风格提取、同类剧本种子库 |
| `app/importer.py` | 原著文件导入：解析 `.txt / .md / .docx` |
| `app/state.py` | 图状态（AgentState）+ 人类决策模型 |
| `app/graph.py` | 把节点 / 边组装成 StateGraph，接入 checkpointer |
| `app/nodes.py` | 图节点：context / plan / propose / guard / review / apply / finalize |
| `app/review.py` | 审阅 / 一致性保障 / 评审打分：多维度打分 + 一致性问题（LLM 审阅） |
| `app/tools.py` | ReAct 工具：剧本概况、场景详情、原文、版本历史、校验 |
| `app/patch.py` | patch 引擎：结构化提议 → 操作清单 → 应用 → 校验 |
| `app/domain.py` | 剧本领域模型（Script / Scene / Character / Beat） |
| `app/export.py` | 剧本导出：渲染为标准剧本 `.txt / .md / .docx` |
| `app/workspace.py` | 工作目录：真实磁盘文件夹 + `01_原稿/02_版本/03_导出/04_知识库` 结构化分格 |
| `app/llm.py` | 模型接入（OpenAI 兼容 + DeepSeek 原生） |
| `app/generation.py` | 线性生成流水线（故事圣经 → 场景 / 节拍） |
| `app/vector.py` | 向量检索层：嵌入器 + Milvus / 内存后端 |
| `app/store.py` | 业务持久化（SQLAlchemy + Postgres/SQLite） |
| `app/agent.py` | Agent 运行服务：start / resume / get |

## API 速览

### 对话式接口

| 端点 | 说明 |
|------|------|
| `POST /api/chat` | 一轮对话（非流式） |
| `POST /api/chat/stream` | SSE 流式对话 |
| `GET /api/conversations/{id}/messages` | 读取消息历史 |
| `GET /api/projects/{id}/conversations` | 列出项目对话 |
| `POST /api/projects/{id}/conversations` | 新建对话 |
| `POST /api/projects/import` | 新建剧本：上传文件或粘贴原文 |
| `GET /api/versions/{id}/text` | 返回标准剧本排版文本 |
| `GET /api/versions/{id}/export?fmt=txt|md|docx` | 导出剧本为 .txt / .md / .docx（并写入工作目录 `03_导出`） |
| `POST /api/versions/{id}/apply` | 应用字段级改动，生成「手动编辑」新版本 |
| `POST /api/versions/{id}/milestone` | 给版本打里程碑标记（草稿 / 候选 / 终稿） |
| `GET /api/workspace` | 查看当前工作目录配置与落盘模式 |
| `POST /api/workspace` | 设置工作目录（`root` + `persist`；persist=false 为仅应用内不落盘） |
| `GET/PUT /api/projects/{id}/notes` | 读取 / 保存「编剧圣经 / 设定备忘」 |
| `GET /api/projects/{id}/files` | 列出项目本地剧本文件（按 `01原稿/02版本/03导出/04知识库` 分组） |
| `GET /api/projects/{id}/files/{path}` | 读取 / 预览某个本地剧本文件（文本内联，附件下载，防目录穿越） |
| `POST /api/projects/{id}/structure` | 把原稿与最新版本落盘到工作目录并返回目录树 |
| `GET /api/projects/{id}/knowledge` | 查看项目知识库 |

### 改编工作流接口

| 端点 | 说明 |
|------|------|
| `POST /api/projects/{project_id}/agent/run` | 启动改编运行 |
| `POST /api/agent/runs/{run_id}/resume` | 恢复审阅（接受 / 编辑 / 重新生成 / 拒绝） |
| `GET /api/agent/runs/{run_id}` | 查看运行状态 |

## 工作目录（默认落盘，自动创建）

默认把剧本以「文件」形式落盘到项目下的 `data/` 目录（不存在会自动创建）；数据库承担聊天与 Agent 工作流（对话、消息、Agent 运行记录、项目与版本的结构化数据）。这样可以直接在资源管理器里翻剧本文件，应用内的编辑 / 审阅仍走数据库的结构化模型。

```
data/
  <剧名>/
    01_原稿/     原著 / 原始文本（导入时写入）
    02_版本/     每次生成的剧本快照
    03_导出/     导出的 .txt / .md / .docx 剧本
    04_知识库/   项目知识与备忘录
  _README.txt   目录结构说明
```

- 导入原著 → 自动写入 `01_原稿`；
- 生成初稿 / 接受改编 → 自动写入 `02_版本`；
- 点击导出 → 下载，并同时写入 `03_导出`；
- 右侧面板「同步到工作目录」→ 手动把原稿 + 最新版本落盘。

默认 `WORKSPACE_PERSIST=true`（落盘到 `data/`）；可用 `WORKSPACE_ROOT` 换个目录，或设 `WORKSPACE_PERSIST=false` 改为仅应用内。`data/` 已在 `.gitignore` 中，不会进版本库。落盘失败不影响主流程（数据库仍是权威数据源）。

## 运行测试

```bash
# 运行全部测试
python -m pytest tests -q

# 运行特定测试
python -m pytest tests/test_agent.py -v
python -m pytest tests/test_patch.py -v
```

## 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 有状态 Agent 编排框架
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [FastAPI](https://github.com/tiangolo/fastapi) - 现代 Python Web 框架
- [PostgreSQL](https://www.postgresql.org/) - 关系型数据库
- [Milvus](https://github.com/milvus-io/milvus) - 向量数据库
