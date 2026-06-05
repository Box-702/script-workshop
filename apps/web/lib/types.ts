export type AdaptationType = "series" | "film" | "short_drama" | "stage" | "other";

export type Language =
  | "auto"
  | "zh-CN"
  | "zh-TW"
  | "en-US"
  | "ja-JP"
  | "ko-KR"
  | "ru-RU"
  | "ar-SA"
  | "es-ES"
  | "fr-FR"
  | "de-DE";

export const LANGUAGE_OPTIONS: Array<{ value: Language; label: string }> = [
  { value: "auto", label: "自动检测（推荐）" },
  { value: "zh-CN", label: "中文（简体）" },
  { value: "zh-TW", label: "中文（繁體）" },
  { value: "en-US", label: "English" },
  { value: "ja-JP", label: "日本語" },
  { value: "ko-KR", label: "한국어" },
  { value: "ru-RU", label: "Русский" },
  { value: "ar-SA", label: "العربية" },
  { value: "es-ES", label: "Español" },
  { value: "fr-FR", label: "Français" },
  { value: "de-DE", label: "Deutsch" },
];

export interface ChapterOut {
  id: string;
  title: string;
  word_count: number;
  order_index: number;
}

export interface ProjectCreateResponse {
  project_id: string;
  chapter_count: number;
  chapters: ChapterOut[];
}

export type RunStatus = "queued" | "running" | "done" | "failed";

export interface RunOut {
  id: string;
  project_id: string;
  status: RunStatus;
  current_step: string;
  progress: number;
  error_message: string | null;
  created_at: string;
  updated_at: string;
}

export interface ValidationError {
  path: string;
  message: string;
  severity: "error" | "warning";
}

export interface ValidateResponse {
  valid: boolean;
  errors: ValidationError[];
}

export interface RepairResponse {
  fixed_yaml: string;
  changes: string[];
}

export interface ScriptVersionSummary {
  id: string;
  project_id: string;
  validation_status: string;
  validation_errors: ValidationError[] | null;
  created_at: string;
}

export interface ScriptVersionDetail extends ScriptVersionSummary {
  yaml_content: string;
}
