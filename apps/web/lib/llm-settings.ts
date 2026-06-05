export type LlmProvider = "openai";

export interface LlmSettings {
  provider: LlmProvider;
  apiKey: string;
  baseUrl: string;
  model: string;
}

const STORAGE_KEY = "script-workshop.llmSettings";
const LEGACY_STORAGE_KEY = "scriptforge.llmSettings";

export const DEFAULT_LLM_SETTINGS: LlmSettings = {
  provider: "openai",
  apiKey: "",
  baseUrl: "https://api.openai.com/v1",
  model: "gpt-4o-mini",
};

export function loadLlmSettings(): LlmSettings {
  if (typeof window === "undefined") return DEFAULT_LLM_SETTINGS;
  const raw =
    window.localStorage.getItem(STORAGE_KEY) ??
    window.localStorage.getItem(LEGACY_STORAGE_KEY);
  if (!raw) return DEFAULT_LLM_SETTINGS;
  try {
    const parsed = JSON.parse(raw) as Partial<LlmSettings>;
    // Normalize legacy 'mock' provider to 'openai' so a stale value never silently downgrades.
    if (parsed.provider && parsed.provider !== "openai") {
      parsed.provider = "openai";
    }
    const settings = { ...DEFAULT_LLM_SETTINGS, ...parsed } as LlmSettings;
    if (!window.localStorage.getItem(STORAGE_KEY)) {
      window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
    }
    return settings;
  } catch {
    return DEFAULT_LLM_SETTINGS;
  }
}

export function saveLlmSettings(settings: LlmSettings) {
  window.localStorage.setItem(STORAGE_KEY, JSON.stringify(settings));
}

export function clearLlmSettings() {
  window.localStorage.removeItem(STORAGE_KEY);
  window.localStorage.removeItem(LEGACY_STORAGE_KEY);
}

export function llmSettingsHeaders(settings: LlmSettings): HeadersInit {
  const headers: Record<string, string> = {
    "X-LLM-Provider": settings.provider,
  };
  if (settings.provider === "openai") {
    if (settings.apiKey.trim()) headers["X-OpenAI-API-Key"] = settings.apiKey.trim();
    if (settings.baseUrl.trim()) headers["X-OpenAI-Base-URL"] = settings.baseUrl.trim();
    if (settings.model.trim()) headers["X-OpenAI-Model"] = settings.model.trim();
  }
  return headers;
}

export function hasUsableLlmSettings(settings: LlmSettings = loadLlmSettings()): boolean {
  return settings.provider === "openai" && settings.apiKey.trim().length > 0;
}
