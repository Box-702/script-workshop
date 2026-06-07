import type { ValidationError } from "@/lib/types";

type ValidationAdvice = {
  location: string;
  title: string;
  suggestion: string;
};

const FIELD_LABELS: Record<string, string> = {
  action: "动作",
  adaptation: "改编设置",
  beat: "节拍",
  beats: "节拍",
  chapter_count: "来源章节数量",
  chapter_ids: "来源章节",
  chapter_refs: "来源章节",
  characters: "出场角色",
  conflict: "冲突",
  dialogue: "对白",
  emotion: "情绪",
  entry_state: "入场状态",
  exit_state: "离场状态",
  fidelity: "改编忠实度",
  id: "ID",
  language: "语言",
  line: "台词",
  locations: "地点",
  location_id: "地点",
  logline: "一句话梗概",
  motivation: "动机",
  name: "名称",
  personality: "性格",
  purpose: "场景目的",
  relationship: "关系",
  role: "角色类型",
  scenes: "场景",
  script: "剧本",
  source: "来源信息",
  speaker: "说话人",
  speech_style: "说话风格",
  text: "内容",
  themes: "主题",
  title: "标题",
  type: "类型",
  version: "版本号",
};

export function ValidationPanel({ busy, errors }: { busy: boolean; errors: ValidationError[] }) {
  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div className="label mb-0">校验</div>
        {!busy && (
          <span className={errors.length === 0 ? "shrink-0 text-xs state-success-text" : "shrink-0 text-xs state-danger-text"}>
            {errors.length === 0 ? "通过" : `${errors.length} 个问题`}
          </span>
        )}
      </div>

      {busy ? (
        <div className="text-sm text-ink-400">校验中...</div>
      ) : errors.length === 0 ? (
        <div className="rounded-md border surface-line surface-soft p-3 text-sm state-success-text">
          通过，没有发现结构问题。
        </div>
      ) : (
        <div className="space-y-3">
          <p className="text-xs leading-relaxed text-ink-400">
            自动修复能处理明显的引用错误，但下面这些需要你确认内容。按建议改完后再点校验或保存快照。
          </p>
          <ul className="space-y-2">
            {errors.map((error, index) => {
              const advice = getValidationAdvice(error);
              return (
                <li key={`${error.path}-${error.message}-${index}`} className="rounded-md border surface-line surface-soft p-2.5">
                  <div className="flex items-start justify-between gap-2">
                    <div className="min-w-0">
                      <div className="text-[11px] font-medium text-ink-500">{advice.location}</div>
                      <div className="mt-1 text-sm font-semibold state-danger-text">{advice.title}</div>
                    </div>
                    <span className={error.severity === "warning" ? "shrink-0 text-[11px] state-warning-text" : "shrink-0 text-[11px] state-danger-text"}>
                      {error.severity === "warning" ? "提醒" : "需处理"}
                    </span>
                  </div>
                  <p className="mt-2 text-xs leading-relaxed text-ink-300">{advice.suggestion}</p>
                  <details className="mt-2 text-[11px] text-ink-500">
                    <summary className="cursor-pointer select-none hover:text-ink-300">查看字段路径</summary>
                    <div className="mt-1 break-all rounded bg-ink-950/40 px-2 py-1 font-mono">
                      {error.path} · {error.message}
                    </div>
                  </details>
                </li>
              );
            })}
          </ul>
        </div>
      )}
    </div>
  );
}

function getValidationAdvice(error: ValidationError): ValidationAdvice {
  const path = error.path || "<root>";
  const message = error.message || "";
  const location = formatPath(path);
  const lower = message.toLowerCase();

  if (lower.startsWith("yaml parse error")) {
    return {
      location: "源码",
      title: "YAML 格式读不出来",
      suggestion: "先检查缩进、冒号和引号。列表项要用同一级缩进的 - 开头，中文冒号不要当字段分隔符用。",
    };
  }

  if (lower.includes("root must be a mapping")) {
    return {
      location: "源码开头",
      title: "最外层结构不对",
      suggestion: "整份内容最外层应该是 script: 开头，下面再缩进写标题、角色、地点和场景。",
    };
  }

  if (lower.includes("^char_[a-z0-9_]+$")) {
    return {
      location,
      title: "角色 ID 格式不对",
      suggestion: "请改成 char_ 开头，只用小写英文、数字、下划线，例如 char_lin_xia。角色表、场景出场角色和对白说话人要使用同一个 ID。",
    };
  }

  if (lower.includes("^loc_[a-z0-9_]+$")) {
    return {
      location,
      title: "地点 ID 格式不对",
      suggestion: "请改成 loc_ 开头，只用小写英文、数字、下划线，例如 loc_xing_gang。地点表和场景地点要使用同一个 ID。",
    };
  }

  if (lower.includes("^scene_[0-9]{3,}$")) {
    return {
      location,
      title: "场景 ID 格式不对",
      suggestion: "请改成 scene_ 加至少三位数字，例如 scene_001、scene_012。不要用中文、空格或重复编号。",
    };
  }

  if (lower.includes("^beat_[0-9]{3,}$")) {
    return {
      location,
      title: "节拍 ID 格式不对",
      suggestion: "请改成 beat_ 加至少三位数字，例如 beat_001、beat_002。同一场里的节拍 ID 不能重复。",
    };
  }

  if (lower.includes("^chapter_[0-9]{3,}$")) {
    return {
      location,
      title: "来源章节 ID 格式不对",
      suggestion: "请改成 chapter_ 加至少三位数字，例如 chapter_001。场景里的来源章节必须能在 source.chapter_ids 里找到。",
    };
  }

  const unknownCharacter = message.match(/unknown character id:\s*(.+)$/i);
  if (unknownCharacter) {
    return {
      location,
      title: "引用了不存在的角色",
      suggestion: `这个位置用了 ${unknownCharacter[1]}，但角色表里没有它。请在“全剧资料”新增这个角色，或把出场角色、说话人改成已有角色 ID。`,
    };
  }

  const unknownLocation = message.match(/unknown location id:\s*(.+)$/i);
  if (unknownLocation) {
    return {
      location,
      title: "引用了不存在的地点",
      suggestion: `这个位置用了 ${unknownLocation[1]}，但地点表里没有它。请在“全剧资料”新增这个地点，或把场景地点改成已有地点 ID。`,
    };
  }

  const unknownChapter = message.match(/unknown chapter id:\s*(.+)$/i);
  if (unknownChapter) {
    return {
      location,
      title: "引用了不存在的来源章节",
      suggestion: `这个位置用了 ${unknownChapter[1]}，但来源章节列表里没有它。请换成已有 chapter_001 这类章节 ID，或在源码的 source.chapter_ids 里补上。`,
    };
  }

  if (lower.includes("beat ids must be unique")) {
    return {
      location,
      title: "同一场里有重复节拍 ID",
      suggestion: "请把这场里的每个节拍改成不同 ID，例如 beat_001、beat_002、beat_003。",
    };
  }

  if (lower.includes("scene ids must be unique")) {
    return {
      location,
      title: "场景 ID 重复了",
      suggestion: "请给每个场景一个不同的 scene_ 编号，例如 scene_001、scene_002。重复 ID 会让保存和改编时找错场景。",
    };
  }

  if (lower.includes("character ids must be unique")) {
    return {
      location,
      title: "角色 ID 重复了",
      suggestion: "请给每个角色一个不同的 char_ ID。场景和对白引用哪个角色，都要对应到唯一角色。",
    };
  }

  if (lower.includes("location ids must be unique")) {
    return {
      location,
      title: "地点 ID 重复了",
      suggestion: "请给每个地点一个不同的 loc_ ID。场景里的 location_id 会按这个 ID 找地点。",
    };
  }

  if (lower.includes("chapter ids must be unique")) {
    return {
      location,
      title: "来源章节 ID 重复了",
      suggestion: "请在 source.chapter_ids 里保留不重复的章节 ID，例如 chapter_001、chapter_002、chapter_003。",
    };
  }

  const requiredField = message.match(/'([^']+)'\s+is a required property/i);
  if (requiredField) {
    return {
      location,
      title: `缺少“${fieldLabel(requiredField[1])}”`,
      suggestion: `请在这个位置补上 ${requiredField[1]} 字段。它是必填项，留空或完全不写都会导致保存后结构不完整。`,
    };
  }

  if (lower.includes("should be non-empty") || lower.includes("is too short") || lower.includes("too short")) {
    return {
      location,
      title: "这里不能留空",
      suggestion: emptySuggestion(path),
    };
  }

  const additional = message.match(/additional properties are not allowed \((.+) was unexpected\)/i);
  if (additional) {
    return {
      location,
      title: "多了不支持的字段",
      suggestion: `请删除 ${additional[1]}，或把内容挪到当前结构允许的字段里。系统只会保存 schema 里定义过的字段。`,
    };
  }

  if (lower.includes("is not one of")) {
    return {
      location,
      title: "选项值不在允许范围里",
      suggestion: "请把这个字段改成下拉选项里已有的值。角色类型、节拍类型、改编类型等字段不能随意写新值。",
    };
  }

  if (lower.includes("is not of type")) {
    return {
      location,
      title: "字段类型不对",
      suggestion: "请检查这里应该写文字、数字、列表还是对象。常见问题是把列表写成一行文字，或把数字数量写成了中文。",
    };
  }

  return {
    location,
    title: "结构字段需要调整",
    suggestion: "请按字段路径找到对应位置，补齐缺失内容或改成允许的格式。改完后再运行校验，确认问题是否消失。",
  };
}

function formatPath(path: string) {
  if (!path || path === "<root>") return "整份剧本";

  const sceneIndex = path.match(/script\.scenes(?:\.|\[)(\d+)/);
  if (sceneIndex) return `第 ${Number(sceneIndex[1]) + 1} 场 · ${tailLabel(path)}`;

  const characterIndex = path.match(/script\.characters(?:\.|\[)(\d+)/);
  if (characterIndex) return `第 ${Number(characterIndex[1]) + 1} 个角色 · ${tailLabel(path)}`;

  const locationIndex = path.match(/script\.locations(?:\.|\[)(\d+)/);
  if (locationIndex) return `第 ${Number(locationIndex[1]) + 1} 个地点 · ${tailLabel(path)}`;

  if (path.includes("script.source")) return `来源信息 · ${tailLabel(path)}`;
  if (path.includes("script.characters")) return "角色列表";
  if (path.includes("script.locations")) return "地点列表";
  if (path.includes("script.scenes")) return "场景列表";
  if (path.startsWith("script.")) return `剧本 · ${tailLabel(path)}`;
  return path;
}

function tailLabel(path: string) {
  const tokens = path.replace(/\[(\d+)\]/g, ".$1").split(".").filter(Boolean);
  const tail = [...tokens].reverse().find((token) => !/^\d+$/.test(token));
  return tail ? fieldLabel(tail) : "结构";
}

function fieldLabel(field: string) {
  return FIELD_LABELS[field] ?? field;
}

function emptySuggestion(path: string) {
  if (path.includes("chapter_refs")) return "每个场景至少要关联一个来源章节，例如 chapter_001。";
  if (path.includes("chapter_ids")) return "来源章节列表至少需要三个章节 ID，例如 chapter_001、chapter_002、chapter_003。";
  if (path.includes("script.scenes") && path.includes("characters")) return "每个场景至少要有一个出场角色，填写已有的 char_ 角色 ID。";
  if (path.includes("dialogue") || path.includes("beats")) return "这条对白或节拍需要有实际内容，不能只保留空字段。";
  if (path.includes("script.characters")) return "至少保留一个角色，并填写角色名称和 char_ 开头的 ID。";
  if (path.includes("script.locations")) return "如果场景使用了地点，请在地点表里保留对应地点，并填写 loc_ 开头的 ID。";
  if (path.includes("script.scenes")) return "至少保留一个场景。场景需要标题、来源章节、地点、出场角色、目的和冲突。";
  return "请填写一段实际内容。标题、目的、冲突、台词这类字段不能留空。";
}
