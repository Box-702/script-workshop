# 技术选型记录 —— 剧本工坊（Script Workshop）

> 本文回答「**为什么用这个，不为什么用那个**」。每条记录一个决策：**背景 → 选项 → 决定 → 理由 → 什么时候该推翻**。
>
> 格式参考 ADR（Architecture Decision Records），但用中文散文写成，方便一个人读完。
> **新决策请追加到文末，不要改写已有条目**——历史决策的"当初为什么"比"现在怎么选"更有价值。
>
> 配套阅读：[`ARCHITECTURE.md`](ARCHITECTURE.md)（怎么分层）· [`DEVELOPMENT.md`](DEVELOPMENT.md)（踩过的坑）

---

## 索引

| # | 决策 | 一句话结论 | 状态 |
|---|---|---|---|
| [D-01](#d-01-模型接入全部走-openai-兼容协议) | 模型接入 | 全部走 OpenAI 兼容协议，不引各家 SDK | 已定 |
| [D-02](#d-02-不用-rag只做原文关键词检索) | 检索 | 不用向量 RAG，原文搜索用关键词 | 已定 |
| [D-03](#d-03-编排用-langgraph-状态图而非多-agent-框架) | 编排 | LangGraph 状态图 + 自研 crew，不引 CrewAI/AutoGen | 已定 |
| [D-04](#d-04-剧组的三个角色是函数不是-agent) | 剧组 | 导演/美术/摄影是单次结构化调用 | 已定 |
| [D-05](#d-05-确定性审计优先于-llm-评判) | 质检 | 能用规则判的绝不用 LLM 判 | 已定 |
| [D-06](#d-06-前端不引-pinia--vue-router) | 前端 | 极简依赖，单页工作台 | 已定 |
| [D-07](#d-07-数据库用-sqlalchemy-13-张表不拆微服务) | 存储 | 单库单表结构 | 已定 |
| [D-08](#d-08-视频统一-minimax-加用户自带-key) | 视频 | 统一 MiniMax，BYOK | 已定 |
| [D-09](#d-09-成片合成用-ffmpeg-命令行不引入-moviepy) | 成片 | FFmpeg 命令行直调 | 已定 |
| [D-10](#d-10-配音用云端-tts-暂不自托管) | 配音 | MiniMax T2A v2 | 待复核 |
| [D-11](#d-11-字幕时间轴双源-配音实测优先否则字数估算) | 字幕 | 双源 + 镜头窗口内估算 | 已定 |
| [D-12](#d-12-不引-agent-框架做技能加载待定) | 技能 | 暂不引 deepagents，倾向自研 | **待决策** |
| [D-13](#d-13-提示词质量回归自建轻量框架) | 评测 | 自建轻量框架（不引 deepeval） | 已定 |

---

<a id="d-01-模型接入全部走-openai-兼容协议"></a>
## D-01 模型接入全部走 OpenAI 兼容协议

**背景**：需要同时支持 DeepSeek、智谱、Moonshot、Qwen，以及本地 Ollama/vLLM，还要让用户自带 key。

**选项**：① 各家官方 SDK；② 一个 OpenAI 兼容门面 + 厂商声明表；③ 抽象层 + 每家一个适配器。

**决定**：选 ②。`app/llm/providers.py` 是唯一的 `ChatOpenAI` 构造点，差异只落在**默认端点、默认模型、额外请求体**三处，用一张 `ProviderSpec` 声明表描述。

**理由**：国内主流厂商都提供 OpenAI 兼容端点，引入各家 SDK 会带来多套依赖、多套重试/超时语义、多套错误类型，收益却只有"多几个原生特性"。声明表让新增厂商的成本降到"加一行"。

**什么时候该推翻**：需要用上某家 SDK 独有的能力时（如 Anthropic Messages API 的 prompt caching、extended thinking）。注意这**不是加一行 ProviderSpec 能解决的**——非 OpenAI 兼容协议要单独写协议客户端。

**相关**：`ARCHITECTURE.md` 2.2 / `DEVELOPMENT.md` 5.3

---

<a id="d-02-不用-rag只做原文关键词检索"></a>
## D-02 不用 RAG，原文检索用关键词搜索

**背景**：改编时需要从长篇原文中找相关段落。

**选项**：① 向量库 + 分块 + 检索；② 纯关键词搜索；③ 混合。

**决定**：选 ②。`app/agent/tools.py` 的 `search_source` 是纯文本搜索，`get_source_text` 按场景取原文片段。

**理由**：原文是**同一本书**——不存在跨文档的语义检索需求，用户问的也是"这段原文里怎么写的"，关键词命中足够。更重要的是：向量库要引入 embedding 服务、chunk 策略、调参、额外的失败面，而本项目的瓶颈根本不在"找得到哪段"，在"生成得对不对"。

**什么时候该推翻**：如果要做"从几十本参考书里找素材"这类跨文档检索，关键词就明显不够了。

**相关**：`app/agent/tools.py` · `app/pipeline/chunking.py`

---

<a id="d-03-编排用-langgraph-状态图而非多-agent-框架"></a>
## D-03 编排用 LangGraph 状态图，不引 CrewAI / AutoGen / Agno

**背景**：需要固定流程 + 中途人工干预 + 状态持久化。

**选项**：① LangGraph 状态图；② CrewAI / AutoGen / Agno 多 Agent 框架；③ 手写循环。

**决定**：选 ①。`app/agent/graph.py` 定义 7 节点固定编排，`interrupt` + `Command(resume=...)` 做审阅闭环，checkpointer 持久化。

**理由**：
- 我们的流程**是固定的**（context → plan → propose → guard → review → apply → finalize），不是"谁该接这个活"由模型决定。状态图把流程画在代码里，可读、可测、可断点。
- CrewAI/AutoGen 的抽象是"角色 + 任务 + 委派"，与我们的固定流水线不匹配，套上去反而更绕。
- 官方的 multi-agent research 系统（Anthropic，2025-06）实测多 Agent 成本是纯对话的 **15 倍 token**，换 90.2% 提升——对本地单机产品不可接受。

**什么时候该推翻**：如果产品形态变成"用户自定义一堆角色自由协作"，那 CrewAI 类的抽象才合适。

**相关**：`ARCHITECTURE.md` 三 · `DEVELOPMENT.md` 5.6

---

<a id="d-04-剧组的三个角色是函数不是-agent"></a>
## D-04 剧组的三个角色是「函数」，不是「Agent」

**背景**：系统里有导演 / 美术指导 / 摄影指导三个角色，各自产出结构化结果并被下游消费。

**选项**：① 每个角色做成一个嵌套 LLM 循环（有自己的工具、自己的上下文）；② 单次结构化调用。

**决定**：选 ②。`app/crew/base.py` 的 `CrewAgent.run()` 走 `self.llm.chat()` **一次**结构化调用，产出 `CrewTaskResult`。

**理由**：
- 三个角色是**流水线上的工位**，输入输出都已定型（剧本 → 分镜 → 提示词），它们不需要自主决策、不需要自己的工具、不需要多轮对话。
- 单次调用让每个角色的产出**可单独重跑、可单独审阅**（导演拆解不过就只重拆导演），这是流水线形态的关键优势。
- 成本与延迟都可预测。

**什么时候该推翻**：如果某个角色需要**回查上游、反复追问、或自己调用工具**，那它就该升级成独立 Agent。

**⚠️ 术语澄清**：这直接关系到业界"多 Agent vs 单 Agent"讨论——Anthropic 说的 subagent 指的是"有自己 context window、自己工具集、自己是嵌套 LLM 循环"的 Agent。**我们的三个 crew 角色不满足这个定义**，所以"把 subagent 折叠进主循环"那套改造对我们**基本不适用**，折叠成本接近零、收益也接近零。真正该借鉴的是其中两条通用原则：**长指令外置成 skill 按需加载**、**tool 按用户意图分组而非一个 API 一个 tool**。

**相关**：`app/crew/base.py` · `ARCHITECTURE.md` 3.2 / 3.4

---

<a id="d-05-确定性审计优先于-llm-评判"></a>
## D-05 确定性审计优先于 LLM 评判

**背景**：剧本与视频提示词需要质量把关。

**选项**：① 全部交给 LLM 打分；② 纯规则；③ 规则在前、LLM 在后。

**决定**：选 ③，且**规则层是主力**。`app/crew/dramaturgy.py` 把方法论里可代码化的部分全部落成纯字符串/字段运算：场景公式五要素、三细节律、五锚点、空洞词表（cinematic/epic/masterpiece 这类渲染不出来的词）、否定句检测（视频模型会把被否定的动作画出来）、台词引用检测。LLM 只在 `app/pipeline/review.py` 的五维评审里出现。

**理由**：规则判定**确定、可复现、零成本、零延迟**；LLM 判定会抖动、会烧钱、会"看情况"。而且规则能写进 `shot.prompt_audit` 让人逐镜核对。

**什么时候该推翻**：需要判断"这段情感是否动人"这类主观维度时，规则无能为力——但那时也只该**补** LLM 判据，不要替换规则层。

**相关**：`app/crew/dramaturgy.py` · `docs/DRAMATURGY.md` · `DEVELOPMENT.md` 5.5

---

<a id="d-06-前端不引-pinia--vue-router"></a>
## D-06 前端不引 Pinia / vue-router

**背景**：Vue 3 + Vite 6 单页工作台，三栏布局。

**选项**：① 引入 Pinia + vue-router；② 纯 `reactive()` 单例 store + 无路由。

**决定**：选 ②。`frontend/src/stores/app.js` 用 Vue `reactive()` 做单例 store，全项目无路由（单页工作台，左栏切换项目、右栏切 tab 都在同一个页面内）。

**理由**：产品形态就是**一个工作台**，没有多页面、多路由参数、面包屑、路由守卫的需求。引框架只增加学习成本和构建体积，换不到任何东西。

**什么时候该推翻**：一旦需要深链接（`/project/xxx/shot/yyy`）、多页面、或独立的分享页，就需要 vue-router。

**相关**：`frontend/src/stores/app.js`

---

<a id="d-07-数据库用-sqlalchemy-13-张表不拆微服务"></a>
## D-07 单库单表结构，不拆微服务

**背景**：需要持久化剧本、版本、镜头、视频任务、后台任务、记忆等。

**选项**：① 单个 PostgreSQL/SQLite 库；② 按域拆库；③ 微服务。

**决定**：选 ①。`app/store.py` 一套 SQLAlchemy 模型（13 张表），Postgres 与 SQLite 双支持（`DATABASE_URL` 切换）。

**理由**：本项目是**单机桌面级工具**（`API_HOST=127.0.0.1`，无鉴权），微服务带来的网络开销、部署复杂度、分布式事务，收益全为零。SQLite 让"克隆下来就能跑"成立——这对开源项目是硬指标。

**什么时候该推翻**：要多用户同时编辑同一项目、或要跨机器部署成服务时，先加鉴权，再考虑拆。

**相关**：`ARCHITECTURE.md` 一 · 技术债表（路由无鉴权）

---

<a id="d-08-视频统一-minimax-加用户自带-key"></a>
## D-08 视频生成统一 MiniMax，用户自带 Key 与模型名

**背景**：视频生成商众多（Kling / Runway / Sora / CogVideoX / MiniMax）。

**选项**：① 平台托管所有 key，按次计费；② 统一一家 + BYOK；③ 全部接入但都暴露给用户。

**决定**：选 ②。产品统一推 MiniMax，用户自带 key 与模型名（存 `api_providers.config_json.model`）。`app/video/providers/` 里 Kling / Runway / Sora / CogVideoX 的适配器**保留但不暴露**。

**理由**：视频生成是**唯一按 token 计费的大头**（MiniMax H3 实测 6s/768P ≈ 19.5 万 token/条）。让用户自带 key，项目方零垫资、零责任。用户想换厂商时，改一行 `config_json.model` 就行，不需要产品侧发版。

**2026-10-28 补充**：MiniMax 也接入了**对话**（`CHAT_PROVIDER=minimax`，模型 `MiniMax-Text-01`），
于是**一把 key 打通对话 / 视频 / 配音**。代价是它的 `/chat/completions` 不支持
`response_format=json_object`（实测 2013），结构化输出要走降级路径（见
[`ARCHITECTURE.md` 2.5](ARCHITECTURE.md)）。这把 key 的价值在于**零配置可用**——
用户已经有 MiniMax key 的话，装完就能跑通全链路。

**什么时候该推翻**：要做"一站式付费出片"的商业化形态时，需要反过来做托管 key + 计费。

**相关**：`app/video/registry.py` · `DEVELOPMENT.md` 5.1

---

<a id="d-09-成片合成用-ffmpeg-命令行不引入-moviepy"></a>
## D-09 成片合成直接调 FFmpeg 命令行，不引 MoviePy

**背景**：拼接多镜、配音混音、ASS 字幕烧录。

**选项**：① FFmpeg 命令行直调；② MoviePy / PyAV 等封装库。

**决定**：选 ①。`app/video/assemble.py`、`app/media/dubbing.py`、`app/media/subtitles.py` 都是 `subprocess` 调 FFmpeg。依赖 `imageio-ffmpeg` 在系统没装 FFmpeg 时兜底提供二进制。

**理由**：
- 本项目的 FFmpeg 用法都是**滤镜图级别**的（`filter_complex` 混音、`subtitles` 滤镜烧录 ASS、concat 拼接）。MoviePy 的抽象在这几个场景里反而绕，因为它自己也是调 FFmpeg，只是多一层字符串拼接。
- 直接命令行 = 参数完全可控，遇到问题能直接查 FFmpeg 文档。
- 少一个重依赖。

**什么时候该推翻**：要做精细的帧级编辑或时间轴图形合成时，MoviePy 的 API 会更省事。

**相关**：`app/video/assemble.py` · `DEVELOPMENT.md` 5.7（未装 ffmpeg 的坑）

---

<a id="d-10-配音用云端-tts-暂不自托管"></a>
## D-10 配音用云端 TTS，暂不自托管

**背景**：视频模型产不出真实语音，台词必须由 TTS 单独合成再混进成片。

**选项**：① MiniMax T2A v2（云端，当前）；② 自托管（CosyVoice / F5-TTS / GPT-SoVITS）。

**决定**：当前用 ①。`app/llm/tts.py` 只有 MiniMax 一个实现。

**理由**：云端 TTS 音质稳定、无需 GPU、延迟低；自托管模型动辄几 GB 权重，对"克隆下来就能跑"的定位是重负。

**⚠️ 待复核的原因**：当前方案**强依赖外部 key**——没有 MiniMax key 就完全无法出片（合成失败会降级成"静片 + 估算字幕"）。

**候选（2026-10-28 调研，均已核实许可证）**：
- `FunAudioLLM/CosyVoice`（Apache-2.0）—— 官方提供 FastAPI server，接入方式与我们自建 provider 抽象完全契合。**注意：PyPI 上的 `cosyvoice` 包是别人 GPL-3.0 的复刻，必须用官方仓库。**
- `SWivid/F5-TTS`（MIT）—— pip 一行装，有 client-server 模式，接入成本最低。
- `RVC-Boss/GPT-SoVITS`（MIT）—— 中文克隆音色最强。
- **排除 `ChatTTS`**：AGPL-3.0，网络传染，提供网络服务会强制整个项目开源。

**什么时候该推翻**：如果要"零外部依赖出片"或面向完全离线的用户，开源本地通道应作为 fallback 接入。

**相关**：`app/llm/tts.py` · `app/media/dubbing.py`

---

<a id="d-11-字幕时间轴双源-配音实测优先否则字数估算"></a>
## D-11 字幕时间轴双源：配音实测优先，否则按字数估算

**背景**：字幕要贴在正确的画面上。

**选项**：① 强制先配音、用 TTS 实测时长；② 纯按字数估算；③ 双源降级。

**决定**：选 ③。配音开启时用 TTS 实测 track（`synthesize_track` 补 `speaker`/`end_ms`）；未配音时按「字数 / 4 秒」估算，且**在所属镜头窗口内**分配、不跨镜。

**理由**：字幕不准是成片最刺眼的缺陷。但强制配音会让"无配音成片"这条路径无法存在——而这恰恰是降级阶梯里需要的一环。

**⚠️ 前提条件**：估算只在镜头窗口内成立，**前提是镜头时长准确**。provider 实际产出与计划时长有偏差（v6 实测：计划 20s、成片 21.2s），所以 `finalize` 必须在下载后**逐镜实测校准**再排时间轴，否则越往后漂移越大。

**什么时候该推翻**：接入 ASR（whisperX / FunASR）做音频转字幕对齐后，可以直接拿词级时间戳，比估算精确得多。

**相关**：`app/media/subtitles.py` · `app/video/finalize.py`

---

<a id="d-12-不引-agent-框架做技能加载待定"></a>
## D-12 不引 Agent 框架做技能加载 —— **待决策**

**背景**：现在所有长 prompt 都硬编码在 Python 常量里（导演规则、美术风格规范、摄影指导方言、三细节律）。改一条规则要改代码，每次调用全量进上下文。

**选项**：① 引 `langchain-ai/deepagents`（MIT，30.7k★）的 `SkillsMiddleware`；② 抄它的设计自研（约 300–500 行）；③ 维持现状。

**选项 ① 的代价**：`deepagents` 硬依赖 **LangChain ≥ 1.4.7**，我们当前锁的是 `langchain>=1.3,<1.4`，需要升级依赖，且迁移期新旧双轨。

**选项 ② 的依据**：Agent Skills 是 **Anthropic 已开源的开放标准**（2025-12-18 发布标准，2026-10-22 捐赠给 Agentic AI Foundation），机制是渐进式披露三级——**metadata → SKILL.md 正文 → 附属文件**。我们走 OpenAI 兼容 function calling，拿不到 Claude 原生的渐进披露，**等价物本来就要自己实现**；既然要实现，按开放标准做比引一个特定框架更稳。

**倾向**：选 ②，顺带把 `app/agent/skills.py` 正名——它现在叫 skills，实际是**后台任务运行器**（`SubAgentRunner`），与 skill 毫无关系，是术语污染。

**为什么这条值得先做**：Anthropic 官方文章《When to fold subagents into your main agent loop》（2026-10-22）把「长指令外置成 skill 按需加载」列为从多 Agent 架构收敛的第一条建议，并说他们靠这个把 Claude Code 的 system prompt 砍了 80%+。我们 prompt 硬编码的问题，正好落在这条建议上。

**前置条件**：**eval 已就绪**（见 [D-13](#d-13-提示词质量回归自建轻量框架)）。官方明确"第一步是建 eval set，10 条 golden examples 就够"，且"折叠后分数更差才保留原结构"——现在这条已经满足，10 条 golden case + 确定性层 + judge 层都在 `evals/` 里。

**改造时的验证方式**（Anthropic 原文的做法）：
1. 先记录当前基线：`python -m evals.run --judge --out baseline.json`
2. 一次只折一个角色（导演 → 美术 → 摄影）
3. 折完跑同样的 eval，**确定性层 critical 必须仍为 0，judge 均值不能掉超过 8 分**
4. 分数更差就把这个角色留回去，再折下一个

**相关**：`app/agent/skills.py` · `app/chat/conductor.py::SYSTEM_PROMPT` · `app/crew/*.py` · `evals/`

---

<a id="d-13-提示词质量回归自建轻量框架"></a>
## D-13 提示词质量回归：自建轻量框架，不引 deepeval —— 已定（2026-10-28）

**背景**：现有 `tests/` 是 pytest 回归，测的是**代码不崩**，不是**提示词质量**。导演/摄影的输出质量只有运行时打分（五维评审）和成片视觉 QA，没有离线回归。改提示词没有编译器，只能靠出片后肉眼发现——太晚了。

**选项**：① `confident-ai/deepeval`（Apache-2.0，pip 原生）；② `promptfoo`（MIT，Node CLI）；③ 自建轻量框架。

**决定**：选 ③。实现在 `evals/`（独立于 `tests/`），分三层：

| 层 | 需要 key | 内容 |
|---|---|---|
| L0 单元 | 否 | 断言库自身、judge 解析器容错、case 完整性 |
| L0.5 离线回归 | 否 | 用**录制的真实产出**（`evals/fixtures/`）跑断言，锁住「不误报」 |
| L1 确定性 | 是 | 真实链路的分镜与提示词，规则判定，critical 必须为 0 |
| L2 judge | 是 | LLM 按五维量表打分，只看趋势 |

**理由（为什么没引 deepeval）**：
- 我们需要的判据**大部分已经是确定性的**——空洞词、否定句、引用台词、零细节、锚未复用，
  这些都能用正则判定，不需要 LLM-as-judge。deepeval 的价值主要在 LLM 判据上，
  而我们只需要它的一小块。
- deepeval 引入自己的 metric 抽象、dataset 格式与报告体系，要把这些映射到
  「导演分镜 / 摄影提示词」这个非常特定的领域模型上，适配成本高于自建。
- 提示词质量判定的**核心难点不是打分，是「判定规则本身对不对」**——这需要能直接读规则、
  能用录制产出做离线回归、能改单个断言并立刻看到影响。自建框架在这些点上更顺手。
- 少一个依赖。deepeval 会带进 torch 等一堆间接依赖。

**怎么借鉴的**：`zenstory-ai/drama-skills/evaluations/`（MIT）那套「rubric + judge prompt +
corpus + 质量门禁」的结构是直接照着来的，包括 judge 提示词里**要求每条扣分必须引用原文**
这条约束（用来压住 judge 的无据扣分与通胀打分）。

**关键设计约束**：
1. **judge 分数不参与红绿判定**——LLM 打分有抖动，10 条样本不够做统计判定。
   CI 只卡确定性的 critical 数。
2. **LLM 输出不确定**，即使把温度钉到 0 也不完全一致。对策：出现 critical 时
   **自动复跑一次**，两次都失败才算稳定缺陷。
3. **必须有离线回归层**。确定性断言最危险的失败模式是**误报**——一条假告警会让每个
   镜头都挂着警告，告警立刻失去意义。用录制的真实产出把「不误报」锁死。
4. **基础设施问题与质量失败分开计数**：余额不足 / 限流 / 鉴权失败归为 `blocked`，
   不算失败，但必须在报告里显式列出。跑不动不能被误读成「跑过了且通过」。

**它立刻回报了什么**（建完当天就跑出三个真问题）：
1. **生产审计器对真实提示词 4/4 全误报「一镜多运镜」**——风格段（全片运镜语法）被当成本镜运镜，
   且运镜动词没有镜头语境（「在地面拉出一道冷光带」里的「拉出」被当成 pull-out）。
   → 已修（`find_camera_moves` + `strip_style_block`），并补了回归测试。
2. **提示词里混进否定句**（「眼睛没有看任何地方」「避免均匀平光」「没有停留」）——
   视频模型会把被否定的内容照画出来。→ 已在美术指导与摄影指导的写作规则里补强，
   实测 critical 从 8 条降到 0 条。
3. **judge 的「克制度」维度只有 44.9 分**（五维里最低）——每镜都整段贴的全片风格段
   与本镜自己的光影/运镜描述打架。这不是 judge 偏差，是**视频模型真的收到了两套矛盾规格**。
   → **已修**（2026-10-28）：风格段改为「只补空、不覆盖」——body 已写光影/运镜就不再贴对应
   风格段，色调永远贴。实测 **克制度 47.0 → 72.9（+25.9）**、一致性 62.6 → 78.1、
   总体 **72.9 → 81.0（+8.1）**，确定性层 critical 归零。
   细节见 [`DEVELOPMENT.md` 5.13(6)](DEVELOPMENT.md)。
4. **角色出场却没带外观锚**——摄影指导的每镜人物列表偶尔漏人，导致画面里露脸的角色
   没有外观锚，跨镜长相漂移。
   → **已修**：`_apply()` 加确定性补漏（body 里点名的人必须有锚；没点名的不许塞进来）。

**这个 eval 的第一次实战结论**：三个真问题里两个已经修好并用数据验证，一个（否定句）
补了「交稿前逐句自查」指令后连续三次跑干净。**改建前先建 eval 是对的**——
否则这三个问题都只能等成片难看了才发现。

**什么时候该推翻**：如果将来要评的不是「本项目的提示词」而是通用 LLM 应用
（比如评问答质量、评 agent 选工具准确率），deepeval / promptfoo 的现成指标体系更划算。

**相关**：`evals/` · [`evals/README.md`](../evals/README.md) · `tests/test_dramaturgy.py`

---

## 附：被明确排除的开源方案（避免反复调研）

> 2026-10-28 调研结论。列出理由是为了**下次不用再查一遍**。

| 项目 | 排除原因 |
|---|---|
| `harry0703/MoneyPrinterTurbo`（136k★） | 素材库拼接路线（关键词→搜素材→配音），不是叙事改编。架构冲突，引入等于推倒重来。**但值得读**：`app/services/task.py` 是完整参考实现 |
| `2noise/ChatTTS`（40k★） | AGPL-3.0 网络传染，提供网络服务会强制整个项目开源 |
| `chatfire-AI/huobao-drama`（16.7k★） | CC BY-NC-SA 4.0，禁止商业使用。**但值得读**：产品流程编排最贴近我们竞品 |
| `microsoft/autogen`（61.6k★） | CC-BY-4.0（非标准开源许可）+ 生态重心已转移 |
| `openai/swarm`（22k★） | 官方标注 "Educational framework"，已被 openai-agents-python 取代 |
| `mastra-ai/mastra`（29k★） | TypeScript 栈，与 Vue3 + Python 后端不匹配；license NOASSERTION |
| `microsoft/semantic-kernel`（28.7k★） | C# 主栈 |
| `RayVentura/ShortGPT`（8k★） | 2025-02 后停更 20 个月，LangChain 0.x 架构 |
| `Tencent-Hunyuan/HunyuanVideo`（12.7k★） | 腾讯社区许可，**地域限制**（不适用欧盟/英国/韩国）+ 商用门槛 |
| `explodinggradients/ragas`（16.2k★） | 面向 RAG 评测，与剧本生成场景不匹配 |
| `Comfy-Org/ComfyUI`（143.7k★） | **不排除**，但注意 GPL-3.0：作为独立进程经 HTTP 调用不构成衍生作品，**绝不可把源码并入本 MIT 仓库** |
| `deepagents`（30.7k★） | 见 D-12，倾向抄设计而非引依赖 |
| `FancyComfy` | **已无法核实**（GitHub API 四次查询全 404、搜索结果 0、owner 不存在），请勿再考虑 |
| `Meituan-AutoML/diffusion-pipe` | 已 404；且实际项目是**分布式训练** pipeline，不是批量推理编排，方向本身不符 |
| `KrillinAI/KrillinAI` | 已迁移为 `krillinai/OpenCreator`，旧路径 404 |

---

## 记录新决策的模板

```markdown
<a id="d-xx-简短标题"></a>
## D-XX 简短标题

**背景**：为什么要做这个选择。
**选项**：① … ② … ③ …
**决定**：选 ②。
**理由**：为什么不是别的。
**什么时候该推翻**：出现什么信号就该重新评估。
**相关**：文件路径 / 文档章节。
```
