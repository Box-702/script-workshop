# 架构

## 总体分层

```
┌────────────────────────────────────────────┐
│  Web (Next.js 14, App Router)              │
│  - 页面、组件、结构化编辑、源码模式与校验面板 │
│  - rewrites 代理 /api/* → FastAPI          │
└────────────────────────────────────────────┘
                   │  HTTP/JSON
                   ▼
┌────────────────────────────────────────────┐
│  API (FastAPI)                             │
│  - routers: projects / scripts / keys      │
│  - services: 版本、导出、模型 key、pipeline │
│  - providers: LLM 抽象                     │
│  - schemas: Pydantic v2 模型               │
│  - db: SQLAlchemy + Alembic + SQLite       │
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
- `OpenAIProvider`：默认实现，兼容 OpenAI 风格接口，模型可按 stage 覆盖。
- 生成需要可用 key。来源优先级为请求头、本地用户 active key、服务端 `OPENAI_API_KEY`。

## 数据流

1. 用户 POST `/api/projects` → 创建 project + chapters
2. 可选：前端从 `/settings` 读取浏览器本地模型设置，生成请求通过 header 携带 `X-LLM-Provider`、`X-OpenAI-API-Key`、`X-OpenAI-Base-URL`、`X-OpenAI-Model`
3. POST `/api/projects/{id}/generate` → 创建 run，丢进后台任务
4. 如果请求头没有 key，后端读取 active 的 `user_model_keys`，解密后构造 provider
5. GET `/api/runs/{id}` → 轮询进度
6. 完成后写入 `script_versions`，项目 `current_version_id` 指向最新版本
7. 编辑页默认读取 `/script.json` 渲染结构化表单；YAML 仅作为高级源码模式和导出格式保留
8. 导出接口提供 YAML、JSON、Markdown，其中 Markdown 面向编剧/改编者阅读稿
9. AI 改编助手读取当前版本和选中场景；有模型 key 时生成结构化 patch，无 key 或模型失败时退回本地建议；用户可接受全部或部分 patch，再保存为新的 `agent_adaptation` 版本

## 目录约定

- 章节原文：DB `chapters.content`，同一项目内使用 `chapter_001` 这类稳定 id；数据库用 `(project_id, id)` 复合主键避免跨项目冲突。
- 任意阶段产物：DB `generation_runs.artifacts` (JSON)
- 最终剧本：DB `script_versions.json_content` 保存规范 JSON，`script_versions.yaml_content` 保存可导出的 YAML
- 可读导出：`services.exports` 将当前或历史版本转换为 JSON/Markdown 文本
- 模型 key：DB `user_model_keys.encrypted_api_key`，只展示 `key_last4`
- 手动保存和历史恢复：通过 `script_versions` 生成新快照
- AI 改编：`agent_runs` 保存用户指令、选中上下文、计划和 patch；接受全部或部分 patch 后写入 `script_versions` 与 `edit_events`
