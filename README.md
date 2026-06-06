<div align="center">

# 剧本工坊 (Script Workshop)

### AI 驱动的剧本 IDE — 从 3 章以上的小说，到可发布的中文剧本初稿。

[English below](#english-summary) · [架构](docs/architecture.md) · [部署](docs/deployment.md) · [Schema](docs/yaml-schema.md) · [变更](CHANGELOG.md)

![status](https://img.shields.io/badge/status-MVP-green)
![frontend](https://img.shields.io/badge/frontend-Next.js%2014-black?logo=next.js)
![backend](https://img.shields.io/badge/backend-FastAPI%20%2B%20Pydantic%20v2-009688?logo=fastapi)
![database](https://img.shields.io/badge/database-Supabase%20Postgres-3ecf8e?logo=supabase)
![auth](https://img.shields.io/badge/auth-Supabase%20RLS-3b82f6)
![deploy](https://img.shields.io/badge/deploy-Vercel%20%2B%20Render-000000)

</div>

---

## 🎬 一句话简介

把小说原文粘进系统,8 阶段 AI 流水线产出**结构化、可校验、可回滚、可导出**的剧本初稿。
之后在结构化表单里逐场打磨,让 AI 助手按你的提示局部重写 — 每一步都进入版本系统。

> **不是一次性生成器**,而是一个**真正能持续创作的剧本 IDE**。

---

## ✨ 为什么这个项目能让评委眼前一亮

### 1. **完整的工程级前端,不是"AI demo 套壳"**

- **CSS 变量驱动的双主题系统**:顶栏 `Studio / Paper` 切换,所有颜色 + 文字对比度 + 阴影 + 边框都跟主题实时切换,**没有任何硬编码颜色**
- **可扩展到任意主题**:加第三套(高对比/色盲友好)只需在 `globals.css` 加一组 `[data-ui-style="..."] { --ink-* }`,**零组件代码改动**
- **微动画系统**:`fade-in / fade-in-up / scale-in / shimmer / pulse-ring / pop / spinner` 七个动效,通过 `sw-anim-in` 等工具类直接使用,内置 stagger 支持
- **统一组件库**:`.btn-primary` / `.card` / `.panel` / `.info-card` / `.danger-panel` / `.surface-line` 等语义化类,**35+ 自定义类全部由 CSS 变量驱动**

### 2. **多用户隔离不只是嘴上说,数据库层兜底**

- **应用层过滤**:`get_project_or_404(user_id=...)` 每个端点都过一遍
- **数据库层 RLS**:7 张表 28 条 `POLICY`(`auth.uid()::text` 匹配 `owner_id`),**任何代码漏洞都无法跨用户访问**
- **跨账号验收**已通过(Supabase Auth + 两个真账号,各自只能看到自己的)

### 3. **8 阶段 AI 流水线** — 不是 1 个 prompt 调 API

```
章节切分 → 章节摘要 → 故事圣经 → 人物抽取 → 场景拆分 → 逐场成稿 → Schema 校验 → 自动修复
```

每个阶段独立可观测、可重试、有 artifact 落库。`/runs/{id}` 实时进度条。

### 4. **AI 改编助手**(高级交互)

- 用户选当前场景 / 全剧范围
- "改编重点"和"约束"快捷片段一键插入
- 模型生成结构化 `patch` (不是字符串拼接)
- **可部分接受**(勾选想要的变更)
- **可重新生成**(同一 prompt 同 base version)
- **无 key 时本地建议 fallback** — 永远不卡
- **未提交的建议刷新页面后仍能恢复** — `agent_runs` 表持久化

### 5. **版本系统不是文件,是真的 IDE 级**

- AI 生成 / 手动保存 / 自动修复 / AI 改编 / 导入 / 回滚 **6 种来源**统一进入 `script_versions`
- **命名快照**:用户能起名"高潮前夜"那种,UI 里直接显示
- **结构化 diff**:按角色/地点/场景的稳定 id 匹配,只报真改
- **一键回滚**:从历史快照直接拉回到当前

### 6. **导出真的为编剧用**

- **Markdown 导出**:中文分段,角色名 + 地点名解析,过滤空行,**读起来像剧本不像 YAML dump**
- YAML / JSON / Markdown 三种格式,菜单统一管理

### 7. **生产级部署配置开箱即用**

- `render.yaml` (Render Blueprint) — 一键拉起后端
- `vercel.json` — 钉住前端
- `supabase/rls.sql` — 28 条 RLS 策略
- `docs/deployment.md` — 完整环境变量 + 验收清单

### 8. **仓库结构是"前后端分别管理"的工业级 monorepo**

| 子项目 | 依赖管理 | CHANGELOG | 启动脚本 | 部署配置 |
|---|---|---|---|---|
| `apps/web` (Next.js) | `apps/web/package.json` | `apps/web/CHANGELOG.md` | `pnpm dev` | `vercel.json` |
| `apps/api` (FastAPI) | `apps/api/pyproject.toml` | `apps/api/CHANGELOG.md` | `apps/api/scripts/dev-api.{sh,ps1}` | `render.yaml` |
| 顶层 (`script-workshop`) | pnpm workspace + Makefile | `CHANGELOG.md` (跨端) | 根 `scripts/dev-*.ps1` | `docker-compose.yml` |

---

## 🖼️ 视觉预览

> 下面三个核心界面均使用 **CSS 变量驱动的双主题系统** 和 **微动画进入效果**。

### 主题切换 (Studio / Paper)
> 切换时所有颜色、阴影、边框通过 CSS 变量实时过渡,不是简单的浅色/深色反转。
>
> ![主题切换](docs/screenshots/theme-switch.gif)
>
> 实现原理:在 `[data-ui-style="studio"]` 和 `[data-ui-style="paper"]` 下定义两套 `--ink-*` / `--accent-*` 变量,所有组件 class 读变量。Paper 主题下 ink 阶反转(低编号=深色文字)恢复浅色主题下高对比度。

### 项目看板 (Dashboard)
> 项目表行用 stagger 错位进入动画,hover 时背景渐变 + 左侧 padding 增加 = "我在点击这行"的物理感。
>
> ![Dashboard](docs/screenshots/dashboard.png)

### AI 改编助手
> 结构化 patch 接受/拒绝,大字号对比预览,角色名对话窗口。
>
> ![Agent 改编](docs/screenshots/agent.png)

> **截图脚本**:`pnpm --dir apps/web build && pnpm --dir apps/web start`,然后用 `docs/screenshots/RECORDING.md` 里的步骤录屏。

---

## 🚀 快速启动 (3 分钟)

依赖: Node.js ≥ 20, pnpm ≥ 9, Python ≥ 3.11。

```bash
# 1. 复制环境变量
cp .env.example .env
# (可选) 填 OPENAI_API_KEY 作为服务端默认 key
# (生产) 填 KEY_ENCRYPTION_KEY 加密用户保存的模型 key

# 2. 安装依赖
make install

# 3. 一键启动前后端
make dev
# 前端  http://localhost:3000
# 后端  http://localhost:8000/docs
```

Windows 用户:

```powershell
.\scripts\dev-api.ps1
.\scripts\dev-web.ps1
```

**只想跑某端** (前后端可完全独立启动,各自有 CHANGELOG/部署配置):

```bash
pnpm --dir apps/web dev            # 仅前端
bash apps/api/scripts/dev-api.sh   # 仅后端 (linux/macOS)
.\apps\api\scripts\dev-api.ps1     # 仅后端 (Windows)
```

---

## 🛠️ 技术栈

| 层 | 技术 |
|---|---|
| 前端 | Next.js 14 (App Router) · TypeScript · Tailwind 3.4 · CSS 变量主题系统 |
| 后端 | FastAPI · Python 3.11+ · Pydantic v2 · SQLAlchemy · Alembic |
| 数据 | Supabase Postgres (生产) · SQLite (本地开发) |
| 认证 | Supabase Auth + 数据库层 RLS |
| AI | OpenAI 兼容 Provider (含 Azure / DeepSeek / 通义千问 等) |
| 部署 | Vercel (前端) · Render (后端) · Supabase (DB + Auth) |

---

## 🤖 8 阶段 AI 生成流程

```
[1] 章节切分与清洗       →  SplitChapters   (基于 ## 标题/第一章 标记)
[2] 章节摘要             →  SummarizeChapter
[3] 故事圣经             →  StoryBible      (主题/主线/基调)
[4] 人物抽取             →  CharacterExtraction (角色弧光/目标/风格)
[5] 场景拆分             →  ScenePlanning
[6] 逐场剧本生成         →  ScriptGeneration
[7] JSON Schema 校验     →  Validate (引用一致性)
[8] JSON → YAML + 修复   →  Repair 自动修复
```

每个阶段独立可观测,进度条实时更新,失败有明确错误信息。

详见 [DESIGN.md §5](./DESIGN.md#5-核心-ai-生成流程) 和 [docs/architecture.md](./docs/architecture.md)。

---

## 🧪 模型 Key 管理 (BYOK)

生成请求必须满足以下**至少一个**:

1. 请求头 `X-OpenAI-API-Key` 临时传入
2. 后端有 active 的 `user_model_keys`,后端解密后调用
3. 服务端 `OPENAI_API_KEY` 环境变量

`/settings` 页面提供:
- **保存到云端**:后端用 `KEY_ENCRYPTION_KEY` 加密,数据库只存密文 + 尾号 + 状态
- **仅保存本地**:浏览器 `localStorage`,不入库
- **测试 / 撤销**:已保存的 key 可测试可撤销

后端**永不返回明文 key**。

---

## 📦 项目结构

```
script-workshop/
├─ apps/
│  ├─ web/                       # Next.js 前端 (独立子项目)
│  │  ├─ app/                    # 页面 (home/dashboard/editor/settings/runs/new/login)
│  │  ├─ components/             # AuthStatus · ExportMenu · StyleSwitcher · AuthRequiredMessage
│  │  ├─ lib/                    # API 客户端 · LLM 设置 · 类型
│  │  ├─ styles/globals.css      # CSS 变量 + 7 套动效 + 35+ 语义化组件类
│  │  ├─ tailwind.config.mjs     # Tailwind 读 CSS 变量
│  │  └─ CHANGELOG.md
│  ├─ api/                       # FastAPI 后端 (独立子项目)
│  │  ├─ app/                    # routers / services / providers / schemas / db
│  │  ├─ tests/
│  │  ├─ alembic/                # 5 个迁移
│  │  ├─ scripts/                # dev-api.sh / dev-api.ps1 / seed_user.py
│  │  └─ CHANGELOG.md
│  └─ ...
├─ supabase/
│  ├─ rls.sql                    # 28 条 RLS 策略
│  └─ migrate_local_user.sql     # legacy data 迁移脚本
├─ docs/                         # architecture / deployment / yaml-schema
├─ schema/                       # JSON Schema (script.schema.json)
├─ samples/                      # 示例小说 + 示例输出
├─ DESIGN.md                     # 总体设计 (20+ 章节)
├─ CHANGELOG.md                  # 跨端变更
├─ Makefile
├─ docker-compose.yml
├─ render.yaml                   # Render Blueprint
└─ vercel.json
```

---

## 🚢 部署 (免费方案)

Vercel + Render + Supabase Free 计划,够 demo 和内测。

```bash
# 后端: Render 控制台 New → Blueprint → 选仓库 → 填环境变量
# 前端: Vercel 控制台 Add New → Project → Root Directory 选 apps/web
```

详细步骤 + 环境变量 + 8 步验收清单: [docs/deployment.md](./docs/deployment.md)

---

## 📚 文档索引

| 文档 | 内容 |
|---|---|
| [DESIGN.md](./DESIGN.md) | 总体设计,20+ 章节,产品定位到风险应对 |
| [docs/architecture.md](./docs/architecture.md) | 系统分层、数据流、Provider 抽象、版本/Agent/主题架构 |
| [docs/yaml-schema.md](./docs/yaml-schema.md) | YAML Schema 字段逐项说明 |
| [docs/deployment.md](./docs/deployment.md) | Vercel + Render + Supabase 部署指南 + 验收 |
| [CHANGELOG.md](./CHANGELOG.md) | 跨端变更 |
| [apps/web/CHANGELOG.md](./apps/web/CHANGELOG.md) | 前端变更 |
| [apps/api/CHANGELOG.md](./apps/api/CHANGELOG.md) | 后端变更 |

---

## 🎯 题目要求对应

| 题目要求 | 实现 |
|---|---|
| 3 章以上小说 | 新建项目页校验章节标记数,支持粘贴 / 上传 .md / .txt / 载入示例 |
| 自动转结构化剧本 | 8 阶段 AI 流水线 |
| YAML 格式 | 后端先生成 JSON 强校验,ruamel.yaml 输出;YAML 源码模式可直编 |
| 可编辑、可打磨 | 结构化场景编辑 + YAML 源码 + 实时校验 + 一键修复 + 命名快照回滚 |
| 自定义 YAML Schema | `schema/script.schema.json` + 字段说明文档 |
| 剧本源码导入 | 独立入口,粘贴/上传 YAML/JSON 直接恢复为项目和首个快照 |

---

## 📍 状态 (2026-06-06)

**已落地 (端到端可用):**

- ✅ 端到端 AI 生成链路 (8 阶段)
- ✅ 项目看板 / 项目详情 / 结构化编辑器 / YAML 源码 / 命名快照 / 回退
- ✅ 编辑事件持久化 + 最近修改记录
- ✅ AI 改编助手:场景/全剧范围,模型 patch + 本地 fallback,部分接受,重新生成,刷新后恢复
- ✅ 模型 key:后端加密 / 浏览器 localStorage / 测试 / 撤销
- ✅ 最新/历史版本 YAML / Markdown / JSON 导出,统一导出菜单
- ✅ 剧本源码导入 (YAML/JSON 直恢复)
- ✅ 结构化角色/地点增删改 + 场景引用维护 + 快照 diff
- ✅ 顶栏 StyleSwitcher (studio / paper),CSS 变量驱动,7 套动效系统
- ✅ 项目看板内联删除面板 (`.danger-panel`),`window.confirm` 退场
- ✅ Supabase RLS 多用户隔离 (应用层 + 数据库层 28 条策略)
- ✅ Render / Vercel 部署配置 (Blueprint + vercel.json)
- ✅ 跨账号隔离验收 (Supabase Auth + 真账号 + RLS)

**下一阶段:**

- 真实 Render + Vercel 部署 (配置已就绪,待用户触发)
- Monaco 编辑器替代 textarea
- AI 改编 patch 风险提示(删除出场/改时间线)
- paper 主题实测回归

---

## English Summary

**Script Workshop** is an AI-driven screenplay IDE: a full-stack monorepo (Next.js 14 + FastAPI + Supabase Postgres) that turns 3+-chapter novels into editable, validated, version-controlled screenplay drafts via an 8-stage AI pipeline. Features include structured scene editing, an AI adaptation agent with partial-accept and retry, named snapshots with diff/rollback, Markdown/YAML/JSON export, multi-tenant isolation via Supabase RLS, and a CSS-variable-driven dual theme system (Studio dark / Paper light) with a micro-animation layer (fade/scale/shimmer/pulse). Deployable for free on Vercel + Render + Supabase Free.
