# ScriptForge AI 设计文档

中文名：剧本工坊  
项目方向：AI 小说转剧本工具  
参赛题目：题目三：AI 小说转剧本工具  
目标：将 3 个章节以上的小说文本自动转换为结构化 YAML 剧本，并提供可编辑、可校验、可导出的创作工作台。

## 1. 项目定位

ScriptForge AI 是一个面向小说作者、编剧和内容改编团队的 AI 辅助剧本创作工具。

它不是简单地把小说总结成大纲，而是将小说内容拆解为可追溯、可编辑、可校验的结构化剧本。系统会先理解章节内容，抽取人物、地点、冲突、主题和情节，再将小说改编为具有场景、动作、对白、情绪、潜台词和改编说明的 YAML 剧本。

核心价值：

- 降低小说改编成剧本的门槛。
- 让作者快速获得结构化剧本初稿。
- 保留原文章节引用，方便追溯和人工打磨。
- 通过 YAML Schema 保证输出格式稳定、可编辑、可程序化处理。
- 提供剧本预览、结构校验、自动修复和导出能力。

## 2. 题目要求对应关系

| 题目要求 | 产品实现 |
|---|---|
| 支持 3 个章节以上小说文本 | 项目创建页要求至少输入 3 个章节，支持粘贴和上传文本 |
| 自动转换为结构化剧本 | 多阶段 AI pipeline 生成人物表、场景表和对白 |
| YAML 格式 | 后端先生成严格 JSON，再转换为 YAML |
| 可编辑、可进一步打磨 | Monaco YAML 编辑器 + 剧本预览 + 校验面板 |
| 额外定义 YAML Schema | 提供 `docs/yaml-schema.md` 和 `schema/script.schema.json` |
| 说明 Schema 设计原因 | Schema 文档解释每个核心字段的设计目的 |

## 3. 技术栈

### 3.1 前端

- Next.js
- React
- TypeScript
- Tailwind CSS
- shadcn/ui
- Monaco Editor
- React Flow
- ECharts 或 Recharts

前端职责：

- 创建项目和输入小说文本。
- 展示章节解析进度。
- 展示人物表、地点表、主题和冲突。
- 展示场景时间线。
- 编辑 YAML。
- 实时显示 Schema 校验结果。
- 展示剧本预览。
- 导出 YAML / Markdown。

### 3.2 后端

- FastAPI
- Python
- Pydantic v2
- ruamel.yaml
- jsonschema
- SQLite 本地数据库

后端职责：

- 接收小说章节。
- 执行长文本分块和预处理。
- 调用 AI 模型完成分阶段生成。
- 使用 Pydantic 校验结构化结果。
- 将合法 JSON 转换为 YAML。
- 存储生成历史。
- 提供自动修复能力。

### 3.3 AI 模型层

建议设计成可替换 provider：

- OpenAI
- Qwen
- DeepSeek
- Doubao

接口抽象：

```python
class LLMProvider:
    async def generate_structured(self, prompt: str, schema: dict) -> dict:
        pass
```

推荐策略：

- 章节摘要、人物抽取：使用低成本模型。
- 全局故事圣经：使用较强模型。
- 场景拆分：使用较强模型。
- 对白生成：使用较强模型。
- Schema 修复：使用低成本模型。

## 4. 系统总体架构

```text
用户输入 3+ 章节小说
        |
        v
前端项目创建页
        |
        v
FastAPI 后端
        |
        v
章节清洗与分块
        |
        v
章节摘要生成
        |
        v
故事圣经生成
        |
        v
人物、地点、主题、冲突抽取
        |
        v
场景规划
        |
        v
逐场生成剧本
        |
        v
Pydantic 结构校验
        |
        v
JSON 转 YAML
        |
        v
前端编辑、预览、校验、导出
```

## 5. 核心 AI Pipeline

### 5.1 阶段一：章节输入与清洗

输入方式：

- 用户粘贴文本。
- 上传 `.txt` 或 `.md` 文件。
- 使用内置原创示例小说。

处理逻辑：

1. 检测章节标题，例如 `第一章`、`Chapter 1`、`## 第一章`。
2. 如果无法检测章节标题，按文本长度和段落自动切分。
3. 校验章节数量是否大于等于 3。
4. 清理空行、重复空格、异常字符。
5. 保存原始文本和清洗文本。

输出：

```json
{
  "chapters": [
    {
      "id": "chapter_001",
      "title": "第一章 雨夜来客",
      "content": "...",
      "word_count": 3200
    }
  ]
}
```

### 5.2 阶段二：章节摘要

目标：

为每个章节生成结构化摘要，降低后续模型处理长文本的压力。

每章输出：

```json
{
  "chapter_id": "chapter_001",
  "summary": "本章讲述...",
  "major_events": ["..."],
  "characters": ["..."],
  "locations": ["..."],
  "conflicts": ["..."],
  "turning_points": ["..."]
}
```

### 5.3 阶段三：故事圣经 Story Bible

目标：

建立全局一致性，避免后续生成中人物性格、目标和情节逻辑漂移。

输出内容：

- 故事标题
- 一句话梗概 logline
- 类型 genre
- 主题 themes
- 世界观 setting
- 主线冲突 central conflict
- 人物表 characters
- 地点表 locations
- 时间线 timeline

### 5.4 阶段四：人物抽取与角色弧光

目标：

将小说人物转换为剧本创作可用的人物卡。

人物字段：

- id
- name
- role
- goal
- motivation
- personality
- relationship
- arc
- speech_style

设计原因：

剧本创作中，人物不只是名字。人物目标、动机、语言风格和弧光会直接影响场景冲突和对白质量。

### 5.5 阶段五：场景拆分 Scene Planning

目标：

将小说叙事转换为剧本场景。

每个场景必须具备：

- 场景 id
- 来源章节
- 地点
- 时间
- 出场人物
- 戏剧目的
- 冲突
- 进入状态
- 离开状态

输出示例：

```json
{
  "id": "scene_001",
  "chapter_refs": ["chapter_001"],
  "location": "旧城区诊所",
  "time": "雨夜",
  "characters": ["char_linyu", "char_moke"],
  "purpose": "建立主角的职业状态，并引出神秘来客",
  "conflict": "陌生来客要求主角隐瞒伤情来源",
  "entry_state": "林屿准备关门",
  "exit_state": "林屿决定收留来客"
}
```

### 5.6 阶段六：逐场剧本生成

目标：

基于场景规划生成剧本正文。

每场包含：

- 场景标题
- 动作描写
- 对白
- 情绪
- 潜台词
- 改编说明

生成策略：

1. 每次只生成 1 到 3 个场景，降低幻觉和格式错误。
2. 传入 Story Bible，保证全局一致性。
3. 传入对应章节摘要，保证内容可追溯。
4. 生成后立即校验。
5. 校验失败则自动修复。

### 5.7 阶段七：Schema 校验

校验内容：

- 必填字段是否存在。
- 字段类型是否正确。
- 场景引用的人物 id 是否存在。
- 章节引用是否存在。
- scene id 是否唯一。
- dialogue speaker 是否来自 characters。
- YAML 是否可解析。

错误示例：

```json
{
  "path": "script.scenes[2].dialogue[1].speaker",
  "message": "speaker references unknown character id: char_unknown",
  "severity": "error"
}
```

### 5.8 阶段八：自动修复

目标：

当生成结果或用户编辑后的 YAML 不符合 Schema 时，系统能提供自动修复。

修复类型：

- 补全缺失字段。
- 修复错误类型。
- 修正人物 id 引用。
- 修复 YAML 缩进。
- 将自由文本转换为结构化字段。

修复原则：

- 不改变原剧情。
- 不删除用户已有内容。
- 修复前后显示 diff。

## 6. YAML Schema 初稿

```yaml
script:
  title: "雨夜来客"
  version: "1.0"
  language: "zh-CN"
  adaptation:
    type: "series"
    target_format: "short_drama"
    tone: "suspense"
  source:
    chapter_count: 3
    chapter_ids:
      - "chapter_001"
      - "chapter_002"
      - "chapter_003"
  logline: "一名年轻医生在雨夜救下神秘来客，却卷入一场关于身份和记忆的阴谋。"
  themes:
    - "信任"
    - "身份"
    - "自我救赎"
  characters:
    - id: "char_linyu"
      name: "林屿"
      role: "protagonist"
      goal: "查明神秘来客的真实身份"
      motivation: "弥补过去一次误诊造成的遗憾"
      personality: "克制、敏锐、谨慎"
      arc: "从逃避责任到主动面对真相"
      speech_style: "简短、理性、偶尔带有冷幽默"
  locations:
    - id: "loc_clinic"
      name: "旧城区诊所"
      description: "狭窄、潮湿、灯光昏黄的小诊所"
  scenes:
    - id: "scene_001"
      title: "雨夜敲门"
      chapter_refs:
        - "chapter_001"
      location_id: "loc_clinic"
      time: "深夜"
      characters:
        - "char_linyu"
      purpose: "建立主角状态并引出核心事件"
      conflict: "主角想关门休息，但门外有人急需救治"
      action:
        - "雨水敲打卷帘门，诊所内只剩一盏台灯。"
      dialogue:
        - speaker: "char_linyu"
          line: "今天已经停诊了。"
          emotion: "疲惫"
          subtext: "他不想再卷入任何麻烦。"
      adaptation_notes:
        reason: "原文大段心理描写被改为环境和动作，以增强画面感。"
```

## 7. Schema 设计原因

### 7.1 为什么保留 source 和 chapter_refs

剧本改编不是脱离原文重新创作。保留章节引用可以让作者知道每场戏来自哪些章节，方便回查原文和人工修改。

### 7.2 为什么人物使用 id

小说中人物可能有本名、昵称、称谓和代号。使用稳定 id 可以避免同一人物在不同场景中被误认为多个角色。

### 7.3 为什么场景中要有 purpose 和 conflict

一个合格剧本场景必须有戏剧功能。`purpose` 说明这场戏为什么存在，`conflict` 说明这场戏的张力来源，可以帮助作者判断场景是否冗余。

### 7.4 为什么对白有 emotion 和 subtext

剧本不是小说复述。演员和导演需要知道台词背后的情绪和潜台词，这能显著提升剧本可用性。

### 7.5 为什么要有 adaptation_notes

AI 改编可能会压缩、合并或重排情节。改编说明能解释“为什么这样改”，增强作者对结果的信任。

### 7.6 为什么选择 YAML

YAML 对人类可读性更好，适合作家和编剧编辑。同时它仍然可以被程序解析、校验和转换，适合后续导入剧本工具、分镜工具或项目管理系统。

## 8. 页面设计

### 8.1 项目创建页

功能：

- 输入项目名。
- 粘贴小说文本。
- 上传 `.txt` / `.md`。
- 自动识别章节。
- 显示章节数量和字数。
- 选择改编类型。

关键校验：

- 章节数必须大于等于 3。
- 单章文本不能为空。
- 总字数过少时提示用户补充内容。

### 8.2 生成进度页

展示 pipeline 状态：

- 章节解析
- 章节摘要
- 故事圣经
- 人物抽取
- 场景拆分
- 剧本生成
- Schema 校验
- YAML 导出

每一步显示：

- 状态：等待中、生成中、完成、失败
- 耗时
- 简要结果

### 8.3 故事分析页

展示：

- Logline
- 类型和基调
- 主题
- 主线冲突
- 人物卡
- 地点表
- 章节摘要

### 8.4 场景规划页

展示：

- 场景时间线
- 每场戏的地点、人物、冲突
- 场景来源章节
- 进入状态和离开状态

### 8.5 YAML 编辑页

布局：

```text
左侧：Monaco YAML 编辑器
右侧：剧本预览
底部：Schema 校验错误
顶部：导出、自动修复、重新生成
```

核心能力：

- YAML 语法高亮。
- Schema 校验。
- 错误定位。
- 一键修复。
- 保存版本。

### 8.6 导出页

导出格式：

- YAML
- Markdown 剧本预览
- JSON
- Schema 文档

## 9. API 设计

### 9.1 创建项目

```http
POST /api/projects
```

请求：

```json
{
  "title": "雨夜来客",
  "raw_text": "...",
  "adaptation_type": "short_drama"
}
```

响应：

```json
{
  "project_id": "proj_001",
  "chapter_count": 3
}
```

### 9.2 启动生成任务

```http
POST /api/projects/{project_id}/generate
```

响应：

```json
{
  "run_id": "run_001",
  "status": "queued"
}
```

### 9.3 查询生成进度

```http
GET /api/runs/{run_id}
```

响应：

```json
{
  "run_id": "run_001",
  "status": "running",
  "current_step": "scene_planning",
  "progress": 62
}
```

### 9.4 获取 YAML

```http
GET /api/projects/{project_id}/script.yaml
```

### 9.5 校验 YAML

```http
POST /api/validate
```

请求：

```json
{
  "yaml": "script:\n  title: ..."
}
```

响应：

```json
{
  "valid": false,
  "errors": [
    {
      "path": "script.scenes[0].purpose",
      "message": "field required"
    }
  ]
}
```

### 9.6 自动修复 YAML

```http
POST /api/repair
```

请求：

```json
{
  "yaml": "...",
  "errors": []
}
```

响应：

```json
{
  "fixed_yaml": "...",
  "changes": [
    "Added missing field: script.scenes[0].purpose"
  ]
}
```

## 10. 数据库设计

### 10.1 projects

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 项目 id |
| title | string | 项目标题 |
| adaptation_type | string | 改编类型 |
| status | string | 项目状态 |
| created_at | datetime | 创建时间 |
| updated_at | datetime | 更新时间 |

### 10.2 chapters

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 章节 id |
| project_id | string | 项目 id |
| title | string | 章节标题 |
| content | text | 章节正文 |
| summary | text | 章节摘要 |
| order_index | int | 章节顺序 |

### 10.3 generation_runs

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 任务 id |
| project_id | string | 项目 id |
| status | string | queued / running / done / failed |
| current_step | string | 当前步骤 |
| progress | int | 进度 |
| error_message | text | 错误信息 |
| created_at | datetime | 创建时间 |

### 10.4 script_versions

| 字段 | 类型 | 说明 |
|---|---|---|
| id | string | 版本 id |
| project_id | string | 项目 id |
| yaml_content | text | YAML 内容 |
| json_content | text | JSON 内容 |
| validation_status | string | 校验状态 |
| created_at | datetime | 创建时间 |

## 11. 仓库结构建议

```text
scriptforge-ai/
  apps/
    web/
      app/
      components/
      lib/
      styles/
    api/
      app/
        main.py
        routers/
        services/
        schemas/
        providers/
        workers/
  docs/
    yaml-schema.md
    architecture.md
    demo-script.md
  schema/
    script.schema.json
  samples/
    sample-novel.md
    sample-output.yaml
  README.md
  docker-compose.yml
```

如果时间紧，可以简化为：

```text
scriptforge-ai/
  web/
  api/
  docs/
  schema/
  samples/
  README.md
```

## 12. Demo 重点

Demo 视频建议控制在 3 到 5 分钟。

### 12.1 开场

说明：

ScriptForge AI 是一个 AI 小说转剧本工具，可以将 3 个章节以上的小说自动改编为结构化 YAML 剧本。

### 12.2 展示输入

展示：

- 输入三章原创小说。
- 系统自动识别章节。
- 选择改编类型为短剧。

### 12.3 展示生成过程

展示 pipeline：

- 章节摘要完成。
- 故事圣经完成。
- 人物抽取完成。
- 场景拆分完成。
- 剧本生成完成。

### 12.4 展示结果

重点展示：

- 人物表。
- 场景时间线。
- YAML 结构。
- 对白中的 emotion 和 subtext。
- 每场戏的 chapter_refs。

### 12.5 展示校验和修复

故意删除一个字段，例如 `purpose`。

展示：

- 系统提示 Schema 错误。
- 点击自动修复。
- YAML 恢复合法。

### 12.6 展示导出

展示：

- 导出 YAML。
- 导出 Markdown 预览。
- 打开 YAML Schema 文档。

## 13. 三天开发计划

### Day 1：2026-06-05

目标：跑通端到端最小链路。

任务：

- 创建项目仓库。
- 搭建 Next.js 前端。
- 搭建 FastAPI 后端。
- 设计 Pydantic 模型。
- 完成章节切分。
- 完成章节摘要和人物抽取。
- 完成第一版 YAML 生成。
- 写 README 初稿。

验收标准：

- 输入 3 章文本后，可以生成一份 YAML。
- YAML 能通过后端基础校验。

### Day 2：2026-06-06

目标：做成可展示的产品。

任务：

- 完成项目创建页。
- 完成生成进度页。
- 完成人物分析页。
- 完成场景规划页。
- 接入 Monaco Editor。
- 实现 YAML 校验面板。
- 实现自动修复。
- 编写 YAML Schema 文档。

验收标准：

- 用户能从页面完成完整流程。
- YAML 编辑后能实时校验。
- 自动修复能处理常见错误。

### Day 3：2026-06-07

目标：打磨、录屏、整理提交材料。

任务：

- 固定 demo 示例小说。
- 修复关键 bug。
- 优化加载状态和错误提示。
- 完善 README。
- 完善设计文档。
- 准备 demo 视频脚本。
- 录制 demo 视频。
- 确认仓库权限和提交信息。

验收标准：

- 本地一键启动。
- demo 视频完整展示核心能力。
- 仓库文档清晰。
- 作品符合题目要求。

## 14. 风险与应对

### 14.1 长文本超过模型上下文

应对：

- 先做章节摘要。
- 再基于摘要生成故事圣经。
- 逐场生成剧本。

### 14.2 YAML 格式错误

应对：

- 模型先输出 JSON。
- Pydantic 校验。
- 校验成功后由程序转 YAML。
- 用户编辑后再次校验。

### 14.3 人物名称不一致

应对：

- 统一生成 character id。
- 场景和对白只能引用 character id。
- 校验 speaker 是否存在。

### 14.4 生成内容像小说摘要，不像剧本

应对：

- Schema 强制区分 action 和 dialogue。
- prompt 明确禁止大段心理描写。
- 增加 emotion 和 subtext 字段。
- 增加 adaptation_notes 解释改编方式。

### 14.5 Demo 生成太慢

应对：

- 准备缓存好的 demo project。
- 录屏时先展示一次实时生成，再展示缓存结果。
- README 中说明完整生成链路。

## 15. 加分点

### 15.1 结构化生成不是单 prompt

强调系统采用多阶段 pipeline：

- 章节摘要
- 故事圣经
- 人物抽取
- 场景规划
- 剧本生成
- Schema 校验
- 自动修复

### 15.2 可追溯改编

每场戏保留 `chapter_refs`，让作者知道剧本内容来自原文哪里。

### 15.3 可编辑和可校验

Monaco YAML 编辑器配合 Schema 校验，让输出不是一次性文本，而是可继续加工的创作资产。

### 15.4 自动修复

用户编辑破坏结构后，系统可以基于 Schema 自动修复。

### 15.5 Schema 文档完整

题目明确要求写 YAML Schema 文档。这个文档应该作为重点交付物，而不是附属说明。

## 16. 最小可行版本

如果时间不足，必须保证以下功能完成：

- 输入 3 个章节。
- 章节摘要。
- 人物抽取。
- 场景拆分。
- YAML 剧本生成。
- YAML Schema 文档。
- YAML 校验。
- 导出 YAML。

可以暂缓：

- 登录系统。
- 云存储。
- 多用户协作。
- PDF 导出。
- 高级可视化。
- 多模型切换。

## 17. 最终交付物

仓库应包含：

- 源代码。
- README。
- 设计文档。
- YAML Schema 文档。
- 示例小说。
- 示例输出 YAML。
- demo 视频链接。
- 本地运行说明。

README 中建议突出：

- 题目对应关系。
- 核心功能。
- 技术架构。
- AI pipeline。
- Schema 设计。
- 如何运行。
- demo 截图。

## 18. 项目一句话介绍

ScriptForge AI 是一个 AI 小说转剧本工作台，能够将 3 个章节以上的小说文本转换为可编辑、可校验、可追溯的 YAML 剧本初稿，帮助作者快速完成从叙事文本到剧本结构的第一轮改编。

