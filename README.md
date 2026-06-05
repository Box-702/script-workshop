# ScriptForge AI

> AI 小说转剧本工作台 — 把 3 章以上的小说自动改编为可编辑、可校验、可追溯的 YAML 剧本初稿。

详细设计：[DESIGN.md](./DESIGN.md) · [docs/yaml-schema.md](./docs/yaml-schema.md)

## 技术栈

- **前端** `apps/web` — Next.js 14 (App Router) + TypeScript + Tailwind + shadcn/ui + Monaco Editor + React Flow + Recharts
- **后端** `apps/api` — FastAPI + Python 3.11+ + Pydantic v2 + ruamel.yaml + jsonschema + SQLite
- **AI 层** — 可替换 LLM provider 抽象；当前默认 OpenAI，支持 mock 兜底

## 目录结构

```
scriptforge-ai/
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
- （可选）OpenAI API Key — 没有也能跑，pipeline 会用 mock provider 输出占位 YAML

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

## 常用命令

| 命令 | 说明 |
|---|---|
| `make install` | 安装前后端依赖 |
| `make dev` | 同时起前后端 |
| `make dev-api` | 仅起后端 |
| `make dev-web` | 仅起前端 |
| `make test` | 跑测试 |
| `make lint` | 跑 lint |

## AI Pipeline

1. 章节输入与清洗
2. 章节摘要
3. 故事圣经（Story Bible）
4. 人物抽取与角色弧光
5. 场景拆分
6. 逐场剧本生成
7. JSON Schema 校验
8. 自动修复
9. JSON → YAML 导出

详见 [DESIGN.md §5](./DESIGN.md#5-核心-ai-pipeline)。

## 题目要求对应

| 题目要求 | 实现 |
|---|---|
| 3 章以上小说 | 项目创建页校验 ≥ 3 章 |
| 自动转结构化剧本 | 8 阶段 AI pipeline |
| YAML 格式 | 后端先生成 JSON 强校验，再 ruamel.yaml 输出 |
| 可编辑、可打磨 | Monaco YAML 编辑器 + 实时校验 + 一键修复 |
| 自定义 YAML Schema | `schema/script.schema.json` + `docs/yaml-schema.md` |
| Schema 设计原因 | 文档逐字段说明 |

## 状态

Day 1（2026-06-05）— 脚手架 + 端到端最小链路。
