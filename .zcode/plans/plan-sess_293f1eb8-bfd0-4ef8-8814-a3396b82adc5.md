
# 桌面端打包 + 创新 UI 重构

## 一、桌面端打包（PyWebView + PyInstaller）

**方案选择**：PyWebView（系统 webview）+ PyInstaller。理由：
- 项目架构天然适合（FastAPI 服务 Vue SPA，全部 API 在 /api 下）
- 零新语言（纯 Python，不引入 Rust/Node）
- 前端已零运行时依赖（vue + vite 构建产物是纯静态 HTML/JS/CSS）
- SQLite + 内存 checkpointer 已有回退，无需 Postgres

**具体步骤**：

### 1.1 新建 `app/desktop.py` — 桌面启动器
```
- 启动 uvicorn（127.0.0.1:0 随机端口）在后台线程
- 轮询 /api/healthz 等待服务就绪
- webview.create_window("剧本工坊", f"http://127.0.0.1:{port}", width=1280, height=800)
- 窗口关闭时优雅停服
```

### 1.2 修改 `app/config.py` — 桌面模式默认值
- 检测是否打包（`getattr(sys, 'frozen', False)`）
- 桌面模式默认 `DATABASE_URL=sqlite:///{app_data}/script_agent.db`
- 桌面模式默认 `CHECKPOINTER=memory`
- `WORKSPACE_ROOT` 默认 `~/.script-workshop/`

### 1.3 新建 `script-workshop.spec` — PyInstaller 配置
- 入口：`app/desktop.py`
- 数据：`frontend/dist` 打包进去
- 隐藏导入：langchain/langgraph 动态导入的模块
- 排除：pymilvus（桌面模式用内存向量）

### 1.4 新建 `build.py` — 构建脚本
- `cd frontend && npm run build`
- `pyinstaller script-workshop.spec`

---

## 二、创新 UI 设计（脱离 Codex 模仿，建立独立 identity）

**设计哲学**：从「聊天工具」转型为「创作工作台」。借鉴 Linear（命令面板 + 键盘优先）、Notion（行内编辑 + 斜杠命令）、Obsidian（图谱视图）的精髓，结合剧本创作的特殊需求。

### 2.1 命令面板（Command Palette）— `Ctrl+K`
**新建 `CommandPalette.vue`**

借鉴 Linear/Raycast 的命令面板：
- `Ctrl+K` 或 `Cmd+K` 唤醒
- 模糊搜索：项目、对话、版本、命令
- 分类：最近项目 / 对话 / 快捷命令（生成初稿、改编、分析…）
- 键盘导航（↑↓ 选择，Enter 执行）
- 替代顶栏的多个按钮，成为主要导航方式

### 2.2 行内 Agent 响应 — 重设计消息渲染
**修改 `MessageItem.vue` + 新设计**

借鉴 Notion 的评论系统 + Linear 的 inline 状态：
- **不再是聊天气泡**：Agent 回复以「编辑器注释」形式出现，像 Google Docs 的建议模式
- **工具调用**：从 chips 改为可折叠的「工作步骤」面板，每个步骤有图标 + 描述 + 状态
- **子代理任务**：从静态卡片改为实时进度条 + 步骤列表
- **审阅卡片**：保留但视觉升级，更像 GitHub PR 的 review 界面

### 2.3 场景导航器 — 左栏重构
**修改 `ProjectTree.vue`**

借鉴 Scrivener 的 Binder + Notion 的页面树：
- 项目下直接显示**场景列表**（不只是对话列表）
- 每个场景显示：标题、人物数、节拍数、完成状态
- 场景可拖拽排序
- 搜索框（过滤场景/对话）
- 折叠/展开全部

### 2.4 上下文感知右栏 — Inspector 模式
**修改 `ViewerPanel.vue`**

借鉴 Xcode 的 Inspector + Figma 的属性面板：
- 右栏内容随上下文变化：
  - 选中场景时 → 显示场景详情（人物、节拍、冲突）
  - 有 Agent 任务时 → 显示任务进度
  - 有审阅建议时 → 显示 diff 预览
- 不再是固定 tab 切换，而是**智能面板**

### 2.5 视觉创新
**修改 `style.css` + 各组件**

- **场景卡片**：左栏场景用微型卡片替代纯文本列表，显示节拍条（类似音频波形）
- **连接线**：项目 → 对话 → 场景的关系用微弱的连接线可视化
- **呼吸灯**：Agent 工作时，相关区域有柔和的呼吸灯效果
- **渐进式披露**：默认简洁，hover/展开后显示更多细节

---

## 三、需要修改/新建的文件

| 文件 | 操作 |
|------|------|
| `app/desktop.py` | **新建** — 桌面启动器 |
| `app/config.py` | 修改 — 桌面模式默认值 |
| `script-workshop.spec` | **新建** — PyInstaller 配置 |
| `build.py` | **新建** — 构建脚本 |
| `frontend/src/components/CommandPalette.vue` | **新建** — 命令面板 |
| `frontend/src/components/MessageItem.vue` | 重设计 — 行内 Agent 响应 |
| `frontend/src/components/ProjectTree.vue` | 重设计 — 场景导航器 |
| `frontend/src/components/ViewerPanel.vue` | 重设计 — 上下文感知 Inspector |
| `frontend/src/components/AgentPanel.vue` | 重设计 — 实时进度面板 |
| `frontend/src/components/HeaderBar.vue` | 简化 — 命令面板入口 |
| `frontend/src/stores/app.js` | 新增命令面板状态 + 场景数据 |
| `frontend/src/style.css` | 新设计令牌 + 组件样式 |
| `frontend/src/App.vue` | 集成命令面板 |

---

## 四、执行顺序

1. 桌面端：`app/desktop.py` + `app/config.py` 桌面模式
2. 桌面端：`script-workshop.spec` + `build.py`
3. UI：`CommandPalette.vue`（命令面板）
4. UI：`HeaderBar.vue` 简化
5. UI：`ProjectTree.vue` 场景导航器
6. UI：`MessageItem.vue` 行内响应
7. UI：`ViewerPanel.vue` + `AgentPanel.vue` Inspector 模式
8. UI：`style.css` 新设计令牌
9. UI：`App.vue` 集成
10. 构建前端 + 测试

---

## 五、不改动的部分

- `app/graph.py`、`app/nodes.py`、`app/agent.py` — 底层 Agent 不变
- `app/patch.py`、`app/domain.py` — 核心引擎不变
- `app/store.py` — 数据层不变
- `ScreenplayEditor.vue`、`ScreenplayView.vue` — 编辑器核心不变
- `PatchDrawer.vue` — 审阅抽屉不变
