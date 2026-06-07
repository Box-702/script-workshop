import type { DialogueLine, ScriptBeat } from "@/lib/types";

export function PatchValue({
  label,
  value,
  characterNames,
}: {
  label: string;
  value: unknown;
  characterNames: Record<string, string>;
}) {
  return (
    <div className="mt-2">
      <div className="mb-1 text-xs text-ink-500">{label}</div>
      <div className="max-h-36 overflow-auto whitespace-pre-wrap break-words rounded-md bg-ink-950/70 px-2.5 py-2 text-[13px] leading-5 text-ink-200">
        {formatPatchValue(value, characterNames)}
      </div>
    </div>
  );
}

function formatPatchValue(value: unknown, characterNames: Record<string, string> = {}) {
  if (value === null || typeof value === "undefined" || value === "") return "空";
  if (typeof value === "string") return value;
  if (isScriptBeatPatchValue(value)) return formatBeat(value, characterNames);
  if (Array.isArray(value)) {
    if (value.length === 0) return "空列表";
    if (value.every((item) => typeof item === "string")) {
      return value.map((item, index) => `${index + 1}. ${item}`).join("\n");
    }
    if (value.every(isScriptBeatPatchValue)) {
      return value
        .map((item, index) => `${index + 1}. ${formatBeat(item, characterNames)}`)
        .join("\n");
    }
    if (value.every(isDialoguePatchValue)) {
      return value
        .map((item) => {
          const emotion = item.emotion ? `（${item.emotion}）` : "";
          const subtext = item.subtext ? `\n  潜台词：${item.subtext}` : "";
          return `${formatSpeakerName(item.speaker, characterNames)}${emotion}：${item.line}${subtext}`;
        })
        .join("\n");
    }
  }
  return JSON.stringify(value, null, 2);
}

function formatSpeakerName(speakerId: string, characterNames: Record<string, string>) {
  return characterNames[speakerId] || speakerId;
}

function formatBeat(beat: ScriptBeat, characterNames: Record<string, string>) {
  if (beat.type === "dialogue") {
    const speaker = formatSpeakerName(beat.speaker || "", characterNames);
    const emotion = beat.emotion ? `（${beat.emotion}）` : "";
    const subtext = beat.subtext ? `\n  潜台词：${beat.subtext}` : "";
    return `${speaker}${emotion}：${beat.line || ""}${subtext}`;
  }
  const prefix = beat.type === "cue" ? "【提示】" : "【动作】";
  return `${prefix}${beat.text || ""}`;
}

function isDialoguePatchValue(value: unknown): value is DialogueLine {
  return (
    typeof value === "object" &&
    value !== null &&
    "speaker" in value &&
    "line" in value &&
    typeof (value as DialogueLine).speaker === "string" &&
    typeof (value as DialogueLine).line === "string"
  );
}

function isScriptBeatPatchValue(value: unknown): value is ScriptBeat {
  return (
    typeof value === "object" &&
    value !== null &&
    "type" in value &&
    ((value as ScriptBeat).type === "action" ||
      (value as ScriptBeat).type === "dialogue" ||
      (value as ScriptBeat).type === "cue")
  );
}
