# 剧本工坊全栈版设计文档

中文名：剧本工坊  
产品方向：AI 剧本 IDE 与智能改编工作台  
当前目标：把现有“小说转结构化 YAML 剧本工具”升级为可免费部署、可登录、可持久化、可追踪版本、可人工编辑、可由 AI Agent 辅助改编的完整全栈项目。

## 1. 新定位

剧本工坊不再只是一次性生成 YAML 的工具，而是一个面向作者、编剧、短剧团队和内容工作室的“剧本 IDE”。

用户可以把小说、故事大纲、已有剧本或分集梗概导入项目，系统先生成结构化剧本初稿，然后让用户像使用 IDE 一样继续创作：

- 保存每一次生成、手动修改、AI 改编和导出记录。
- 管理多个剧本项目、章节原文、角色卡、场景表、分集结构和版本历史。
- 保存用户自己的模型 API key，并在服务端安全调用模型。
- 通过 AI Agent 处理自然语言改编需求，例如“把第 3 场改得更悬疑”“删掉支线角色”“把短剧改成电影第一幕”。
- 支持人工直接编辑 YAML、结构化表单或剧本文本，AI 改编和手动编辑都进入同一套版本系统。

一句话：剧本工坊是一个把“AI 生成初稿”延伸到“持续改编、审稿、版本管理和导出交付”的剧本开发环境。

## 2. 现有基础

当前项目已经具备以下基础：

- 前端：Next.js App Router、TypeScript、Tailwind。
- 后端：FastAPI、Pydantic v2、SQLAlchemy、Alembic、SQLite。
- AI 流程：章节切分、章节摘要、故事圣经、角色抽取、场景规划、逐场生成、Schema 校验、YAML 输出。
- 数据表：`projects`、`chapters`、`generation_runs`、`script_versions`、`user_model_keys`、`edit_events`、`agent_runs`。
- 基础页面：项目看板、项目详情、新建项目、运行进度、YAML 编辑、模型设置。
- 基础接口：创建项目、启动生成、查询 run、获取 YAML、校验 YAML、修复 YAML、版本保存/恢复、编辑记录查询、Agent 改编建议/接受、模型 key 保存/测试/撤销。

这些能力证明核心链路已经通了。全栈版要做的是把它从“本地单用户 MVP”扩展成“云端多用户剧本 IDE”。

## 3. 架构升级原则

### 3.1 不推倒重来

保留现有 FastAPI pipeline、Pydantic schema、YAML 校验和 Next.js 页面资产。新增认证、云数据库、版本模型、Agent 改编服务和 IDE 页面。

### 3.2 数据从本地 SQLite 迁移到云端 Postgres

免费部署时不能依赖本地 SQLite 文件，因为免费云服务的磁盘可能不可持久化，服务也可能休眠。生产数据放到 Supabase Postgres，本地开发仍可继续使用 SQLite。

### 3.3 API key 不能明文保存

用户 API key 分两种模式：

- 推荐模式：登录后保存到后端，后端使用服务端主密钥加密，数据库只保存密文、provider、base_url、model、last4 和更新时间。
- 兜底模式：浏览器 localStorage 保存 key，只在请求头临时传给后端，不进入数据库。适合纯本地或不愿托管 key 的用户。

### 3.4 所有编辑都版本化

AI 生成、AI 改编、手动保存、自动修复、导入和回滚都生成版本或编辑事件。用户永远可以回到旧版本、查看差异、知道哪次修改来自自己，哪次来自 AI。

### 3.5 AI Agent 只改结构化数据

Agent 不直接拼接最终 YAML 文本。它先读取项目上下文，生成改编计划，再输出结构化 patch，后端应用 patch、校验 schema、保存新版本。这样可控、可回滚、可解释。

## 4. 推荐免费部署方案

### 4.1 首选方案

```text
Next.js 前端       -> Vercel Hobby
FastAPI 后端       -> Render Free Web Service
Postgres/Auth/文件 -> Supabase Free
模型调用           -> 用户自带 API key
```

选择原因：

- Vercel 对 Next.js 支持最好，Hobby 计划适合个人项目和小型应用。
- Render 可以免费部署 Python Web Service，适合保留当前 FastAPI 后端。
- Supabase 免费计划提供 Postgres、Auth、Storage，足够支撑早期项目和演示。
- AI 成本由用户自带 API key 承担，平台本身不承担模型费用。

需要接受的限制：

- Render Free Web Service 空闲一段时间会休眠，首次访问可能冷启动。
- Supabase Free 项目有数据库、存储、活跃项目和闲置暂停限制。
- 免费方案不适合作为正式商业生产环境，但足够 demo、内测和个人作品集。

### 4.2 可选替代方案

如果后续希望减少后端运维，可以考虑：

- 前端和轻量 API 都放 Vercel，长任务仍留给外部 worker。
- Cloudflare Pages + Workers + D1，但需要重写较多 Python 后端逻辑。
- Supabase Edge Functions 承担部分轻量任务，但复杂 pipeline 和长模型调用仍建议留在 FastAPI。

### 4.3 部署环境变量

前端：

```text
NEXT_PUBLIC_API_BASE_URL=https://script-workshop-api.onrender.com
NEXT_PUBLIC_SUPABASE_URL=...
NEXT_PUBLIC_SUPABASE_ANON_KEY=...
```

后端：

```text
DATABASE_URL=postgresql+psycopg://...
SUPABASE_URL=...
SUPABASE_SERVICE_ROLE_KEY=...
KEY_ENCRYPTION_KEY=base64-encoded-32-byte-key
OPENAI_API_KEY=
OPENAI_BASE_URL=https://api.openai.com/v1
OPENAI_MODEL=gpt-4o-mini
```

`OPENAI_API_KEY` 可以留空，因为默认使用用户自己的 key。

## 5. 总体系统架构

```text
浏览器
  |
  | Next.js UI
  v
Vercel 前端
  |
  | HTTPS / JSON / SSE
  v
Render FastAPI 后端
  |
  | SQLAlchemy / Alembic
  v
Supabase Postgres
  |
  | Auth / Storage / RLS
  v
用户数据、剧本版本、编辑事件、加密 API key

FastAPI 后端
  |
  | 用户 API key 解密后临时调用
  v
OpenAI 或兼容模型服务
```

关键模块：

- `auth`：登录、会话校验、用户身份映射。
- `projects`：项目、章节、源材料管理。
- `scripts`：剧本结构、YAML/JSON、版本与导出。
- `edits`：手动编辑记录、自动保存、diff。
- `keys`：模型 provider 配置和加密 API key。
- `agent`：AI 改编需求理解、上下文检索、patch 生成、校验和保存。
- `runs`：长任务状态、进度、错误、产物。

## 6. 用户核心流程

### 6.1 首次使用

1. 用户打开站点。
2. 使用邮箱 magic link、GitHub OAuth 或 Supabase Auth 登录。
3. 进入模型设置页。
4. 选择 provider，填写 API key、base URL、模型名。
5. 后端加密保存 key，只展示 provider、模型名和 key 后四位。

### 6.2 创建剧本项目

1. 用户新建项目。
2. 输入项目标题、目标格式、语言、原文或大纲。
3. 后端切分章节，保存 `source_documents` 和 `chapters`。
4. 用户确认章节切分结果。
5. 启动生成。

如果用户导入的是已导出的 YAML/JSON 剧本源码，则走独立“剧本源码导入”入口：后端直接创建项目和 `import` 快照，不启动 AI 生成，也不把源码当作小说原文重新切分。

### 6.3 生成初稿

1. 后端创建 `generation_run`。
2. pipeline 分阶段执行。
3. 前端通过轮询或 SSE 展示进度。
4. 生成完整 `script_versions` 版本。
5. 进入剧本 IDE。

### 6.4 手动编辑

1. 用户在 IDE 内编辑场景、对白、角色、YAML 或剧本文本。
2. 前端本地自动保存草稿。
3. 用户点击保存，后端校验并写入 `edit_events`。
4. 重要保存点生成新的 `script_versions`。

### 6.5 AI Agent 改编

1. 用户选中一段场景、角色或全剧，输入改编需求。
2. Agent 读取当前版本、相关章节、角色卡、场景上下文和历史编辑记录。
3. Agent 生成改编计划。
4. 后端要求模型输出结构化 patch。
5. 系统应用 patch 到当前 JSON 剧本。
6. 执行 Pydantic 和 JSON Schema 校验。
7. 前端展示 diff。
8. 用户选择接受、局部接受、重新生成或放弃。
9. 接受后保存新版本，并记录 agent prompt、计划、patch、模型和耗时。

## 7. 剧本 IDE 页面设计

### 7.1 项目首页

展示：

- 项目标题、状态、更新时间。
- 最新剧本版本。
- 最近生成/改编任务。
- 章节原文入口。
- 剧本 IDE 入口。
- 导出入口。

#### 7.1.1 项目看板

`/dashboard` 列出当前账号下的全部项目，每行展示项目名、状态、章节数、版本数、最新版本备注和操作（详情 / 编辑 / 导出 / 删除）。删除走 `.danger-panel` 内联确认面板，避免浏览器原生 `window.confirm`，并在用户点击"确认删除"时显示 `删除中…` 状态以防误触。

### 7.2 IDE 主界面

推荐布局：

```text
顶部：项目名、保存状态、版本选择、导出、运行校验

左侧：资源树
  - 原文章节
  - 角色
  - 地点
  - 场景
  - 版本历史

中间：编辑区
  - 剧本文本视图
  - 场景结构表单
  - YAML/JSON 高级编辑

右侧：AI 改编助手
  - 当前选择上下文
  - 改编需求输入
  - 改编计划
  - Diff 预览
  - 接受/拒绝/重试

底部：校验问题、引用来源、修改记录
```

### 7.3 编辑视图

至少提供三种视图：

- 剧本文本视图：更像传统剧本，适合写对白和动作。
- 结构化视图：角色、地点、场景、冲突、目的、情绪、潜台词等字段可编辑。
- YAML 高级视图：保留当前能力，方便技术用户直接改结构。

### 7.4 改编助手

用户可以输入：

- “把第 4 场节奏加快，减少解释性对白。”
- “把女主改成更主动，但不要改变结局。”
- “按照短剧前三秒强钩子重写第一场。”
- “把这个版本改成电影大纲。”
- “检查所有角色动机是否前后矛盾。”

助手输出：

- 改编计划。
- 影响范围。
- 修改后的片段。
- 结构化 diff。
- 风险提示，例如“该修改会删除 scene_008 中的角色出场”。

### 7.5 界面风格切换

顶栏右侧 `StyleSwitcher` 提供两套主题：

- `studio`：深色专业工作台，紫蓝强调色（`--accent-500: 91 61 240`），用于长时间编辑。
- `paper`：浅色米黄纸面，暖棕强调色（`--accent-500: 152 71 22`），用于长文审阅与导出前校对。

实现要点：

- 所有颜色都通过 CSS 变量（`--ink-*` / `--accent-*` / `--surface-*` / `--line-rgb`）定义，Tailwind 配置读变量，组件和工具类在切换时自动跟随。
- paper 主题反转 ink 阶：低编号 = 深色文字，高编号 = 浅色底色，避免在浅色主题下"白底白字"。
- 用户选择持久化到 `localStorage`，刷新或重开浏览器保持。
- 半透明边框和浅色覆盖层（`surface-line` / `surface-soft`）随主题切换深浅，保证编辑器内分区在两种风格下都看得见。

## 8. 数据模型设计

### 8.1 users

Supabase Auth 负责用户表，业务库通过 `user_id` 关联。

### 8.2 projects

| 字段 | 类型 | 说明 |
|---|---|---|
| id | uuid/string | 项目 id |
| owner_id | uuid | 用户 id |
| title | text | 项目标题 |
| description | text | 简介 |
| adaptation_type | text | short_drama / film / series / stage |
| language | text | zh-CN / en / ja 等 |
| status | text | draft / generating / ready / archived |
| current_version_id | string | 当前剧本版本 |
| created_at | timestamp | 创建时间 |
| updated_at | timestamp | 更新时间 |

### 8.3 source_documents

保存导入的原始材料。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 文档 id |
| project_id | string | 项目 id |
| type | text | novel / outline / script / notes |
| title | text | 文档标题 |
| content | text | 原文内容 |
| storage_path | text | 大文件路径，可选 |
| metadata | jsonb | 文件名、字数、语言等 |

### 8.4 chapters

继续保留现有表，但增加 `source_document_id`。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | chapter_001 |
| project_id | string | 项目 id |
| source_document_id | string | 原文文档 id |
| title | text | 章节名 |
| content | text | 章节正文 |
| summary | text | AI 摘要 |
| order_index | int | 顺序 |

### 8.5 script_versions

剧本的快照版本。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 版本 id |
| project_id | string | 项目 id |
| parent_version_id | string | 来源版本 |
| version_no | int | 项目内递增版本号 |
| label | text | 用户命名，例如“短剧第一版” |
| yaml_content | text | YAML 快照 |
| json_content | jsonb | 结构化剧本 |
| validation_status | text | valid / invalid |
| validation_errors | jsonb | 校验错误 |
| created_by | text | user / ai / system |
| source_run_id | string | 生成或改编任务 id |
| created_at | timestamp | 创建时间 |

### 8.6 edit_events

记录手动编辑和 AI patch。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 事件 id |
| project_id | string | 项目 id |
| version_id | string | 关联版本 |
| actor_type | text | user / agent / system |
| actor_id | string | 用户或 agent id |
| edit_type | text | manual_save / autosave / ai_patch / repair / rollback |
| target_path | text | JSON path，例如 script.scenes[3].dialogue |
| before_snapshot | jsonb | 修改前片段 |
| after_snapshot | jsonb | 修改后片段 |
| patch | jsonb | JSON Patch 或自定义 patch |
| note | text | 用户备注或 AI 说明 |
| created_at | timestamp | 创建时间 |

### 8.7 user_model_keys

保存用户模型配置。API key 必须加密。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | key id |
| user_id | uuid | 用户 id |
| provider | text | openai / deepseek / qwen / custom_openai |
| base_url | text | 兼容 OpenAI 的 base URL |
| default_model | text | 默认模型 |
| encrypted_api_key | text | 认证密文 payload |
| key_last4 | text | 用于展示 |
| status | text | active / revoked |
| created_at | timestamp | 创建时间 |
| updated_at | timestamp | 更新时间 |

### 8.8 agent_runs

AI Agent 改编任务。

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | run id |
| project_id | string | 项目 id |
| base_version_id | string | 改编基准版本 |
| result_version_id | string | 接受后生成的新版本 |
| user_prompt | text | 用户改编需求 |
| selected_context | jsonb | 用户选中的场景、角色、章节等 |
| plan | jsonb | Agent 改编计划 |
| patch | jsonb | 结构化修改 |
| status | text | queued / running / waiting_review / accepted / rejected / failed |
| model | text | 使用模型 |
| error_message | text | 错误 |
| created_at | timestamp | 创建时间 |
| updated_at | timestamp | 更新时间 |

## 9. API 设计

### 9.1 认证

```http
GET /api/me
```

返回当前用户信息。后端从 Supabase JWT 中解析 `user_id`。

### 9.2 模型 key

```http
POST /api/user/model-keys
GET /api/user/model-keys
DELETE /api/user/model-keys/{key_id}
POST /api/user/model-keys/{key_id}/test
```

写入时后端加密 key；读取时永不返回明文。

### 9.3 项目

```http
POST /api/projects
GET /api/projects
GET /api/projects/{project_id}
PATCH /api/projects/{project_id}
DELETE /api/projects/{project_id}
POST /api/projects/import-script
```

### 9.4 原文与章节

```http
POST /api/projects/{project_id}/sources
GET /api/projects/{project_id}/sources
POST /api/projects/{project_id}/chapters/resplit
PATCH /api/projects/{project_id}/chapters/{chapter_id}
```

### 9.5 生成

```http
POST /api/projects/{project_id}/generate
GET /api/runs/{run_id}
GET /api/runs/{run_id}/events
```

`/events` 可用 SSE 推送进度，免费部署初期也可以继续轮询。

### 9.6 剧本版本

```http
GET /api/projects/{project_id}/versions
GET /api/projects/{project_id}/versions/{version_id}
POST /api/projects/{project_id}/versions
POST /api/projects/{project_id}/versions/{version_id}/restore
GET /api/projects/{project_id}/versions/{version_id}/script.yaml
```

### 9.7 手动编辑

```http
POST /api/projects/{project_id}/edits/autosave
POST /api/projects/{project_id}/edits/save
GET /api/projects/{project_id}/edits
GET /api/projects/{project_id}/diff?from=ver_a&to=ver_b
```

保存策略：

- autosave 只保存草稿，不一定生成正式版本。
- save 生成 `edit_event`。
- 当用户主动保存、AI patch 被接受或导出前保存时，生成 `script_version`。

### 9.8 AI Agent 改编

```http
POST /api/projects/{project_id}/agent/adapt
GET /api/agent-runs/{agent_run_id}
POST /api/agent-runs/{agent_run_id}/accept
POST /api/agent-runs/{agent_run_id}/reject
POST /api/agent-runs/{agent_run_id}/retry
```

请求示例：

```json
{
  "base_version_id": "ver_001",
  "instruction": "把第一场改成更强的短剧开场，前三秒必须有悬念，但不要改变人物关系。",
  "scene_ids": ["scene_001"]
}
```

当前前端提供“当前场景 / 全剧”范围选择。“全剧”会把当前版本内所有 `scene_ids` 显式传给后端，避免空数组被解释成默认场景。改编助手会加载最近建议并恢复待确认项；审阅时展示原始用户需求、改编计划、结构化 patch、可读的动作/对白预览和局部勾选状态。接受局部 patch 时，后端会在编辑记录中保留 `accepted_patch_indexes`，用于追溯本次真正落版的范围。

Agent 返回：

```json
{
  "agent_run_id": "agent_001",
  "status": "waiting_review",
  "plan": [
    "保留诊所雨夜环境",
    "提前暴露神秘来客受伤",
    "减少解释性对白"
  ],
  "patch_preview": {
    "affected_paths": [
      "script.scenes[0].action",
      "script.scenes[0].dialogue"
    ]
  }
}
```

## 10. AI Agent 设计

### 10.1 Agent 分层

```text
用户需求
  |
  v
Intent Parser：识别任务类型、范围、约束
  |
  v
Context Builder：拉取版本、场景、角色、原文、编辑历史
  |
  v
Planner：生成改编计划和风险说明
  |
  v
Patch Generator：输出结构化 patch
  |
  v
Validator：Schema 校验、引用校验、剧情约束校验
  |
  v
Reviewer：生成 diff 和说明，等待用户确认
```

### 10.2 支持的改编类型

- 场景重写：重写某一场动作、对白、冲突和节奏。
- 角色调整：改变角色性格、目标、口吻，并同步影响相关场景。
- 结构改编：从小说改短剧、短剧改电影大纲、电影改分集剧。
- 风格改编：悬疑、喜剧、现实主义、古装、赛博朋克等。
- 长度控制：压缩到 N 场、扩展到 N 集、每集 N 分钟。
- 连贯性检查：查找角色动机冲突、地点前后矛盾、时间线问题。
- 对白打磨：更口语、更克制、更有潜台词、更适合短视频节奏。
- 审稿建议：只给修改建议，不直接改文本。

### 10.3 Patch 格式

内部推荐使用 JSON Patch 或接近 JSON Patch 的格式：

```json
[
  {
    "op": "replace",
    "path": "/script/scenes/0/action/0",
    "value": "雨声砸在卷帘门上。门外的敲击突然停住，一道血水从门缝渗进来。"
  },
  {
    "op": "add",
    "path": "/script/scenes/0/adaptation_notes/agent_reason",
    "value": "提前放出危险信号，增强短剧开场钩子。"
  }
]
```

应用规则：

- patch 只能作用在允许编辑的字段。
- 不能删除角色 id、场景 id、章节引用等关键索引，除非用户明确要求。
- 所有 patch 应用后必须重新校验。
- 校验失败时不覆盖当前版本，只保存失败原因和可重试上下文。

### 10.4 上下文控制

Agent 不应把全项目所有内容都塞进模型。Context Builder 按范围裁剪：

- 用户选中场景：当前场景、前后各一场、相关角色卡、相关原文章节。
- 用户选中角色：角色卡、该角色出现的场景列表、代表性对白。
- 全剧结构改编：故事圣经、场景摘要、角色弧光、分集结构，不传全文。
- 一致性检查：传结构化摘要和索引，必要时分批检查。

## 11. 安全设计

### 11.1 API key 加密

后端保存 API key 时：

1. 生成随机 nonce。
2. 使用 `KEY_ENCRYPTION_KEY` 派生服务端主密钥。
3. 数据库保存带认证标签的密文 payload。
4. 只展示 `key_last4`。
5. 调用模型时短暂解密到内存。
6. 日志、错误、artifacts 禁止记录明文 key。

当前本地实现使用标准库 HMAC 认证加密方案，避免额外依赖；生产增强时建议切换到 AES-GCM 或云 KMS。

### 11.2 权限隔离

所有表都必须带 `owner_id` 或通过 project 关联 owner。后端接口每次校验：

- 当前 JWT 是否有效。
- 用户是否拥有该 project。
- 用户是否有权限读取该 version、edit、run。

如果直接让前端访问 Supabase 表，需要配置 RLS；如果统一走 FastAPI，则 FastAPI 是主权限边界，Supabase service role 只在服务端使用。

### 11.3 内容安全

- 模型输出永远进入校验层，不直接写入当前版本。
- AI patch 接受前先展示 diff。
- 大规模删除、跨项目操作、导出全部数据需要二次确认。
- 用户删除项目默认软删除，保留短期恢复窗口。

## 12. 生成与编辑版本策略

### 12.1 版本类型

- `initial_generation`：第一次 AI 生成。
- `manual_save`：用户手动保存。
- `agent_adaptation`：AI Agent 改编后用户接受。
- `repair`：自动修复后保存。
- `rollback`：从历史版本恢复。
- `import`：用户导入已有 YAML/JSON。

### 12.2 何时生成正式版本

生成正式版本的触发条件：

- pipeline 完成。
- 用户点击保存快照，并可填写快照名。
- 用户接受 AI 改编。
- 用户从快照历史回退到旧快照。
- 用户导入新剧本。

不生成正式版本的情况：

- 每次键盘输入。
- 自动保存草稿。
- Agent 生成了 diff 但用户未接受。

### 12.3 Diff 设计

短期：

- 后端比较两个 JSON 快照，返回 path 级 diff。
- YAML diff 作为文本辅助显示。

中期：

- 场景、角色、对白等结构化 diff。
- 支持局部接受 Agent 修改。

## 13. 前端实现计划

### 13.1 保留现有页面

- `/new`：继续作为创建项目入口。
- `/runs/[id]`：继续展示生成进度。
- `/projects/[id]/edit`：结构化场景/全剧编辑为主，YAML 源码模式作为高级入口保留。
- `/settings`：从 localStorage key 升级为登录后的模型 key 管理。

### 13.2 新增页面

```text
/login
/dashboard
/projects/[id]
/projects/[id]/ide
/projects/[id]/versions
/projects/[id]/sources
/projects/[id]/exports
```

### 13.3 组件拆分

```text
components/
  ide/
    ResourceTree.tsx
    ScriptEditor.tsx
    SceneInspector.tsx
    AgentPanel.tsx
    VersionTimeline.tsx
    ValidationPanel.tsx
    DiffViewer.tsx
  settings/
    ModelKeyForm.tsx
    ModelKeyList.tsx
  projects/
    ProjectCard.tsx
    ProjectStatusBadge.tsx
```

### 13.4 编辑器选型

短期继续 textarea，尽快完成全栈闭环。  
中期引入 Monaco Editor 做 YAML/JSON 编辑。  
结构化剧本编辑可以先用 React 表单和列表，不必一开始做复杂富文本编辑器。

## 14. 后端实现计划

### 14.1 目录调整

```text
apps/api/app/
  auth/
    dependencies.py
    supabase.py
  routers/
    projects.py
    runs.py
    scripts.py
    edits.py
    agent.py
    model_keys.py
    validate.py
  services/
    project_service.py
    version_service.py
    edit_service.py
    key_service.py
    agent_service.py
    context_builder.py
    patch_service.py
  providers/
    base.py
    openai_provider.py
  db.py
  schemas.py
  pipeline.py
```

### 14.2 迁移策略

1. 新增 Supabase/Postgres 支持，保留 SQLite 本地开发。
2. 加入 `owner_id`，旧本地数据可用匿名开发用户迁移。
3. 新增 source、edit、key、agent 表。
4. 将 `script_versions` 扩展为正式版本系统。
5. 把 `projects.current_version_id` 指向当前版本。

### 14.3 长任务策略

免费阶段：

- 继续使用 FastAPI BackgroundTasks。
- run 状态持久化到数据库。
- 服务重启时把长时间 stuck 的 running run 标记为 failed 或 queued。

增强阶段：

- 增加轻量 job queue 表。
- API 进程启动时拉取 queued jobs。
- 后续如需要再拆成独立 worker。

## 15. 导出设计

支持格式：

- YAML：保留结构化资产。
- JSON：给开发者或下游工具。
- Markdown：面向编剧和改编者的可读剧本文本，弱化内部 id，使用中文栏目和角色/地点名。
- Fountain：对接专业剧本工具。
- DOCX/PDF：后续实现，用于交付和打印。

导出记录写入 `export_jobs`：

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 导出 id |
| project_id | string | 项目 id |
| version_id | string | 导出版本 |
| format | text | yaml / json / md / fountain / docx / pdf |
| storage_path | text | 文件路径 |
| status | text | done / failed |
| created_at | timestamp | 创建时间 |

## 16. Roadmap

### 阶段 1：免费部署可用版

目标：用户登录后能创建项目、保存 key、生成剧本、保存版本、再次打开继续编辑。

任务：

- 接入 Supabase Auth。
- 数据库迁移到 Supabase Postgres。
- 后端支持 JWT 校验。
- 新增 user_model_keys 加密保存。
- 项目列表和项目详情页。
- script_versions 支持 current version。
- 结构化剧本编辑保存到后端，YAML 作为高级源码模式保留。
- Vercel + Render + Supabase 部署文档。

验收：

- 新用户能注册登录。
- 保存 API key 后刷新页面仍可使用。
- 生成后的剧本能持久保存。
- 通过结构化编辑或 YAML 源码模式保存后，重新打开仍是新版本。

### 阶段 2：剧本 IDE 版

目标：用户不必只改 YAML，可以以剧本 IDE 的方式编辑。

任务：

- IDE 三栏布局。
- 资源树：章节、角色、地点、场景、版本。
- 场景结构化编辑和全剧摘要编辑。
- 校验面板。
- 版本时间线。
- 基础版本 diff 已完成；后续增强 JSON/YAML 文本辅助 diff 和更细的结构化风险提示。
- 导出 Markdown/YAML/JSON。

验收：

- 用户能通过表单改角色和场景。
- 每次正式保存都有版本记录。
- 能查看两个版本差异。
- 能从旧版本恢复。
- 导出的 Markdown 能作为可读剧本文本交给编剧或改编者。

### 阶段 3：AI Agent 改编版

目标：用户用自然语言提出改编要求，AI 能生成可审查、可接受、可回滚的修改。

任务：

- Agent adapt API。
- Context Builder。
- Patch Generator。
- Patch Validator。
- Diff Review UI。
- Agent run 历史。
- 支持场景重写、对白打磨、角色调整、结构压缩。

验收：

- 用户选中一个场景后输入改编需求。
- AI 给出计划和 diff。
- 用户接受后生成新版本。
- 用户拒绝后当前版本不变。
- Agent 修改失败时能看到错误和重试入口。

### 阶段 4：高级创作协作

目标：接近专业团队可用。

任务：

- 评论和批注。
- 多人协作权限。
- 分支版本。
- 角色弧光图、场景节奏图。
- 自动一致性检查。
- DOCX/PDF/Fountain 导出。
- 模板库：短剧、电影、分集剧、舞台剧。

## 17. 风险与应对

### 17.1 免费部署休眠影响体验

应对：

- 前端显示“服务启动中”状态。
- 首次请求失败时自动重试。
- demo 录屏时提前唤醒后端。

### 17.2 长模型任务中断

应对：

- 每个阶段结束都保存 artifacts。
- run 状态持久化。
- 支持从失败阶段重试。
- 生成过程按章节和场景分块。

### 17.3 API key 安全风险

应对：

- 密文存储。
- 明文不进日志。
- key 测试接口只返回成功/失败。
- 用户可随时撤销。
- 后端调用模型时设置超时和错误清洗。

### 17.4 AI 修改不可控

应对：

- Agent 输出 patch 而不是整份覆盖。
- 用户接受前必须看 diff。
- 关键字段保护。
- Schema 校验和剧情约束校验。
- 失败不覆盖当前版本。

### 17.5 数据量超过免费额度

应对：

- 原文和导出文件压缩或放 Supabase Storage。
- 限制单项目最大字数和版本数量。
- 给用户提供清理历史版本功能。
- 大文件后续支持外部对象存储。

## 18. 近期代码改造顺序

推荐按这个顺序动代码：

1. 已完成：给 `projects` 增加 `owner_id` 和 `current_version_id`。
2. 已完成：扩展 `script_versions`，支持版本列表、版本详情、恢复。
3. 已完成：新增 `user_model_keys` 和加密服务。
4. 已完成：改造 `/settings`，支持云端 key 管理，同时保留本地模式。
5. 已完成：新增项目看板和项目详情页。
6. 已完成：改造 YAML 编辑页，加入保存版本。
7. 接 Supabase Auth，给后端加 `get_current_user`。
8. 把数据库 URL 改为同时支持 Supabase Postgres。
9. 已完成：新增 `edit_events`，记录手动保存和历史恢复。
10. 已完成：新增 Agent API 和 Agent Panel，支持改编重点/约束快捷输入、模型生成结构化 patch、本地 fallback 建议、最近建议恢复、重新生成建议、确认全部或部分建议后保存版本。
11. 已完成：加入 Agent diff review、结构化 patch 预览和局部接受。
12. 已完成：加入基础版本 diff 接口和编辑器快照对比面板，可将历史快照与当前快照按剧本、角色、地点和场景分组比较。
13. 已完成：补充 Vercel、Render、Supabase 免费部署文档、生产环境变量和上线验收清单。

## 19. 最小可上线版本定义

全栈免费版的最低可上线范围：

- 用户登录。
- 用户保存模型 key。
- 用户创建项目。
- 用户生成剧本。
- 用户再次登录后能看到项目和剧本。
- 用户能通过结构化编辑器保存新版本，并可在高级源码模式手动编辑 YAML。
- 用户能查看版本列表和恢复版本。
- 用户能导出 YAML/Markdown/JSON。

AI Agent 改编不必放进第一版上线，但数据库和版本系统必须提前为它留好位置。

## 20. 最终产品愿景

剧本工坊最终应该成为一个懂剧本结构的 AI 创作环境。它既能把小说改成初稿，也能陪用户做后续漫长的改编：删线、改角色、调节奏、补动机、查矛盾、做版本、导出交付。

真正的核心不是“生成一次”，而是让每一次生成和每一次修改都变成可保存、可解释、可比较、可回滚的创作资产。

## 21. 后续实施优先级

### P0：先把剧本 IDE 的当前缺口补齐

目标：不改变部署架构，先让本地 MVP 的编辑体验更完整。

当前状态：
- 已完成基础角色结构化增删改：支持编辑姓名、角色类型、目标、动机、性格、关系、弧光和说话风格。
- 已完成基础地点结构化增删改：支持编辑地点名称和描述。
- 已完成基础场景引用维护：场景可切换地点、调整出场角色；删除角色或地点前会检查是否仍被场景或对白引用。
- 已完成版本保存闭环：角色/地点/场景结构化编辑通过“保存快照”落入 `script_versions`。
- 已完成基础版本 diff：历史快照可与当前快照对比，后端按稳定 id 匹配角色、地点和场景。

后续增强：
- 补充浏览器端验收或 E2E 测试，覆盖角色/地点编辑、保存、刷新和导出。
- 增强 diff 风险提示，例如删除角色出场、替换地点、压缩场景和改动对白 speaker。
- 回滚前增加差异预览，让用户确认将恢复到哪个版本。

验收：

- 用户能在“全剧资料”里直接编辑角色卡和地点卡。
- 用户能新增未引用的角色/地点，并在场景中使用。
- 用户不能误删仍被场景或对白引用的角色/地点。
- 保存快照后刷新页面，角色/地点修改仍存在。

### P1：上线前的数据和权限底座

目标：把单用户本地应用推进到免费云端可用。

- 已完成基础用户隔离依赖：本地开发默认 `local_user`，也可用 `X-Dev-User-Id` 模拟不同用户。
- 已完成项目、版本、导出、编辑记录、Agent run 和模型 key 的 owner/user 过滤。
- 已完成后端 `AUTH_MODE=supabase` 验证入口：通过 Supabase Auth user endpoint 校验 Bearer access token 并提取用户 id。
- 已完成前端 Supabase 客户端、登录状态显示、邮箱 magic link 入口和 API Authorization header 注入。
- 已完成未登录状态的统一提示：生产 Auth 模式下引导用户去设置页登录，不再显示裸 HTTP 401。
- 已完成独立 `/login` 和 `/auth/callback`，magic link 回跳后会建立 session 并回到原访问页面。
- 接入 Supabase Auth，前端保存登录态。
- 使用真实 Supabase 项目做端到端登录验收，并按结果补充部署说明。
- 数据库从本地 SQLite 兼容迁移到 Supabase Postgres；本地开发仍保留 SQLite。
- 已完成 Postgres 驱动依赖、生产环境变量说明和 Render/Vercel/Supabase 部署文档。
- 梳理 CORS、错误清洗和 API key 加密配置，生产环境必须显式设置 `KEY_ENCRYPTION_KEY`。

验收：

- 两个用户登录后看不到彼此项目、版本和模型 key。
- Render + Vercel + Supabase 环境能完成创建项目、生成、保存、导出。
- 没有模型 key 时提示清楚，不产生空白失败页。

### P2：版本 diff 和可解释改编

目标：让用户知道 AI 和自己到底改了什么。

- 已完成基础结构化 diff：按剧本、角色、地点、场景、动作、对白分组展示历史快照与当前快照差异。
- 版本对比入口：任意历史版本可与当前版本比较。
- Agent diff 风险提示：删除角色出场、替换地点、压缩场景、改动对白 speaker 时明确提示。
- 编辑事件聚合：项目详情页展示最近人工保存、回滚、AI 接受的摘要。

验收：

- 用户能看懂两个快照之间的主要差异。
- Agent 建议接受前能看到改动范围和潜在风险。
- 回滚前能预览将回到哪个版本。

### P3：专业创作与交付能力

目标：从 demo 工具走向编剧/短剧团队可用。

- 一致性检查：角色是否突然消失、对白角色是否在场、地点是否定义、场景是否缺目的/冲突。
- 格式模板：短剧、电影、分集剧、舞台剧。
- DOCX/PDF/Fountain 导出。
- 原文对照：场景可跳回来源章节，便于核对忠实度。
- 评论和批注：先做单人批注，再考虑多人协作。
- 角色弧光图和场景节奏图：作为高级可视化能力，不阻塞上线。

验收：

- 导出文件能直接给编剧或改编者阅读。
- 一致性检查能发现至少 5 类常见结构问题。
- 用户能从场景回到原文来源，理解 AI 改编依据。
