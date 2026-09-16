# 开发文档 —— 剧本工坊（Script Workshop）

> 面向继续开发本项目的人。除了架构与开发指引，重点记录**踩过的坑**：
> 每条都写清「症状 → 根因 → 解法 → 涉及文件」，避免重复踩。
>
> 本文档基于真实调试过程整理（2026-09 ~ 2026-09），所有结论都在本机实测验证过。

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
  ├─ crew/dp.py             摄影指导 → 视频提示词（模型感知 + 锚逐字复用）
  │                  只做组装：环境锚 + 出场人物锚 + 本镜动作运镜 + 风格
  │
  ├─ video/providers/*      视频 Provider 适配层（runway/kling/cogvideo/sora/minimax）
  ├─ video/queue.py         异步任务队列（线程池 + 轮询 + 状态回调写回 DB）
  ├─ video/continuity.py    把 reference_group/chain_from 解析成 reference_videos
  └─ video/assemble.py      FFmpeg 拼接成片
```

**分层原则**：视觉锚只产一次（美术指导），下游逐字复用；LLM 提示词与目标模型方言对齐。

---

## 二、开发环境与启动

```bash
# 依赖（Python 3.12+）
pip install -e .

# 启动后端（开发模式）
python -m uvicorn app.main:app --host 127.0.0.1 --port 8000

# 前端
cd frontend && npm install && npm run build   # 构建产物由 FastAPI 托管
```

**关键约定**

- `.env` 是唯一配置入口；改完**必须重启 uvicorn**（`Settings` 是 `lru_cache` 单例，热改不生效）。
- 本机若没有项目自带 Postgres，可用 SQLite 独立跑，不碰别人的容器：
  ```bash
  DATABASE_URL="sqlite:///./data/dev.db" CHECKPOINTER=memory python -m uvicorn app.main:app --port 8000
  ```
- 跑测试：`DATABASE_URL="sqlite:///./data/ci.db" CHECKPOINTER=memory python -m pytest tests/ -q`

---

## 三、核心数据流

| 产物 | 定义位置 | 说明 |
|---|---|---|
| `Script` | `app/domain.py` | 剧本：characters / locations / scenes（含 beats） |
| `SceneBreakdown` + `Shot` | `app/domain.py` | 分镜方案；`Shot` 承载连续性字段与视频状态 |
| `StyleGuide` | `app/domain.py` | 视觉风格指南；**角色造型与环境描述是全局唯一来源** |
| 视频提示词 | `Shot.video_prompt` | DP 组装的最终提示词，直接喂给视频模型 |
| `VideoJob` | `app/store.py` | 视频任务；状态由队列回调写回 DB |

**`Shot` 字段速查**

- 基础：`shot_type / camera / subject / action / duration_sec / lighting / mood`
- 切镜理由：`cut_reason`（写不出理由就该合并）
- 连续性计划：`reference_group`（共享环境参考分组）、`chain_from`（本镜首帧取自哪一镜尾帧）
- 运行时输入：`reference_images / reference_videos / first_frame_image / last_frame_image`
- 生成状态：`video_prompt / video_url / video_job_id`

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

路由按业务域拆在 `app/api/` 下（system / projects / versions / agent_runs / chat / video / plugins）。
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

视频任务与子代理任务的状态若只在内存，进程重启即丢。两者现在都通过落库解决：
视频任务是「状态回调写回 DB」（`app/main.py` 的 `_wire_video_job_writeback`），
子代理任务是「起止两个时刻各落库一次」（`app/agent/skills.py` 的 `SubAgentRunner._persist`
→ `subagent_tasks` 表，`/api/tasks` 合并内存态与历史态）。
注意：**进行中**的任务本身随线程终止，落库只保证已完成任务的历史可查，不假装它还在跑。

> 踩坑：测试里子代理 runner 若不显式绑定测试库，会经由全局 `deps.store()` 去连 `.env`
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

## 六、排查手册（症状 → 先查什么）

| 症状 | 先查 |
|---|---|
| 剧本生成 `mode=local-fallback` | 服务端日志里的 validation error（`app/pipeline/generation.py` 的容错模型是否漏了字段） |
| 提示词里缺少某个锚 | 风格指南是否生成（`projects.video_style_json`）；锚的键是否与地点名/人物名对得上；`normalize_id` 是否又出双前缀 |
| 视频任务失败 | 错误信息里是 `402/insufficient balance`（余额）还是 `400`（内容审核）还是 `Invalid header`（provider key） |
| 任务长时间 `generating` | 直接拿 `external_task_id` 查服务商真实状态，再对照状态映射（子串陷阱） |
| 后台子代理没动静 | 用 `GET /api/tasks` 确认任务是否真的创建（别信回复文本） |
| 分镜切得很碎 | 上游是否把多章塞成了一场戏；导演提示词是否被改回了「覆盖式拍摄」 |
| 参考图质检永远不合格 | 判定标准是否把「水印 / 细节数量」也算 FAIL；角色是否戴面具（东亚面孔那条要写例外） |
| 视觉质检报 `Failed to download image` | 图片 URL 是否失效；改用 base64 data URI |
