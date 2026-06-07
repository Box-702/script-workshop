import type {
  AgentRunSummary,
  EditEventSummary,
  ModelKeySummary,
  ModelKeyTestResponse,
  ProjectDetail,
  ProjectCreateResponse,
  ProjectScriptImportResponse,
  ProjectSummary,
  RepairResponse,
  RunOut,
  ScriptDocument,
  ScriptVersionDetail,
  ScriptVersionSummary,
  ValidateResponse,
  VersionDiffSummary,
} from "./types";
import type { LlmSettings } from "./llm-settings";
import { getAccessToken } from "./auth";
import { getLocalUserId } from "./local-user";
import { llmSettingsHeaders } from "./llm-settings";

export const AUTH_REQUIRED_MESSAGE = "请先登录后继续。";

export class AuthRequiredError extends Error {
  constructor() {
    super(AUTH_REQUIRED_MESSAGE);
    this.name = "AuthRequiredError";
  }
}

async function requestHeaders(initHeaders?: HeadersInit) {
  const headers = new Headers(initHeaders);
  if (!headers.has("Content-Type")) headers.set("Content-Type", "application/json");
  const token = await getAccessToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  else headers.set("X-Local-User-Id", getLocalUserId());
  return headers;
}

async function jfetch<T>(url: string, init?: RequestInit): Promise<T> {
  const res = await fetch(url, {
    ...init,
    headers: await requestHeaders(init?.headers),
  });
  if (!res.ok) {
    if (res.status === 401) throw new AuthRequiredError();
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

async function tfetch(url: string, init?: RequestInit): Promise<string> {
  const res = await fetch(url, {
    ...init,
    headers: await requestHeaders(init?.headers),
  });
  if (!res.ok) {
    if (res.status === 401) throw new AuthRequiredError();
    throw new Error(`HTTP ${res.status}`);
  }
  return res.text();
}

export async function downloadBlob(url: string, init?: RequestInit): Promise<Blob> {
  const res = await fetch(url, {
    ...init,
    headers: await requestHeaders(init?.headers),
  });
  if (!res.ok) {
    if (res.status === 401) throw new AuthRequiredError();
    const text = await res.text();
    throw new Error(text || `HTTP ${res.status}`);
  }
  return res.blob();
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

  importScriptProject: (body: {
    title?: string;
    content: string;
    format: "yaml" | "json";
    label?: string;
  }) =>
    jfetch<ProjectScriptImportResponse>("/api/projects/import-script", {
      method: "POST",
      body: JSON.stringify(body),
    }),

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
    tfetch(`/api/projects/${projectId}/script.yaml`),

  getScriptJson: (projectId: string) =>
    jfetch<{ script: ScriptDocument }>(`/api/projects/${projectId}/script.json`),

  listVersions: (projectId: string) =>
    jfetch<ScriptVersionSummary[]>(`/api/projects/${projectId}/versions`),

  getVersionDiff: (projectId: string, fromVersionId: string, toVersionId?: string) => {
    const params = new URLSearchParams({ from: fromVersionId });
    if (toVersionId) params.set("to", toVersionId);
    return jfetch<VersionDiffSummary>(`/api/projects/${projectId}/diff?${params.toString()}`);
  },

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
    llmSettings?: LlmSettings,
  ) =>
    jfetch<AgentRunSummary>(`/api/projects/${projectId}/agent/adapt`, {
      method: "POST",
      headers: llmSettings ? llmSettingsHeaders(llmSettings) : undefined,
      body: JSON.stringify(body),
    }),

  listAgentRuns: (projectId: string, limit = 20) =>
    jfetch<AgentRunSummary[]>(`/api/projects/${projectId}/agent-runs?limit=${limit}`),

  acceptAgentRun: (runId: string, patchIndexes?: number[]) =>
    jfetch<ScriptVersionDetail>(`/api/agent-runs/${runId}/accept`, {
      method: "POST",
      body: JSON.stringify(
        patchIndexes ? { patch_indexes: patchIndexes } : {},
      ),
    }),

  rejectAgentRun: (runId: string) =>
    jfetch<AgentRunSummary>(`/api/agent-runs/${runId}/reject`, {
      method: "POST",
    }),

  retryAgentRun: (runId: string, llmSettings?: LlmSettings) =>
    jfetch<AgentRunSummary>(`/api/agent-runs/${runId}/retry`, {
      method: "POST",
      headers: llmSettings ? llmSettingsHeaders(llmSettings) : undefined,
    }),

  validate: (yaml: string) =>
    jfetch<ValidateResponse>("/api/validate", {
      method: "POST",
      body: JSON.stringify({ yaml }),
    }),

  validateScript: (script: ScriptDocument) =>
    jfetch<ValidateResponse>("/api/validate/script", {
      method: "POST",
      body: JSON.stringify({ script }),
    }),

  scriptToYaml: (script: ScriptDocument) =>
    jfetch<{ yaml: string }>("/api/script-to-yaml", {
      method: "POST",
      body: JSON.stringify({ script }),
    }),

  repair: (yaml: string) =>
    jfetch<RepairResponse>("/api/repair", {
      method: "POST",
      body: JSON.stringify({ yaml, errors: [] }),
    }),
};
