# 架构说明 —— 剧本工坊（Script Workshop）

> 本文回答四件事：**包结构怎么分层**、**不同模型厂商怎么适配**、**多 Agent 各是谁**、
> **核心链路从小说到成片怎么走**。踩坑与调试经验见 [`DEVELOPMENT.md`](DEVELOPMENT.md)。

---

## 一、包结构与分层

```
app/
├── main.py / cli.py                         入口层（HTTP / CLI）
├── api/           REST 路由包 —— 按业务域分模块
├── config.py / deps.py                      配置与依赖装配（全项目唯一装配点）
├── domain.py / store.py / workspace.py      领域模型 / 持久化 / 文件系统
│
├── llm/        模型接入层   —— 对上提供能力，对下屏蔽厂商
├── pipeline/   内容生产线   —— 纯逻辑，不依赖 LangGraph / HTTP
├── agent/      改编智能体   —— LangGraph 状态图 + 后台任务运行器
├── chat/       对话编排层   —— 对话式 Agent（复用 agent 的工作流）
├── crew/       剧组 Agent   —— 导演 / 美术指导 / 摄影指导
├── media/      参考资产层   —— 定妆图 → 质检 → 注册 → 回填
└── video/      视频生成层   —— Provider 抽象 + 队列 + 连续性 + 拼接
```

`app/api/` 内部再分一层，避免路由堆在一个大文件里：

```
api/
├── __init__.py   组装 /api 前缀的父 router
├── deps.py       依赖入口（路由统一 deps.store() 取值，测试可整体替换）
├── common.py     共享的序列化与落盘辅助
├── schemas.py    请求模型
├── system.py     运行状态 / 后台任务 / 工作目录
├── projects.py   项目生命周期、初稿生成、导入、落盘、笔记、文件浏览
├── versions.py   剧本版本（含导出）
├── agent_runs.py 改编智能体的运行与审阅
├── chat.py       对话式 Agent 与会话管理
└── video.py      Provider / 模型偏好 / 视频版本 / 生成任务
```

**依赖方向（单向向下，不允许反向或跨层回指）**

```
入口层 (api / cli / main)
   ↓
编排层 (chat / agent)  ──→  crew / media
   ↓                          ↓
生产线 (pipeline)          视频层 (video)
   ↓                          ↓
基础层 (llm / domain / store / config)
```

规则：

1. `pipeline/` 里不准出现 LangGraph 与 FastAPI 的 import（它是纯函数层，可单测、可复用）。
2. 需要模型能力时只 `from ..llm import LLM`，不允许任何模块自己 new `ChatOpenAI` 或直接读写 API key。
3. 路由不直接 `from ..deps import store`，一律经 `app/api/deps.py` 取值——依赖查找是运行时的，
   测试替换一处即可覆盖全部路由。
4. 所有单例（Store / LLM / 视频队列 / 后台任务管理器）只在 `app/deps.py` 里创建，
   入口层取值；测试可以单独构造。后台任务的落库依赖也在这里注入。
5. 状态里只放可序列化数据，依赖（store / llm / tools）通过闭包注入图节点。


---

## 二、模型厂商适配（`app/llm/`）

### 2.1 设计：一个门面 + 一张厂商表

| 文件 | 职责 |
|---|---|
| `client.py` | 门面 `LLM`：`chat()` / `structured()` / `system_prompt()` / `vision()` / `image()` |
| `base.py` | 数据契约：`Modality`（chat/vision/image）、`ModelConfig`、`ProviderSpec` |
| `providers.py` | 厂商表 + `build_chat_model()`（唯一的 `ChatOpenAI` 构造点） |
| `registry.py` | 配置解析：`.env` / DB → `ModelConfig` |
| `vision.py` | 视觉客户端（定妆图质检），OpenAI 兼容多模态消息 |
| `image.py` | 文生图客户端（CogView / OpenAI Images） |

**适配策略：全部走 OpenAI 兼容协议。** 国内厂商（DeepSeek / 智谱 / Moonshot / Qwen）
与本地服务（Ollama / vLLM）都提供 OpenAI 兼容端点，因此不需要为每家引入官方 SDK——
差异只落在三处：**默认端点、默认模型、额外请求体**，用一张声明表描述：

```python
ProviderSpec(
    name="deepseek", label="DeepSeek",
    default_base_url="https://api.deepseek.com", default_model="deepseek-chat",
    env_key="DEEPSEEK_API_KEY",
    supports_vision=True, vision_model="deepseek-v4-flash-vision-exp",
    extra_body=_deepseek_extra_body,   # 推理模型需显式关闭 thinking
)
```

### 2.2 已适配的厂商

| 厂商 | 对话 | 视觉质检 | 文生图 | 备注 |
|---|---|---|---|---|
| OpenAI 兼容（含自建网关 / vLLM） | ✅ | ✅ | ✅ | `OPENAI_BASE_URL` 指向任意兼容端点 |
| DeepSeek | ✅ | ✅ | — | 推理模型需 `DEEPSEEK_THINKING=false` 直出 content |
| 智谱 GLM | ✅ | ✅ | ✅ | 同一个 key 同时可调 GLM / CogView / CogVideoX |
| Moonshot Kimi | ✅ | — | — | 用真实环境变量 `MOONSHOT_API_KEY` 配置 |
| 通义千问 Qwen | ✅ | ✅ | — | 走 DashScope 兼容模式 |
| Ollama（本地） | ✅ | ✅ | — | 无需 key；仅在 `CHAT_PROVIDER=ollama` 时启用 |
| 视频（独立体系） | — | — | — | MiniMax / Runway / Kling / CogVideoX / Sora，见 `app/video/` |

> 非 OpenAI 兼容的厂商（如 Anthropic Messages API）目前**没有**适配：需要为它单独实现
> 协议客户端，而不是加一条 `ProviderSpec`。这是有意的取舍——主流可选厂商里它不占多数，
> 且引入后要多维护一套 SDK 依赖。

### 2.3 配置解析优先级（`registry.py`）

```
显式指定（CHAT_PROVIDER / VISION_PROVIDER / IMAGE_PROVIDER）
   ↓ 没有
.env 厂商优先级链：OPENAI_* > ZHIPUAI_* > DEEPSEEK_*
   ↓ 都没有
数据库 api_providers / model_preferences（前端「设置 → 模型」里配的）
```

- **三个能力维度各自解析，互不干扰**：对话用 DeepSeek、质检用智谱视觉、文生图用 CogView 是允许的。
- 视觉未显式配置时，自动复用一个「自带视觉能力且 key 可用」的厂商，并把模型名换成该厂商的视觉模型。
- 文生图未显式配置时，按 `cogview` → `openai` 顺序找 key。
- 解析结果是一个 `ModelConfig`（`provider / model / api_key / base_url / extra_body / source`），
  上层只消费它，不关心来源是 `.env` 还是数据库。

### 2.4 新增一个厂商要改什么

1. 在 `providers.py` 的 `_register_builtins()` 加一条 `ProviderSpec`（若是 OpenAI 兼容，到此为止）。
2. 若该厂商需要额外请求体，给 `extra_body` 传一个函数。
3. 若它要能在 `.env` 里配置，在 `config.py` 加对应字段，并在 `registry._from_settings()` 里接上。
4. 若它提供新的能力形态（例如 TTS），在 `base.py` 的 `Modality` 加维度 + 新客户端文件。

---

## 三、多 Agent 协作：谁是谁

系统里共有 **4 个 LLM Agent 角色**，分两类：

### 3.1 对话编排（1 个）—— `app/chat/conductor.py`

| Agent | 角色 | 职责 |
|---|---|---|
| **ChatConductor** | 前厅 / 调度 | 绑定 9 个工具理解用户意图，把请求路由到确定性流水线或后台剧组任务 |

它是一个 ReAct 小图（`chat_agent` ↔ `tools`），工具循环上限 8 轮。
关键设计：**审阅动作走确定性路径**（accept/reject 不经过 LLM），避免「对话式工具调用不可靠」导致误操作。

### 3.2 剧组 Agent（3 个）—— `app/crew/`

| Agent | 类 | 输入 → 输出 | 关键约束 |
|---|---|---|---|
| 🎬 **导演** Director | `DirectorAgent` | 剧本 → `SceneBreakdown[]`（分镜） | 一个分镜 = 一段连贯动作 **或** 一段连贯对话；`cut_reason` 必填；**画面调度五件套**必写（`camera.path`/`camera.height` 运镜轨迹与机位高度、带方向的光线、`spatial` 空间关系、`background_action` 背景人物、`action` 的接触动作物理过程），运动镜头缺轨迹会被连续性校验打回；镜头数由模型按内容决定（不写死） |
| 🎨 **美术指导** ArtDirector | `ArtDirectorAgent` | 剧本 → `StyleGuide` | **全片视觉锚的唯一来源**：角色造型 + 环境描述只产一次，下游逐字复用；`camera_style` 要带全片运镜语法与「拍摄呼吸感」，环境描述要写清关键光源方向与常驻背景人群 |
| 📹 **摄影指导** DP | `DPAgent` | 剧本 + 分镜 + 风格锚 → `Shot.video_prompt` | 只做组装：环境锚 + 出场人物锚 + 本镜画面调度 + 风格；写作守七条铁律（动作与运镜并重、保留呼吸感、光影写方向、人物编号与距离、背景人物各有各的事、只写看得见的东西、接触动作写物理过程）；提示词语言与目标视频模型方言对齐 |

三者都继承 `CrewAgent`，输出统一的 `CrewTaskResult`（结构化数据 + 摘要 + 错误列表），
并且都有**规则兜底**：LLM 不可用时返回可用的降级结果，而不是报错中断。

### 3.3 后台任务运行器 —— `app/agent/skills.py`

剧组工具（导演拆解 / 美术指导 / 摄影指导 / 参考资产）都是耗时操作，统一由 `SubAgentRunner`
在后台线程执行，通过 `update_step()` 实时上报进度到前端右栏任务面板；任务起止快照落库
（`subagent_tasks` 表），重启后历史仍可查询。

### 3.4 不是 Agent 的部分（容易混淆，单独说明）

- **改编图节点（7 个）**：`context → plan → propose → guard → review → apply → finalize`。
  它们是 `app/agent/graph.py` 里的固定编排节点，不是自主 Agent——流程由代码决定，
  模型只在 `plan` / `propose` 两个节点里产出内容。
- `guard` 是自纠错闸门（硬校验 + LLM 五维评审），`review` 是 `interrupt` 人机协同点。
- 成片拼接（`app/video/assemble.py`，FFmpeg）也不是 Agent。

---

## 四、核心链路（端到端）

```
① 导入              小说 / 剧本文件（txt / md / docx / 粘贴）
  pipeline/importer.py    编码容错解析 → 原文 + 章节结构

② 生成初稿          pipeline/generation.py（两阶段，防退化）
  Stage 1  _stage_bible    故事圣经：人物 / 地点 / 主题 / 梗概
  Stage 2  _stage_scenes   按戏剧单元拆场（一地 + 连续时间 + 一个目标 + 一场冲突）
                           → Script：scenes（目的/冲突/入出状态）+ beats（动作/对白）
  ★ 容错层：模型 id 不合规 / 结构错位 / 多章塌成一场，都有兼容与退化护栏

③ 改编              app/agent/graph.py（人机协同闭环）
  context → plan(ReAct 查原文/查版本) → propose(结构化 patch)
          → guard(硬校验 + 五维评审，不合格回炉，上限 3 次)
          → review(interrupt：接受 / 编辑 / 重新生成 / 拒绝)
          → apply(落成新版本) → finalize

④ 视觉锚            crew/art_director.py
  StyleGuide：角色造型（character_appearances）+ 环境描述（environment_descriptions）

⑤ 参考资产          app/media/refs.py + app/llm/image.py + app/llm/vision.py
  定妆 prompt → 文生图 → 视觉质检（不合格重生成，≤2 次）→ 注册为全局参考
  → apply_reference_images() 按「场景→环境图 / 人物→角色图」回填到每个镜头

⑥ 分镜              crew/director.py
  SceneBreakdown[] + 连续性计划：reference_group（共享环境分组）、chain_from（首尾帧接力）
  画面调度：camera.path/height（镜头轨迹与机位高度）、带方向的光线、spatial、background_action、
  action 的接触动作物理过程（接触点 / 先后节拍 / 身体姿态 / 不穿模的让位关系）

⑦ 视频提示词        crew/dp.py → 视频工作台 Prompt 人审
  摄影指导提出 Shot.video_prompt 草稿：环境锚 + 出场人物锚 + 本镜画面调度 + 风格
  （锚逐字复用）。用户可以逐镜编辑、保存草稿、标记需修改或批准。
  每次人工操作创建新的 VideoVersion 快照；只有 prompt_status=approved 的镜头可提交。
  工作台支持多选镜头批量审批，版本列表展示 Prompt 审阅汇总，单镜可沿 parent_version_id 查看历史与差异。
  七条写作铁律见 dp.py::_BODY_RULES_ZH：动作与运镜并重 / 呼吸感 / 光的方向 / 人物编号与距离 /
  背景人物各有各的事 / 只写看得见的东西 / 接触动作写物理过程
  （LLM 整段漏写运镜时用 camera.path 兜底补一次）

⑧ 视频生成          app/video/
  registry 选 Provider → queue 提交 + 轮询 + 状态回调写回 DB
  continuity.resolve_continuity() 已实现「reference_group / chain_from → reference_videos」
  （上一镜成片的公开直链作为下一镜的参考素材，无需额外图床）——
  单镜和批量投递都会再次校验 Prompt 是否已批准

⑨ 拼接成片          app/video/assemble.py（FFmpeg concat / filter_complex）
```

**两条贯穿全链路的原则**

1. **视觉锚只产一次，下游逐字复用**——这是跨镜一致性的第一道保障。
2. **AI 只提议，人做决定**——改编走 `interrupt` 四决策闭环；视频先审 Prompt，再审成片，所有操作都进入可回溯的链式快照。

---

## 五、技术债与已完成的整理

本轮（2026-09-11）已解决：

| 位置 | 原问题 | 处理 |
|---|---|---|
| `app/api.py` | 单文件 1400+ 行，业务逻辑写在路由里 | 拆成 `app/api/` 包（7 个域模块 + common/schemas/deps）；路由表逐条比对无增删（66 → 66） |
| `app/chat/conductor.py` | 部分工具直接用 `store.session()` 操作 ORM，绕过 `Store` | 收敛为 `Store` 方法（`get/set_version_breakdown`、`get/set/merge_video_style`） |
| `app/agent/skills.py` | 后台任务只在内存，进程重启即丢 | 起止两个时刻快照落库（`subagent_tasks` 表）；`/api/tasks` 合并内存态与历史态 |
| `app/api/video.py` | `cancel` 只改本地状态，未通知服务商 | 先尽力调用 provider 的 `cancel_job`，失败不影响本地状态收尾 |
| `app/api/system.py` | `/status` 用 openai/deepseek 三元表达式猜模型名（漏了智谱） | 改为读 `LLM.describe()` 的解析结果，另附视觉模型状态 |

仍有待处理：

| 位置 | 问题 | 影响 | 建议 |
|---|---|---|---|
| 全仓 | `ruff` 配置为 `select = ["E","F","I","B","UP"]`、`line-length = 100`，但全量检查有 200 处 `E501` 等未清 | 一旦在 CI 里加 ruff 就会红 | 要么清账（主要是长行拆分），要么把 `E501` 移出 select。`app/api/`、`app/llm/` 这两个新目录目前是全绿的 |
| `app/chat/conductor.py` | 每轮对话重建图与全部工具闭包 | 实测开销可忽略（纯对象装配，无 I/O；LLM 调用才是耗时大头） | 仅在压测显示瓶颈后再做，需要先把 collector 从闭包挪进图状态 |
| `app/agent/skills.py` | 进行中的任务只有内存态（历史已落库） | 重启后运行中的任务面板清空——这是真实情况，不假装还活着 | 若要多实例部署再接队列 |
| `app/api/` | 全部路由无鉴权，且默认可设置任意工作目录 | 仅限本机使用 | 已默认 `API_HOST=127.0.0.1`；若要做多用户需先加鉴权 |


---

## 六、扩展速查

| 想做什么 | 改哪里 |
|---|---|
| 加一个模型厂商 | `app/llm/providers.py` 加一条 `ProviderSpec`；需要 `.env` 配置就同时在 `config.py` 与 `registry._from_settings()` 补字段 |
| 加一个能力维度（如 TTS） | `app/llm/base.py` 的 `Modality` 加枚举 + 新客户端文件 + `LLM` 门面加方法 |
| 加一个剧组 Agent | `app/crew/` 新建继承 `CrewAgent` 的文件 → `crew/__init__.py` 导出 → 要在对话里触发就在 `chat/conductor.py` 的 `build_chat_tools()` 加工具 |
| 加一个视频 Provider | `app/video/providers/` 新建继承 `VideoProvider` 的适配器 → `video/registry.py` 的 `_register_builtins()` 注册 → 先跑「Provider 体检」（见 DEVELOPMENT.md 5.1） |
| 加一个 API 路由 | 在 `app/api/` 对应域模块里加 `@router.xxx`；新域就新建文件并在 `api/__init__.py` 的列表里注册 |
| 加一个持久化字段 | `app/store.py` 加模型字段（新表由 `create_all` 自动建；给老表加列要在 `_ensure_columns()` 里补 ALTER） |
| 加一个生成阶段 | `app/pipeline/` 加模块，由 `agent/nodes.py` 或 `chat/conductor.py` 调用 |


