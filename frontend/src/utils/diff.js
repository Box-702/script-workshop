// =====================================================================
// diff.js —— 剧本版本对比算法
//
// keyedDiff(a, b)：比较两个版本 JSON 的顶层键。
//   - 值是数组（scenes / characters / locations）时，按对象 id 配对，
//     产出 新增(+) / 删除(-) / 修改(~) 三类差异；
//   - 其它值直接 JSON 串比较。
// 返回 [{ t: '+'|'-'|'~', p: '路径', before, after }]
// =====================================================================

export function keyedDiff(a, b) {
  const out = []
  const keys = new Set([...Object.keys(a || {}), ...Object.keys(b || {})])
  for (const k of keys) {
    const va = a?.[k]
    const vb = b?.[k]

    if (Array.isArray(va) && Array.isArray(vb)) {
      // 按 id 建索引，做集合差 + 逐项比对
      const ma = new Map(va.filter((x) => x && x.id).map((x) => [x.id, x]))
      const mb = new Map(vb.filter((x) => x && x.id).map((x) => [x.id, x]))
      for (const [id, item] of ma) if (!mb.has(id)) out.push({ t: '-', p: `${k}/${id}`, before: item })
      for (const [id, item] of mb) if (!ma.has(id)) out.push({ t: '+', p: `${k}/${id}`, after: item })
      for (const [id, item] of mb)
        if (ma.has(id) && JSON.stringify(ma.get(id)) !== JSON.stringify(item))
          out.push({ t: '~', p: `${k}/${id}`, before: ma.get(id), after: item })
    } else if (JSON.stringify(va) !== JSON.stringify(vb)) {
      // 非数组：一侧缺失记增/删，两侧都有记修改
      out.push({ t: va === undefined ? '+' : vb === undefined ? '-' : '~', p: k, before: va, after: vb })
    }
  }
  return out
}
