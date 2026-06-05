"use client";

import { useEffect, useState } from "react";
import {
  clearLlmSettings,
  DEFAULT_LLM_SETTINGS,
  loadLlmSettings,
  saveLlmSettings,
} from "@/lib/llm-settings";
import type { LlmProvider, LlmSettings } from "@/lib/llm-settings";

export default function SettingsPage() {
  const [settings, setSettings] = useState<LlmSettings>(DEFAULT_LLM_SETTINGS);
  const [saved, setSaved] = useState(false);

  useEffect(() => {
    setSettings(loadLlmSettings());
  }, []);

  function update<K extends keyof LlmSettings>(key: K, value: LlmSettings[K]) {
    setSaved(false);
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  function save() {
    saveLlmSettings(settings);
    setSaved(true);
  }

  function reset() {
    clearLlmSettings();
    setSettings(DEFAULT_LLM_SETTINGS);
    setSaved(false);
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">模型设置</h1>
        <p className="mt-1 text-sm text-ink-400">
          配置 OpenAI 兼容接口。API 密钥只保存在当前浏览器，生成时临时传给后端。
        </p>
      </div>

      <div className="card space-y-4">
        <div>
          <label className="label" htmlFor="apiKey">API 密钥</label>
          <input
            id="apiKey"
            className="input font-mono"
            type="password"
            value={settings.apiKey}
            onChange={(e) => update("apiKey", e.target.value)}
            placeholder="sk-..."
            autoComplete="off"
          />
        </div>

        <div className="grid gap-4 md:grid-cols-2">
          <div>
            <label className="label" htmlFor="baseUrl">接口地址</label>
            <input
              id="baseUrl"
              className="input font-mono"
              value={settings.baseUrl}
              onChange={(e) => update("baseUrl", e.target.value)}
            />
          </div>
          <div>
            <label className="label" htmlFor="model">模型名称</label>
            <input
              id="model"
              className="input font-mono"
              value={settings.model}
              onChange={(e) => update("model", e.target.value)}
            />
          </div>
        </div>

        {saved && (
          <div className="rounded border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-200">
            设置已保存。
          </div>
        )}

        <div className="flex justify-end gap-2">
          <button type="button" className="btn-ghost" onClick={reset}>
            重置
          </button>
          <button type="button" className="btn-primary" onClick={save}>
            保存设置
          </button>
        </div>
      </div>
    </div>
  );
}
