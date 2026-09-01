<script setup>
// =====================================================================
// ScreenplayView.vue —— 把结构化剧本渲染成「像一部真的剧本」的排版
//
// 与导出（.txt/.md/.docx）共享同一套剧本语义，但用 CSS 呈现：
//   - 场景标题：INT./EXT. 地点 - 时间（大写、加粗、左对齐）
//   - 动作行：左对齐
//   - 角色名：居中大写
//   - 提示 (emotion)：居中对白之下，斜体
//   - 对白：左缩进
//   - 场景之间：转场（CUT TO:）右对齐
// 用预计算的 structure 驱动，模板不做复杂逻辑。
// =====================================================================

import { computed } from 'vue'

const props = defineProps({
  script: { type: Object, required: true },
})

const INT_KEYS = ['内景', '室内', '屋内', '房间里', 'INT', 'INTERIOR']
const EXT_KEYS = ['外景', '室外', '户外', '屋外', '街头', '路上', 'EXT', 'EXTERIOR']

function upper(text) {
  return String(text || '').replace(/[a-z]/g, (c) => c.toUpperCase())
}

function intExt(scene, locName) {
  const hay = `${scene?.title || ''} ${scene?.entry_state || ''} ${scene?.exit_state || ''} ${locName || ''}`.toLowerCase()
  if (EXT_KEYS.some((k) => hay.includes(k.toLowerCase()))) return 'EXT.'
  if (INT_KEYS.some((k) => hay.includes(k.toLowerCase()))) return 'INT.'
  return 'INT.'
}

const ROLE_ZH = { protagonist: '主角', antagonist: '反派', supporting: '配角', mentor: '导师', foil: '对照', other: '其他' }

const structure = computed(() => {
  const s = props.script || {}
  const locs = (s.locations || []).reduce((m, l) => ((m[l.id] = l.name), m), {})
  const chars = (s.characters || []).reduce((m, c) => ((m[c.id] = c.name), m), {})

  const scenes = (s.scenes || []).map((sc) => {
    const locName = locs[sc.location_id] || sc.location_id || '场景'
    const heading = `${intExt(sc, locName)} ${upper(locName)}` + (sc.time ? ` - ${sc.time}` : '')
    let beats = (sc.beats || []).map((b) => {
      if (b.type === 'dialogue') {
        return { kind: 'dialogue', speaker: upper(chars[b.speaker] || b.speaker || ''), emotion: b.emotion || '', line: b.line || '' }
      }
      if (b.type === 'cue') {
        return { kind: 'cue', text: b.text || '' }
      }
      return { kind: 'action', text: b.text || '' }
    })
    // 兼容老版本：只有 action / dialogue 字段、没有 beats 的场景，回退用兼容字段渲染。
    if (!beats.length) {
      beats = []
      for (const a of sc.action || []) if (a) beats.push({ kind: 'action', text: a })
      for (const d of sc.dialogue || []) {
        const spk = typeof d === 'string' ? d : (d.speaker || '')
        beats.push({ kind: 'dialogue', speaker: upper(chars[spk] || spk || ''), emotion: d?.emotion || '', line: typeof d === 'string' ? d : (d.line || '') })
      }
    }
    return {
      id: sc.id,
      heading,
      beats,
      purpose: sc.purpose || '',
      conflict: sc.conflict || '',
    }
  })

  const characters = (s.characters || []).map((c) => ({
    name: c.name,
    role: ROLE_ZH[c.role] || '',
  }))

  return {
    title: s.title || '',
    logline: s.logline || '',
    characters,
    scenes,
  }
})
</script>

<template>
  <div class="sp">
    <!-- 标题页 -->
    <div class="sp-title">{{ structure.title }}</div>
    <div v-if="structure.logline" class="sp-logline">{{ structure.logline }}</div>

    <!-- 角色表 -->
    <div v-if="structure.characters.length" class="sp-chars">
      <div class="sp-chars-head">人物</div>
      <div v-for="(c, i) in structure.characters" :key="i" class="sp-char">
        {{ c.name }}<span v-if="c.role" class="sp-char-role">（{{ c.role }}）</span>
      </div>
    </div>

    <!-- 场景 -->
    <template v-for="(sc, si) in structure.scenes" :key="sc.id">
      <div class="sp-scene">
        <div class="sp-heading">{{ sc.heading }}</div>
        <div v-if="sc.purpose" class="sp-action">{{ sc.purpose }}</div>
        <div v-if="sc.conflict" class="sp-action">{{ sc.conflict }}</div>

        <template v-for="(b, bi) in sc.beats" :key="bi">
          <!-- 对白 -->
          <template v-if="b.kind === 'dialogue'">
            <div class="sp-speaker">{{ b.speaker }}</div>
            <div v-if="b.emotion" class="sp-paren">{{ b.emotion }}</div>
            <div class="sp-dialogue">{{ b.line }}</div>
          </template>
          <!-- 提示 / 舞台指令 -->
          <div v-else-if="b.kind === 'cue'" class="sp-paren">{{ b.text }}</div>
          <!-- 动作 -->
          <div v-else class="sp-action">{{ b.text }}</div>
        </template>

        <!-- 场景间转场 -->
        <div v-if="si < structure.scenes.length - 1" class="sp-transition">CUT TO:</div>
      </div>
    </template>
  </div>
</template>

<style scoped>
/* 剧本观感：等宽正文、舒适行高、接近标准剧本的边距 */
.sp { color: oklch(0.88 0.005 75); line-height: 1.7; font-size: 14px; }
.sp-title { text-align: center; font-weight: 700; font-size: 16px; letter-spacing: 0.06em; margin: 6px 0 4px; }
.sp-logline { text-align: center; color: var(--muted); font-size: 12.5px; margin-bottom: 18px; font-style: italic; }

/* 人物表 */
.sp-chars { text-align: center; margin: 8px 0 24px; }
.sp-chars-head { font-weight: 700; margin-bottom: 6px; }
.sp-char { font-size: 12.5px; margin: 2px 0; }
.sp-char-role { color: var(--muted); }

/* 场景 */
.sp-scene { margin-bottom: 26px; }
.sp-heading {
  font-weight: 700; color: var(--ink); letter-spacing: 0.02em;
  border-left: 3px solid var(--dlg); padding-left: 10px; margin-bottom: 12px;
}
.sp-action { margin: 8px 0; max-width: 60ch; }

/* 对白：角色名居中，提示斜体，台词缩进 */
.sp-speaker { text-align: center; font-weight: 700; letter-spacing: 0.04em; margin-top: 12px; }
.sp-paren { text-align: center; color: var(--muted); font-style: italic; font-size: 12.5px; margin: 2px 0; }
.sp-dialogue { margin: 4px 0 2px; padding-left: 12%; max-width: 46ch; }

/* 转场：右对齐 */
.sp-transition { text-align: right; color: var(--muted); font-size: 12.5px; letter-spacing: 0.05em; margin-top: 18px; }
</style>
