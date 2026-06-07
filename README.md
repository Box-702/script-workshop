<div align="center">

# 剧本工坊 (Script Workshop)

### AI 驱动的剧本 IDE：从 3 章以上小说生成可编辑、可校验、可回滚的中文剧本初稿。

[English below](#english-summary) · [架构](docs/architecture.md) · [部署](docs/deployment.md) · [Schema](docs/yaml-schema.md) · [变更](CHANGELOG.md)

![status](https://img.shields.io/badge/status-MVP-green)
![frontend](https://img.shields.io/badge/frontend-Next.js%2014-black?logo=next.js)
![backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20Pydantic%20v2-009688?logo=fastapi)
![database](https://img.shields.io/badge/database-Supabase%20Postgres-3ecf8e?logo=supabase)
![auth](https://img.shields.io/badge/auth-Supabase%20RLS-3b82f6)
![deploy](https://img.shields.io/badge/deploy-Vercel%20%2B%20Render-000000)

</div>

---

## 项目简介

剧本工坊把小说原文转换成结构化剧本。用户可以粘贴或上传 3 章以上小说，系统通过 8 阶段 AI 流水线生成剧本初稿，再在结构化编辑器里继续打磨。

它的核心能力包括：逐场编辑、AI 改编建议、命名快照、结构化 diff、一键回滚、YAML / JSON / Markdown 导出，以及基于 Supabase RLS 的多用户隔离。前端和后端分别作为独立子项目维护，支持本地开发和 Vercel + Render + Supabase 部署。

## 在线体验

| 服务 | 地址 |
|---|---|
| 在线应用 | <https://script-workshop-web.vercel.app> |
| 后端 API | <https://script-workshop-api.onrender.com> |
| 健康检查 | <https://script-workshop-web.vercel.app/api/healthz> |

官网适合快速体验在线版本和登录流程。当前登录使用 Supabase 邮箱验证码，免费额度和默认发信服务会有频率限制；如果遇到“验证码邮件发送过于频繁”、收信延迟或验证码邮件不可用，可以先不登录，直接使用官网的“本地模式”。本地模式会把模型 key 保存到当前浏览器，并用浏览器本地身份隔离项目；它不跨设备同步，清空浏览器数据后可能失去原本地身份。

---

## 题目要求对应

| 题目要求 | 实现 |
|---|---|
| 3 章以上小说 | 新建项目页校验章节标记数，支持粘贴 / 上传 .md / .txt / 载入示例 |
| 自动转结构化剧本 | 8 阶段 AI 流水线 |
| YAML 格式 | 后端先生成 JSON 强校验，ruamel.yaml 输出；YAML 源码模式可直编 |
| 可编辑、可打磨 | 结构化场景编辑 + YAML 源码 + 实时校验 + 一键修复 + 命名快照回滚 |
| 自定义 YAML Schema | `schema/script.schema.json` + 字段说明文档 |
| 剧本源码导入 | 独立入口，粘贴 / 上传 YAML / JSON 直接恢复为项目和首个快照 |

---

## 快速启动

依赖：Node.js >= 20，pnpm >= 9，Python >= 3.11。

本地开发默认使用 SQLite 和本地鉴权模式，不需要 Supabase 登录，也不会连接线上数据库。SQLite 文件位于 `apps/api/data/script-workshop.db`；FastAPI 启动时会自动执行 Alembic 迁移。

```bash
# 1. 复制环境变量
cp .env.example .env
# 本地开发不必填写 Supabase 变量。
# 可选：填 OPENAI_API_KEY 作为服务端默认 key；也可以在网页 /settings 里只保存到浏览器本地。

# 2. 安装依赖
make install

# 3. 一键启动前后端
make dev
# 前端  http://localhost:3000
# 后端  http://localhost:8000/docs
```

`make dev-api` 会默认设置：

```text
AUTH_MODE=local
DATABASE_URL=sqlite:///./data/script-workshop.db
CORS_ORIGINS=http://localhost:3000,http://127.0.0.1:3000
```

`make dev-web` 会默认把 Next.js 的 `/api/*` 代理到 `http://127.0.0.1:8000`。

Windows 用户：

```powershell
.\scripts\dev-api.ps1
.\scripts\dev-web.ps1
```

这两个 PowerShell 脚本同样会强制走本地 SQLite 默认值，因此即使根目录 `.env` 里写了生产 Supabase 配置，也不会误连线上数据库。确实要覆盖时，可以在当前 shell 里手动设置 `AUTH_MODE` 或 `DATABASE_URL`。

只想跑某一端时，前后端可以完全独立启动，各自有 CHANGELOG 和部署配置：

```bash
pnpm --dir apps/web dev            # 仅前端
bash apps/api/scripts/dev-api.sh   # 仅后端 (linux/macOS)
.\apps\api\scripts\dev-api.ps1     # 仅后端 (Windows)
```

推荐本地验证路径：

1. 启动后打开 <http://localhost:3000/dashboard>。
2. 顶部应显示“当前为本地模式”。
3. 打开 `/settings`，把模型 key 选择“仅保存本地”。
4. 回到 `/new` 创建项目并生成剧本。

---

## 生成流程

```text
章节切分 -> 章节摘要 -> 故事圣经 -> 人物抽取 -> 场景拆分 -> 逐场成稿 -> Schema 校验 -> 自动修复
```

| 阶段 | 名称 | 说明 |
|---|---|---|
| 1 | SplitChapters | 章节切分与清洗，基于 `##` 标题 / `第一章` 标记 |
| 2 | SummarizeChapter | 章节摘要 |
| 3 | StoryBible | 故事圣经，包含主题、主线和基调 |
| 4 | CharacterExtraction | 人物抽取，包含角色弧光、目标和风格 |
| 5 | ScenePlanning | 场景拆分 |
| 6 | ScriptGeneration | 逐场剧本生成 |
| 7 | Validate | JSON Schema 校验，检查引用一致性 |
| 8 | Repair | JSON -> YAML，并自动修复可修复问题 |

每个阶段独立可观测、可重试，并有 artifact 落库。`/runs/{id}` 页面显示实时进度；失败时返回明确错误信息。

详见 [DESIGN.md §5](./DESIGN.md#5-核心-ai-生成流程) 和 [docs/architecture.md](./docs/architecture.md)。

---

## 编辑、改编与版本

AI 改编助手支持当前场景和全剧两种范围。用户可以插入“改编重点”和“约束”的快捷片段，模型返回结构化 `patch`，前端展示变更预览，用户可勾选部分变更接受，也可以基于同一 prompt 和 base version 重新生成。没有模型 key 时，系统会给出本地建议 fallback；未提交建议会持久化到 `agent_runs`，刷新页面后仍可恢复。

版本系统统一记录 AI 生成、手动保存、自动修复、AI 改编、导入、回滚 6 种来源，全部进入 `script_versions`。用户可以给快照命名，例如“高潮前夜”；结构化 diff 会按角色、地点、场景的稳定 id 匹配，只展示实际变化；历史快照可以一键回滚为当前版本。

导出支持 YAML / JSON / Markdown 三种格式。Markdown 导出会做中文分段、角色名和地点名解析，并过滤空行，便于直接阅读和二次整理。

---

## 工程实现

### 前端体验

- CSS 变量驱动的双主题系统：顶栏 `Studio / Paper` 切换，颜色、文字对比度、阴影、边框随主题实时变化，组件内不写硬编码颜色。
- 主题可扩展：新增高对比或色盲友好主题时，在 `globals.css` 增加一组 `[data-ui-style="..."] { --ink-* }` 即可复用现有组件，无需改组件代码。
- 微动画系统：`fade-in` / `fade-in-up` / `scale-in` / `shimmer` / `pulse-ring` / `pop` / `spinner` 七个动效，通过 `sw-anim-in` 等工具类使用，并支持 stagger。
- 统一组件类：`.btn-primary` / `.card` / `.panel` / `.info-card` / `.danger-panel` / `.surface-line` 等 35+ 语义化自定义类全部由 CSS 变量驱动。

### 多用户隔离

- 应用层过滤：每个相关端点都通过 `get_project_or_404(user_id=...)` 校验项目归属。
- 数据库层 RLS：7 张表、28 条 `POLICY`，通过 `auth.uid()::text` 匹配 `owner_id`。
- 跨账号验收：已用 Supabase Auth 和两个真实账号验证，各自只能看到自己的项目与数据。

### 部署配置

- `render.yaml`：Render Blueprint，用于拉起后端。
- `vercel.json`：前端部署配置。
- `supabase/rls.sql`：28 条 RLS 策略。
- `docs/deployment.md`：环境变量、部署步骤和验收清单。

---

## 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 14 (App Router) · TypeScript · Tailwind 3.4 · CSS 变量主题系统 |
| 后端 | FastAPI · Python 3.11+ · Pydantic v2 · SQLAlchemy · Alembic |
| 数据 | Supabase Postgres (生产) · SQLite (本地开发) |
| 认证 | Supabase Auth + 数据库层 RLS |
| AI | OpenAI 兼容 Provider，支持 Azure / DeepSeek / 通义千问等 |
| 部署 | Vercel (前端) · Render (后端) · Supabase (DB + Auth) |

---

## 仓库结构

### 子项目管理

| 子项目 | 依赖管理 | CHANGELOG | 启动脚本 | 部署配置 |
|---|---|---|---|---|
| `apps/web` (Next.js) | `apps/web/package.json` | `apps/web/CHANGELOG.md` | `pnpm dev` | `vercel.json` |
| `apps/api` (FastAPI) | `apps/api/pyproject.toml` | `apps/api/CHANGELOG.md` | `apps/api/scripts/dev-api.{sh,ps1}` | `render.yaml` |
| 顶层 (`script-workshop`) | pnpm workspace + Makefile | `CHANGELOG.md` (跨端) | 根 `scripts/dev-*.ps1` | `docker-compose.yml` |

### 目录说明

| 路径 | 内容 |
|---|---|
| `apps/web/` | Next.js 前端，独立子项目 |
| `apps/web/app/` | 页面：home / dashboard / editor / settings / runs / new / login |
| `apps/web/components/` | AuthStatus · ExportMenu · StyleSwitcher · AuthRequiredMessage |
| `apps/web/lib/` | API 客户端 · LLM 设置 · 类型 |
| `apps/web/styles/globals.css` | CSS 变量 + 7 套动效 + 35+ 语义化组件类 |
| `apps/web/tailwind.config.mjs` | Tailwind 读取 CSS 变量 |
| `apps/api/` | FastAPI 后端，独立子项目 |
| `apps/api/app/` | routers / services / providers / schemas / db |
| `apps/api/tests/` | 后端测试 |
| `apps/api/alembic/` | 5 个迁移 |
| `apps/api/scripts/` | dev-api.sh / dev-api.ps1 / seed_user.py |
| `supabase/rls.sql` | 28 条 RLS 策略 |
| `supabase/migrate_local_user.sql` | legacy data 迁移脚本 |
| `docs/` | architecture / deployment / yaml-schema |
| `schema/` | JSON Schema：`script.schema.json` |
| `samples/` | 示例小说 + 示例输出 |
| `DESIGN.md` | 总体设计，20+ 章节 |
| `CHANGELOG.md` | 跨端变更 |
| `Makefile` | 根任务入口 |
| `docker-compose.yml` | 本地服务编排 |
| `render.yaml` | Render Blueprint |
| `vercel.json` | Vercel 配置 |

---

## 模型 Key 管理 (BYOK)

生成请求必须满足以下至少一个条件：

1. 请求头 `X-OpenAI-API-Key` 临时传入
2. 后端存在 active 的 `user_model_keys`，后端解密后调用
3. 服务端配置了 `OPENAI_API_KEY` 环境变量

`/settings` 页面提供三类操作：

- 保存到云端：后端用 `KEY_ENCRYPTION_KEY` 加密，数据库只存密文、尾号和状态。
- 仅保存本地：浏览器 `localStorage`，不入库。
- 测试 / 撤销：已保存的 key 可测试、可撤销。

后端永不返回明文 key。

---

## 部署

当前生产环境已经部署在 Vercel + Render + Supabase Free 计划上，适合演示和内测。

```text
Frontend: https://script-workshop-web.vercel.app
Backend:  https://script-workshop-api.onrender.com
Health:   https://script-workshop-web.vercel.app/api/healthz
```

重新部署时：

```bash
# 后端：Render 控制台 New -> Blueprint -> 选仓库 -> 填环境变量
# 前端：Vercel 控制台 Add New -> Project -> Root Directory 选 apps/web
```

详细步骤、环境变量和 8 步验收清单见 [docs/deployment.md](./docs/deployment.md)。

---

## 文档索引

| 文档 | 内容 |
|---|---|
| [DESIGN.md](./DESIGN.md) | 总体设计，20+ 章节，覆盖产品定位到风险应对 |
| [docs/architecture.md](./docs/architecture.md) | 系统分层、数据流、Provider 抽象、版本 / Agent / 主题架构 |
| [docs/yaml-schema.md](./docs/yaml-schema.md) | YAML Schema 字段逐项说明 |
| [docs/deployment.md](./docs/deployment.md) | Vercel + Render + Supabase 部署指南 + 验收 |
| [CHANGELOG.md](./CHANGELOG.md) | 跨端变更 |
| [apps/web/CHANGELOG.md](./apps/web/CHANGELOG.md) | 前端变更 |
| [apps/api/CHANGELOG.md](./apps/api/CHANGELOG.md) | 后端变更 |

---

## 状态 (2026-06-06)

已落地，端到端可用：

- 端到端 AI 生成链路，包含 8 个阶段。
- 项目看板、项目详情、结构化编辑器、YAML 源码、命名快照、回退。
- 编辑事件持久化和最近修改记录。
- AI 改编助手：场景 / 全剧范围、模型 patch、本地 fallback、部分接受、重新生成、刷新后恢复。
- 模型 key：后端加密、浏览器 localStorage、测试、撤销。
- 最新 / 历史版本 YAML、Markdown、JSON 导出，统一导出菜单。
- 剧本源码导入，支持 YAML / JSON 直接恢复。
- 结构化角色 / 地点增删改、场景引用维护、快照 diff。
- 顶栏 StyleSwitcher：studio / paper，CSS 变量驱动，7 套动效系统。
- 项目看板内联删除面板：`.danger-panel`，替代 `window.confirm`。
- Supabase RLS 多用户隔离：应用层校验 + 数据库层 28 条策略。
- Render / Vercel 生产部署：前端、后端和 `/api/*` 代理均已验收通过。
- 跨账号隔离验收：Supabase Auth + 真实账号 + RLS。

下一阶段：

- 补充公开演示录屏和生产截图。
- Monaco 编辑器替代 textarea。
- AI 改编 patch 风险提示，例如删除出场、修改时间线。
- paper 主题实测回归。

---

## English Summary

Script Workshop is an AI-driven screenplay IDE: a full-stack monorepo (Next.js 14 + FastAPI + Supabase Postgres) that turns 3+-chapter novels into editable, validated, version-controlled screenplay drafts via an 8-stage AI pipeline. Features include structured scene editing, an AI adaptation agent with partial accept and retry, named snapshots with diff and rollback, Markdown / YAML / JSON export, multi-tenant isolation via Supabase RLS, and a CSS-variable-driven dual theme system (Studio dark / Paper light) with a micro-animation layer. The current production deployment runs on Vercel + Render + Supabase Free.
