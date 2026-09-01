# 🎬 剧本智能体 · Script Adaptation Agent

<p align="center">
  <strong>基于 LangGraph 的剧本改编 Agent 工作台</strong><br>
  <em>有状态、可工具调用、可人机协同的 AI 剧本改写系统</em>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/python-3.12+-blue.svg" alt="Python 3.12+">
  <img src="https://img.shields.io/badge/langgraph-1.x-green.svg" alt="LangGraph 1.x">
  <img src="https://img.shields.io/badge/langchain-1.x-green.svg" alt="LangChain 1.x">
  <img src="https://img.shields.io/badge/fastapi-0.115+-teal.svg" alt="FastAPI">
  <img src="https://img.shields.io/badge/license-MIT-yellow.svg" alt="MIT License">
  <img src="https://img.shields.io/badge/tests-26%20passed-brightgreen.svg" alt="Tests">
</p>

---

## ✨ 项目亮点

> **Agent 的正确位置不是替用户覆盖文本，而是给出可解释、可选择、可回滚的建议。**

| 特性 | 说明 |
|------|------|
| 🔄 **状态图编排** | LangGraph StateGraph + 条件边，模型是否用工具、用户接受/拒绝都用边表达 |
| 🛠️ **ReAct 工具调用** | Agent 自主决定查看场景/检索原文/查版本/校验 |
| 👤 **人机协同** | `interrupt` 暂停，`Command.resume` 恢复；支持接受/编辑/重新生成/拒绝 |
| 🛡️ **自我审阅** | `guard` 节点先 dry-run 应用并自纠错，再交给人类 |
| 📝 **结构化输出** | patch 是原子操作，可逐条审、逐条接受、可回滚 |
| 💬 **对话式交互** | Codex/DSH 风格，通过自然语言完成整套流程 |
| 🧠 **项目级知识 RAG** | 每个项目维护「同类走向/写作手法/作者风格」三类记忆 |
| 📤 **剧本导出** | 一键导出标准剧本为 `.txt / .md / .docx`（Word 可直接打开） |
| ✏️ **直接编辑剧本** | 内置剧本编辑器：所见即所得改台词/动作/场景，保存成新版本（复用 patch 引擎） |
| 📚 **编剧圣经/设定** | 右侧「编剧设定」面板维护人物小传、时间线、伏笔清单，自动写入工作目录 |
| 🏷️ **版本里程碑** | 给版本打 草稿/候选/终稿 标记，一键「定为终稿」 |
| 📁 **工作目录三选一** | 默认落盘 / 指定真实文件夹 / 仅应用内不落盘，可随时切换 |
| 📂 **本地文件浏览** | 右侧「本地文件」面板直接查看/下载 `data/<剧名>/` 里的剧本文件 |
| 📁 **真实工作目录** | 关联电脑磁盘文件夹，导入/生成/导出自动归入 `01_原稿 / 02_版本 / 03_导出 / 04_知识库`，形成结构化工作流程 |
| 💾 **持久化 + 可观测** | Postgres 存业务数据 + checkpointer；`graph.stream` 采集节点级执行轨迹 |

---

## 📖 为什么做这个项目

市面上的「脚本工具」大多是**一次性生成器**：输入小说 → 吐一份剧本 → 结束。它的价值其实很有限，因为：

1. 一次生成的剧本永远需要人继续改；
2. AI 无脑覆盖会毁掉作者已有的结构；
3. 没有版本、没有回滚、没有「这条改动到底改了什么」。

所以本项目把重心从「AI 一次生成」挪到 **AI 如何安全、可控地参与改写**，这正是 **Agent（智能体）** 的核心命题。

---

## 🏗️ 架构总览

```
┌────────────────────────────────────────────────────────────┐
│  Web（Vue 3 + Vite 单页）    REST API (FastAPI)              │
│  frontend/src/components <-> app/api.py（含 SSE 流式对话）   │
└──────────────────────────────┬─────────────────────────────┘
                               │
   ┌───────────────────────────▼───────────────────────────┐
   │  app/chat.py  对话式 Agent（ChatConductor）              │
   │  工具：create_project / generate_script / run_adaptation│
   │        / resume(确定性) / ask / remember / overview    │
   │  记忆：app/knowledge.py  项目级改编知识 RAG               │
   └───────────────────────────┬───────────────────────────┘
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

---

## 🚀 快速开始

### 方式 A：Docker Compose（推荐）

```bash
# 1. 准备环境变量
cp .env.example .env
# 编辑 .env，填入你的 API Key（可选，不填也能跑通演示链路）

# 2. 启动（Postgres + API）
docker compose up --build

# 3. 访问
# Web（对话式单页）: http://localhost:8000
# API 文档（Swagger）: http://localhost:8000/docs
# 健康检查: http://localhost:8000/api/healthz
```

**可选：启用 Milvus RAG（生产级向量检索）**

```bash
# 额外拉起 Milvus 向量栈
docker compose --profile milvus up -d
# 并在 .env 里设置：
#   ENABLE_RAG=true
#   EMBEDDING_PROVIDER=openai
#   EMBEDDING_API_KEY=your_key
```

### 方式 B：本地开发

```bash
# 1. 安装依赖
pip install -e ".[dev]"

# 2. 配置环境变量（可选，不配也能跑通演示）
export DATABASE_URL="sqlite:///./data/dev.db"
export CHECKPOINTER="memory"

# 3. 运行命令行演示
python -m app.cli

# 4. 启动 API（后端）
uvicorn app.main:app --port 8000 --reload

# 5. 启动前端（Vue 3 + Vite，开发模式，/api 自动代理到 8000）
cd frontend && npm install && npm run dev
# 打开 http://localhost:5173

# （可选）构建前端产物，之后 FastAPI 会直接在 http://localhost:8000 托管
npm run build
```

> 💡 `ENABLE_RAG=false`、`OPENAI_API_KEY=` 留空时，全部走本地回退，链路依然闭环。

---

## 📁 项目结构

```
Script Workshop/
├── README.md                 # 项目说明
├── pyproject.toml            # Python 包配置
├── Dockerfile                # API 镜像
├── docker-compose.yml        # 本地编排（Postgres + 可选 Milvus）
├── .env.example              # 环境变量模板
├── LICENSE                   # MIT 许可证
│
├── app/                      # 核心应用
│   ├── main.py               # FastAPI 入口 + 极简 Web
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
│   ├── cli.py                # 命令行演示
│   └── web/index.html        # （旧版）单文件页面，作为无构建时的回退
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

### 各模块职责

| 文件 | 职责 |
|------|------|
| `app/chat.py` | **对话式 Agent**：ChatConductor 图 + 工具集 + SSE 流式对话 |
| `app/knowledge.py` | **项目级改编知识 RAG**：题材识别、作者风格提取、同类剧本种子库 |
| `app/importer.py` | **原著文件导入**：解析 `.txt / .md / .docx` |
| `app/state.py` | 图状态（AgentState）+ 人类决策模型 |
| `app/graph.py` | 把节点/边组装成 StateGraph，接入 checkpointer |
| `app/nodes.py` | 图节点：context / plan / propose / guard / review / apply / finalize |
| `app/tools.py` | ReAct 工具：剧本概况、场景详情、原文、版本历史、校验 |
| `app/patch.py` | patch 引擎：结构化提议 → 操作清单 → 应用 → 校验 |
| `app/domain.py` | 剧本领域模型（Script / Scene / Character / Beat） |
| `app/export.py` | **剧本导出**：把 Script 渲染为标准剧本 `.txt / .md / .docx` |
| `app/workspace.py` | **工作目录**：真实磁盘文件夹 + `01_原稿/02_版本/03_导出/04_知识库` 结构化分格 |
| `app/llm.py` | 模型接入（OpenAI 兼容 + DeepSeek 原生） |
| `app/generation.py` | 线性生成流水线（故事圣经 → 场景/节拍） |
| `app/vector.py` | 向量检索层：嵌入器 + Milvus/内存后端 |
| `app/store.py` | 业务持久化（SQLAlchemy + Postgres/SQLite） |
| `app/agent.py` | Agent 运行服务：start / resume / get |

---

## 🔌 API 速览

### 对话式 API

| 端点 | 说明 |
|------|------|
| `POST /api/chat` | 一轮对话（非流式） |
| `POST /api/chat/stream` | SSE 流式对话 |
| `GET /api/conversations/{id}/messages` | 读取消息历史 |
| `GET /api/projects/{id}/conversations` | 列出项目对话 |
| `POST /api/projects/{id}/conversations` | 新建对话 |
| `POST /api/projects/import` | **新建剧本**：上传文件或粘贴原文 |
| `GET /api/versions/{id}/text` | 返回标准剧本排版文本 |
| `GET /api/versions/{id}/export?fmt=txt\|md\|docx` | **导出剧本**为 .txt / .md / .docx 文件（并写入工作目录 `03_导出`） |
| `POST /api/versions/{id}/apply` | **内置编辑器**：应用字段级改动，生成「手动编辑」新版本 |
| `POST /api/versions/{id}/milestone` | 给版本打里程碑标记（草稿/候选/终稿） |
| `GET /api/workspace` | 查看当前工作目录配置与落盘模式 |
| `POST /api/workspace` | 设置工作目录（`root` + `persist`；persist=false 为仅应用内不落盘） |
| `GET/PUT /api/projects/{id}/notes` | 读取/保存「编剧圣经 / 设定备忘」 |
| `GET /api/projects/{id}/files` | 列出项目本地剧本文件（按 `01原稿/02版本/03导出/04知识库` 分组） |
| `GET /api/projects/{id}/files/{path}` | 读取/预览某个本地剧本文件（文本内联，附件下载，防目录穿越） |
| `POST /api/projects/{id}/structure` | 把原稿与最新版本落盘到工作目录并返回目录树 |
| `GET /api/projects/{id}/knowledge` | 查看项目知识库 |

### 改编工作流 API

| 端点 | 说明 |
|------|------|
| `POST /api/projects/{project_id}/agent/run` | 启动改编运行 |
| `POST /api/agent/runs/{run_id}/resume` | 恢复审阅（接受/编辑/重新生成/拒绝） |
| `GET /api/agent/runs/{run_id}` | 查看运行状态 |

---

## 📁 工作目录（默认落盘，自动创建）

**默认把剧本以「文件」形式落盘到项目下的 `data/` 目录**，`data/` 不存在时自动创建；数据库承担聊天与 Agent 工作流（对话、消息、Agent 运行记录、项目与版本的结构化数据）。这样你能直接去资源管理器里翻剧本文件，应用里的编辑/审阅还走数据库的结构化模型。

> 产出目录随项目自动生成，用「导入 → 生成 → 导出」串成结构化工作流程：

```text
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
- 点击「⤓ 导出」→ 下载，并同时写入 `03_导出`；
- 右侧面板「⤷ 同步到工作目录」→ 手动把原稿 + 最新版本落盘。

> 默认 `WORKSPACE_PERSIST=true`（落盘到 `data/`）；可用 `WORKSPACE_ROOT` 换个目录，或设 `WORKSPACE_PERSIST=false` 改为仅应用内。`data/` 已在 `.gitignore` 中，不会进版本库。落盘失败不影响主流程（数据库仍是权威数据源）。

---

## 🧪 运行测试

```bash
# 运行全部测试（26 个）
python -m pytest tests -q

# 运行特定测试
python -m pytest tests/test_agent.py -v
python -m pytest tests/test_patch.py -v
```

---

## 💡 面试讲稿大纲

1. **痛点**：一次生成的剧本没法安全地后续修改，AI 无脑覆盖会毁掉作者结构。
2. **方案**：用 LangGraph 把「改写」建模成有状态、可中断的 Agent 流程，并以**对话形式**呈现。
3. **亮点 1 · 状态图 + 条件边**：模型是否用工具、用户接受/编辑/重新生成/拒绝，都用边来表达。
4. **亮点 2 · ReAct + 工具**：Agent 自主决定查看场景/检索原文/查版本/校验。
5. **亮点 3 · 人机协同**：`interrupt` 暂停，`Command.resume` 恢复；支持四种决策。
6. **亮点 4 · 自我审阅**：`guard` 节点先 dry-run 应用并自纠错，再交给人类。
7. **亮点 5 · 结构化输出**：patch 是原子操作，可逐条审、逐条接受、可回滚。
8. **亮点 6 · 对话式编排**：Codex/DSH 风格，审阅动作走确定性路径。
9. **亮点 7 · 项目级知识 RAG**：每个项目维护三类记忆，改编与问答都参考。
10. **亮点 8 · 持久化 + 可观测**：Postgres + checkpointer；`graph.stream` 采集执行轨迹。

> **一句话总结**：用 LangGraph 编排了一套「会推理、会查证、会停下来等人类决定、并把决定安全落库」的 Agent 工作流，并且把它包成了像 Codex 一样可以直接对话使用的产品形态。

---

## 🗺️ 后续演进方向

- [ ] 把生成流水线也升级为 LangGraph 图
- [ ] 增加角色弧光、时间线一致性等多场景全局检查工具
- [ ] 版本 diff 复用 `patch` 的字段级对比
- [ ] 知识库支持跨项目借阅
- [ ] 对话支持多模态输入（PDF / 网页）
- [ ] Milvus 检索支持跨项目、混合检索

---

## 📄 许可证

本项目采用 [MIT 许可证](LICENSE)。

---

## 🙏 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 有状态 Agent 编排框架
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [FastAPI](https://github.com/tiangolo/fastapi) - 现代 Python Web 框架
- [PostgreSQL](https://www.postgresql.org/) - 强大的关系型数据库
- [Milvus](https://github.com/milvus-io/milvus) - 向量数据库
