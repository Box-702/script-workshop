<script setup>
// =====================================================================
// ScreenplayEditor.vue —— 内置剧本编辑器（所见即所得改剧本原文）
//
// 编辑字段：场景标题/地点/时间/目的/冲突，以及每个节拍（动作/对白/提示）。
// 支持：改内容、删除节拍、在各场景末尾新增动作或对白。
// 保存：对比编辑前后结构，生成字段级 patch 操作，POST /api/versions/{id}/apply
//       生成一个「手动编辑」新版本（复用 patch 引擎，数据仍是结构化剧本）。
// 这样用户改的是剧本正文，而不是 patch JSON。
// =====================================================================

import { ref, computed } from 'vue'
import { store, applyEdits, notify } from '../stores/app'

const props = defineProps({
  script: { type: Object, required: true },
  versionId: { type: String, required: true },
})
const emit = defineEmits(['saved', 'cancel'])

// 本地可编辑副本（深拷贝）
const local = ref(JSON.parse(JSON.stringify(props.script)))
const saving = ref(false)
const editErr = ref('')

const locs = computed(() => (local.value.locations || []).reduce((m, l) => ((m[l.id] = l.name), m), {}))
const chars = computed(() => (local.value.characters || []).reduce((m, c) => ((m[c.id] = c.name), m), {}))

function nextBeatId(beats) {
  let mx = 0
  for (const b of beats) { const m = /^beat_(\d+)$/.exec(b.id || ''); if (m) mx = Math.max(mx, parseInt(m[1], 10)) }
  let cand
  do { cand = `beat_${String(mx + 1).padStart(3, '0')}`; mx++ } while (beats.some((b) => b.id === cand))
  return cand
}

function addBeat(scene, kind) {
  const beats = scene.beats || (scene.beats = [])
  if (kind === 'dialogue') {
    beats.push({ id: nextBeatId(beats), type: 'dialogue', speaker: (scene.characters || [])[0] || '', line: '', emotion: '' })
  } else if (kind === 'cue') {
    beats.push({ id: nextBeatId(beats), type: 'cue', text: '' })
  } else {
    beats.push({ id: nextBeatId(beats), type: 'action', text: '' })
  }
}
function removeBeat(scene, i) { (scene.beats || []).splice(i, 1) }

function buildOps(orig, edited) {
  const ops = []
  const os = orig?.scenes || []
  const es = edited?.scenes || []
  const n = Math.max(os.length, es.length)
  for (let i = 0; i < n; i++) {
    const o = os[i], e = es[i]
    if (!e) continue
    for (const f of ['title', 'purpose', 'conflict', 'entry_state', 'exit_state', 'time', 'location_id']) {
      const ov = o?.[f] ?? null, ev = e[f] ?? null
      if (ov !== ev) ops.push({ op: 'set', path: `/script/scenes/${i}/${f}`, value: ev })
    }
    const ob = (o?.beats || []), eb = (e?.beats || [])
    const obById = {}; for (const b of ob) obById[b.id] = b
    const ebIds = new Set(eb.map((b) => b.id))
    for (const b of eb) {
      const bv = b
      if (!obById[b.id]) ops.push({ op: 'add', path: `/script/scenes/${i}/beats/${b.id}`, value: bv })
      else if (JSON.stringify(obById[b.id]) !== JSON.stringify(bv)) ops.push({ op: 'set', path: `/script/scenes/${i}/beats/${b.id}`, value: bv })
    }
    for (const b of ob) if (!ebIds.has(b.id)) ops.push({ op: 'remove', path: `/script/scenes/${i}/beats/${b.id}` })
  }
  return ops
}

async function save() {
  if (saving.value) return
  editErr.value = ''
  // 清掉空的新增对白/动作（没有内容的节拍不保存）
  for (const sc of local.value.scenes || []) {
    sc.beats = (sc.beats || []).filter((b) => {
      if (b.type === 'dialogue') return (b.line || '').trim()
      return (b.text || '').trim()
    })
  }
  const ops = buildOps(props.script, local.value)
  if (!ops.length) { editErr.value = '没有改动'; return }
  saving.value = true
  try {
    await applyEdits(props.versionId, ops)
    notify('已保存为新版本', 'ok')
    emit('saved')
  } catch (e) { editErr.value = e.message } finally { saving.value = false }
}

function cancel() { emit('cancel') }
</script>

<template>
  <div class="ed">
    <!-- 顶部工具条 -->
    <div class="ed-bar">
      <span class="ed-title">编辑剧本</span>
      <span class="ed-hint">改台词/动作后点「保存为新版本」</span>
      <span class="spacer"></span>
      <button class="ghost small" :disabled="saving" @click="cancel">取消</button>
      <button class="small" :disabled="saving" @click="save">{{ saving ? '保存中…' : '保存为新版本' }}</button>
    </div>
    <div v-if="editErr" class="ed-err">⚠️ {{ editErr }}</div>

    <div class="ed-body">
      <div
        v-for="(sc, si) in local.scenes || []"
        :key="sc.id || si"
        class="ed-scene"
        :class="{ empty: !sc.beats || !sc.beats.length }"
      >
        <!-- 场景字段 -->
        <div class="ed-head">
          <span class="ed-num">{{ String(si + 1).padStart(2, '0') }}</span>
          <input class="inp strong" v-model="sc.title" placeholder="场景标题" />
          <select v-model="sc.location_id" class="inp loc">
            <option value="" disabled>地点</option>
            <option v-for="(name, lid) in locs" :key="lid" :value="lid">{{ name }}</option>
          </select>
          <input class="inp time" v-model="sc.time" placeholder="时间" />
        </div>
        <div class="ed-fields">
          <input class="inp" v-model="sc.purpose" placeholder="场景目的（动作）" />
          <input class="inp" v-model="sc.conflict" placeholder="场景冲突" />
        </div>

        <!-- 节拍 -->
        <div class="ed-beats">
          <div v-for="(b, bi) in sc.beats || []" :key="b.id" class="ed-beat" :class="'bt-' + b.type">
            <span class="bt-tag">{{ b.type === 'dialogue' ? '对白' : b.type === 'cue' ? '提示' : '动作' }}</span>
            <template v-if="b.type === 'dialogue'">
              <select v-model="b.speaker" class="inp spk">
                <option value="" disabled>说话人</option>
                <option v-for="(name, cid) in chars" :key="cid" :value="cid">{{ name }}</option>
              </select>
              <input class="inp" v-model="b.line" placeholder="台词" />
              <input class="inp emo" v-model="b.emotion" placeholder="(语气)" />
            </template>
            <input v-else class="inp" v-model="b.text" :placeholder="b.type === 'cue' ? '（舞台提示）' : '动作描写'" />
            <button class="mini del" title="删除该节拍" @click="removeBeat(sc, bi)">✕</button>
          </div>
          <div v-if="!sc.beats || !sc.beats.length" class="ed-beats-empty">本场景还没有节拍，点击下方添加。</div>
          <div class="ed-add">
            <button class="mini" @click="addBeat(sc, 'action')">＋ 动作</button>
            <button class="mini" @click="addBeat(sc, 'dialogue')">＋ 对白</button>
            <button class="mini" @click="addBeat(sc, 'cue')">＋ 提示</button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.ed { display: flex; flex-direction: column; min-height: 0; }
.ed-bar { display: flex; align-items: center; gap: 10px; padding: 8px 16px; border-bottom: 1px solid var(--line); }
.ed-title { font-weight: 700; font-size: 13px; }
.ed-hint { font-size: 11px; color: var(--dim); }
.spacer { flex: 1; }
.ed-err { color: var(--bad); font-size: 12px; padding: 8px 16px 0; }
.ed-body { flex: 1; overflow-y: auto; padding: 14px 16px 20px; }

.ed-scene { border: 1px solid var(--line); border-radius: 12px; background: var(--code-bg); padding: 12px 14px; margin-bottom: 14px; }
.ed-scene.empty { border-style: dashed; }
.ed-head { display: flex; align-items: center; gap: 8px; }
.ed-num { font-size: 11px; color: var(--dim); font-family: var(--mono); font-variant-numeric: tabular-nums; }
.inp { background: var(--panel2); border: 1px solid var(--line); border-radius: 8px; color: var(--ink);
  padding: 5px 8px; font-size: 12.5px; font-family: inherit; min-width: 0; }
.inp:focus { outline: none; border-color: color-mix(in oklch, var(--accent) 40%, var(--line)); }
.inp.strong { flex: 1; font-weight: 600; font-size: 13px; }
.inp.loc { width: 130px; }
.inp.time { width: 90px; }
.ed-fields { display: flex; gap: 8px; margin-top: 8px; }
.ed-fields .inp { flex: 1; }

.ed-beats { margin-top: 10px; display: flex; flex-direction: column; gap: 6px; }
.ed-beat { display: flex; align-items: center; gap: 6px; }
.bt-tag { font-size: 10.5px; color: var(--muted); border: 1px solid var(--line); border-radius: 6px; padding: 0 6px; flex: none; }
.bt-dialogue .bt-tag { color: var(--dlg); border-color: color-mix(in oklch, var(--dlg) 45%, var(--line)); }
.bt-action .bt-tag { color: var(--act); border-color: color-mix(in oklch, var(--act) 40%, var(--line)); }
.ed-beat .inp { flex: 1; }
.ed-beat .spk { width: 120px; }
.ed-beat .emo { width: 90px; }
.mini { background: transparent; border: 1px solid var(--line); color: var(--muted); border-radius: 6px;
  padding: 0 7px; font-size: 11px; font-weight: 500; line-height: 1.6; cursor: pointer; flex: none; }
.mini:hover { color: var(--ink); border-color: var(--line-strong); }
.mini.del:hover { color: var(--bad); border-color: color-mix(in oklch, var(--bad) 55%, var(--line)); }
.ed-beats-empty { color: var(--dim); font-size: 12px; padding: 2px 2px; }
.ed-add { display: flex; gap: 6px; margin-top: 4px; }
.ed-add .mini { color: var(--cue); }
</style>
