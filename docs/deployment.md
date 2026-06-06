# 免费部署指南

> 目标拓扑：Vercel 托管 Next.js 前端，Render 托管 FastAPI 后端，Supabase 提供 Auth 和 Postgres。本文按官方文档在 2026-06-06 核对过关键入口：Vercel 环境变量、Render FastAPI、Supabase Auth Redirect URLs、Supabase Postgres 连接。

官方参考：
- [Vercel Environment Variables](https://vercel.com/docs/environment-variables)
- [Render Deploy FastAPI](https://render.com/docs/deploy-fastapi)
- [Supabase Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
- [Supabase Connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres)

## 1. 准备 Supabase

1. 新建 Supabase project。
2. 在 `Project Settings -> API` 记录：
   - `Project URL` -> `SUPABASE_URL`
   - `anon public` key -> `SUPABASE_ANON_KEY` 和前端 `NEXT_PUBLIC_SUPABASE_ANON_KEY`
   - `service_role` key -> `SUPABASE_SERVICE_ROLE_KEY`。只放后端，不要放前端。
3. 在 `Database -> Connect` 复制 Postgres 连接串，后端使用 SQLAlchemy/psycopg 形式：

```text
DATABASE_URL=postgresql+psycopg://postgres:<password>@<host>:5432/postgres
```

4. 在 `Authentication -> URL Configuration` 配置：
   - `Site URL`：Vercel 前端正式域名，例如 `https://script-workshop.vercel.app`
   - `Redirect URLs`：至少加入 `https://script-workshop.vercel.app/auth/callback`
   - 本地调试可另加 `http://localhost:3000/auth/callback`

## 2. 部署 Render 后端

推荐先用 Render Web Service 的原生 Python 部署，避免 Docker 端口配置差异。

### 基本设置

| 项 | 值 |
|---|---|
| Runtime | Python 3 |
| Root Directory | 仓库根目录 |
| Build Command | `cd apps/api && pip install -U pip && pip install -e .` |
| Start Command | `cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port $PORT` |
| Health Check Path | `/api/healthz` |

### 后端环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `DATABASE_URL` | 是 | Supabase Postgres 连接串，使用 `postgresql+psycopg://...` |
| `AUTH_MODE` | 是 | 生产设为 `supabase` |
| `SUPABASE_URL` | 是 | Supabase Project URL |
| `SUPABASE_ANON_KEY` | 是 | 后端用它向 Supabase Auth 验证 Bearer token |
| `SUPABASE_SERVICE_ROLE_KEY` | 建议 | 预留给后续服务端管理能力；不要暴露到前端 |
| `KEY_ENCRYPTION_KEY` | 是 | 加密用户保存的模型 key。用 `python -c "import secrets; print(secrets.token_urlsafe(32))"` 生成 |
| `OPENAI_API_KEY` | 否 | 可留空，默认让用户在 `/settings` 自带 key |
| `OPENAI_BASE_URL` | 否 | 默认 `https://api.openai.com/v1` |
| `OPENAI_MODEL` | 否 | 默认 `gpt-4o-mini` |
| `OUTPUT_LANGUAGE` | 否 | 默认 `zh-CN` |
| `CORS_ORIGINS` | 是 | Vercel 前端域名，例如 `https://script-workshop.vercel.app` |

部署后打开：

```text
https://<render-service>.onrender.com/api/healthz
```

返回 `{"status":"ok","version":"0.1.0"}` 即后端启动成功。首次访问可能有冷启动延迟。

## 3. 部署 Vercel 前端

### 基本设置

导入 GitHub 仓库后，选择 `apps/web` 作为 Next.js 应用目录。如果 Vercel 没有自动识别 pnpm workspace，可手动设置：

| 项 | 值 |
|---|---|
| Framework Preset | Next.js |
| Install Command | `pnpm install --frozen-lockfile` |
| Build Command | `pnpm --dir apps/web build` |

如果项目根目录被设置为 `apps/web`，则使用默认 `pnpm build` 也可以；关键是最终构建命令必须运行 `apps/web/package.json` 中的 `build`。

### 前端环境变量

| 变量 | 必填 | 说明 |
|---|---|---|
| `BACKEND_URL` | 是 | Render 后端地址，例如 `https://script-workshop-api.onrender.com` |
| `NEXT_PUBLIC_API_BASE` | 建议 | 保持 `/api`，由 Next rewrites 转发到后端 |
| `NEXT_PUBLIC_SUPABASE_URL` | 是 | Supabase Project URL |
| `NEXT_PUBLIC_SUPABASE_ANON_KEY` | 是 | Supabase anon public key |

注意：不要在 Vercel 中设置 `SUPABASE_SERVICE_ROLE_KEY` 或任何服务端私钥。

## 4. 生产验收清单

上线后按顺序检查：

1. 打开前端 `/settings`，输入邮箱，确认 magic link 能回跳到 `/auth/callback`。
2. 登录后保存一个模型 key，刷新页面，确认已保存 key 仍显示尾号。
3. 创建一个 3 章以上项目。
4. 点击生成剧本，确认没有空白失败页；如果没有 key，应显示明确提示。
5. 进入编辑器，保存一个快照，再修改一处场景并保存第二个快照。
6. 在快照历史里点击“对比当前”，确认能看到版本差异。
7. 导出 YAML、JSON、Markdown，确认响应正常。
8. 用第二个账号登录，确认看不到第一个账号的项目和模型 key。

## 5. 常见问题

### 登录后 API 仍返回 401

检查：
- Vercel 是否配置了 `NEXT_PUBLIC_SUPABASE_URL` 和 `NEXT_PUBLIC_SUPABASE_ANON_KEY`。
- Render 是否配置了 `AUTH_MODE=supabase`、`SUPABASE_URL`、`SUPABASE_ANON_KEY`。
- Supabase Redirect URLs 是否包含 Vercel 的 `/auth/callback`。

### 前端请求仍打到 localhost

检查 Vercel 的 `BACKEND_URL`。Next.js rewrites 会把 `/api/*` 转发到 `BACKEND_URL/api/*`。

### Render 启动失败

检查 Start Command 是否使用 `$PORT`：

```bash
cd apps/api && uvicorn app.main:app --host 0.0.0.0 --port $PORT
```

Render 不应使用固定 `8000` 作为生产 start command。

### 数据没有持久化

检查 `DATABASE_URL` 是否指向 Supabase Postgres。生产不要使用 SQLite，因为免费服务磁盘可能不持久。

### 保存云端模型 key 失败

生产必须设置 `KEY_ENCRYPTION_KEY`。如果换了这个值，旧的已保存 key 将无法解密，需要用户重新保存。
