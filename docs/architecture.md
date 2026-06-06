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

1. 小说改编入口：用户 POST `/api/projects` → 创建 project + chapters
2. 可选：前端从 `/settings` 读取浏览器本地模型设置，生成请求通过 header 携带 `X-LLM-Provider`、`X-OpenAI-API-Key`、`X-OpenAI-Base-URL`、`X-OpenAI-Model`
3. POST `/api/projects/{id}/generate` → 创建 run，丢进后台任务
4. 如果请求头没有 key，后端读取 active 的 `user_model_keys`，解密后构造 provider
5. GET `/api/runs/{id}` → 轮询进度
6. 完成后写入 `script_versions`，项目 `current_version_id` 指向最新版本
7. 编辑页默认读取 `/script.json` 渲染结构化表单；YAML 仅作为高级源码模式和导出格式保留
8. 导出接口提供 YAML、JSON、Markdown，其中 Markdown 面向编剧/改编者阅读稿
9. AI 改编助手读取当前版本和选中场景；有模型 key 时生成结构化 patch，无 key 或模型失败时退回本地建议；编辑页会加载最近建议并恢复待确认项，审阅时保留原始用户需求并用角色名展示对白变更；用户可重新生成建议，或接受全部/部分 patch，再保存为新的 `agent_adaptation` 版本
10. 版本历史支持基础结构化 diff：`GET /api/projects/{project_id}/diff?from=<version_id>&to=<version_id>` 会按剧本、角色、地点和场景分组返回差异；编辑器可将历史快照与当前快照对比
11. 剧本源码入口：用户 POST `/api/projects/import-script` 导入 YAML/JSON，后端直接创建 project + 占位 chapters + `import` 快照，不启动 AI 生成任务

## 目录约定

- 章节原文：DB `chapters.content`，同一项目内使用 `chapter_001` 这类稳定 id；数据库用 `(project_id, id)` 复合主键避免跨项目冲突。
- 任意阶段产物：DB `generation_runs.artifacts` (JSON)
- 最终剧本：DB `script_versions.json_content` 保存规范 JSON，`script_versions.yaml_content` 保存可导出的 YAML
- 可读导出：`services.exports` 将当前或历史版本转换为 JSON/Markdown 文本
- 模型 key：DB `user_model_keys.encrypted_api_key`，只展示 `key_last4`
- 手动保存和历史恢复：通过 `script_versions` 生成可命名快照；编辑页隐藏技术来源字段，用户从快照历史直接回退到任意旧快照
- 剧本源码导入：`script_versions.source_type = import`，用于恢复从 YAML/JSON 导出的剧本源码；章节表只保存占位来源，不代表小说原文已导入
- AI 改编：`agent_runs` 保存用户指令、选中上下文、计划和 patch；接受全部或部分 patch 后写入 `script_versions` 与 `edit_events`，并记录 `accepted_patch_indexes` 便于追溯局部落版范围
- 版本差异：`services.diff` 使用角色、地点和场景的稳定 id 匹配结构化实体，避免仅因数组顺序变化产生整组误报

## 前端主题

- 颜色全部走 CSS 变量（`apps/web/styles/globals.css`），Tailwind 配置（`apps/web/tailwind.config.mjs`）用 `rgb(var(--x) / <alpha-value>)` 读变量。
- `StyleSwitcher` 组件通过给 `document.documentElement` 设置 `data-ui-style="studio" | "paper"` 触发两套变量定义，支持运行时切换。
- 选择持久化在 `localStorage[script-workshop-ui-style]`，下次打开页面自动还原。
- 自定义半透明工具类（`surface-line` / `surface-soft`）替代硬编码的 `border-white/10` / `bg-white/[0.02]`，避免 paper 主题下半透明白看不见。
- paper 主题下 `ink` 阶反转（低编号 = 深色文字），保证浅色主题下高对比度。

## 多用户隔离 (Supabase RLS)

7 张业务表的隔离分两层：

- **应用层**：每个路由的 `db.query(...)` 都先过 `get_project_or_404(project_id, user_id=current_user.id)`，404 路径由 Python 守护。
- **数据库层**：`supabase/rls.sql` 给每张表 `ENABLE + FORCE ROW LEVEL SECURITY`，28 条 `POLICY` 用 `auth.uid()::text` 匹配 `owner_id`（projects / user_model_keys）或通过 `SECURITY DEFINER` 辅助函数 `project_owner_id()` 间接匹配（chapters / generation_runs / script_versions / agent_runs / edit_events）。

子表的 RLS policy 通过 `project_owner_id(project_id) = auth.uid()::text` 实现，避免在每个 policy 写复杂的 join。删除一个 project 时，子表行靠 `cascade` 自动清理。

service_role 直连 Postgres 时 `BYPASSRLS` 自动生效（Postgres 默认），所以后端 ORM 写库不受 RLS 限制；前端 supabase-js 走 anon JWT，会被 RLS 拦截。

## 微动画系统

`apps/web/styles/globals.css` 的 `@layer components` 集中提供 7 个动效：

| 工具类 | 用途 |
|---|---|
| `.sw-anim-in` | 元素进入 (fade + 微上移) |
| `.sw-anim-in-up` | 元素进入 (fade + 大幅上移) |
| `.sw-anim-scale` | 元素进入 (fade + scale) |
| `.sw-skeleton` | 加载占位 shimmer |
| `.sw-attention` | 主 CTA 的 pulse 描边 |
| `.sw-spinner` | 加载中圆环 |
| `.sw-pop` | 切换态 pop 反馈 |

每个 `.sw-anim-*` 都接受 `--sw-delay` CSS 变量控制延迟，用于列表错位 (stagger)：

```tsx
{items.map((item, i) => (
  <div
    className="project-row sw-anim-in"
    style={{ "--sw-delay": `${Math.min(i, 12) * 40}ms` } as React.CSSProperties}
  >
    {item}
  </div>
))}
```

所有动效用 `cubic-bezier(0.16, 1, 0.3, 1)` (ease-out expo) — 不弹跳、不延迟累积。`prefers-reduced-motion` 用户的体验由浏览器自动降级（CSS 动画会失效但不影响布局）。

## 部署拓扑

```
┌────────────────────┐
│  Vercel            │  Next.js 14 (apps/web)
│  - pnpm install    │  Root Directory: apps/web
│  - pnpm build      │  Env: BACKEND_URL, NEXT_PUBLIC_*
└─────────┬──────────┘
          │ /api/*  (rewrites via next.config.mjs)
          ▼
┌────────────────────┐
│  Render            │  FastAPI (apps/api)
│  - pip install -e  │  Health check: /api/healthz
│  - uvicorn         │  Env: DATABASE_URL, AUTH_MODE=supabase,
└─────────┬──────────┘     SUPABASE_URL, KEY_ENCRYPTION_KEY, ...
          │ psycopg3 / pgbouncer
          ▼
┌────────────────────┐
│  Supabase          │  Postgres 17 (free tier)
│  - Auth (GoTrue)   │  Region: us-west-2 (Oregon)
│  - RLS enabled     │  28 policies via supabase/rls.sql
└────────────────────┘
```

当前生产环境：

- 前端：`https://script-workshop-web.vercel.app`
- 后端：`https://script-workshop-api.onrender.com`
- `/api/*`：由 Vercel rewrite 转发到 Render 后端

`render.yaml` (Render Blueprint) 和 `vercel.json` 已写好；生产环境已在 2026-06-06 通过前端首页、后端 `/api/healthz`、前端代理 `/api/healthz` 和未登录 `/api/projects` 401 验收。
