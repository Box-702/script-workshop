# 架构

## 总体分层

```
┌────────────────────────────────────────────┐
│  Web (Next.js 14, App Router)              │
│  - 页面、组件、Monaco、React Flow          │
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
    async def generate_structured(
        self,
        prompt: str,
        schema: dict,
        *,
        stage: PipelineStage,
    ) -> dict: ...
```

实现：
- `OpenAIProvider` — 默认，模型可按 stage 覆盖
- `MockProvider` — 离线占位，用于本地无 key 跑通

## 数据流

1. 用户 POST `/api/projects` → 创建 project + chapters
2. POST `/api/projects/{id}/generate` → 创建 run，丢进后台任务
3. GET `/api/runs/{id}` → 轮询进度
4. 完成后 GET `/api/projects/{id}/script.yaml`

## 目录约定

- 章节原文：DB `chapters.content`
- 清洗后段落：`storage/chunks/{project_id}/{chapter_id}.txt`
- 任意阶段产物：DB `generation_runs.artifacts` (JSON 字符串)
- 最终 YAML：DB `script_versions.yaml_content`
