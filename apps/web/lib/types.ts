export type AdaptationType = "series" | "film" | "short_drama" | "stage" | "other";

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
