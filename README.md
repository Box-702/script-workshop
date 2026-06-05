# Script Workshop

> AI 小说转剧本工作台 — 把 3 章以上的小说自动改编为可编辑、可校验、可追溯的 YAML 剧本初稿。

详细设计：[DESIGN.md](./DESIGN.md) · 架构说明：[docs/architecture.md](./docs/architecture.md) · Schema：[docs/yaml-schema.md](./docs/yaml-schema.md)

## 技术栈

- **前端** `apps/web`：Next.js 14 (App Router) + TypeScript + Tailwind。当前使用项目看板、项目详情、运行进度、YAML 编辑器和模型设置页承载 MVP。
- **后端** `apps/api`：FastAPI + Python 3.11+ + Pydantic v2 + SQLAlchemy + Alembic + SQLite。
- **AI 层**：OpenAI 兼容 Provider。支持浏览器临时传 key，也支持后端加密保存用户模型 key。

## 目录结构

```
script-workshop/
  apps/
    web/          # Next.js 前端
    api/          # FastAPI 后端
  docs/           # 设计 & Schema 文档
  schema/         # JSON Schema
  samples/        # 示例小说 + 示例输出
  scripts/        # 本地开发启动脚本
  DESIGN.md       # 总体设计
  Makefile        # 一键启动
  docker-compose.yml
```

## 本地启动

需要：
- Node.js ≥ 20
- pnpm ≥ 9
- Python ≥ 3.11
- OpenAI 或兼容接口 API key。可在 `/settings` 保存到后端加密存储，也可以只保存在当前浏览器。

```bash
# 1. 复制环境变量
cp .env.example .env
# 可选：填 OPENAI_API_KEY 作为服务端默认 key
# 推荐：填 KEY_ENCRYPTION_KEY，用于加密用户保存的模型 key

# 2. 安装依赖
make install

# 3. 一键启动前后端
make dev
# 前端 http://localhost:3000
# 后端 http://localhost:8000/docs
```

Windows PowerShell 下也可以直接使用项目内虚拟环境：

```powershell
.\apps\api\.venv\Scripts\python.exe -m pytest apps\api\tests
pnpm --dir apps/web build
```

IDE 集成终端里推荐用更短的启动脚本：

```powershell
.\scripts\dev-api.ps1
.\scripts\dev-web.ps1
```

`dev-web.ps1` 会在启动前清理陈旧的 `.next` 缓存，并自动停掉本项目占用 3000 端口的旧前端进程，避免 Next.js dev server 出现 webpack 热更新缓存错误。

## 常用命令

| 命令 | 说明 |
|---|---|
| `make install` | 安装前后端依赖 |
| `make dev` | 同时起前后端 |
| `make dev-api` | 仅起后端 |
| `make dev-web` | 仅起前端 |
| `make test` | 跑测试 |
| `make lint` | 跑 lint |
| `pnpm clean` | 清理前端构建缓存、Python 缓存和本地日志 |

## 模型设置与自带 API Key

前端提供 `/settings` 模型设置入口：

- `保存到云端`：后端加密保存用户模型 key，只展示尾号和状态。生成时如果请求头没有 key，会自动使用 active key。
- `仅保存本地`：key 保存在当前浏览器 `localStorage`，生成时通过请求头临时传给后端。
- `撤销/测试`：可以测试已保存 key 是否可解密，也可以随时撤销旧 key。

后端不会返回明文 key，也不会把明文写入 YAML、运行 artifacts 或日志。生产部署必须设置 `KEY_ENCRYPTION_KEY`。

生成时必须至少满足一个条件：

- 请求头携带 `X-OpenAI-API-Key`。
- 后端存在 active 的用户模型 key。
- 服务端环境变量 `OPENAI_API_KEY` 已配置。

## AI 生成流程

1. 章节输入与清洗
2. 章节摘要
3. 故事圣经（Story Bible）
4. 人物抽取与角色弧光
5. 场景拆分
6. 逐场剧本生成
7. JSON Schema 校验与引用检查
8. 自动修复与 JSON → YAML 导出

详见 [DESIGN.md §5](./DESIGN.md#5-核心-ai-生成流程)。

## 题目要求对应

| 题目要求 | 实现 |
|---|---|
| 3 章以上小说 | 项目创建页支持粘贴文本、载入示例、上传 `.txt` / `.md`，并校验 ≥ 3 章 |
| 自动转结构化剧本 | 8 阶段 AI 生成流程 |
| YAML 格式 | 后端先生成 JSON 强校验，再 ruamel.yaml 输出 |
| 可编辑、可打磨 | YAML textarea 编辑器 + 实时校验 + 一键修复 |
| 自定义 YAML Schema | `schema/script.schema.json` + `docs/yaml-schema.md` |
| Schema 设计原因 | 文档逐字段说明 |

## 状态

Day 1（2026-06-05）已完成：

- 脚手架与端到端生成链路。
- 章节校验、跨项目章节存储、运行进度持久化。
- 项目看板、项目详情、YAML 编辑保存、剧本版本列表和恢复。
- 模型 key 后端加密保存、本地浏览器保存、测试和撤销。
- Docker 构建上下文、Alembic 迁移和基础文档同步。

下一阶段重点：`edit_events`、AI Agent 改编 API、Diff Review UI、Supabase Auth/Postgres 和免费部署文档。
