import type {
  AgentRunSummary,
  EditEventSummary,
  ModelKeySummary,
  ModelKeyTestResponse,
  ProjectDetail,
  ProjectCreateResponse,
  ProjectSummary,
  RepairResponse,
  RunOut,
  ScriptDocument,
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
    let message = text;
    try {
      const data = JSON.parse(text) as { detail?: unknown; message?: unknown };
      if (typeof data.detail === "string") message = data.detail;
      else if (typeof data.message === "string") message = data.message;
    } catch {
      // Keep the raw response text.
    }
    throw new Error(message || `HTTP ${res.status}`);
  }
  if (res.status === 204) return undefined as T;
  return (await res.json()) as T;
}

export const api = {
  listModelKeys: () => jfetch<ModelKeySummary[]>("/api/user/model-keys"),

  getActiveModelKey: () =>
    jfetch<ModelKeySummary | null>("/api/user/model-keys/active"),

  saveModelKey: (body: {
    provider: "openai";
    api_key: string;
    base_url: string;
    model: string;
  }) =>
    jfetch<ModelKeySummary>("/api/user/model-keys", {
      method: "POST",
      body: JSON.stringify(body),
    }),

  revokeModelKey: (keyId: string) =>
    jfetch<ModelKeyTestResponse>(`/api/user/model-keys/${keyId}`, {
      method: "DELETE",
    }),

  testModelKey: (keyId: string) =>
    jfetch<ModelKeyTestResponse>(`/api/user/model-keys/${keyId}/test`, {
      method: "POST",
    }),

  listProjects: () => jfetch<ProjectSummary[]>("/api/projects"),

  getProject: (projectId: string) =>
    jfetch<ProjectDetail>(`/api/projects/${projectId}`),

  deleteProject: (projectId: string) =>
    jfetch<void>(`/api/projects/${projectId}`, { method: "DELETE" }),

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

  getScriptJson: (projectId: string) =>
    jfetch<{ script: ScriptDocument }>(`/api/projects/${projectId}/script.json`),

  listVersions: (projectId: string) =>
    jfetch<ScriptVersionSummary[]>(`/api/projects/${projectId}/versions`),

  listEditEvents: (projectId: string, limit = 50) =>
    jfetch<EditEventSummary[]>(`/api/projects/${projectId}/edits?limit=${limit}`),

  saveVersion: (
    projectId: string,
    yaml: string,
    metadata?: { label?: string; notes?: string },
  ) =>
    jfetch<ScriptVersionDetail>(`/api/projects/${projectId}/versions`, {
      method: "POST",
      body: JSON.stringify({ yaml, ...metadata }),
    }),

  saveStructuredVersion: (
    projectId: string,
    script: ScriptDocument,
    metadata?: { label?: string; notes?: string },
  ) =>
    jfetch<ScriptVersionDetail>(`/api/projects/${projectId}/versions/json`, {
      method: "POST",
      body: JSON.stringify({ script, ...metadata }),
    }),

  restoreVersion: (projectId: string, versionId: string) =>
    jfetch<ScriptVersionDetail>(
      `/api/projects/${projectId}/versions/${versionId}/restore`,
      { method: "POST" },
    ),

  createAgentRun: (
    projectId: string,
    body: { instruction: string; base_version_id?: string; scene_ids?: string[] },
  ) =>
    jfetch<AgentRunSummary>(`/api/projects/${projectId}/agent/adapt`, {
      method: "POST",
      body: JSON.stringify(body),
    }),

  acceptAgentRun: (runId: string) =>
    jfetch<ScriptVersionDetail>(`/api/agent-runs/${runId}/accept`, {
      method: "POST",
    }),

  rejectAgentRun: (runId: string) =>
    jfetch<AgentRunSummary>(`/api/agent-runs/${runId}/reject`, {
      method: "POST",
    }),

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
