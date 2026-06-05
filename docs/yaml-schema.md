# Script Workshop YAML Schema

> JSON Schema 源文件：[`schema/script.schema.json`](../schema/script.schema.json)

本文档逐字段解释 Schema 设计原因。

## 顶层结构

```yaml
script:
  title: ...
  version: 1.0
  language: zh-CN
  adaptation: {...}     # 可选
  source: {...}
  logline: ...
  themes: [...]
  characters: [...]
  locations: [...]
  scenes: [...]
```

## 字段设计原因

### `script.title` & `version`
- `title`：剧本对外显示的标题，与项目名可不同。
- `version`：语义化版本号，给作者区分草稿。

### `script.language`
BCP-47 编码（如 `zh-CN` / `en-US`），影响后续台词语言校验与导出格式。

### `script.adaptation`（可选）
编剧常问"这是给短剧/电影/舞台 用的"，把这一信息写在剧本里，避免作者每次重新交代。

| 子字段 | 说明 |
|---|---|
| `type` | 改编目标载体：`series` / `film` / `short_drama` / `stage` / `other` |
| `target_format` | 自由描述，如 "横屏 3 分钟短剧" |
| `tone` | 基调，如 "suspense" / "warm" |

### `script.source` —— 追溯回原文
**为什么必须保留来源**：AI 改编不应当成"再创作"对待。保留 `chapter_ids` 让作者能跳回原文核对。

| 字段 | 类型 | 约束 |
|---|---|---|
| `chapter_count` | int | ≥ 3（题目硬性要求） |
| `chapter_ids` | string[] | 形如 `chapter_001`，至少 3 个 |

### `script.logline`
一句话故事内核（"25 个字内讲清故事"）。强约束 `minLength: 10` 防止 AI 偷懒输出空字符串。

### `script.themes`
主题词数组（如 `["信任", "身份"]`）。无数量下限，但每项非空。

### `characters[]` —— 人物卡

| 字段 | 必填 | 作用 |
|---|---|---|
| `id` | ✅ | 形如 `char_linyu`，剧本中所有引用都用 id 而非中文名 |
| `name` | ✅ | 显示用名 |
| `role` | ❌ | `protagonist` / `antagonist` / `supporting` / `mentor` / `foil` / `other` |
| `goal` | ❌ | 人物目标 |
| `motivation` | ❌ | 行为动机 |
| `personality` | ❌ | 性格特征 |
| `relationship` | ❌ | 与其他人物的关系 |
| `arc` | ❌ | 人物弧光 |
| `speech_style` | ❌ | 台词风格（决定对白生成约束） |

**为什么用 id 而不是中文名**：小说里同一人物可能有"林屿 / 林医生 / 林老师"等多个称呼。用稳定 id 避免校验时把同一个人当三个人。

### `locations[]` —— 地点卡
| 字段 | 必填 |
|---|---|
| `id` | ✅（形如 `loc_clinic`） |
| `name` | ✅ |
| `description` | ❌ |

### `scenes[]` —— 场景（核心）

| 字段 | 必填 | 说明 |
|---|---|---|
| `id` | ✅ | `scene_001` |
| `title` | ✅ | 场景短标题，如"雨夜敲门" |
| `chapter_refs` | ✅ | 来源章节，至少 1 个 |
| `location_id` | ✅ | 引用 `locations[].id` |
| `time` | ❌ | 时间标签 |
| `characters` | ✅ | 出场人物 id 列表 |
| `purpose` | ✅ | **戏剧目的** —— 这场戏为什么存在 |
| `conflict` | ✅ | **戏剧冲突** —— 张力来源 |
| `entry_state` | ❌ | 人物进入时的状态 |
| `exit_state` | ❌ | 离开时的状态 |
| `action` | ❌ | 动作描写（短句数组，非大段散文） |
| `dialogue` | ❌ | 对白 |
| `adaptation_notes` | ❌ | 改编说明 |

**为什么 `purpose` 和 `conflict` 必填**：
- 场景没戏剧功能 = 冗余场景。
- 写明目的和冲突，作者和编辑能快速判断"这场戏是否必要"。

**为什么 `action` 是数组而不是字符串**：
- 剧本中动作描述按镜头/节拍拆分，方便后期改写。
- 强制短句，避免模型直接复述大段心理描写。

### `dialogue[]` —— 对白

| 字段 | 必填 | 说明 |
|---|---|---|
| `speaker` | ✅ | 引用 `characters[].id` |
| `line` | ✅ | 台词正文 |
| `emotion` | ❌ | 情绪（"疲惫"/"警觉"） |
| `subtext` | ❌ | 潜台词 —— 演员/导演看的 |

**为什么有 `emotion` 和 `subtext`**：
- 剧本不是小说。演员要的不只是台词文本，还包括情绪走向和没说出口的话。
- 这两个字段让 AI 输出接近"可用剧本"而非"对话摘要"。

### `adaptation_notes` —— 改编说明
| 字段 | 说明 |
|---|---|
| `reason` | 为什么这样改（合并/压缩/重排） |
| `fidelity` | 忠实度：`faithful` / `compressed` / `reordered` / `merged` / `invented` |

**为什么需要**：AI 改编是"加工"而非"重写"，让作者理解改动意图，减少"AI 改了什么"的不信任感。

## 校验规则（jsonschema 之外）

后端除跑 JSON Schema 外，还会做：
- `scene.location_id` 必须命中 `locations[].id`
- `scene.characters[]` 每个 id 必须命中 `characters[].id`
- `dialogue.speaker` 必须命中 `characters[].id`
- `scenes[].id` 全剧唯一
- `characters[].id` 全剧唯一
- `locations[].id` 全剧唯一
- `source.chapter_ids[]` 全剧唯一
- `chapter_refs[]` 必须命中 `source.chapter_ids`

校验失败时返回结构化错误（带 `path` + `message`），供前端编辑器和校验面板展示。

## 演进原则

- **不删除已有字段**，只加 `additionalProperties: false` 的"白名单"字段，避免下游解析器中断。
- **新增字段默认可选**，并附 `description`。
- **修改必填集合**视为 breaking change，必须升 major 版本号。
