"use client";

import { useCallback, useEffect, useState } from "react";
import { useParams } from "next/navigation";
import { api } from "@/lib/api";
import type { AgentRunSummary, ScriptVersionSummary, ValidationError } from "@/lib/types";

export default function EditPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [yaml, setYaml] = useState("");
  const [errors, setErrors] = useState<ValidationError[]>([]);
  const [changes, setChanges] = useState<string[]>([]);
  const [versions, setVersions] = useState<ScriptVersionSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentInstruction, setAgentInstruction] = useState("");
  const [agentSceneIds, setAgentSceneIds] = useState("");
  const [agentRun, setAgentRun] = useState<AgentRunSummary | null>(null);
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
      const saved = await api.saveVersion(projectId, yaml, {
        label: "手动保存",
        notes: "用户从编辑器保存。",
      });
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

  async function createAgentSuggestion() {
    if (!agentInstruction.trim()) return;
    setAgentBusy(true);
    setNotice(null);
    try {
      const sceneIds = agentSceneIds
        .split(",")
        .map((item) => item.trim())
        .filter(Boolean);
      const run = await api.createAgentRun(projectId, {
        instruction: agentInstruction,
        scene_ids: sceneIds,
      });
      setAgentRun(run);
      setNotice("已生成改编建议，等待确认。");
    } catch (e) {
      setErrors([{ path: "<agent>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setAgentBusy(false);
    }
  }

  async function acceptAgentSuggestion() {
    if (!agentRun) return;
    setAgentBusy(true);
    setNotice(null);
    try {
      const version = await api.acceptAgentRun(agentRun.id);
      setYaml(version.yaml_content);
      setAgentRun(null);
      setAgentInstruction("");
      await loadVersions();
      await revalidate(version.yaml_content);
      setNotice("已接受 AI 改编，并保存为新版本。");
    } catch (e) {
      setErrors([{ path: "<agent>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setAgentBusy(false);
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
            编辑 YAML 后保存为新版本，历史版本可随时恢复。
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

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <textarea
          className="input min-h-[640px] font-mono text-xs leading-relaxed"
          value={yaml}
          onChange={(e) => onChange(e.target.value)}
          spellCheck={false}
        />
        <aside className="space-y-4">
          <div className="card space-y-3">
            <div className="label">AI 改编助手</div>
            <textarea
              className="input min-h-[96px] text-sm"
              value={agentInstruction}
              onChange={(e) => setAgentInstruction(e.target.value)}
              placeholder="例如：把第一场改得更悬疑，减少解释性对白。"
            />
            <input
              className="input font-mono text-xs"
              value={agentSceneIds}
              onChange={(e) => setAgentSceneIds(e.target.value)}
              placeholder="scene_001, scene_002"
            />
            <div className="flex gap-2">
              <button
                className="btn-ghost flex-1"
                onClick={createAgentSuggestion}
                disabled={agentBusy || saving || !agentInstruction.trim()}
              >
                {agentBusy ? "生成中..." : "生成建议"}
              </button>
              <button
                className="btn-primary flex-1"
                onClick={acceptAgentSuggestion}
                disabled={agentBusy || saving || !agentRun}
              >
                接受
              </button>
            </div>
            {agentRun && (
              <div className="space-y-3 rounded border border-white/10 bg-white/[0.02] p-3 text-xs">
                <div className="flex items-center justify-between gap-2">
                  <span>{formatAgentStatus(agentRun.status)}</span>
                  <span className="font-mono text-ink-500">{agentRun.model}</span>
                </div>
                {agentRun.plan && (
                  <ul className="space-y-1 text-ink-300">
                    {agentRun.plan.map((item, index) => (
                      <li key={index}>{String(item)}</li>
                    ))}
                  </ul>
                )}
                {agentRun.patch && (
                  <ul className="space-y-1 font-mono text-ink-500">
                    {agentRun.patch.map((item, index) => (
                      <li key={index}>{formatPatchLine(item)}</li>
                    ))}
                  </ul>
                )}
              </div>
            )}
          </div>

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
                    <div className="mt-2 space-y-1 text-ink-400">
                      <div>{version.label || formatSource(version.source_type)}</div>
                      <div>来源：{formatSource(version.source_type)}</div>
                      {version.notes && <div>备注：{version.notes}</div>}
                      {version.parent_version_id && (
                        <div className="font-mono">父版本：{version.parent_version_id}</div>
                      )}
                      <div className="font-mono">{new Date(version.created_at).toLocaleString()}</div>
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

function formatSource(value: string) {
  return (
    {
      generation: "AI 生成",
      manual: "手动保存",
      restore: "历史恢复",
      repair: "自动修复",
      import: "导入",
    }[value] ?? value
  );
}

function formatAgentStatus(value: string) {
  return (
    {
      waiting_review: "待确认",
      accepted: "已接受",
      rejected: "已拒绝",
      failed: "失败",
    }[value] ?? value
  );
}

function formatPatchLine(value: unknown) {
  if (!value || typeof value !== "object") return String(value);
  const patch = value as { op?: string; path?: string };
  return `${patch.op ?? "patch"} ${patch.path ?? ""}`.trim();
}
