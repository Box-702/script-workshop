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
  parent_version_id: string | null;
  source_type: string;
  label: string | null;
  notes: string | null;
  validation_status: string;
  validation_errors: ValidationError[] | null;
  created_at: string;
}

export interface ScriptVersionDetail extends ScriptVersionSummary {
  yaml_content: string;
}

export interface EditEventSummary {
  id: string;
  project_id: string;
  version_id: string | null;
  actor_type: string;
  actor_id: string;
  edit_type: string;
  target_path: string;
  before_snapshot: unknown;
  after_snapshot: unknown;
  patch: unknown;
  note: string | null;
  created_at: string;
}

export interface ProjectRunSummary {
  id: string;
  status: RunStatus;
  current_step: string;
  progress: number;
  created_at: string;
}

export interface ProjectSummary {
  id: string;
  owner_id: string;
  title: string;
  adaptation_type: AdaptationType;
  language: string;
  status: string;
  current_version_id: string | null;
  created_at: string;
  updated_at: string;
  chapter_count: number;
  version_count: number;
  latest_version: ScriptVersionSummary | null;
  latest_run: ProjectRunSummary | null;
}

export interface ProjectDetail extends ProjectSummary {
  chapters: ChapterOut[];
}

export interface ModelKeySummary {
  id: string;
  provider: string;
  base_url: string;
  default_model: string;
  key_last4: string;
  status: string;
  created_at: string;
  updated_at: string;
}

export interface ModelKeyTestResponse {
  ok: boolean;
  message: string;
}
