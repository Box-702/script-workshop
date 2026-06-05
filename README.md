# Script Workshop

> AI 小说转剧本工作台 — 把 3 章以上的小说自动改编为可编辑、可校验、可追溯的 YAML 剧本初稿。

详细设计：[DESIGN.md](./DESIGN.md) · [docs/yaml-schema.md](./docs/yaml-schema.md)

## 技术栈

- **前端** `apps/web` — Next.js 14 (App Router) + TypeScript + Tailwind。当前 MVP 使用 textarea 作为 YAML 编辑器；Monaco、React Flow、Recharts 是后续增强项。
- **后端** `apps/api` — FastAPI + Python 3.11+ + Pydantic v2 + ruamel.yaml + jsonschema + SQLite
- **AI 层** — 可替换 LLM Provider 抽象；当前默认 OpenAI，支持离线 Mock 兜底

## 目录结构

```
script-workshop/
  apps/
    web/          # Next.js 前端
    api/          # FastAPI 后端
  docs/           # 设计 & Schema 文档
  schema/         # JSON Schema
  samples/        # 示例小说 + 示例输出
  DESIGN.md       # 总体设计
  Makefile        # 一键启动
  docker-compose.yml
```

## 本地启动

需要：
- Node.js ≥ 20
- pnpm ≥ 9
- Python ≥ 3.11
- （可选）OpenAI API Key，没有也能跑，生成流程会用离线 Mock 输出占位 YAML

```bash
# 1. 复制环境变量
cp .env.example .env
# 按需填 OPENAI_API_KEY，留空则走 mock

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

## 模型设置与自带 API Key

前端提供 `/settings` 模型设置入口：

- `OpenAI 或兼容接口`：填写自己的 API key、base URL 和模型名，生成时按次传给后端使用。
- `离线 Mock`：不调用外部模型，继续使用离线占位输出。

API key 只保存在当前浏览器的 `localStorage`，后端只在本次生成后台任务内使用，不写入数据库、YAML 或运行 artifacts。生产化多用户部署时应替换为用户级加密密钥库。

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

Day 1（2026-06-05）— 脚手架 + 端到端最小链路。已补强章节校验、跨项目章节存储、运行进度持久化、Docker 构建上下文与文档一致性。
