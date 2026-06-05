# 架构

## 总体分层

```
┌────────────────────────────────────────────┐
│  Web (Next.js 14, App Router)              │
│  - 页面、组件、YAML 编辑与校验面板         │
│  - rewrites 代理 /api/* → FastAPI          │
└────────────────────────────────────────────┘
                   │  HTTP/JSON
                   ▼
┌────────────────────────────────────────────┐
│  API (FastAPI)                             │
│  - routers: projects / runs / scripts      │
│  - services: 章节切分、pipeline、校验      │
│  - providers: LLM 抽象                     │
│  - schemas: Pydantic v2 模型               │
│  - db: SQLAlchemy + SQLite                 │
└────────────────────────────────────────────┘
                   │
                   ▼
┌────────────────────────────────────────────┐
│  Pipeline (8 stages)                       │
│  1. 章节切分与清洗                         │
│  2. 章节摘要                               │
│  3. 故事圣经                               │
│  4. 人物/地点抽取                          │
│  5. 场景拆分                               │
│  6. 逐场剧本生成                           │
│  7. JSON Schema 校验                       │
│  8. JSON → YAML + 自动修复                 │
└────────────────────────────────────────────┘
```

## LLM Provider 抽象

```python
class LLMProvider(Protocol):
    def generate_structured(
        self,
        prompt: str,
        schema: dict,
        *,
        stage: Stage,
    ) -> dict: ...
```

实现：
- `OpenAIProvider` — 默认，模型可按 stage 覆盖
- `MockProvider` — 离线占位，用于本地无 key 跑通

## 数据流

1. 用户 POST `/api/projects` → 创建 project + chapters
2. 可选：前端从 `/settings` 读取浏览器本地模型设置，生成请求通过 header 携带 `X-LLM-Provider`、`X-OpenAI-API-Key`、`X-OpenAI-Base-URL`、`X-OpenAI-Model`
3. POST `/api/projects/{id}/generate` → 创建 run，丢进后台任务
4. 后台任务用本次请求的临时 key 构造 provider；key 不进入 DB artifacts
5. GET `/api/runs/{id}` → 轮询进度
6. 完成后 GET `/api/projects/{id}/script.yaml`

## 目录约定

- 章节原文：DB `chapters.content`，同一项目内使用 `chapter_001` 这类稳定 id；数据库用 `(project_id, id)` 复合主键避免跨项目冲突。
- 任意阶段产物：DB `generation_runs.artifacts` (JSON)
- 最终 YAML：DB `script_versions.yaml_content`
