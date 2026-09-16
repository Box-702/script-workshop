# 剧本工坊（Script Workshop）

小说 → 剧本 → AI 短剧 全链路 Agent 工作台。

基于 LangGraph 的多 Agent 协作系统，模仿真实剧组分工（编剧生成 → 导演拆镜 → 美术定视觉 → 摄影出提示词），通过对话完成从导入小说到生成短剧的完整流程。AI 给出可解释、可逐条选择、可回滚的修改建议，由人来决定接受、编辑或拒绝。

- Python 3.12+ / LangGraph 1.x / LangChain 1.x / FastAPI
- 后端 FastAPI（REST + 流式对话），前端 Vue 3 + Vite
- 可选 Postgres（业务库 + checkpointer）
- 模型接入：统一门面 `app/llm/`，一套 OpenAI 兼容协议覆盖 OpenAI / DeepSeek / 智谱 GLM / Kimi / Qwen / Ollama；对话、视觉质检、文生图三维度可分别用不同厂商
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

- **剧组 Agent 系统**：导演 / 美术指导 / 摄影指导三个 Agent 各司其职（美术指导产出的角色造型与环境描述是全片视觉锚的唯一来源，下游逐字复用）。
- **参考资产流水线（图像级一致性）**：为角色与场景生成定妆图 → 视觉模型质检 → 注册为全局参考 → 回填到镜头，让视频模型「看见」同一个角色，而不是只靠文字描述。
- **镜头级视频生成**：镜头数由导演按剧情内容决定（分镜 = 一段连贯的角色动作或一段连贯的角色对话剧情），首尾帧接力 + 参考图/参考视频锁一致性，最后 FFmpeg 拼接。
- **视频 Provider 抽象层**：统一接口适配 Runway / Kling / CogVideoX / Sora / MiniMax，用户自由切换。
- **人审环节**：剧本改编走 `interrupt` 暂停 / `Command.resume` 恢复的四决策闭环（接受 / 编辑 / 重新生成 / 拒绝）；视频侧以「分镜版本 → 提示词版本 → 成片版本」的链式快照承载人工审核与回退。
- **版本迭代**：视频版本链式快照，支持回溯/分叉/里程碑标记。

> 开发指引与踩坑记录见 [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)；
> 包结构、模型接入层、Agent 清单与核心链路见 [`docs/ARCHITECTURE.md`](docs/ARCHITECTURE.md)。

### 工具集

**对话 Conductor 工具（14 个）**：`create_project` / `generate_script` / `run_adaptation` / `get_script_overview` / `ask` / `remember` / `analyze_scenes` / `check_style` / `polish_dialogue` / `breakdown_scenes` / `generate_style_guide` / `generate_video_prompts` / `generate_reference_assets` / `web_search`。

**改编图 ReAct 工具（11 个）**：

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
| `remember_preference` | 记住用户偏好 |
| `recall_preferences` | 回忆用户偏好 |
| `web_search` | 联网搜索（Tavily） |

两组工具都会自动合并 `app/plugin/` 注册的插件工具（内置 `research` 插件提供 `deep_research`）。

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

分层（依赖单向向下，见 `docs/ARCHITECTURE.md`）：

- `app/llm/`：**统一模型接入层**。门面 `LLM` + 厂商表 + 配置解析（`.env` / DB），覆盖 chat / vision / image 三个能力维度。
- `app/pipeline/`：**内容生产线**。导入解析、两阶段生成、patch 与校验、题材知识、记忆、评审、搜索、导出；不依赖 LangGraph，也不感知 HTTP。
- `app/agent/`：**改编智能体**。`graph` / `nodes` / `tools` / `state` 是 LangGraph 状态图，`runner` 是薄服务层，`skills` 是后台专职子代理。
- `app/chat/`：**对话式编排**（ChatConductor），绑定工具理解意图，底层复用 `app/agent` 的审阅工作流。
- `app/crew/`：**剧组 Agent**（导演 / 美术指导 / 摄影指导）。
- `app/media/`：**参考资产流水线**（定妆图 → 视觉质检 → 注册 → 回填镜头）。
- `app/video/`：视频 Provider 抽象层 + 异步任务队列 + 连续性解析（尚未接入投递路径）+ FFmpeg 拼接。
- `app/plugin/`：插件系统（内置 / 用户级 / 项目级）。插件 `mcp:` 清单段已能解析，MCP 执行层尚未接线。
- `app/api/`：**REST 路由包**，按域拆分为 system / projects / versions / agent_runs / chat / video / plugins；统一经 `api/deps.py` 取依赖。
- `app/store.py`：业务持久化（SQLAlchemy，Postgres / SQLite）。
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
│   ├── config.py             # 配置管理（.env → Settings）
│   ├── deps.py               # 依赖单例装配点
│   ├── domain.py             # 领域模型（Script + Shot + StyleGuide）
│   ├── store.py              # 业务持久化
│   ├── workspace.py          # 工作目录文件树
│   │
│   ├── api/                  # ★ REST 路由包（按业务域拆分）
│   │   ├── system.py         #   运行状态 / 子代理任务 / 工作目录
│   │   ├── projects.py       #   项目生命周期、导入、落盘、笔记、文件
│   │   ├── versions.py       #   剧本版本 + 导出
│   │   ├── agent_runs.py     #   改编智能体的运行与审阅
│   │   ├── chat.py           #   对话式 Agent 与会话管理
│   │   ├── video.py          #   Provider / 模型偏好 / 视频版本 / 生成任务
│   │   └── plugins.py        #   插件管理
│   │
│   ├── llm/                  # ★ 统一模型接入层
│   │   ├── client.py         #   LLM 门面（chat / structured / vision / image）
│   │   ├── providers.py      #   厂商表（OpenAI 兼容 / DeepSeek / 智谱 / Kimi / Qwen / Ollama）
│   │   ├── registry.py       #   配置解析（.env 优先级链 + DB 偏好）
│   │   ├── vision.py         #   视觉质检客户端
│   │   └── image.py          #   文生图客户端
│   │
│   ├── pipeline/             # ★ 内容生产线（无 LangGraph / 无 HTTP 依赖）
│   │   ├── generation.py     #   两阶段生成：故事圣经 → 场景规划
│   │   ├── patch.py          #   结构化 patch + 剧本校验
│   │   ├── profiles.py       #   改编类型 profile
│   │   ├── knowledge.py      #   题材知识 + 作者风格
│   │   ├── memory.py         #   用户/项目记忆
│   │   ├── review.py         #   五维评审打分
│   │   ├── search.py         #   Tavily 联网搜索
│   │   ├── importer.py       #   文件导入解析
│   │   ├── export.py         #   导出 txt / md / docx
│   │   └── chunking.py       #   文本切片
│   │
│   ├── agent/                # ★ 改编智能体
│   │   ├── graph.py          #   LangGraph 图拓扑
│   │   ├── nodes.py          #   图节点实现
│   │   ├── tools.py          #   ReAct 工具集
│   │   ├── state.py          #   AgentState
│   │   ├── runner.py         #   运行服务（启动 / 恢复 / 兜底）
│   │   └── skills.py         #   后台子代理（场景分析 / 风格检查 / 对白润色）
│   │
│   ├── chat/
│   │   └── conductor.py      # 对话式 Agent（ChatConductor）
│   ├── media/
│   │   └── refs.py           # 参考资产流水线（定妆图 → 质检 → 回填）
│   ├── crew/                 # 剧组 Agent
│   │   ├── director.py       #   导演（分镜）
│   │   ├── art_director.py   #   美术指导（视觉锚唯一来源）
│   │   └── dp.py             #   摄影指导（视频提示词构建）
│   ├── video/                # 视频生成
│   │   ├── base.py           #   Provider 抽象基类
│   │   ├── registry.py       #   Provider 注册表
│   │   ├── queue.py          #   异步任务队列
│   │   ├── continuity.py     #   连续性解析（接力 → 参考视频）
│   │   ├── assemble.py       #   FFmpeg 拼接
│   │   └── providers/        #   5 个 Provider 适配器
│   ├── plugin/               # 插件系统（内置 / 用户级 / 项目级）
│   └── plugins/builtin/      # 内置插件（research）
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
└── tests/                    # 测试套件（98 tests）
```

## 环境变量

模型接入统一由 `app/llm/registry.py` 解析：**显式指定 > `.env` 优先级链（OPENAI > ZHIPUAI > DEEPSEEK）> 数据库里配的 provider**。
对话、视觉质检、文生图三维度可分别配置，互相独立。

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `CHAT_PROVIDER` | 强制指定对话厂商（`openai` / `deepseek` / `zhipu` / `ollama` / `moonshot` / `qwen`） | 按优先级链自动选 |
| `ZHIPUAI_API_KEY` | 智谱 key（GLM 对话 / CogView 文生图 / CogVideoX 视频共用） | - |
| `DEEPSEEK_API_KEY` | DeepSeek key（也用于默认视觉质检模型） | - |
| `OPENAI_API_KEY` | OpenAI 或任意兼容服务的 key | - |
| `DEEPSEEK_THINKING` | 推理模型是否开启思考链 | `false` |
| `VISION_PROVIDER` / `VISION_MODEL` / `VISION_API_KEY` | 视觉质检单独配置（留空则自动复用支持视觉的厂商） | 自动 |
| `IMAGE_PROVIDER` / `IMAGE_MODEL` / `IMAGE_API_KEY` | 文生图单独配置（`cogview` / `openai`） | `cogview` → `openai` |
| `MINIMAX_API_KEY` | MiniMax 视频生成 key | - |
| `TAVILY_API_KEY` | 联网搜索 key | - |
| `DATABASE_URL` | 数据库连接串 | SQLite |
| `CHECKPOINTER` | checkpointer 类型（`memory` / `postgres`） | `memory` |

## 运行测试

```bash
python -m pytest tests -q
# 98 passed
```

## 许可证

本项目采用 [MIT 许可证](LICENSE)。

## 致谢

- [LangGraph](https://github.com/langchain-ai/langgraph) - 有状态 Agent 编排框架
- [LangChain](https://github.com/langchain-ai/langchain) - LLM 应用开发框架
- [FastAPI](https://github.com/tiangolo/fastapi) - 现代 Python Web 框架
- [PostgreSQL](https://www.postgresql.org/) - 关系型数据库
