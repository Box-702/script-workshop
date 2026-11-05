# DESIGN.md

## Theme
暗色，唯一主题。**「安静工作台」**：这是一个工具，不是 AI 演示页。
中性暗色表面、清晰的密度层级、克制的状态色——界面退后，创作内容是主角。

已明确移除的旧元素（v3「夜幕片场」遗留）：渐变字标、光晕/流光/浮动等装饰动画、
楷书 UI 字体、胶囊型分类标签（改下拉或扁平小标签）、大圆角（14px+）。

## Color(OKLCH)
中性近黑 + 稿纸米白主按钮 + 黄铜点缀 + 低饱和语义色：
- 表面（hue 80 极微染，几乎不可感）：--bg ≈L0.155 < --panel ≈L0.19 < --panel2 ≈L0.23，
  1px --line 分层，不用投影表达层级
- 文字：--ink 暖白主 / --muted 次 / --dim 弱
- 主操作：**稿纸米白按钮**（--accent ≈L0.91 + --on-accent 近黑）——全站唯一的大面积亮色
- 品牌黄铜：--gold ≈oklch(0.74 0.07 85)。只用于焦点环、选中指示、等待态；
  不做渐变、不做发光、不参与正文层级
- 语义（低饱和，深底可读）：--ok 绿（成功/对白）· --warn 琥珀（警告/修改）· --bad 红（危险/删除）
  · --cyan 蓝灰（进行中）
- diff 行底色沿用 v3：--diff-add-bg / --diff-del-bg
- 悬停/按压用 color-mix 从基色派生，不单设色值

## Typography
系统无衬线字体栈（-apple-system / Segoe UI / PingFang SC / Microsoft YaHei）。
正文 14px，中文阅读行高 1.7；数字 tabular-nums；技术字符串（id、版本号、路径）用等宽（.mono）。
字重只用两档：400 正文 / 500-600 标题强调，不用 700+。

## Layout
三栏结构：项目树 | 弹性对话流（内容列 ≤ 900px）| Inspector 面板，均可拖拽调宽。
4px 间距基准；面板内边距 12/16。
≤1023px 左右面板抽屉化（fixed + 遮罩），任何视口不出现横向滚动。

## Elevation
底色亮一层表达层级；浮层（下拉菜单、弹窗、回到最新）允许极轻投影（--shadow-2/3）。
圆角小：控件 6px、卡片/弹窗 8-10px，无 999px 胶囊（圆点除外）。

## Controls
- **分类选择一律用下拉（select），不用一排胶囊**：画风、画幅、清晰度、性别、音色等；
  自绘箭头统一外观，option 深底
- 状态标记（版本、校验、性别等）：扁平小标签（radius 3px、无描边、颜色写在文字上），
  不再用胶囊
- 按钮：primary（稿纸米白底黑字）/ ok（绿）/ danger（红描边）/ ghost（描边）；
  字重 500
- **基础层按钮 hover/active 用 `:where()` 零特异性**（`button:where(:hover)`）：
  只对没有自定义背景的裸按钮生效；任何组件自定义了背景即自动免疫米白悬停填充，
  否则卡片类按钮悬停会被染成米白、深底浅字不可读（已踩过此坑）
- 页签：seg-tabs 安静分段控件，选中 = panel2 底色，无内阴影

## Icons
- **全站唯一入口：`AppIcon.vue`**（name prop），禁止再写内联 SVG 或文本字符图标
  （＋ × ✕ ▶ ⚠ ⌕ ✎ 等已全部清除）
- 语言：16×16 视窗、1.5 描边、round cap/join、currentColor，尺寸 = 1em 跟随字号
- 品牌图形 `LogoMark.vue` v7：竖屏 + 斜向胶片带 + 灵感金点，**纯平两色**
  （v6 的 3D 挤出小尺寸糊成一团，已废弃）；variant: color / light / mono
- `FolderIcon.vue`：描边版文件夹（闭合/打开两态），供 FolderTree / WorkspaceModal

## Motion
120–180ms，ease-out。只表达状态：悬停、焦点、开关、流式、折叠。
无装饰动画（流光/浮动/弹跳已移除）；加载态 = 骨架屏 / 三点 / 旋转。
尊重 prefers-reduced-motion。弹窗不用 Vue Transition（后台标签页冻结会卡住关不掉），
入场用纯 CSS 动画，关闭与 v-if 同步瞬时移除。
