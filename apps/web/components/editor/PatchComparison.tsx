import type { AgentPatchOperation, ScriptBeat } from "@/lib/types";
import { PatchValue } from "./PatchValue";

const BEAT_FIELDS = ["type", "speaker", "text", "line", "emotion", "subtext"] as const;

type BeatField = (typeof BEAT_FIELDS)[number];

const FIELD_LABELS: Record<BeatField, string> = {
  type: "类型",
  speaker: "说话人",
  text: "内容",
  line: "台词",
  emotion: "情绪",
  subtext: "潜台词",
};

const TYPE_LABELS: Record<ScriptBeat["type"], string> = {
  action: "动作",
  dialogue: "对白",
  cue: "提示",
};

export function PatchComparison({
  item,
  characterNames,
}: {
  item: AgentPatchOperation;
  characterNames: Record<string, string>;
}) {
  const beforeBeat = asScriptBeat(item.before);
  const afterBeat = asScriptBeat(item.after ?? item.value);

  if (item.field === "beats" && (beforeBeat || afterBeat)) {
    return (
      <BeatPatchComparison
        before={beforeBeat}
        after={afterBeat}
        op={item.op}
        characterNames={characterNames}
      />
    );
  }

  return (
    <>
      <PatchValue label="修改前" value={item.before} characterNames={characterNames} />
      <PatchValue label="修改后" value={item.after ?? item.value} characterNames={characterNames} />
    </>
  );
}

function BeatPatchComparison({
  before,
  after,
  op,
  characterNames,
}: {
  before: ScriptBeat | null;
  after: ScriptBeat | null;
  op?: string;
  characterNames: Record<string, string>;
}) {
  const rows = getVisibleBeatFields(before, after);
  const changedCount = rows.filter((field) => beatFieldChanged(before, after, field)).length;

  return (
    <div className="mt-2 overflow-hidden rounded-md border surface-line bg-ink-950/50 text-[13px]">
      <div className="flex items-center justify-between gap-2 border-b surface-line bg-ink-900/60 px-2.5 py-2">
        <span className="font-medium text-ink-200">字段对比</span>
        <span className="shrink-0 text-[11px] text-ink-500">
          {formatPatchOp(op, changedCount)}
        </span>
      </div>
      <div className="divide-y divide-ink-700/40">
        {rows.map((field) => {
          const changed = beatFieldChanged(before, after, field);
          return (
            <div
              key={field}
              className={`grid gap-2 px-2.5 py-2 ${
                changed ? "bg-accent-500/10" : ""
              }`}
            >
              <div className="flex items-center justify-between gap-2">
                <span className="text-xs font-medium text-ink-500">{FIELD_LABELS[field]}</span>
                {changed && (
                  <span className="rounded border border-accent-500/30 bg-accent-500/10 px-1.5 py-0.5 text-[10px] text-accent-300">
                    已改动
                  </span>
                )}
              </div>
              <div className="grid gap-2 sm:grid-cols-2">
                <BeatFieldValue
                  label="修改前"
                  value={formatBeatField(before, field, characterNames)}
                  muted={!before}
                  changed={changed}
                />
                <BeatFieldValue
                  label="修改后"
                  value={formatBeatField(after, field, characterNames)}
                  muted={!after}
                  changed={changed}
                />
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}

function BeatFieldValue({
  label,
  value,
  muted,
  changed,
}: {
  label: string;
  value: string;
  muted: boolean;
  changed: boolean;
}) {
  return (
    <div
      className={`min-h-12 rounded border px-2 py-1.5 ${
        changed ? "border-accent-500/30 bg-accent-500/10" : "surface-line bg-ink-900/40"
      }`}
    >
      <div className="mb-1 text-[10px] text-ink-500">{label}</div>
      <div className={`whitespace-pre-wrap break-words leading-5 ${muted ? "text-ink-600" : "text-ink-200"}`}>
        {value}
      </div>
    </div>
  );
}

function getVisibleBeatFields(before: ScriptBeat | null, after: ScriptBeat | null) {
  return BEAT_FIELDS.filter((field) => {
    if (field === "type") return true;
    if (field === "speaker") return before?.type === "dialogue" || after?.type === "dialogue";
    return hasBeatFieldValue(before, field) || hasBeatFieldValue(after, field);
  });
}

function beatFieldChanged(before: ScriptBeat | null, after: ScriptBeat | null, field: BeatField) {
  return formatRawBeatField(before, field) !== formatRawBeatField(after, field);
}

function hasBeatFieldValue(beat: ScriptBeat | null, field: BeatField) {
  return formatRawBeatField(beat, field) !== "";
}

function formatBeatField(
  beat: ScriptBeat | null,
  field: BeatField,
  characterNames: Record<string, string>,
) {
  if (!beat) return "无";
  if (field === "type") return TYPE_LABELS[beat.type] ?? beat.type;
  if (field === "speaker") {
    const speaker = beat.speaker || "";
    return speaker ? characterNames[speaker] || speaker : "空";
  }
  return formatRawBeatField(beat, field) || "空";
}

function formatRawBeatField(beat: ScriptBeat | null, field: BeatField) {
  if (!beat) return "";
  const value = beat[field];
  return typeof value === "string" ? value.trim() : "";
}

function formatPatchOp(op: string | undefined, changedCount: number) {
  if (op === "add") return "新增节拍";
  if (op === "remove") return "删除节拍";
  return changedCount > 0 ? `${changedCount} 个字段变化` : "内容一致";
}

function asScriptBeat(value: unknown): ScriptBeat | null {
  if (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    ((value as ScriptBeat).type === "action" ||
      (value as ScriptBeat).type === "dialogue" ||
      (value as ScriptBeat).type === "cue")
  ) {
    return value as ScriptBeat;
  }
  return null;
}
