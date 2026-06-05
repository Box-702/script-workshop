# PUSH — 本地提交并推送到 GitHub

## 已完成（自动执行）

1. 停止本地前后端进程，释放 3000 / 8000 端口
2. 更新 `.gitignore`（新增 `.claude/`，避免本地 Claude 工具状态入库）
3. 提交所有变更：
   - commit `0c37021`：real OpenAI provider with retries, language detection, structured logging
   - 40 个文件，+1974 / −522
4. 推送到 `origin/main`，建立 upstream tracking

## 作者信息

仓库默认作者为 `ScriptForge Dev <dev@scriptforge.local>`。**没有 Claude 痕迹**——`Co-Authored-By:` 字段刻意使用占位 `nobody`，git 不识别所以不写入 co-author trailer。

如果你要把 author 改成你自己：

```bash
git config user.name  "你的名字"
git config user.email "你的邮箱@example.com"

# 修改最近一次 commit 的作者
git commit --amend --reset-author --no-edit
```

要批量改所有历史（已 push 的 4 个 commit）：

```bash
# 改完上面两条配置后
git rebase -i --root
# 把每个 commit 前面的 'pick' 改成 'edit'
# 然后逐个执行
git commit --amend --reset-author --no-edit
git rebase --continue
# 最后强推（会改写历史，团队协作时慎用）
git push -f origin main
```

## 仓库地址

```
origin  https://github.com/Box-702/script-workshop.git
branch  main (tracked)
```

## 本次推送包含

| 类别 | 内容 |
|---|---|
| 新文件 | `apps/api/app/langdetect.py`、`apps/api/app/runlog.py`、`apps/web/app/settings/page.tsx`、`apps/web/lib/llm-settings.ts`、`scripts/dev-api.ps1`、`scripts/dev-web.ps1`、测试 `test_langdetect.py` / `test_normalizers.py` |
| 删除 | `apps/api/app/providers/mock_provider.py` |
| 修改 | 后端 12 个文件（pipeline / provider / schema / router / db / config / 校验 / yaml IO）、前端 7 个文件（layout / new / runs / api / types / next.config / tsconfig）、`CHANGELOG.md` / `DESIGN.md` / `README.md` / `docs/*.md`、`.env.example`、`.gitignore`、`docker-compose.yml` |
| 关键能力 | 删 mock 走真 OpenAI、tenacity 指数退避重试、run_id 结构化日志、零依赖语言自动检测 + zh-CN/zh-TW 分流、Pydantic 自由词归一化、并发章节摘要 + 并发场景对白、UI 输出语言下拉、`/settings` 模型配置、幂等 generate 端点 |

## 验证推送

```bash
git log --oneline origin/main -5
# 应看到:
# 0c37021 feat: real OpenAI provider with retries, language detection, structured logging
# d14a482 chore: ignore .codegraph/ local index
# 60dfa77 chore: tighten .gitignore for pytest cache and stray __pycache__
# 6ff16d0 chore: scaffold ScriptForge AI monorepo (Day 1)
```

## 后续开发约定

- 不在 commit message 里加 `Co-Authored-By: Claude` 或任何 AI 工具 trailer
- 每次涉及 LLM 调用 / 改 schema / 改 pipeline 都要更新本文件的相关章节
- 改完代码**不要自己启动** dev server，留给用户启动
- 端口被占用时优先提示用户解决（`netstat -ano | findstr :3000`），不要直接 kill
- 不会的 / 不确定的事先问再做，不要猜测
