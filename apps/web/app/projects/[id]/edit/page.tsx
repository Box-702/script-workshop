"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { ValidationError } from "@/lib/types";

export default function EditPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [yaml, setYaml] = useState<string>("");
  const [errors, setErrors] = useState<ValidationError[]>([]);
  const [changes, setChanges] = useState<string[]>([]);
  const [busy, setBusy] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);

  useEffect(() => {
    api
      .getYaml(projectId)
      .then(setYaml)
      .catch((e) => setLoadErr((e as Error).message));
  }, [projectId]);

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
    void revalidate(next);
  }

  async function doRepair() {
    setBusy(true);
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

  if (loadErr) {
    return <div className="card border-red-500/40 text-red-200">加载 YAML 失败：{loadErr}</div>;
  }

  return (
    <div className="space-y-4">
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-semibold tracking-tight">YAML 编辑</h1>
        <div className="flex gap-2">
          <button className="btn-ghost" onClick={doRepair} disabled={busy || !yaml}>
            一键修复
          </button>
          <a
            className="btn-ghost"
            href={`/api/projects/${projectId}/script.yaml`}
            download
          >
            下载
          </a>
        </div>
      </div>

      <div className="grid gap-4 lg:grid-cols-[1fr_320px]">
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
              <div className="text-sm text-ink-400">校验中…</div>
            ) : errors.length === 0 ? (
              <div className="text-sm text-emerald-400">通过 ✓</div>
            ) : (
              <ul className="space-y-1 text-xs">
                {errors.map((e, i) => (
                  <li key={i} className="font-mono text-red-300">
                    <span className="text-ink-400">{e.path}</span> — {e.message}
                  </li>
                ))}
              </ul>
            )}
          </div>
          {changes.length > 0 && (
            <div className="card">
              <div className="label">最近修复</div>
              <ul className="space-y-1 text-xs text-ink-200">
                {changes.map((c, i) => (
                  <li key={i} className="font-mono">{c}</li>
                ))}
              </ul>
            </div>
          )}
        </aside>
      </div>
    </div>
  );
}
