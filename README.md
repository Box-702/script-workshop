# 剧本工坊（Script Workshop）

小说 → 剧本 → AI 短剧 全链路 Agent 工作台。

基于 LangGraph 的多 Agent 协作系统，模仿真实剧组分工（编剧/导演/摄影/美术/剪辑/制片），通过对话完成从导入小说到生成短剧的完整流程。AI 给出可解释、可逐条选择、可回滚的修改建议，由人来决定接受、编辑或拒绝。

- Python 3.12+ / LangGraph 1.x / LangChain 1.x / FastAPI
- 后端 FastAPI（REST + 流式对话），前端 Vue 3 + Vite
- 可选 Postgres（业务库 + checkpointer）
- 对话模型：智谱 GLM / DeepSeek / OpenAI 兼容
- 视频生成：MiniMax 海螺 / Runway / Kling / CogVideoX / Sora

## 为什么做这个项目

市面上常见的剧本工具大多是「一次性生成」：输入小说，吐出一份剧本，结束。这类工具价值有限，因为：

1. 一次生成的剧本仍需要人工继续修改；
2. AI 无脑覆盖会破坏作者已有的结构；
3. 没有版本、没有回滚，也说不清「这条改动到底改了什么」。

这个项目把重心从「AI 一次生成」移到「AI 如何安全、可控地参与改写」，这才是 Agent 的核心命题。

## 功能

### 剧本改编

- **状态图编排**：LangGraph StateGraph + 条件边，模型是否用工具、用户是否接受都用边来表达。
- **ReAct 工具调用**：Agent 自主决定查看场景详情、搜索原文、查版本历史、校验。
- **人机协同**：`interrupt` 暂停图执行，`Command.resume` 恢复；支持接受 / 编辑 / 重新生成 / 拒绝四种决策。
- **自我审阅**：`guard` 节点先 dry-run 应用并自纠错，再交给人类。
- **评审打分 + 一致性保障**：guard 之上再跑一次 LLM 审阅，对提议按「忠实度 / 一致性 / 冲突 / 风格 / 结构」五维打分。
- **结构化输出**：patch 是原子操作，可逐条审、逐条接受、可回滚。
- **对话式交互**：用自然语言完成从导入、改编到审阅的整套流程。

### AI 短剧制作

- **剧组 Agent 系统**：8 个 Agent 模仿真实剧组分工（编剧/剧本医生/导演/摄影指导/美术指导/分镜师/剪辑师/制片人）。
- **镜头级视频生成**：每个场景拆解为 3-8 个镜头，每镜头生成 5-10 秒视频，最后 FFmpeg 拼接。
- **视频 Provider 抽象层**：统一接口适配 Runway / Kling / CogVideoX / Sora / MiniMax，用户自由切换。
- **4 个 HITL 审批节点**：剧本定稿、分镜方案、视频 Prompt、成片审核。
- **版本迭代**：视频版本链式快照，支持回溯/分叉/里程碑标记。

### Agent 工具（12 个）

| 工具 | 说明 |
|------|------|
| `get_script_overview` | 查看剧本概况 |
| `get_scene_detail` | 查看场景详情 |
| `get_source_text` | 查看原文片段 |
| `search_source` | 在原文中搜索关键词 |
| `get_genre_knowledge` | 查看题材改编知识 |
| `get_author_style` | 查看作者语言风格 |
| `list_versions` | 查看历史版本 |
| `validate_tool` | 校验剧本一致性 |
| `web_search` | 联网搜索（Tavily） |
| `remember_preference` | 记住用户偏好 |
| `recall_preferences` | 回忆用户偏好 |
| `breakdown_scenes` | 场景拆解为镜头 |

### 其他

- **聊天与项目解耦**：可直接开聊，无需先建项目。
- **工作区文件树**：左栏显示本地文件夹映射。
- **剧本导出**：一键导出为 `.txt / .md / .docx`。
- **剧本编辑器**：直接改台词、动作、场景，保存成新版本。
- **联网搜索**：Agent 可搜索创作参考、同类作品分析。
- **用户记忆**：从用户行为中学习偏好，自动优化改编建议。

## 架构

```
┌─────────────┐    ┌─────────────┐    ┌─────────────┐
│  STAGE 1    │    │  STAGE 2    │    │  STAGE 3    │
│  小说 → 剧本 │───→│  剧本 → 分镜 │───→│  分镜 → 短剧 │
│  (编剧组)    │    │  (导演组)    │    │  (制作组)    │
└─────────────┘    └─────────────┘    └─────────────┘
```

- `app/api.py`：REST 路由 + SSE 流式对话，对外提供 `/api/*`。
- `app/chat.py`：对话式 Agent（ChatConductor），持有工具集并编排对话。
- `app/agent.py`：运行服务，负责启动运行、恢复审阅与兜底。
- `app/graph.py` + `app/nodes.py` + `app/tools.py`：LangGraph StateGraph 编排。
- `app/crew/`：剧组 Agent（director / dp / art_director / editor / producer）。
- `app/video/`：视频生成 Provider 抽象层 + 异步任务队列。
- `app/memory.py`：用户级记忆系统（替代 RAG）。
- `app/store.py`：业务持久化（SQLAlchemy，Postgres / SQLite）。
- `app/llm.py`：模型接入（智谱 / OpenAI 兼容 / DeepSeek）。
- `frontend/`：Vue 3 + Vite 单页，三栏布局（聊天 + 创作区 + Inspector）。

### LangGraph 图拓扑

```text
START → context → plan ──(有工具调用)──> tools → plan   (ReAct 循环)
                        └──(无工具调用)──> propose → guard(自纠错)
                                                  │(问题)└→ propose（重做循环）
                                                  │(通过)└→ review(interrupt)
                       ┌──(accept/edit)──> apply ──> finalize ──> END
                       ├──(regenerate)───> propose
                       └──(reject)──────> finalize ──> END
```

## 快速开始

### 方式一：本机运行（零基础设施）

```bash
# 1. 安装依赖
pip install -e ".[dev]"

# 2. 配置环境变量（可选，不配也能跑通演示）
# 复制 .env.example 为 .env，填入模型 key
cp .env.example .env

# 3. 运行命令行演示
python -m app.cli

# 4. 启动 API
uvicorn app.main:app --port 8000 --reload

# 5. 启动前端
cd frontend && npm install && npm run dev
# 打开 http://localhost:5173
```

不配模型 key 时，全部走本地回退，链路依然闭环。

### 方式二：用 Docker 提供 Postgres

```bash
# 1. 准备环境变量
cp .env.example .env

# 2. 启动 Postgres
docker compose up -d

# 3. 本机安装依赖并连 Postgres 启动
pip install -e ".[dev]"
export DATABASE_URL="postgresql+psycopg://script:script@localhost:5432/script_agent"
export CHECKPOINTER="postgres"
uvicorn app.main:app --port 8000
```

两种方式访问入口相同：

- Web：http://localhost:8000
- API 文档（Swagger）：http://localhost:8000/docs
- 健康检查：http://localhost:8000/api/healthz

## 项目结构

```
Script Workshop/
├── README.md
├── pyproject.toml
├── docker-compose.yml        # Postgres
├── .env.example
│
├── app/
│   ├── main.py               # FastAPI 入口
│   ├── api.py                # REST 路由
│   ├── chat.py               # 对话式 Agent
│   ├── agent.py              # Agent 运行服务
│   ├── graph.py              # LangGraph 图编排
│   ├── nodes.py              # 图节点实现
│   ├── tools.py              # ReAct 工具集（12 个）
│   ├── domain.py             # 领域模型（Script + Shot + StyleGuide）
│   ├── store.py              # 业务持久化
│   ├── llm.py                # 模型接入（智谱/DeepSeek/OpenAI）
│   ├── config.py             # 配置管理
│   ├── memory.py             # 用户记忆系统
│   ├── knowledge.py          # 题材知识 + 风格提取
│   ├── search.py             # 联网搜索（Tavily）
│   ├── generation.py         # 剧本生成流水线
│   ├── patch.py              # patch 引擎
│   ├── review.py             # 评审打分
│   ├── export.py             # 剧本导出
│   ├── crew/                 # 剧组 Agent
│   │   ├── director.py       # 导演
│   │   ├── dp.py             # 摄影指导
│   │   ├── art_director.py   # 美术指导
│   │   ├── editor.py         # 剪辑师
│   │   └── producer.py       # 制片人
│   ├── video/                # 视频生成
│   │   ├── base.py           # Provider 抽象基类
│   │   ├── registry.py       # Provider 注册表
│   │   ├── queue.py          # 异步任务队列
│   │   ├── assemble.py       # FFmpeg 拼接
│   │   └── providers/        # 5 个 Provider 适配器
│   └── vector.py             # 文本切片工具
│
├── frontend/
│   └── src/
│       ├── App.vue           # 三栏布局
│       ├── stores/app.js     # 全局状态
│       └── components/
│           ├── ChatList.vue          # 聊天列表
│           ├── WorkspaceTree.vue     # 工作区文件树
│           ├── SettingsModal.vue     # 模型/Provider 设置
│           ├── ShotList.vue          # 镜头列表
│           ├── VideoPlayer.vue       # 视频播放器
│           ├── CrewPanel.vue         # 剧组工位面板
│           └── ...
│
└── tests/                    # 测试套件（67 tests）
```

## 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ZHIPUAI_API_KEY` | 智谱对话模型 key | - |
| `ZHIPUAI_MODEL_NAME` | 智谱模型名 | `GLM-5.3-Flash` |
| `DEEPSEEK_API_KEY` | DeepSeek key（备用） | - |
| `OPENAI_API_KEY` | OpenAI 兼容 key（备用） | - |
| `MINIMAX_API_KEY` | MiniMax 视频生成 key | - |
| `TAVILY_API_KEY` | 联网搜索 key | - |
| `DATABASE_URL` | 数据库连接串 | SQLite |
| `CHECKPOINTER` | checkpointer 类型 | `memory` |

## 运行测试

```bash
python -m pytest tests -q
# 67 passed
```

## 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 有状态 Agent 编排框架
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [FastAPI](https://github.com/tiangolo/fastapi) - 现代 Python Web 框架
- [PostgreSQL](https://www.postgresql.org/) - 关系型数据库
