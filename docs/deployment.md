# 免费部署指南

> 目标拓扑：Vercel 托管 Next.js 前端，Render 托管 FastAPI 后端，Supabase 提供 Auth 和 Postgres。本文按官方文档在 2026-06-06 核对过关键入口：Vercel 环境变量、Render FastAPI、Supabase Auth Redirect URLs、Supabase Postgres 连接。

官方参考：
- [Vercel Environment Variables](https://vercel.com/docs/environment-variables)
- [Render Deploy FastAPI](https://render.com/docs/deploy-fastapi)
- [Supabase Redirect URLs](https://supabase.com/docs/guides/auth/redirect-urls)
- [Supabase Connecting to Postgres](https://supabase.com/docs/guides/database/connecting-to-postgres)

## 当前生产环境

已部署并验收于 2026-06-06：

| 服务 | 地址 |
|---|---|
| 前端 (Vercel) | `https://script-workshop-web.vercel.app` |
| 后端 (Render) | `https://script-workshop-api.onrender.com` |
| 前端代理健康检查 | `https://script-workshop-web.vercel.app/api/healthz` |
| 后端直连健康检查 | `https://script-workshop-api.onrender.com/api/healthz` |

验收结果：

- 前端首页返回 `200`。
- 后端直连 `/api/healthz` 返回 `{"status":"ok","version":"0.1.0"}`。
- 前端代理 `/api/healthz` 返回 `{"status":"ok","version":"0.1.0"}`。
- 未登录访问前端时会进入本地模式；请求会携带浏览器本地身份 `X-Local-User-Id`。

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
   - `Site URL`：Vercel 前端正式域名，例如 `https://script-workshop-web.vercel.app`
   - `Redirect URLs`：验证码登录不依赖回跳；如需兼容旧 magic link，可加入 `https://script-workshop-web.vercel.app/auth/callback`
   - 本地旧链接兼容可另加 `http://localhost:3000/auth/callback`

5. 在 `Authentication -> Email Templates` 确认登录邮件包含验证码 token，例如 `{{ .Token }}`。不要只放 magic link，否则前端验证码输入框拿不到可输入的码。也可以用 Supabase Management API 同步模板：
   ```powershell
   $env:SUPABASE_ACCESS_TOKEN="你的 Supabase Management API personal access token"
   pnpm supabase:otp-template
   ```
   这个 token 只用于一次性维护，不要部署到 Vercel 或 Render。
6. 如果线上出现 `email rate limit exceeded`，说明 Supabase Auth 发信限流已触发。生产环境建议在 `Authentication -> SMTP Settings` 配置自定义 SMTP，并在 `Authentication -> Rate Limits` 里按实际需要调整邮件/OTP 限制。

> 已验证 2026-06-06：项目 `wsogpdggsmehdrujdjrx` (West US, Oregon) 配齐以上四个值后，`alembic upgrade head` 在 Transaction pooler (`aws-1-us-west-2.pooler.supabase.com:6543`) 上跑通 5 个迁移，`/api/healthz` 与 `/api/projects` 401 路径均正常返回。

## 2. 部署 Render 后端

仓库根目录已经写好 `render.yaml` (Render Blueprint)。在 Render 控制台:

1. **New** → **Blueprint** → 选 GitHub 仓库 `Box-702/script-workshop`。
2. Render 会读 `render.yaml` 自动建一个 `script-workshop-api` Web Service。
3. 在 **Environment** 标签,把所有 `sync: false` 的 secret 手动填入(用密码框,不进 git)：

   | 变量 | 来源 |
   |---|---|
   | `DATABASE_URL` | Supabase → Database → Settings → Connection string (Transaction pooler) |
   | `SUPABASE_URL` | Supabase Project URL |
   | `SUPABASE_ANON_KEY` | Supabase → Settings → API Keys → Publishable key |
   | `SUPABASE_SERVICE_ROLE_KEY` | Supabase → Settings → API Keys → Secret keys |
   | `CORS_ORIGINS` | Vercel 前端域名,例如 `https://script-workshop-web.vercel.app` |
   | `KEY_ENCRYPTION_KEY` | `python -c "import secrets; print(secrets.token_urlsafe(32))"` |

   `AUTH_MODE=hybrid` / `LLM_PROVIDER=openai` 等默认值已在 `render.yaml` 写死,不用手填。

   `hybrid` 模式含义：用户登录后使用 Supabase 用户 id；未登录时使用浏览器本地身份 id。未登录项目不跨设备同步，清空浏览器数据后也可能失去原本地身份。

4. **Apply** → 等部署完成。

部署后打开:

```text
https://script-workshop-api.onrender.com/api/healthz
```

返回 `{"status":"ok","version":"0.1.0"}` 即后端启动成功。Free 计划首次访问有冷启动延迟。

如果用 Docker 而非 Blueprint: 用仓库根目录的 `docker-compose.yml`,命令一致。

## 3. 部署 Vercel 前端

仓库根目录有 `vercel.json` 钉住 framework。导入 GitHub 仓库后:

1. **Project Settings → General → Root Directory** 设为 `apps/web`。
2. **Environment Variables** 填 (密码框,不进 git):

   | 变量 | 值 |
   |---|---|
   | `BACKEND_URL` | Render 后端地址,例如 `https://script-workshop-api.onrender.com` |
   | `NEXT_PUBLIC_API_BASE` | `/api` |
   | `NEXT_PUBLIC_SUPABASE_URL` | Supabase Project URL |
   | `NEXT_PUBLIC_SUPABASE_ANON_KEY` | Publishable key |

3. **Deploy**。`/api/*` 会被 `apps/web/next.config.mjs` 里的 rewrites 转发到 `BACKEND_URL/api/*`。

**禁止在 Vercel 设置 `SUPABASE_SERVICE_ROLE_KEY` 或任何后端私钥。**

## 4. 生产验收清单

上线后按顺序检查：

1. 打开前端 `/settings`，输入邮箱，确认能收到邮箱验证码并完成登录。
2. 退出登录后打开前端，确认顶部显示“当前为本地模式”，并且 `/dashboard` 不再被登录拦截。
3. 在未登录状态保存一个浏览器本地模型 key，创建一个 3 章以上项目并生成剧本。
4. 登录后保存一个模型 key，刷新页面，确认已保存 key 仍显示尾号。
5. 创建一个 3 章以上项目。
6. 点击生成剧本，确认没有空白失败页；如果没有 key，应显示明确提示。
7. 进入编辑器，保存一个快照，再修改一处场景并保存第二个快照。
8. 在快照历史里点击“对比当前”，确认能看到版本差异。
9. 导出 YAML、JSON、Markdown，确认响应正常。
10. 用第二个账号登录，确认看不到第一个账号的项目和模型 key。

## 5. 常见问题

### 登录后 API 仍返回 401

检查：
- Vercel 是否配置了 `NEXT_PUBLIC_SUPABASE_URL` 和 `NEXT_PUBLIC_SUPABASE_ANON_KEY`。
- Render 是否配置了 `AUTH_MODE=hybrid`、`SUPABASE_URL`、`SUPABASE_ANON_KEY`。
- Supabase 邮件模板是否包含 `{{ .Token }}`，且 Vercel 环境变量是否在改完后重新部署。
- 如果页面提示验证码邮件发送过于频繁，检查 Supabase Auth Rate Limits 和 SMTP 设置。

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

### alembic 报 `invalid interpolation syntax`

Postgres 连接串里 percent-encoded 字符（`%2C`、`%26`、`%2B` 等）和 alembic 的 ConfigParser `%` 插值冲突。`alembic/env.py` 与 `app/db.py` 已经做了 `.replace("%", "%%")` 兼容处理；如果升级 alembic 后又遇到这个错，优先检查这两处。

### 保存云端模型 key 失败

生产必须设置 `KEY_ENCRYPTION_KEY`。如果换了这个值，旧的已保存 key 将无法解密，需要用户重新保存。
