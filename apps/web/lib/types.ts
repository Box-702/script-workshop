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

export interface ProjectScriptImportResponse {
  project_id: string;
  version_id: string;
  validation_status: string;
  validation_errors: ValidationError[] | null;
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

export interface VersionDiffItem {
  path: string;
  section: string;
  label: string;
  change_type: "added" | "removed" | "changed";
  before: unknown;
  after: unknown;
}

export interface VersionDiffSummary {
  project_id: string;
  from_version_id: string;
  to_version_id: string;
  items: VersionDiffItem[];
  summary: Record<string, number>;
}

export interface DialogueLine {
  speaker: string;
  line: string;
  emotion?: string | null;
  subtext?: string | null;
}

export interface ScriptBeat {
  id: string;
  type: "action" | "dialogue" | "cue";
  text?: string | null;
  speaker?: string | null;
  line?: string | null;
  emotion?: string | null;
  subtext?: string | null;
}

export interface ScriptScene {
  id: string;
  title: string;
  chapter_refs: string[];
  location_id: string;
  time?: string | null;
  characters: string[];
  purpose: string;
  conflict: string;
  entry_state?: string | null;
  exit_state?: string | null;
  action: string[];
  dialogue: DialogueLine[];
  beats?: ScriptBeat[];
  adaptation_notes?: { reason?: string | null; fidelity?: string | null } | null;
}

export interface ScriptCharacter {
  id: string;
  name: string;
  role?: string | null;
  goal?: string | null;
  motivation?: string | null;
  personality?: string | null;
  relationship?: string | null;
  arc?: string | null;
  speech_style?: string | null;
}

export interface ScriptLocation {
  id: string;
  name: string;
  description?: string | null;
}

export interface ScriptDocument {
  title: string;
  version: string;
  language: string;
  adaptation?: Record<string, unknown> | null;
  source: { chapter_count: number; chapter_ids: string[] };
  logline: string;
  themes: string[];
  characters: ScriptCharacter[];
  locations: ScriptLocation[];
  scenes: ScriptScene[];
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

export interface AgentPatchOperation {
  op?: string;
  path?: string;
  field?: string;
  scene_id?: string | null;
  scene_title?: string | null;
  before?: unknown;
  value?: unknown;
  after?: unknown;
}

export interface AgentRunSummary {
  id: string;
  project_id: string;
  base_version_id: string;
  result_version_id: string | null;
  user_prompt: string;
  selected_context: Record<string, unknown> | null;
  plan: unknown[] | null;
  patch: AgentPatchOperation[] | null;
  status: string;
  model: string | null;
  error_message: string | null;
  created_at: string;
  updated_at: string;
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
