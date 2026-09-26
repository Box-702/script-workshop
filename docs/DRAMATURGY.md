# 戏剧结构方法论落地说明

> 方法论来源：[smixs/visual-skills](https://github.com/smixs/visual-skills)（CC BY 4.0 · Serge Shima）
> 原始整理稿：《AIGC 视觉内容提示词方法论》（2026-09-22）

## 核心思想

**先戏剧，后语法**——模型语法在戏剧结构到位之前一文不值。结构对了，模型才有
东西可渲染；结构错了，再正确的镜头语言也救不了这个镜头。普通 prompt 是四个形容
词加零个事实；本链路的 prompt 是「一个情绪 · 三个镜头 · 三个细节 · 一个最终画面」。

## 落地位置

| 方法论概念 | 落地模块 | 说明 |
|---|---|---|
| 三工作规则（改情绪/推进/施压） | `Shot.function` + 导演系统提示词 | 一镜必做一件事，写不出 function 的镜头是壁纸，critique 循环强制重拆 |
| 细节律（三细节） | `dramaturgy.three_details` | 环境压力 / 身体微动作 / 声音锚点·视觉母题；零细节=废镜头，一细节=单薄 |
| 五锚点（One-anchor） | `SceneAnchors` + 导演 JSON 输出 | 每场只承诺：一个情绪、一个母题、一个物体、一次破裂、一个最终画面 |
| 最终画面规则（U11） | `Shot.final_frame` + DP 拼装兜底 | 视频模型把最后一帧当情绪目的地；body 必须以结束帧收尾，漏写自动补 |
| 运镜动机（Fincher 法则） | 导演系统提示词 | camera_path 起笔写「什么变了」，答不出就 static |
| 节奏阶梯 | 导演系统提示词 | 同场时长走「长→渐短→冲击」阶梯，最大冲击前一镜放最慢 |
| 场景公式 | 导演系统提示词 | desire/obstacle/geometry/gaze/rhythm 五问；gaze = 每镜 subject 是唯一焦点 |
| 空洞占位词禁用 | `dramaturgy.find_slop_words` / `strip_slop` | 电影感/epic/masterpiece 等渲染不出来的词：整段占位机械剥除，混写句审计告警 |
| 否定句禁用 | `dramaturgy.find_negations` | 模型会把被否定的动作画出来；引号内的实体招牌文字不误伤 |
| 情绪只写身体（U3） | DP body 规则 11 | 情绪名词翻译成 2-4 个可观察身体线索，多了像演技过火 |
| 写实人物公式（反 AI 脸） | 美术指导系统提示词 | 肤色肤质+3-4 个面部细节+视线神态；气质词渲染不出来 |
| 环境会表演（黑泽明） | 美术指导系统提示词 | 每个地点写一个承载情绪的「环境压力」细节 |
| 出厂前双重审计 | `dramaturgy.audit_breakdowns` / `audit_video_prompt` | 第一道在导演侧回喂 critique；第二道写进 `Shot.prompt_audit` 供人工审阅 |

## 数据流

```
导演拆解 ──→ audit_breakdowns（戏剧结构检查）──→ critique 循环重拆（有界 3 次）
   │
   └─ Shot.function / final_frame、SceneAnchors 随版本落库
                    │
摄影指导 ──→ body 写作规则（十一条）+ 台词/占位词机械兜底 + final_frame 兜底
   │
   └─ audit_video_prompt → Shot.prompt_audit 落库
                    │
人工审阅 ──→ 审阅面板展示逐镜审计提醒（PromptEditor / ShotList 角标）
   │
   └─ PUT /prompts/review 保存时服务端刷新 prompt_audit
```

## 设计约束

- 审计只提醒、不拦截（沿用成片质检的教训：把小瑕疵也算 FAIL 会让告警脱敏）；
- 词库判定是保守的：命中算有，零命中才报「废镜头」；
- 机械剥除（台词引用、整段占位词）只做语法安全的子集，其余交给写作规则在源头避免。
