# 剧本工坊 (Script Workshop)

> AI 驱动的剧本 IDE — 把 3 章以上的小说自动改编为可编辑、可校验、可追溯、可导出的结构化剧本。

把小说原文交给系统,8 阶段 AI 流水线产出结构化剧本初稿;之后你可以像用 IDE 一样持续打磨:多版本快照、AI 改编助手、命名回滚、结构化 diff、Markdown 导出,所有改动都进入同一套版本系统。

文档索引:
- 总体设计: [DESIGN.md](./DESIGN.md)
- 架构与数据流: [docs/architecture.md](./docs/architecture.md)
- YAML Schema 字段说明: [docs/yaml-schema.md](./docs/yaml-schema.md)
- 免费部署指南 (Vercel + Render + Supabase): [docs/deployment.md](./docs/deployment.md)
- 变更历史: [CHANGELOG.md](./CHANGELOG.md)

## 核心能力

| 能力 | 说明 |
|---|---|
| 8 阶段 AI 生成 | 章节切分 → 摘要 → 故事圣经 → 角色抽取 → 场景拆分 → 逐场成稿 → Schema 校验 → 自动修复 |
| 结构化编辑 | 角色 / 地点 / 场景 / 动作 / 对白 全部结构化可编辑,YAML 源码模式留给技术用户 |
| AI 改编助手 | 当前场景或全剧范围,带"改编重点 + 约束"快捷片段,模型生成 patch 或本地建议 fallback |
| 版本系统 | AI 生成 / 手动保存 / 自动修复 / AI 改编 / 导入 / 回滚 全部走统一快照,可命名、可回退、可 diff |
| Markdown 导出 | 面向编剧/改编者阅读稿,中文分段,角色名 + 地点名解析,过滤空行 |
| 剧本源码导入 | 粘贴或上传 YAML/JSON 即可恢复为项目和首个快照,无需 AI |
| 模型 key 管理 | 浏览器 localStorage BYOK 或后端加密保存(展示尾号,可测试/撤销) |
| 界面主题切换 | 顶栏 StyleSwitcher: studio 深色专业 / paper 浅色审阅,所有颜色由 CSS 变量驱动 |

## 技术栈

- **前端** `apps/web`: Next.js 14 (App Router) + TypeScript + Tailwind 3.4。Tailwind 色板读 CSS 变量,所有自定义组件走语义化 class (`.btn-primary` / `.panel` / `.info-card` / `.danger-panel` / `.surface-line` 等)。
- **后端** `apps/api`: FastAPI + Python 3.11+ + Pydantic v2 + SQLAlchemy + Alembic。SQLite 本地开发,Supabase Postgres 生产。
- **AI 层**: OpenAI 兼容 Provider。`X-OpenAI-*` 请求头临时 key,或后端解密用户 active key。
- **认证**: 当前 MVP `AUTH_MODE=local`;Supabase Auth 已留接口,生产配置见 `docs/deployment.md`。

## 界面主题

所有颜色由 `apps/web/styles/globals.css` 的 CSS 变量驱动,Tailwind 在 `tailwind.config.mjs` 里通过 `rgb(var(--x) / <alpha-value>)` 读取。

- `studio`(默认): 深色 + 紫蓝强调色 (`--accent-500: 91 61 240`)。长时间编辑首选。
- `paper`: 浅色 + 暖棕强调色 (`--accent-500: 152 71 22`)。导出前校对 / 长文审阅首选。

切换方式: 顶栏右上 `StyleSwitcher` → 选 Studio / Paper。选择持久化在 `localStorage`,刷新保持。新增主题只需在 globals.css 加一组 `[data-ui-style="..."] { --ink-* }` 定义,无需改任何组件。

主题感知工具类 (替换硬编码 `border-white/10` 等):

- `.surface-line` 边框
- `.surface-line-soft` 弱边框
- `.surface-soft` 浅色覆盖层

## 快速启动

依赖: Node.js ≥ 20,pnpm ≥ 9,Python ≥ 3.11。

```bash
# 1. 复制环境变量
cp .env.example .env
# 可选: 填 OPENAI_API_KEY 作为服务端默认 key
# 推荐: 填 KEY_ENCRYPTION_KEY (32 字节 base64),用于加密用户保存的模型 key

# 2. 安装依赖
make install

# 3. 一键启动前后端
make dev
# 前端 http://localhost:3000
# 后端 http://localhost:8000/docs
```

Windows 用户也可以分别用项目内的 PowerShell 脚本 (推荐 IDE 集成终端):

```powershell
.\scripts\dev-api.ps1
.\scripts\dev-web.ps1
```

`dev-web.ps1` 会在启动前自动停掉本项目占用的 3000 端口旧进程,并清理陈旧 `.next` 缓存,避免热更新缓存错误。

### 单独启动任一端

前后端可完全独立启动,各自有自己的依赖、配置和部署管道:

```bash
# 仅前端 (cd apps/web && pnpm dev)
pnpm --dir apps/web dev

# 仅后端 (linux/macOS)
bash apps/api/scripts/dev-api.sh

# 仅后端 (Windows PowerShell)
.\apps\api\scripts\dev-api.ps1
```

或者走各自原生的工具链:

```bash
# 前端
cd apps/web && pnpm install && pnpm dev
# 后端
cd apps/api && pip install -e . && uvicorn app.main:app --reload
```

`Makefile` / `scripts/dev-*.ps1` 只是开发期并行启动的便利,**不**是部署前置。

## 常用命令

| 命令 | 说明 |
|---|---|
| `make install` | 安装前后端依赖 |
| `make dev` | 同时起前后端 (两个终端合并输出) |
| `make dev-api` | 仅起后端 (uvicorn :8000) |
| `make dev-web` | 仅起前端 (next dev :3000) |
| `make test` | 跑后端 pytest + 前端 typecheck |
| `make lint` | 跑 ruff + next lint |
| `make db-upgrade` | alembic upgrade head |
| `make db-history` | 查看迁移历史 |
| `pnpm clean` | 清理前端构建缓存 + Python 缓存 + 本地日志 |

## 模型 Key 管理

生成时必须满足以下至少一个:

1. 请求头 `X-OpenAI-API-Key` 临时传入。
2. 后端存在 active 的 `user_model_keys`,后端解密后调用。
3. 服务端环境变量 `OPENAI_API_KEY` 已配置。

`/settings` 页面提供:

- **保存到云端**: 后端用 `KEY_ENCRYPTION_KEY` 加密保存,数据库只存密文 + 尾号 + 状态。生成请求头没 key 时自动使用 active key。
- **仅保存本地**: 浏览器 `localStorage`,生成时通过请求头临时传给后端,不入库。
- **测试 / 撤销**: 已保存的 key 可测试是否可解密,可随时撤销。

后端永不返回明文 key,也不写入 YAML / artifacts / 日志。生产部署必须设 `KEY_ENCRYPTION_KEY`。

## AI 生成流程 (8 阶段)

1. 章节输入与清洗
2. 章节摘要
3. 故事圣经 (Story Bible)
4. 人物抽取与角色弧光
5. 场景拆分
6. 逐场剧本生成
7. JSON Schema 校验与引用检查
8. 自动修复 + JSON → YAML

详见 [DESIGN.md §5](./DESIGN.md#5-核心-ai-生成流程) 与 [docs/architecture.md](./docs/architecture.md) 数据流章节。

## 目录结构

**前后端分别管理:** 每个子项目有自己的依赖清单、CHANGELOG、启动脚本和部署配置,见各自 README / 配置文件:

- 前端 → `apps/web/` (Next.js) + `apps/web/CHANGELOG.md` + `vercel.json`
- 后端 → `apps/api/` (FastAPI) + `apps/api/CHANGELOG.md` + `render.yaml`

根 `CHANGELOG.md` 只记录跨端架构和 monorepo 级别的变更。

```
script-workshop/
  apps/
    web/                    # Next.js 前端 (独立子项目)
      app/                  # 页面 (dashboard / projects / editor / settings / runs / new)
      components/           # AuthStatus / ExportMenu / StyleSwitcher / AuthRequiredMessage
      lib/                  # API 客户端 / LLM 设置 / 类型
      styles/globals.css    # CSS 变量 + 主题 + 组件样式
      tailwind.config.mjs   # 读 CSS 变量
    api/                    # FastAPI 后端
      app/                  # routers / services / providers / schemas / db
      tests/
      alembic/
  docs/                     # 架构 / 部署 / Schema 文档
  schema/                   # JSON Schema (script.schema.json)
  samples/                  # 示例小说 + 示例输出
  scripts/                  # dev-api.ps1 / dev-web.ps1 / clean.mjs (根级编排)
  apps/api/scripts/         # dev-api.sh / dev-api.ps1 (后端独立启动)
  DESIGN.md                 # 总体设计
  CHANGELOG.md              # 跨端变更
  apps/web/CHANGELOG.md     # 前端变更
  apps/api/CHANGELOG.md     # 后端变更
  Makefile                  # 并行启动前后端 (开发期)
  docker-compose.yml        # 本地容器化
  render.yaml               # Render Blueprint (后端部署)
  vercel.json               # Vercel 项目配置 (前端部署)
```

## 示例与样本数据

- `samples/sample-novel.md`: 内置示例小说,新建项目页"载入示例"一键使用。
- `samples/sample-output.yaml`: 对应 AI 生成的结构化剧本输出。
- `schema/script.schema.json`: YAML/JSON 导出与校验依据,字段说明见 [docs/yaml-schema.md](./docs/yaml-schema.md)。

## 部署

免费方案: Vercel (前端) + Render (后端) + Supabase (Postgres + Auth)。

仓库已写好:

- `render.yaml` (Render Blueprint) — 一键拉起 FastAPI Web Service
- `vercel.json` — 钉住 Next.js framework
- `docker-compose.yml` — 本地容器化备选

详细步骤、环境变量、生产 checklist 见 [docs/deployment.md](./docs/deployment.md)。

## 题目要求对应

| 题目要求 | 实现 |
|---|---|
| 3 章以上小说 | 新建项目页校验章节标记数,支持粘贴 / 上传 .md / .txt / 载入示例 |
| 自动转结构化剧本 | 8 阶段 AI 流水线 |
| YAML 格式 | 后端先生成 JSON 强校验,ruamel.yaml 输出;YAML 源码模式可直编 |
| 可编辑、可打磨 | 结构化场景编辑 + YAML 源码 + 实时校验 + 一键修复 + 命名快照回滚 |
| 自定义 YAML Schema | `schema/script.schema.json` + 字段说明文档 |
| 剧本源码导入 | 独立入口,粘贴/上传 YAML/JSON 直接恢复为项目和首个快照 |

## 状态

2026-06-06 当前已落地:

- 端到端 AI 生成链路 + 章节校验 + 跨项目章节存储
- 项目看板 / 项目详情 / 结构化编辑器 / YAML 源码 / 命名快照 + 回退
- 编辑事件持久化 + 项目详情页最近修改记录
- AI 改编助手: 当前场景 / 全剧,改编重点 + 约束,模型 patch 或本地 fallback,部分接受,重新生成
- 模型 key: 后端加密 / 浏览器 localStorage / 测试 / 撤销
- 最新/历史版本 YAML / Markdown / JSON 导出,统一导出菜单
- 剧本源码导入 (YAML/JSON 直恢复)
- 结构化角色/地点增删改 + 场景引用维护 + 快照 diff
- 顶栏 StyleSwitcher (studio / paper),CSS 变量驱动,所有组件跟随
- 项目看板内联删除面板 (`.danger-panel`),`window.confirm` 退场

下一阶段重点: 真实 Supabase + Render + Vercel 端到端部署验收 / 跨账号数据隔离 / 版本 diff 风险提示与回滚前预览。
