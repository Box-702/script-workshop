// =====================================================================
// markdown.js —— 内联轻量 Markdown 渲染（无第三方依赖，离线可用）
//
// 支持：标题、粗体/斜体/行内代码、链接、围栏代码块、表格、
//       引用块、无序/有序列表、分割线、段落。
// 所有文本先经过 HTML 转义，避免 XSS。
// =====================================================================

/** HTML 转义，防止注入。 */
export const esc = (s) =>
  String(s ?? '').replace(/[&<>"']/g, (c) =>
    ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' }[c]))

/** 行内元素：`code`、**粗体**、*斜体*、[链接](url)。 */
function inlineMd(s) {
  return esc(s)
    .replace(/`([^`]+)`/g, '<code>$1</code>')
    .replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>')
    .replace(/(^|[^*])\*([^*\n]+)\*/g, '$1<em>$2</em>')
    .replace(/\[([^\]]+)\]\(([^)\s]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>')
}

/** 块级解析主入口：逐行扫描，按前缀分派到对应的块类型。 */
export function mdToHtml(src) {
  const lines = String(src ?? '').replace(/\r\n/g, '\n').split('\n')
  let html = ''
  let i = 0
  let inCode = false
  let codeBuf = []
  while (i < lines.length) {
    const line = lines[i]

    // 围栏代码块 ``` 开 / 关
    if (/^```/.test(line.trim())) {
      if (!inCode) { inCode = true; codeBuf = [] }
      else { inCode = false; html += '<pre><code>' + esc(codeBuf.join('\n')) + '</code></pre>' }
      i++; continue
    }
    if (inCode) { codeBuf.push(line); i++; continue }

    // 表格：当前行以 | 开头，下一行是分隔行 |---|---|
    if (/^\|/.test(line.trim()) && i + 1 < lines.length && /^\|[\s:|-]+\|$/.test(lines[i + 1].trim()) && lines[i + 1].includes('-')) {
      const head = line.split('|').slice(1, -1).map((s) => s.trim())
      i += 2
      const rows = []
      while (i < lines.length && /^\|/.test(lines[i].trim())) {
        rows.push(lines[i].split('|').slice(1, -1).map((s) => s.trim()))
        i++
      }
      html += '<table><thead><tr>' + head.map((h) => `<th>${inlineMd(h)}</th>`).join('') + '</tr></thead><tbody>'
        + rows.map((r) => '<tr>' + r.map((c) => `<td>${inlineMd(c)}</td>`).join('') + '</tr>').join('') + '</tbody></table>'
      continue
    }

    // 标题 # ~ ######
    const h = line.match(/^(#{1,6})\s+(.*)$/)
    if (h) { const n = h[1].length; html += `<h${n}>${inlineMd(h[2])}</h${n}>`; i++; continue }

    // 分割线 --- / *** / ___
    if (/^\s*(---|\*\*\*|___)\s*$/.test(line)) { html += '<hr/>'; i++; continue }

    // 引用块：连续的 > 行合并
    if (/^>\s?/.test(line)) {
      const buf = []
      while (i < lines.length && /^>\s?/.test(lines[i])) { buf.push(lines[i].replace(/^>\s?/, '')); i++ }
      html += '<blockquote>' + buf.map(inlineMd).join('<br/>') + '</blockquote>'
      continue
    }

    // 无序列表 - / * / +
    if (/^\s*[-*+]\s+/.test(line)) {
      const buf = []
      while (i < lines.length && /^\s*[-*+]\s+/.test(lines[i])) { buf.push(lines[i].replace(/^\s*[-*+]\s+/, '')); i++ }
      html += '<ul>' + buf.map((l) => `<li>${inlineMd(l)}</li>`).join('') + '</ul>'
      continue
    }

    // 有序列表 1. / 1)
    if (/^\s*\d+[.)]\s+/.test(line)) {
      const buf = []
      while (i < lines.length && /^\s*\d+[.)]\s+/.test(lines[i])) { buf.push(lines[i].replace(/^\s*\d+[.)]\s+/, '')); i++ }
      html += '<ol>' + buf.map((l) => `<li>${inlineMd(l)}</li>`).join('') + '</ol>'
      continue
    }

    // 空行跳过
    if (!line.trim()) { i++; continue }

    // 普通段落：把后续不匹配任何块前缀的行并入，行内用 <br/> 换行
    const buf = [line]; i++
    while (i < lines.length && lines[i].trim() && !/^(#{1,6}\s|```|>|[-*+]\s|\d+[.)]\s|\||---)/.test(lines[i].trim())) {
      buf.push(lines[i]); i++
    }
    html += '<p>' + buf.map(inlineMd).join('<br/>') + '</p>'
  }
  // 代码块未闭合时兜底输出
  if (inCode) html += '<pre><code>' + esc(codeBuf.join('\n')) + '</code></pre>'
  return html
}
