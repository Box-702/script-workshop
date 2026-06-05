"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { ScriptVersionSummary, ValidationError } from "@/lib/types";

export default function EditPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [yaml, setYaml] = useState<string>("");
  const [errors, setErrors] = useState<ValidationError[]>([]);
  const [changes, setChanges] = useState<string[]>([]);
  const [versions, setVersions] = useState<ScriptVersionSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const loadVersions = useCallback(async () => {
    const next = await api.listVersions(projectId);
    setVersions(next);
  }, [projectId]);

  useEffect(() => {
    api
      .getYaml(projectId)
      .then((text) => {
        setYaml(text);
        return loadVersions();
      })
      .catch((e) => setLoadErr((e as Error).message));
  }, [projectId, loadVersions]);

  async function revalidate(next: string) {
    setBusy(true);
    try {
      const r = await api.validate(next);
      setErrors(r.errors);
    } catch (e) {
      setErrors([{ path: "<root>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setBusy(false);
    }
  }

  function onChange(next: string) {
    setYaml(next);
    setNotice(null);
    void revalidate(next);
  }

  async function doRepair() {
    setBusy(true);
    setNotice(null);
    try {
      const r = await api.repair(yaml);
      setYaml(r.fixed_yaml);
      setChanges(r.changes);
      await revalidate(r.fixed_yaml);
    } catch (e) {
      setErrors([{ path: "<root>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setBusy(false);
    }
  }

  async function saveVersion() {
    setSaving(true);
    setNotice(null);
    try {
      const saved = await api.saveVersion(projectId, yaml);
      await loadVersions();
      setNotice(
        saved.validation_status === "valid"
          ? "已保存为新版本。"
          : "已保存为新版本，但仍有结构问题需要处理。",
      );
      await revalidate(saved.yaml_content);
    } catch (e) {
      setErrors([{ path: "<root>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setSaving(false);
    }
  }

  async function restoreVersion(versionId: string) {
    setSaving(true);
    setNotice(null);
    try {
      const restored = await api.restoreVersion(projectId, versionId);
      setYaml(restored.yaml_content);
      await loadVersions();
      setNotice("已从历史版本恢复，并创建了新的当前版本。");
      await revalidate(restored.yaml_content);
    } catch (e) {
      setErrors([{ path: "<root>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setSaving(false);
    }
  }

  if (loadErr) {
    return <div className="card border-red-500/40 text-red-200">加载 YAML 失败：{loadErr}</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">剧本编辑</h1>
          <p className="mt-1 text-sm text-ink-400">
            编辑 YAML 后可以保存为新版本，历史版本可随时恢复。
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={doRepair} disabled={busy || saving || !yaml}>
            自动修复
          </button>
          <button className="btn-primary" onClick={saveVersion} disabled={busy || saving || !yaml}>
            {saving ? "保存中..." : "保存版本"}
          </button>
          <a className="btn-ghost" href={`/api/projects/${projectId}/script.yaml`} download>
            下载
          </a>
        </div>
      </div>

      {notice && (
        <div className="rounded border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          {notice}
        </div>
      )}

      <div className="grid gap-4 lg:grid-cols-[1fr_340px]">
        <textarea
          className="input min-h-[640px] font-mono text-xs leading-relaxed"
          value={yaml}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
        />
        <aside className="space-y-4">
          <div className="card">
            <div className="label">校验</div>
            {busy ? (
              <div className="text-sm text-ink-400">校验中...</div>
            ) : errors.length === 0 ? (
              <div className="text-sm text-emerald-400">通过</div>
            ) : (
              <ul className="space-y-1 text-xs">
                {errors.map((e, i) => (
                  <li key={i} className="font-mono text-red-300">
                    <span className="text-ink-400">{e.path}</span> - {e.message}
                  </li>
                ))}
              </ul>
            )}
          </div>

          <div className="card">
            <div className="label">版本历史</div>
            {versions.length === 0 ? (
              <div className="text-sm text-ink-400">暂无历史版本。</div>
            ) : (
              <ul className="space-y-2 text-xs">
                {versions.map((version, index) => (
                  <li
                    key={version.id}
                    className="rounded border border-white/10 bg-white/[0.02] p-2"
                  >
                    <div className="flex items-center justify-between gap-2">
                      <span className="font-mono text-ink-200">
                        {index === 0 ? "当前" : `历史 ${index}`}
                      </span>
                      <span
                        className={
                          version.validation_status === "valid"
                            ? "text-emerald-300"
                            : "text-amber-300"
                        }
                      >
                        {version.validation_status}
                      </span>
                    </div>
                    <div className="mt-1 font-mono text-ink-500">
                      {new Date(version.created_at).toLocaleString()}
                    </div>
                    {index > 0 && (
                      <button
                        className="btn-ghost mt-2 w-full px-2 py-1 text-xs"
                        onClick={() => restoreVersion(version.id)}
                        disabled={saving}
                      >
                        恢复为当前版本
                      </button>
                    )}
                  </li>
                ))}
              </ul>
            )}
          </div>

          {changes.length > 0 && (
            <div className="card">
              <div className="label">最近修复</div>
              <ul className="space-y-1 text-xs text-ink-200">
                {changes.map((change, i) => (
                  <li key={i} className="font-mono">
                    {change}
                  </li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
