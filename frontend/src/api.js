// =====================================================================
// api.js —— 后端接口封装
//
// 职责：
//   - 统一 JSON 请求（自动拼 /api 前缀、解析错误 detail）；
//   - FormData 文件上传（导入项目）；
//   - SSE 流式对话：逐帧解析 event/data 并回调给调用方。
// =====================================================================

const BASE = '/api'

/** 通用 JSON 请求。path 形如 '/projects'；失败时抛出带 detail 的 Error。 */
export async function api(path, method = 'GET', body) {
  const res = await fetch(BASE + path, {
    method,
    headers: body ? { 'Content-Type': 'application/json' } : undefined,
    body: body ? JSON.stringify(body) : undefined,
  })
  if (!res.ok) {
    let msg = res.statusText
    try { const j = await res.json(); msg = j.detail || JSON.stringify(j) } catch { /* 保留 statusText */ }
    throw new Error(msg)
  }
  return res.json()
}

/** 导入项目（新建剧本）：FormData 内含 title / adaptation_type / file 或 raw_text。 */
export async function importProject(formData) {
  const res = await fetch(BASE + '/projects/import', { method: 'POST', body: formData })
  if (!res.ok) {
    const j = await res.json().catch(() => ({}))
    throw new Error(j.detail || res.statusText)
  }
  return res.json()
}

/**
 * SSE 流式对话。
 * @param {object} body  { project_id, conversation_id, message, meta }
 * @param {(ev: {event: string, data: any}) => void} onFrame 每解析出一帧回调一次
 */
export async function streamChat(body, onFrame) {
  const res = await fetch(BASE + '/chat/stream', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify(body),
  })
  if (!res.ok || !res.body) {
    const j = await res.json().catch(() => ({}))
    throw new Error(j.detail || res.statusText)
  }
  // 按字节读取，遇到空行（\n\n）切分成一帧再解析
  const reader = res.body.getReader()
  const decoder = new TextDecoder()
  let buf = ''
  while (true) {
    const { done, value } = await reader.read()
    if (done) break
    buf += decoder.decode(value, { stream: true })
    let idx
    while ((idx = buf.indexOf('\n\n')) >= 0) {
      const frame = buf.slice(0, idx)
      buf = buf.slice(idx + 2)
      const ev = parseFrame(frame)
      if (ev) onFrame(ev)
    }
  }
}

/** 解析单帧 SSE 文本：`event: xxx` + `data: {...}`，解析失败返回 null。 */
function parseFrame(frame) {
  let event = 'message'
  let data = ''
  for (const line of frame.split('\n')) {
    if (line.startsWith('event:')) event = line.slice(6).trim()
    else if (line.startsWith('data:')) data += line.slice(5).trim()
  }
  if (!data) return null
  try { return { event, data: JSON.parse(data) } } catch { return null }
}
