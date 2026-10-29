# 开发文档 —— 剧本工坊（Script Workshop）

> 面向继续开发本项目的人。除了架构与开发指引，重点记录**踩过的坑**：
> 每条都写清「症状 → 根因 → 解法 → 涉及文件」，避免重复踩。
>
> 本文档基于真实调试过程整理（2026-09 ~ 2026-10），所有结论都在本机实测验证过。
>
> **选型理由**（为什么用这个技术、不为什么用那个）见 [`DECISIONS.md`](DECISIONS.md)；
> **分层结构与核心链路**见 [`ARCHITECTURE.md`](ARCHITECTURE.md)。

---

## 一、架构总览（当前链路）

> 包结构与分层规则见 [`ARCHITECTURE.md`](ARCHITECTURE.md)；这里只画数据流。

```
小说原文
  │
  ├─ pipeline/generation.py 两阶段生成：故事圣经 → 场景规划（按戏剧单元拆场）
  │                  产出 Script：scenes（目的/冲突/入出状态）+ beats（动作/对白）
  │
  ├─ crew/art_director.py   美术指导 → StyleGuide
  │                  ★ 视觉锚的唯一来源：
  │                    character_appearances（按人物名）、environment_descriptions（按地点名）
  │
  ├─ media/refs.py          参考资产流水线（图像级一致性）
  │                  定妆图生成（llm/image.py，CogView）→ 视觉质检（llm/vision.py，DeepSeek 视觉）
  │                  → 注册进 StyleGuide.reference_images → 回填 Shot.reference_images
  │
  ├─ crew/director.py       导演 → SceneBreakdown[]（分镜）
  │                  分镜定义：一个分镜 = 一段连贯的角色动作，或一段连贯的角色对话剧情
  │                  输出连续性计划：reference_group（共享环境分组）、chain_from（首尾接力）、cut_reason
  │
  ├─ crew/dp.py             摄影指导 → 视频提示词草稿（模型感知 + 锚逐字复用）
  │                  ↓
  │   视频工作台              用户逐镜编辑 / 保存 / 标记需修改 / 批准
  │                  只做组装：环境锚 + 出场人物锚 + 本镜动作运镜 + 风格
  │
  ├─ video/providers/*      视频 Provider 适配层（runway/kling/cogvideo/sora/minimax）
  ├─ video/queue.py         异步任务队列（线程池 + 轮询 + 状态回调写回 DB）
  ├─ video/continuity.py    把 reference_group/chain_from 解析成 reference_videos
  ├─ video/finalize.py      成片合成编排（最后一公里）
  │                  收集版本内成功镜头 → 下载 → 逐镜实测时长校准 → 拼装
  │                  → 配音（可选）→ ASS 字幕烧录（可选）→ 成片+SRT 注册为项目素材
  └─ video/assemble.py      FFmpeg 拼接成片
```

**分层原则**：视觉锚只产一次（美术指导），下游逐字复用；LLM 提示词与目标模型方言对齐。

---

## 二、开发环境与启动

```bash
# 依赖（uv 按 .python-version 自动准备解释器，按 uv.lock 精确安装）
uv sync

# 启动后端（开发模式）
uv run python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端
cd frontend && npm install && npm run build   # 构建产物由 FastAPI 托管
```

**关键约定**

- `.env` 是唯一配置入口；改完**必须重启 uvicorn**（`Settings` 是 `lru_cache` 单例，热改不生效）。
- 本机若没有项目自带 Postgres，可用 SQLite 独立跑，不碰别人的容器：
  ```bash
  DATABASE_URL="sqlite:///./data/dev.db" CHECKPOINTER=memory uv run python -m uvicorn app.main:app --port 8000
  ```
- 跑测试：`DATABASE_URL="sqlite:///./data/ci.db" CHECKPOINTER=memory uv run pytest tests/ -q`

---

## 三、核心数据流

| 产物 | 定义位置 | 说明 |
|---|---|---|
| `Script` | `app/domain.py` | 剧本：characters / locations / scenes（含 beats） |
| `SceneBreakdown` + `Shot` | `app/domain.py` | 分镜方案；`Shot` 承载连续性字段与视频状态 |
| `StyleGuide` | `app/domain.py` | 视觉风格指南；**角色造型与环境描述是全局唯一来源** |
| 视频提示词 | `Shot.video_prompt` | DP 提出的草稿；批准后才会喂给视频模型 |
| `VideoJob` | `app/store.py` | 视频任务；状态由队列回调写回 DB |

**`Shot` 字段速查**

- 基础：`shot_type / camera / subject / action / duration_sec / lighting / mood`
- 切镜理由：`cut_reason`（写不出理由就该合并）
- 连续性计划：`reference_group`（共享环境参考分组）、`chain_from`（本镜首帧取自哪一镜尾帧）
- 运行时输入：`reference_images / reference_videos / first_frame_image / last_frame_image`
- 生成状态：`video_prompt / video_url / video_job_id`
- Prompt 审阅：`prompt_status`（`needs_review` / `needs_revision` / `approved`）、`prompt_review_note`

### 3.1 Prompt 人机协同

摄影指导的职责是提出结构化 Prompt 草稿，不负责替作者做最终出片决定。视频工作台把每个镜头分成三个状态：

- `needs_review`：模型刚生成，或用户保存了草稿，不能提交视频任务；
- `needs_revision`：用户认为仍需修改，保留备注并继续编辑；
- `approved`：用户确认当前 Prompt，单镜和批量生成才允许使用。

每次 Prompt 操作都会基于当前 `VideoVersion` 创建新的手动版本，使用 `parent_version_id` 串成版本链。这样 Prompt 文本、审阅备注和批准时点都可追溯，不需要再引入单独的审批表。

后端有两道门：单镜提交前校验当前镜头状态，批量生成只收集 `approved` 镜头。前端按钮状态只是体验层提示，不能替代后端校验。

批量审阅调用 `POST /api/projects/{project_id}/video-versions/{version_id}/prompts/review`，只改变选中镜头的审阅状态并创建新快照。版本列表返回 `prompt_summary`，镜头历史调用 `GET /api/projects/{project_id}/video-versions/{version_id}/shots/{shot_id}/prompt-history`，沿父版本链返回备注、状态和 unified diff。

---

## 四、扩展指南

### 4.1 新增一个视频 Provider

1. 在 `app/video/providers/` 新建适配器，继承 `VideoProvider`（`app/video/base.py`），实现
   `create_job / poll_job / cancel_job`，并声明能力类属性（`max_duration_sec`、`supported_resolutions`、
   `chinese_prompt_support` 等）。
2. 在 `app/video/registry.py` 的 `_register_builtins()` 注册。
3. 在 DB 注册配置（REST）：`POST /api/providers`，`kind="video"`，填 `name/label/base_url/api_key`。
4. **先跑「Provider 体检」再接入**（见 5.1 末尾），别直接进流水线。

### 4.2 新增一个剧组 Agent

1. 在 `app/crew/` 新建文件，继承 `CrewAgent`（`app/crew/base.py`），实现 `run()`。
2. 在 `app/crew/__init__.py` 导出。
3. 若要在对话里触发，在 `app/chat/conductor.py` 的 `build_chat_tools()` 加工具。
4. 参考 `director.py`：LLM 输出必须做**枚举容错 + 范围钳制 + 有界重做**（见 5.2）。

### 4.3 新增一个 API 路由

路由按业务域拆在 `app/api/` 下（system / projects / versions / agent_runs / chat / video）。
新增同域路由直接加在对应文件；新开一域就新建文件并在 `app/api/__init__.py` 的 include 列表里注册。

两条约定：

- 取值一律走 `from . import deps` 再 `deps.store()`，不要 `from ..deps import store` 绑名字——
  测试里 `monkeypatch.setattr(app.api.deps, "store", ...)` 一处即可覆盖全部路由。
- 路由只做参数校验与序列化；业务放 `pipeline/`、`agent/`、`store`（共享辅助放 `api/common.py`）。

---

## 五、踩坑记录

### 5.1 视频 Provider API

#### （1）模型名会失效，别照抄旧值

- **症状**：提交视频任务报 `incorrect model param input`。
- **根因**：MiniMax 旧模型名 `MiniMax-Hailuo-01` 已无效；旧接口的 `MiniMax-Hailuo-02` 也属 v1。
- **解法**：用 V2 接口的 `MiniMax-H3`（`/v2/video_generation`）。改模型前先探测。
- **文件**：`app/video/providers/minimax.py`

#### （2）状态映射的子串陷阱：`"success" in "succeeded"` 是 False

- **症状**：任务在服务商侧早已成功，队列却一直轮询到超时（每任务白等 10–20 分钟）。
- **根因**：`succeeded` 中间是 `succee` 而非 `succes`，所以 `"success" in status` 永远不成立，成功态被映射成 `generating`。
- **解法**：用 `"succeed" in status_str`；状态值统一 `lower()`。**所有适配器都要检查这一点。**
- **文件**：`app/video/providers/minimax.py`

#### （3）查询响应可能把任务对象嵌套在下层

- **症状**：查询接口返回 200，但代码读不到 `status`。
- **根因**：MiniMax V2 的查询响应是 `{"task": {"status": ..., "content": {"url": ...}}}`，顶层没有 `status`。
- **解法**：`task = data.get("task") if isinstance(data.get("task"), dict) else data`，再从 `task` 取状态与 `content.url`。

#### （4）查询路径不是创建路径

- **症状**：`GET /videos/generations/{id}` 返回 **404**。
- **根因**：智谱（CogVideoX）异步任务的查询走 `/async-result/{task_id}`，不是创建路径 + id。
- **解法**：创建 `POST /videos/generations`，查询 `GET /async-result/{id}`。
- **文件**：`app/video/providers/cogvideo.py`

#### （5）状态字段名与结果字段名逐家不同

- **症状**：智谱任务永远 `unknown`，成功也拿不到视频地址。
- **根因**：字段是 `task_status`（值为大写 `PROCESSING/SUCCESS/FAIL`），结果在 `video_result`（**单数**）`[0].url`。
- **解法**：字段名与大小写都要按各家实际响应处理，别假设统一。

#### （6）域名/平台可能不通

- **MiniMax**：`api.minimax.cn` 与 `api.minimaxi.com` 可用；`api.minimax.io`（国际站）**同 key 不通**。
- **智谱**：`open.bigmodel.cn/api/paas/v4`，同一个 key 同时可调 **LLM（GLM）+ 文生图（CogView）+ 视频（CogVideoX）**。

#### （7）免费档与付费档的能力差异要写清楚

- `cogvideox-flash`：**免费**（`usage.total_tokens=0`），但输出约 5s、720p、**无音轨、带水印**。
- `cogvideox-2 / cogvideox-3`：付费档，质量更好（旗舰是 `-3`）。
- MiniMax H3：带音轨，但按 token 计费（实测 6s/768P ≈ **195,294 token**）。

#### （8）内容审核：直陈暴力会被拒

- **症状**：`POST /videos/generations` 返回 **400 Bad Request**。
- **根因**：提示词直写「头部撞击桌面」「脑组织」等触发审核。
- **解法**：改成**暗示不直陈**——「手掌按下后脑的瞬间镜头猛地甩开，只留众人表情」，即可通过。

#### （9）Provider 注册表会把无 key 的实例缓存下来

- **症状**：视频任务失败，错误是 `Illegal header value b'Bearer '`（key 为空）。
- **根因**：先有一次不带 key 的 `get_provider()`（如仅用于费用估算），实例被缓存；后续带 key 的调用直接命中缓存，key 永远进不去。
- **解法**：`registry.get_provider()` 在缓存实例缺 key 而调用方带 key 时就地补齐。
- **文件**：`app/video/registry.py`

#### （10）余额不足是硬失败

- **症状**：`402 Payment Required`，或查询里 `error.code=1008 / message=insufficient balance`。
- **说明**：任务直接失败，需要充值后重试。这类失败**不要与内容审核混淆**（前者无 task_id，后者有 task_id 但 status=failed）。

#### （11）接入新 Provider 前先体检

拿各家 key 探活，避免把「模型名错 / 端点错 / 字段错」带进流水线：

```python
# 1) 鉴权探测：故意给非法参数，能返回「参数错」= 鉴权通过
# 2) 模型探测：给不存在的模型名，返回「模型不存在」= 端点正确
# 3) 真跑一条最短生成，确认状态映射与结果字段
```

---

### 5.2 LLM 输出容错（最容易炸的一层）

> 原则：**永远不要假设 LLM 的输出结构**。一个不合规字段会让整次生成抛异常、静默回退到本地演示数据。
> `app/pipeline/generation.py` 里所有 `_xxxIn` 模型都是为容错而存在的。

| 症状 | 根因 | 解法 |
|---|---|---|
| 整次生成 `mode=local-fallback` | 模型给 `scene_01_wake_up` 这类 id，不符合 `^scene_[0-9]{3,}$` | 场景 id 不合规时**回退纯数字序号**并保证唯一 |
| 同上 | 模型把 `dialogue` 输出成 `{"line": "..."}` 对象 | 加 `field_validator(mode="before")` 解包成字符串 |
| Bible 解析失败（`Field required`） | 模型只给 `name` 不给 `id` | 输出模型里 `id` 设为可选，后续按序号补齐 |
| 整场戏没有节拍 | 模型用 `action`/`dialogue` 数组而非 `beats` | 加兼容层 `_synth_beats()`，`beats` 为空时由数组合成 |
| 导演整次失败 | `camera_type` 不在枚举内 | 枚举容错：别名映射 + 兜底默认（见 `_pick_enum`） |
| 导演整次失败 | `duration_sec=0.8` 或 `20` 超出 `Shot` 范围 | 解析时钳制到合法区间 |
| 接力全部错位 | 多场时模型给的是「场景内局部 order」 | 解析时**全局重编号**，并把 `chain_from` 从局部映射到全局 |
| 多章素材只生成 1 场戏 | 场景规划退化（把整段塞进一场） | 加**退化护栏** `_is_degenerate_plan()` + 带反馈重做 |

**涉及的枚举与范围**（`app/domain.py`）：

- `shot_type`：extreme_wide/wide/medium/close_up/extreme_close_up/over_shoulder/pov
- `camera.type`：static/pan/tilt/dolly/tracking/crane/handheld/zoom/steady
- `camera.speed`：slow/medium/fast；`pacing`：slow/medium/fast/variable
- `Shot.duration_sec`：1–30（但目标模型可行区间通常 4–15，见 5.5）

---

### 5.3 对话模型配置

#### （1）优先级链：改 key 要连上一级一起注释

`app/llm/registry.py` 的默认优先级链是 **OPENAI > ZHIPUAI > DEEPSEEK**。只想切到 DeepSeek，
必须先把 `ZHIPUAI_API_KEY` 注释掉（或置空），否则不生效。
更省事的做法是直接指定：`CHAT_PROVIDER=deepseek`（视觉/文生图同理，见 `VISION_PROVIDER` / `IMAGE_PROVIDER`），
显式指定会跳过整条优先级链。

#### （2）推理模型的 `reasoning_content` 陷阱

- **症状**：模型调用成功（HTTP 200），但 LangChain 拿到的 `content` 是空的。
- **根因**：`deepseek-v4-pro` 是**推理模型**，默认把内容写进 `reasoning_content`，`content` 留空；`max_tokens` 太小时全被思考链吃掉。
- **解法**：显式关闭思考 —— `DEEPSEEK_THINKING=false`，`app/llm/providers.py` 会发 `extra_body={"thinking": {"type": "disabled"}}`，直出 `content`。实测开启思考约慢 2.2 倍（1.37s vs 3.08s）。

#### （3）改 `.env` 必须重启服务

`Settings` 是 `lru_cache` 单例，热改不生效。

---

### 5.4 数据与 ID

#### `normalize_id` 的双前缀 bug

- **症状**：场景的 `location_id` 变成 `loc_loc_main`，与地点 `loc_main` 对不上；依赖地点名的查找（如环境锚）全部落空。
- **根因**：主值 slug 为空、回退到 `fallback` 时，fallback 自带的 `loc_` 前缀**没被剥掉**，又拼了一次前缀。
- **解法**：fallback 也先剥前缀（抽成 `_strip_prefix()` 复用）。
- **文件**：`app/domain.py`

#### 任务只在内存里会丢

视频任务与后台任务的状态若只在内存，进程重启即丢。两者现在都通过落库解决：
视频任务是「状态回调写回 DB」（`app/main.py` 的 `_wire_video_job_writeback`），
后台任务是「起止两个时刻各落库一次」（`app/agent/skills.py` 的 `SubAgentRunner._persist`
→ `subagent_tasks` 表，`/api/tasks` 合并内存态与历史态）。
注意：**进行中**的任务本身随线程终止，落库只保证已完成任务的历史可查，不假装它还在跑。

> 踩坑：测试里后台任务 runner 若不显式绑定测试库，会经由全局 `deps.store()` 去连 `.env`
> 里配置的开发库（本机是 Postgres），连接不可达时会把整个测试卡住。`tests/test_api.py`
> 的 client fixture 因此额外替换了 `app.api.deps.subagent_runner`。

---

### 5.5 视频一致性（提示词工程）

这是本项目最核心的领域经验。

#### （1）文生视频每个镜头是独立采样，只靠 prompt 无法跨镜一致

- **现象**：同一角色在不同镜头里长相/服装变化，场景也漂移（甚至漂成西方人）。
- **解法**（三层）：
  1. **视觉锚逐字复用**：环境描述与人物造型由美术指导产出一次，代码**逐字**拼进每个镜头（`app/crew/dp.py` 的 `_apply`）。不许每镜重新描述。
  2. **人物按镜过滤**：只列本镜实际出场的人，别把全场人物塞进每个镜头。
  3. **显式写「中国人 / 东亚面孔」**：否则模型默认漂成西方人。

#### （2）分镜切太碎 = 不连贯 + 更贵

- **错误做法**：真人影视的「覆盖式拍摄」思路（一人一切、正反打、谁说话切谁）。
- **正确做法**：**一个分镜 = 一段连贯的角色动作，或一段连贯的角色对话剧情**。具体执行：把该场节拍流按类型切成连续的「动作段」和「对话段」，每段一镜。
- **配套约束**：`cut_reason` 必填（写不出理由就合并）；禁止相邻镜头是同一主体的重复特写。

#### （3）镜头数不能盲目固定

- 既不能写死 8 镜，也不能写死 3 镜 —— **交给模型按内容判断**。
- 但必须给**约束 + 校验**：时长区间、切镜理由、分组与接力自洽（`director._validate_continuity`），不合格就带反馈重做。

#### （4）剧本层退化会毁掉下游

- **现象**：多章素材被塞进 1 场戏，下游导演只能被迫「一人一切」硬切。
- **解法**：上游强制「按戏剧单元拆场」（一场 = 同一地点 + 连续时间 + 一个戏剧目标 + 一场冲突），并加退化护栏。

#### （5）单镜时长必须落在模型可行区间

导演规划的时长要和目标模型对齐（如 CogVideoX 约 5s/条，MiniMax H3 支持 4–15s）。规划 2s / 20s 这种无法执行的时长会直接失败或被忽略。

#### （6）参考素材需要公开 URL

MiniMax / 智谱的参考图/参考视频都要公开 URL。**零托管技巧**：上一镜成片的 `video_url` 本身就是公开直链，可直接作为下一镜的 `reference_videos`（`app/video/continuity.py`）。

#### （7）账户余额要盯

MiniMax 按 token 计费（6s/768P ≈ 19.5 万 token/条）。反复「盲出片再返工」是最大的浪费——先做 previz/参考注册再出片。

---

### 5.6 编排与运行时
#### （1）对话式工具调用不可靠

- **症状**：用户/脚本让 Agent「生成风格指南」，模型回复"已启动任务 task_0001"，但**任务根本没创建**（它复述了历史任务号）。GLM 与 DeepSeek 都出现过。
- **判定方法**：不要相信回复文本里的任务号，要用**任务差集**（`GET /api/tasks` 前后对比）确认真实新任务。
- **建议**：确定性流水线直接调用 `run_director / run_art_director / run_dp`，不要绕道 LLM 选工具。

#### （2）`store` 参数遮蔽模块名

- **症状**：`'Store' object has no attribute 'Project'`。
- **根因**：函数参数 `store`（Store 实例）遮蔽了模块名，`store.Project` 解析成实例属性。
- **解法**：模型类显式导入：`from .store import Project`。

#### （3）API 只落库、不投递

- **症状**：视频任务永远 `pending`。
- **根因**：创建任务的接口只写了 DB，没有提交到异步队列；`retry` 也只重置状态、不重投。
- **解法**：创建/重试都调用统一的投递函数，状态由队列回调写回 DB。

---

### 5.7 本机环境

| 坑 | 现象 | 解法 |
|---|---|---|
| 系统代理劫持 localhost | 本机请求超时 / 被代理吞掉 | httpx 用 `trust_env=False` |
| 未安装 ffmpeg | 拼接报「FFmpeg 未找到」 | `pip install imageio-ffmpeg`，取其二进制放进 PATH |
| 文本文件是 GBK | `UnicodeDecodeError` | 按 `utf-8 → gb18030 → utf-16` 顺序尝试解码 |
| Windows 下 curl 传中文 JSON | `invalid unicode code point` | 改用 Python httpx 发请求 |
| Postgres 容器角色不存在 | `role "script" does not exist` | 本次开发用 SQLite（`DATABASE_URL=sqlite:///...`） |
| 轮询上限太低 | 高峰期任务被判超时 | 提高 `MAX_POLLS`（服务商侧排队可能超过 10 分钟） |

---

### 5.8 参考资产层（图像级一致性）

> 这是「工业级思路」的第一阶段：产角色/场景定妆图 → 视觉质检 → 注册为全局参考 →
> 回填到镜头。相关代码：`app/llm/image.py`（文生图）、`app/media/refs.py`（流水线）。

**为什么需要它**：文字锚只能「减少」跨镜漂移；把同一个角色的**图**作为参考喂给视频模型，
模型是「看见」同一个人，强度高一个量级。

**流程**：定妆 prompt → 文生图 → 视觉质检 →（不合格重生成，最多 N 次）→ 注册 → 回填镜头。

#### 文生图（智谱 CogView）的坑

- 端点是**同步**返回：`POST /images/generations` → `{"data":[{"url": "..."}]}`，直接取 `data[0].url`（不像视频是异步轮询）。
- 与 LLM / CogVideoX **共用同一个智谱 key**；key 存在 DB `api_providers` 里 `kind="image"` 的行（`resolve_image_key` 优先 DB，再回落环境变量/Settings）。
- 免费档 `cogvideox-3-flash`（文生图是 `cogview-3-flash`）出图**带平台水印**、**URL 有有效期（约 7 天）**；付费档质量更好。

#### 视觉质检（DeepSeek 视觉模型）的坑

- **图片是服务端拉取**：`image_url` 必须当时可达，否则报 `Failed to download image`。图片 URL 失效/被回收就会失败——**base64 data URI 也支持，更稳**（下载后转 `data:image/png;base64,...`）。
- **输出在 `reasoning_content`**：该模型是推理模型，`content` 可能是空的，要兼容读 `reasoning_content`（和对话模型同一个坑）。
- **判定标准必须「只对致命问题 FAIL」**：早期把「有无水印」「家具数量是否一致」也算 FAIL，结果**永远不合格、重试白跑**（平台水印是免费档必带的）。正确做法是只对「画面主体类型错 / 人物不对」这类致命问题判 FAIL，其余作为提示。
- **要处理角色自身设定**：戴面具/头盔的角色不能要求「东亚面孔」——否则必然 FAIL。质检标准里要写明例外。

#### 回填到镜头

- `apply_reference_images()` 按「场景 → 环境图、人物 → 角色图」把注册表映射进 `Shot.reference_images`（上限 9）。
- 参考注册表存在 `StyleGuide.reference_images`（`{名称: 图片URL}`），随风格指南一起持久化在 `projects.video_style_json` —— **不需要改数据库表**。

#### 一致性效果（已实测）与两个限制

- **效果**：把同一张角色定妆图作为**首帧**（图生视频）喂给 3 个不同动作的镜头，用视觉模型判定：t=0.2s 与 t=3.0s 均 **PASS**——三镜被判定为同一人物（连「颈部右侧的痣」都一致）。
- **限制 1：水印会传播**。智谱 CogView **各档（含付费 cogview-4）都带水印**，参考图的水印会出现在生成视频里。生产环境需要换无水印图源（自建开源模型 / 其他图床级服务）。
- **限制 2：智谱 CogVideoX 只有「首帧图」没有「参考图」**。真正的 reference_image（多主体参考）目前只有 MiniMax H3 支持；用首帧做的锁定其实更强（首帧就是那个角色），但灵活度较低。

---

### 5.9 成片合成与字幕（2026-10 最后一公里）

> 相关代码：`app/video/finalize.py`（合成编排）· `app/media/dubbing.py`（配音）· `app/media/subtitles.py`（字幕）

#### （1）双 deps 单例陷阱：根 `deps.py` 加了还不够

- **症状**：路由运行时 `AttributeError: module 'app.api.deps' has no attribute 'finalize_manager'`，
  但**导入期完全正常**（`import app.main` 不报错）。
- **根因**：项目有**两个** deps 模块——
  - `app/deps.py`：全项目唯一装配点，真正创建单例（`@lru_cache`）。
  - `app/api/deps.py`：API 层的晚绑定入口，**路由只认这个**。
  新增单例只在根 deps 加，API 层拿不到。
- **解法**：两个地方都要加（`app/deps.py` 建、`app/api/deps.py` 再导出）。
- **⚠️ 检测方法**：这类错误**只有发真实请求才会暴露**。单元测试用 `monkeypatch` 直接替换依赖，
  绕过了这条路径。**新加单例后必须用 TestClient 打一次真实 HTTP 请求冒烟**，
  只跑 `pytest` 是不够的。
- **文件**：`app/deps.py` · `app/api/deps.py`

#### （2）`.env` 只进了 Settings，没进 `os.environ`

- **症状**：视频能出片（key 走数据库 `api_providers`），但配音永远失败，报 key 缺失。
- **根因**：pydantic-settings 只把 `.env` 的值读进 `Settings` 对象，**不会导出到进程环境变量**。
  而 TTS 的回落链是 `resolve_tts() → os.environ["MINIMAX_API_KEY"]` 直接读环境变量——链是断的。
- **解法**：`app/main.py` 顶部加 `load_dotenv()`，进程启动时先落进环境变量。
  注意这与「改 `.env` 必须重启」是同一条约束的两面（见 5.3(3)）。
- **文件**：`app/main.py` · `app/llm/tts.py`

#### （3）provider 实际时长 ≠ 计划时长，时间轴会越往后漂越大

- **现象**：字幕和配音整体后移，末尾明显对不上画面。
- **根因**：v6 实测——计划 6+8+6=20s，成片实测 **21.2s**。按计划时长排配音/字幕，
  每一处偏差都往后累积。
- **解法**：`finalize` 在**下载之后**逐镜实测真实时长，用 `model_copy(update={"duration_sec": ...})`
  替换镜头时长，配音排程与字幕估算都用校准后的镜头。
- **文件**：`app/video/finalize.py::finalize_film`

#### （4）先测量，后 move

- **症状**：注册成片素材后拿到的时长是 0。
- **根因**：`_register_asset()` 会把文件 **move** 进素材目录，move 之后原路径不存在，
  再去量就量到空文件。
- **解法**：**时长必须在 move 之前量**。顺序反了就是 0。
- **文件**：`app/video/finalize.py`

#### （5）便携版 ffmpeg 没有 ffprobe

- **症状**：成片时长恒为 0；质检抽的 5 帧全挤在片头 8 秒内。
- **根因**：本机 `imageio-ffmpeg` 提供的便携二进制**只有 `ffmpeg.exe`，没有 `ffprobe.exe`**。
- **解法**：统一的三级降级链——**ffprobe → 解析 `ffmpeg -i` 的 stderr `Duration:` 行 → 返回 0 由调用方兜底**。
  `finalize._media_duration_sec` 与 `qa._duration` 两处都要有。
- **文件**：`app/video/finalize.py` · `app/video/qa.py`

#### （6）ASS 字幕烧录：Windows 盘符要转义

- **解法**：字幕滤镜的路径里的盘符冒号会被 FFmpeg 误解析，要写成 `C\:/...` 并用单引号包裹整个路径。
  用 `subtitles` 滤镜**单次重编码**，不要分两步（先烧字再转码，画质二次损失）。

#### （7）降级阶梯要写死，别让一步失败毁掉整条链路

- 配音失败 → 交**静片 + 估算字幕**；
- 烧录失败 → 交**无字幕成片**；
- 单镜下载失败 → **跳过并警告**，其余镜头照常合成。
- 真正致命的只有两种：**没有任何可用镜头**、**拼装失败**。

---

### 5.10 对话流式输出（2026-10）

#### （1）`ChatOpenAI` 不开 `streaming`，前端就没有流式

- **症状**：回复（含思考内容）整轮结束后一次性到达，前端完全没有流式观感。
- **根因**：`build_chat_model()` 的默认参数里没有 `streaming=True`。
- **解法**：`app/llm/providers.py::build_chat_model()` 统一带上 `"streaming": True`。

#### （2）`AIMessageChunk.type` 返回 `'AIMessageChunk'`，不是 `'ai'`

- **症状**：流式 token 一个都不出来。
- **根因**：代码写的是 `if getattr(msg_chunk, "type", "") != "ai": continue`，
  但 LangChain 的 `AIMessageChunk.type` 实际返回 **`'AIMessageChunk'`**，所有块都被过滤掉了。
- **解法**：**用 `isinstance` 判断**，不要比较 `type` 字符串：
  ```python
  if not isinstance(msg_chunk, AIMessage):
      continue
  ```
  字符串比较是这里最容易犯的错——它不报错，只是静默丢光。

#### （3）长篇建图要防重复

- **症状**：同一本书被反复建章节地图，每次几分钟，token 白烧。
- **解法**：`map_novel` 先查 `project.novel_map` 里已有章节数，已有则直接拒绝并提示用户
  「直接说挑一段改编」；只有用户明确要求重建时传 `rebuild=true`。

---

### 5.11 长篇改编与「模型编造」（2026-10）

#### （1）一次生成有容量上限，选段要按容量切

- **现象**：用户选了 3 章的区间，生成结果只覆盖了选段**开头一小段**。
- **根因**：单次生成的原文容量约 **1.2 万字**（`novel_map.ARC_CHAR_BUDGET = 12000`），
  超过就截断。注意这与「触发长篇提示」的阈值不是同一个数——
  后者是 `conductor.LONG_TEXT_CHARS = 1200 × 12 = 14400`（约 1.44 万字）。
- **解法**：有章节地图时，不传 `to_chapter` 就按 `next_to_chapter()` 按容量自动续接；
  选段超容量时在回复里**明确告知**「初稿只覆盖了选段开头，建议切到 2 章左右」。

#### （2）模型会在没调工具的情况下编造结果（deepseek 实测）

- **症状**：模型回复「已生成初稿版本 ver_xxx」，但**根本没有这个版本**——它照抄了历史消息里的
  轨迹格式，凭对话记忆编了一份结果。
- **根因**：上下文里存在「［本轮动作］生成初稿：已生成初稿版本 ver_xxx…」这类历史文本，
  模型把它当成了格式模板。
- **解法**：**确定性护栏**——`app/chat/conductor.py` 的 `_CLAIM_PATTERNS` 匹配「已生成初稿 / 已改编到第 /
  章节地图已建成 / 个候选故事弧 / 已提交出片 / 已批准」等结果短语；若本轮**没有任何真实工具返回**，
  就追加 `_CORRECTION_PROMPT` 让模型重跑一轮。回复末尾再追加 `_FABRICATED_NOTICE` 说明是误报。
- **同类问题**见 5.6(1)：**不要相信回复文本里的任务号**，用任务差集确认真实新任务。

#### （3）摘要与剧本的输出容错

- 解法同 5.2 的思路：摘要/剧本的模型输出都要容错解析，**不能假设结构**。

---

### 5.12 依赖装配与单例（2026-10）

| 坑 | 现象 | 解法 |
|---|---|---|
| 双 deps 模块 | 路由运行时才报 `AttributeError`，导入期无感 | 根 `deps.py` 与 `api/deps.py` 两处都加；**必须用 TestClient 发真实请求冒烟**（见 5.9(1)） |
| `load_dotenv` 缺失 | 配了 `.env` 但 `os.environ` 为空，配音链断 | `app/main.py` 顶部 `load_dotenv()`（见 5.9(2)） |
| 路由直接绑依赖名 | 测试无法整体替换 | 路由一律 `from . import deps` 再 `deps.store()`（见 `DEVELOPMENT.md` 4.3） |
| `Settings` 是 `lru_cache` 单例 | 改 `.env` 不重启不生效 | 重启；或改完调 `reset_llm()` 热重建模型层 |

---

### 5.13 提示词质量 eval（2026-10）

> 详细说明见 [`../evals/README.md`](../evals/README.md)；选型理由见 [`DECISIONS.md`](DECISIONS.md) D-13。

#### （1）确定性断言最危险的失败模式是**误报**，不是漏报

- **现象**：审计器对**真实链路产出的提示词 4/4 全误报**「疑似一镜多运镜」，
  每个镜头的 `prompt_audit` 都挂着假告警，用户审阅时被反复干扰。
- **根因**：两处叠加——
  1. 提示词里带**全片风格段**（美术指导的 `camera_style`，描述整部片的运镜语法），
     每个镜头都带一遍。统计运镜时没排除它，等于把全片语法算成本镜的运镜。
  2. 运镜动词**没有镜头语境要求**：「在靠门地面拉出一道冷光带」里的「拉出」被当成 pull-out。
- **解法**：新增 `find_camera_moves()`（要求动词附近有镜头/摄影机/机位等语境词）
  与 `strip_style_block()`（剥掉全片风格段，容忍末尾标点从「。」变「，」），
  `audit_video_prompt()` 改为用这两者，并接受 `style_context` 参数。
- **调用点**：dp.py 传 `style`；`app/api/video.py` 传 `current.style_guide.camera_style`
  （新增 `_style_context()` 辅助）；`app/chat/conductor.py` 同样传。
- **⚠️ 教训**：断言库一定要有**录制真实产出**的离线回归层（`evals/fixtures/`）。
  只用手写的坏例子测断言库，测不出误报。

#### （2）LLM 输出不确定，回归信号会被抖动淹没

- **现象**：同一份代码两次跑出的分镜与提示词并不相同；默认温度 0.4 下差异更大。
- **根因**：`ModelConfig.temperature` 默认 0.4。采样带来的随机性会让「这次改动是不是退化了」
  这个问题无法回答。
- **解法**：
  1. eval 专用模型把温度钉到 **0**（贪心解码）——为此给 `LLM.__init__` 与 `build_llm`
     加了 `temperature` 覆盖参数（生产链路不受影响）。
  2. 出现 critical 时**自动复跑一次**，两次都失败才算稳定缺陷。
- **注意**：温度 0 也不保证逐字一致（远端模型有别的随机源），所以复跑机制不能省。

#### （3）模型余额耗尽不是质量回归

- **现象**：eval 跑着跑着出现 `402 Insufficient Balance`（智谱是 `429 code 1113`），
  case 全部失败。
- **根因**：把基础设施故障当成质量失败，报告里一片红，实际是没跑成。
- **解法**：`EvalRunner` 识别余额/限流/鉴权/连接类错误，标记为 **blocked**——
  **不计入失败**，但在报告里显式列出，并让 `python -m evals.run` 返回退出码 2。
  「跑不动」不能被误读成「跑过了且通过」。

#### （4）锚复用判定要看整体，不能只看开头几个字

- **现象**：`appear[:16] not in prompt` 判成「没复用人物锚」，但锚其实**完整地**在提示词里。
- **根因**：DP 偶尔会重写锚里的个别词，只比对前 16 字会把「轻微改写」误判成「完全没复用」。
- **解法**：改成**整段锚是否原样出现** + `difflib` 相似度分级——
  原样出现=通过；相似度 ≥85% 但非原样=warn（轻微改写）；<85%=critical（没复用）。

#### （5）eval 找出的提示词缺陷：否定句

- **现象**：judge 与确定性层同时报出提示词里有否定式描述——
  「眼睛没有看任何地方」「避免均匀平光」「低头快走掠过，没有停留」。
- **根因**：视频模型会把被否定的内容**照画出来**（这是提示词工程的常识，
  但写作规则里虽然写了「禁止否定句」，模型并不总是遵守；且美术指导的风格段里也会冒出来）。
- **解法**：在美术指导与摄影指导的写作规则里补强——
  ① 美术指导新增第 6 条：五样产出（会被**逐字复制进每个镜头**）一律不写否定句，
  给出正向改写示例；② 摄影指导第 8 条补上两类高发写法的改写示例。
- **实测**：10 条 case 的 DPT-04 从 8 条 critical 降到 **0 条**。

#### （6）全片风格段逐字贴进每个镜头 = 每个镜头都收到第二套矛盾指令

- **现象**：judge 的「克制度」维度只有 **44.9 分**（五维最低），其他四维都在 70-82。
- **根因（走了两次弯路才找准）**：`lighting_style` + `camera_style` + 色调 被整段贴在
  每一个镜头的末尾，而**镜头 body 自己已经写了光影和运镜**。于是同一段提示词里出现两套
  互相矛盾的规格，视频模型只能随机挑一套执行。judge 的实际投诉：
  - 「镜头固定不动」，末尾又被贴上「保留细微的手持浮动」「偶尔略高俯看」；
  - 「冷绿日光灯为主光」，末尾又贴「暖黄灯为主光」；
  - 分镜写「轻微仰拍」，末尾写「与视线齐平」「略高俯看」。
- **第一次修错了方向**：以为只是「运镜动词列举害的」，就去剥运镜子句——
  judge 只从 44.9 升到 47.0，基本没动。**证据在 judge 的 evidence 字段里，不在猜测里。**
- **真正的解法：风格段「只补空，不覆盖」**（`DPAgent._style_text(style_guide, body=...)`）：
  - body 已经写了光影 → 不贴 `lighting_style`；
  - body 已经写了摄影机/运镜 → 不贴 `camera_style`；
  - 色调永远贴（配色不与单镜描述冲突，且是跨镜统一的必要信息）。
  认知转变：**风格指南是给「写这个镜头的人」看的设计依据，不是要逐字贴给视频模型的文本。**
- **配套**：
  1. 美术指导的 `camera_style` 只写「不与具体镜头冲突」的风格身份，禁止列举具体运镜（给正反例）；
  2. `dramaturgy.strip_camera_moves()` 兜底剥离运镜子句（`camera_style` 要贴时用）；
  3. 摄影指导规则补「本镜运镜只写 camera_path 指定的那一种」。
- **实测**（10 条 golden case，同一套 case，deepseek-flash 温度 0）：

  | 维度 | 修复前 | 修复后 | 变化 |
  |---|---|---|---|
  | 克制度 restraint | 47.0 | **72.9** | **+25.9** |
  | 一致性 consistency | 62.6 | **78.1** | **+15.5** |
  | 可渲染性 renderable | 81.6 | 85.8 | +4.2 |
  | 戏剧性 dramatic | 80.2 | 80.0 | −0.2 |
  | 具体度 specificity | 84.3 | 84.5 | +0.2 |
  | **总分** | **72.9** | **81.0** | **+8.1** |

  确定性层 critical **0 条**、warn 1 条（残留一条「疑似一镜多运镜」提醒）。

- **测试**：`tests/test_crew_video.py` 锁住两条不变量——
  组装后提示词里的运镜动词不超过一种；body 已写光影/运镜时风格段不得重复贴。

#### （7）MiniMax 的 `/chat/completions` 不支持 `response_format=json_object`

- **症状**：结构化输出报 `2013 unknown response_format type`。
- **根因**：MiniMax 的标准 OpenAI 兼容路径能正常对话（`/v1/chat/completions` 可用），
  但**不认 `response_format`**。
- **解法**：`ProviderSpec` 加 `supports_json_mode` 字段；置 `False` 的厂商，
  `LLM.structured()` 自动降级为「提示词要求 JSON + 容错解析 + 失败重采样」
  （`client._JsonPromptStructured`）。
- **附带价值**：MiniMax 因此成为**一把 key 打通对话 / 视频（H3）/ 配音（T2A）**的选项。

#### （8）余额耗尽时三家一起倒，逼出了「blocked」这个状态

- **现象**：DeepSeek `402 Insufficient Balance`、智谱 `429 code 1113`、MiniMax `402 (1008)`。
- **根因**：`.env` 里的 key 都指向已耗尽的账户；`llm.available` 仍然是 True
  （配置存在 ≠ 能调用），所以 CI 会以「质量回归」的假象失败。
- **解法**：
  1. `EvalRunner` 识别余额 / 限流 / 鉴权 / 连接类错误 → 标记 **blocked**，不算质量失败；
  2. `evals/test_eval.py` 的 `eval_llm` 夹具**先探活一次**（`probe_llm`），探不通就 skip；
  3. `python -m evals.run` 遇 blocked 返回退出码 **2**（环境问题）而不是 1（质量失败）。
- **教训**：**「跑不动」必须和「跑过了且没通过」严格区分**。否则每次余额告急，
  质量信号就被基础设施噪音淹没。

#### （9）否定句靠提示词管不住，要有界修复兜底

- **现象**：写作规则第 8 条明写「禁止否定句」、还加了「交稿前逐句自查」，
  但概率模型仍会漏——10 条 case 里约 1 条稳定出现「视线扫过空椅子**但没有停留**」。
- **根因**：**负面约束对概率模型天然不可靠**。规则能降低发生率，降不到零。
- **解法**：`DPAgent._repair_negations()` —— 装配完成后检查哪些镜头的提示词仍含否定词，
  **只把这些问题镜头的 body** 送给模型要求改写成正向，然后重新装配。
  - **只修 1 轮**：修不掉就交给逐镜审计提醒，不开无限循环；
  - **只送有问题的镜头**，无关镜头不重写（省 token，也避免把好的改坏）；
  - **不采纳仍含否定词的改写**，免得来回改更糟；
  - **修复失败不连累结果**：模型不配合时保留原稿，只记一条 warning。
- **实测**：`object_carry` 从「两次复跑都 critical」变成连跑三次干净。

#### （10）技能模板不能用 `str.format()`

- **现象（预防性）**：写作规则里全是 JSON 示例——`{"scene_id": "scene_001"}`。
- **根因**：`str.format()` 会把**所有**单花括号当占位符，`{"scene_id"...}` 直接抛
  `KeyError: '"scene_id"'`。
- **解法**：模板只认双花括号 `{{var}}`，用正则替换，单花括号原样保留。
  条件块也只做一层（`{% if x %}…{% else %}…{% endif %}`），不支持嵌套。
- **另一半**：**缺变量必须报错**。静默留一个 `{{x}}` 进最终提示词，
  比运行时报错更糟——那会让模型看到一段字面量的花括号。
- **文件**：`app/skills/loader.py`

#### （11）有角色出场却没带外观锚

- **现象**：eval 报 `DPT-10 没有复用人物锚「徐姐」的造型（相似度 14%）`，
  两次复跑都在，是稳定缺陷。
- **根因**：摄影指导为每个镜头回一个 `characters` 列表，`_apply()` 按这个列表贴人物锚。
  模型偶尔漏报出场人物——body 里明明写了「徐姐横臂挡在楼梯口」，列表里却只有「马三」。
  于是这个角色在画面里露脸却没有外观锚，跨镜必然长相漂移。
- **解法**：`_apply()` 加**确定性补漏**——body 里点名出现的本场人物，即使 LLM 列表漏了，
  也把锚补进去。原则「视觉锚只产一次、下游逐字复用」不能靠模型自觉。
- **反向约束**：没在 body 里点名的角色**不许**塞进来（避免每个镜头都带全员锚，
  既浪费预算又让模型分不清主次）。
- **测试**：`test_dp_backfills_anchor_for_named_but_unlisted_character` +
  `test_dp_does_not_add_anchor_for_absent_character`。

---

### 5.14 主 Agent 按需加载技能（2026-10）

#### （1）把触发器一起搬进技能，模型就"不会做事了"

- **现象（预判，已避开）**：D-12 之后第一反应是"主 Agent 的 15 条规则也搬进技能"。
- **为什么错**：那 15 条是**路由信息**（用户说"出片"该调哪个工具），每一轮都要用。
  搬进技能 = 每轮多一次工具往返，而且**模型一旦没加载就等于不会做事**——
  这不是省 token，是把可靠性押在"模型每次都记得加载"上。
- **正确分界**：**"该做什么"留在提示词，"怎么做 / 什么顺序 / 什么会失败"进技能。**
  提示词因此只从 1890 字降到 1748 字（还多了 4 行技能目录）——**这次改造的收益不是变短，
  而是细则终于可写、可维护、可单测。**

#### （2）"进入领域前先加载技能"是句废话，得写成"按动作"

- **现象**：软要求版本实测"帮我出片吧" → **0/3 加载技能**，模型只调了 `list_video_shots`。
  它把"进入领域"理解成了"先查状态"，而不是"要动手了"。
- **解法**：按**动作**规定顺序——「本轮只要要动手（生成/改编/拆解/提交/批准/合成），
  第一个工具调用就该是 `load_skill`；只读盘点（看进度、看待批）可以先查，动手前补上」。
- **实测**：改完 3/3 稳定加载；「拆好了吗」3/3 不加载（纯盘点，不该浪费一次往返）。
- **教训**：**软要求写不进概率模型的行为里。要么给顺序，要么给反例。**

#### （3）`audience` 写错会「技能存在，但永远不被加载」

- **现象（预防性）**：frontmatter 里 `audience: mian` 拼错。
- **后果**：技能既进不了主 Agent 的目录、又混进剧组目录，表现为"文件明明在、
  模型从来不用"，这种静默失效最难查。
- **解法**：`_parse()` 里非法受众直接 `ValueError`，由既有逻辑 log.error 跳过该技能；
  测试 `test_unknown_audience_is_loud` 锁住这条。
- **顺带的边界**：主 Agent 的目录里**不许出现剧组技能**。主 Agent 不执行分镜，
  列进去既是白付 token，也会诱导它越位去"自己写分镜"——**目录本身就是一种授权**。

#### （4）`load_skill` 传错名字：返回文本，不要抛异常

- **原因**：工具抛异常会在当轮消息流里插一条错误，模型连"改口换名字"的机会都没有。
- **解法**：未知技能返回 `没有这个技能：xxx。可加载：a、b、c`——把可用清单直接给它。
- **测试**：`test_load_skill_rejects_crew_skill_and_typos`（含拼错、空串、剧组技能三种）。

#### （5）提示词是代码，要有预算和护栏测试

改造提示词最容易的失误是**漏掉一条流程**或**丢掉一条铁律**。三条测试兜住：

- `test_every_trigger_points_at_a_real_tool`：14 条触发器逐条断言"这一行指向真工具"，
  工具改名/删掉会直接红；
- `test_system_prompt_keeps_hard_rules`：事实约束、不替用户决定、MiniMax BYOK 不许丢；
- `test_system_prompt_stays_within_budget`：<2400 字，防止以后有人往提示词里堆细则。

外加 `test_main_skills_related_tools_exist`：每个技能末尾"相关工具"点名的必须是真实工具，
防止代码改名后技能文档悄悄失真。

---

## 六、排查手册（症状 → 先查什么）

| 症状 | 先查 |
|---|---|
| 剧本生成 `mode=local-fallback` | 服务端日志里的 validation error（`app/pipeline/generation.py` 的容错模型是否漏了字段） |
| 提示词里缺少某个锚 | 风格指南是否生成（`projects.video_style_json`）；锚的键是否与地点名/人物名对得上；`normalize_id` 是否又出双前缀 |
| 视频任务失败 | 错误信息里是 `402/insufficient balance`（余额）还是 `400`（内容审核）还是 `Invalid header`（provider key） |
| 任务长时间 `generating` | 直接拿 `external_task_id` 查服务商真实状态，再对照状态映射（子串陷阱） |
| 后台任务没动静 | 用 `GET /api/tasks` 确认任务是否真的创建（别信回复文本） |
| 分镜切得很碎 | 上游是否把多章塞成了一场戏；导演提示词是否被改回了「覆盖式拍摄」 |
| 参考图质检永远不合格 | 判定标准是否把「水印 / 细节数量」也算 FAIL；角色是否戴面具（东亚面孔那条要写例外） |
| 视觉质检报 `Failed to download image` | 图片 URL 是否失效；改用 base64 data URI |
| 成片合成接口 500 且报 `AttributeError` | 新单例只在根 `deps.py` 加了，忘了 `app/api/deps.py`（见 5.9(1)） |
| 配音永远失败但视频能出 | `.env` 没落进 `os.environ`，TTS 回落链断了（见 5.9(2)） |
| 字幕/配音整体后移、末尾对不上 | 用了计划时长而非实测时长；是否走了逐镜校准（见 5.9(3)） |
| 成片时长恒为 0 | 便携 ffmpeg 缺 ffprobe；是否走了 stderr 兜底（见 5.9(5)） |
| 前端没有流式效果 | `build_chat_model()` 少了 `streaming=True`（见 5.10(1)） |
| 流式 token 一个都不出来 | 用 `type == "ai"` 过滤 chunk，应改 `isinstance`（见 5.10(2)） |
| 模型报「已生成 ver_xxx」但版本不存在 | 编造护栏没触发，或本轮确实调过工具；查 `_CLAIM_PATTERNS`（见 5.11(2)） |
| 长篇选段只生成了开头一小段 | 选段超单次容量（约 1.2 万字），需切小（见 5.11(1)） |
| 技能文件明明在、模型从来不用 | `audience` 是否拼对（`crew`/`main`）；main 技能是否真的进了 `system_prompt()` 的目录（见 5.14(3)） |
| 模型没加载细则就直接动手 | 提示词的排序规则是否被改回了软要求「进入领域前先加载」，要按**动作**写（见 5.14(2)） |
| `load_skill` 报「没有这个技能」 | 是不是让主 Agent 去加载了剧组技能；或技能名拼错（返回里带可用清单） |
