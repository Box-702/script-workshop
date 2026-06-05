import type {
  ProjectDetail,
  ProjectCreateResponse,
  ProjectSummary,
  RepairResponse,
  RunOut,
  ScriptVersionDetail,
  ScriptVersionSummary,
  ValidateResponse,
} from "./types";
import type { LlmSettings } from "./llm-settings";
import { llmSettingsHeaders } from "./llm-settings";

async function jfetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
  });
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`HTTP ${res.status}: ${text}`);
  }
  return (await res.json()) as T;
}

export const api = {
  listProjects: () => jfetch<ProjectSummary[]>("/api/projects"),

  getProject: (projectId: string) =>
    jfetch<ProjectDetail>(`/api/projects/${projectId}`),

  createProject: (body: {
    title: string;
    raw_text: string;
    adaptation_type: string;
    language?: string;
  }) => jfetch<ProjectCreateResponse>("/api/projects", { method: "POST", body: JSON.stringify(body) }),

  generate: (projectId: string, llmSettings?: LlmSettings) =>
    jfetch<{ run_id: string; status: string }>(
      `/api/projects/${projectId}/generate`,
      {
        method: "POST",
        headers: llmSettings ? llmSettingsHeaders(llmSettings) : undefined,
      },
    ),

  getRun: (runId: string) => jfetch<RunOut>(`/api/runs/${runId}`),

  getYaml: (projectId: string) =>
    fetch(`/api/projects/${projectId}/script.yaml`).then((r) => {
      if (!r.ok) throw new Error(`HTTP ${r.status}`);
      return r.text();
    }),

  listVersions: (projectId: string) =>
    jfetch<ScriptVersionSummary[]>(`/api/projects/${projectId}/versions`),

  saveVersion: (projectId: string, yaml: string) =>
    jfetch<ScriptVersionDetail>(`/api/projects/${projectId}/versions`, {
      method: "POST",
      body: JSON.stringify({ yaml }),
    }),

  restoreVersion: (projectId: string, versionId: string) =>
    jfetch<ScriptVersionDetail>(
      `/api/projects/${projectId}/versions/${versionId}/restore`,
      { method: "POST" },
    ),

  validate: (yaml: string) =>
    jfetch<ValidateResponse>("/api/validate", {
      method: "POST",
      body: JSON.stringify({ yaml }),
    }),

  repair: (yaml: string) =>
    jfetch<RepairResponse>("/api/repair", {
      method: "POST",
      body: JSON.stringify({ yaml, errors: [] }),
    }),
};
