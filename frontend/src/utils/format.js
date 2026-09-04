// =====================================================================
// format.js —— 展示格式化工具
//
// 职责：把 patch 操作 / 版本差异里的字段值转成人类可读的单行文本。
// =====================================================================

/** patch 字段名 -> 中文标签（scene_id、character_id 等原样显示）。 */
export const FIELD_LABEL = {
  title: '标题', purpose: '目的', conflict: '冲突',
  entry_state: '入场状态', exit_state: '离场状态', time: '时间', location_id: '地点',
  action: '动作', dialogue: '对白', beats: '节拍',
  'adaptation_notes/reason': '改编说明', 'adaptation_notes/fidelity': '忠实度',
}

/** 评审维度 -> 中文名（对应后端 app/review.py 的维度）。 */
export const DIM_LABEL = {
  fidelity: '忠实度', consistency: '一致性', conflict: '冲突', style: '风格', structure: '结构',
}

/** 评审问题类别 -> 中文名。 */
export const ISSUE_CAT_LABEL = {
  consistency: '一致性', fidelity: '忠实度', structure: '结构', style: '风格', conflict: '冲突',
}

/** 把任意字段值压平成可读字符串（数组用 " / " 或 " ⏎ " 连接）。 */
export function fmtVal(v) {
  if (v === null || v === undefined) return '∅'
  if (typeof v === 'string') return v
  if (Array.isArray(v)) {
    if (!v.length) return '[]'
    if (typeof v[0] === 'string') return v.join(' / ')
    // 数组元素是对象：优先显示 对白/动作 的关键字段
    return v
      .map((x) => {
        if (typeof x === 'string') return x
        const o = x || {}
        return o.speaker ? `${o.speaker}：${o.line}`
          : o.type === 'action' ? '动作: ' + o.text
          : o.text || o.line || JSON.stringify(o)
      })
      .join(' ⏎ ')
  }
  if (typeof v === 'object') {
    // 对象：按固定键序拼出 k=v 对；一个都没有就退回 JSON
    const keys = ['title', 'purpose', 'conflict', 'entry_state', 'exit_state', 'text', 'line', 'speaker', 'type', 'reason', 'fidelity']
    return keys.filter((k) => v[k] !== undefined).map((k) => `${k}=${v[k]}`).join(' ') || JSON.stringify(v)
  }
  return String(v)
}

/** 把 patch 操作按场景分组，返回 [{ key, items: [{ op, idx }] }]，idx 为原数组下标。 */
export function groupPatch(patch) {
  const groups = []
  const byKey = new Map()
  for (let idx = 0; idx < (patch || []).length; idx++) {
    const op = patch[idx]
    const key = op.scene_title || op.scene_id || '（未分组）'
    if (!byKey.has(key)) {
      const g = { key, items: [] }
      byKey.set(key, g)
      groups.push(g)
    }
    byKey.get(key).items.push({ op, idx })
  }
  return groups
}

/** patch 操作统计：{ add, remove, modify, total }。 */
export function patchStats(patch) {
  const s = { add: 0, remove: 0, modify: 0 }
  for (const op of patch || []) {
    if (op.op === 'add') s.add++
    else if (op.op === 'remove') s.remove++
    else s.modify++
  }
  return { ...s, total: s.add + s.remove + s.modify }
}
