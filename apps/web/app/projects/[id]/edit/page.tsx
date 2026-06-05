"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { ExportMenu } from "@/components/ExportMenu";
import { api } from "@/lib/api";
import { loadLlmSettings } from "@/lib/llm-settings";
import type {
  AgentPatchOperation,
  AgentRunSummary,
  DialogueLine,
  ScriptDocument,
  ScriptScene,
  ScriptVersionSummary,
  ValidationError,
} from "@/lib/types";

type EditorMode = "script" | "scene" | "yaml";

export default function EditPage() {
  const params = useParams<{ id: string }>();
  const projectId = params.id;
  const [yaml, setYaml] = useState("");
  const [script, setScript] = useState<ScriptDocument | null>(null);
  const [selectedSceneId, setSelectedSceneId] = useState<string>("");
  const [mode, setMode] = useState<EditorMode>("scene");
  const [errors, setErrors] = useState<ValidationError[]>([]);
  const [changes, setChanges] = useState<string[]>([]);
  const [versions, setVersions] = useState<ScriptVersionSummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [saving, setSaving] = useState(false);
  const [agentBusy, setAgentBusy] = useState(false);
  const [agentInstruction, setAgentInstruction] = useState("");
  const [agentScope, setAgentScope] = useState<"current_scene" | "whole_script">("current_scene");
  const [agentRun, setAgentRun] = useState<AgentRunSummary | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentRunSummary[]>([]);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);

  const selectedScene = useMemo(() => {
    return script?.scenes.find((scene) => scene.id === selectedSceneId) ?? script?.scenes[0] ?? null;
  }, [script, selectedSceneId]);

  const selectedSceneIndex = useMemo(() => {
    if (!script || !selectedScene) return 0;
    const index = script.scenes.findIndex((scene) => scene.id === selectedScene.id);
    return index >= 0 ? index : 0;
  }, [script, selectedScene]);

  const characterNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const character of script?.characters ?? []) map[character.id] = character.name;
    return map;
  }, [script]);

  const locationNames = useMemo(() => {
    const map: Record<string, string> = {};
    for (const location of script?.locations ?? []) map[location.id] = location.name;
    return map;
  }, [script]);

  const loadVersions = useCallback(async () => {
    const next = await api.listVersions(projectId);
    setVersions(next);
  }, [projectId]);

  const loadAgentRuns = useCallback(async () => {
    const next = await api.listAgentRuns(projectId, 10);
    setAgentRuns(next);
    return next;
  }, [projectId]);

  const loadScript = useCallback(async () => {
    const [yamlText, jsonDoc, , nextAgentRuns] = await Promise.all([
      api.getYaml(projectId),
      api.getScriptJson(projectId),
      loadVersions(),
      loadAgentRuns(),
    ]);
    setYaml(yamlText);
    setScript(jsonDoc.script);
    setSelectedSceneId((prev) =>
      jsonDoc.script.scenes.some((scene) => scene.id === prev)
        ? prev
        : jsonDoc.script.scenes[0]?.id || "",
    );
    setAgentRun((current) => current ?? nextAgentRuns.find((run) => run.status === "waiting_review") ?? null);
    const validation = await api.validate(yamlText);
    setErrors(validation.errors);
  }, [projectId, loadVersions, loadAgentRuns]);

  useEffect(() => {
    loadScript().catch((e) => setLoadErr((e as Error).message));
  }, [loadScript]);

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

  function updateScript(patch: (current: ScriptDocument) => ScriptDocument) {
    setNotice(null);
    setScript((current) => (current ? patch(current) : current));
  }

  function updateScene(sceneId: string, patch: (scene: ScriptScene) => ScriptScene) {
    updateScript((current) => ({
      ...current,
      scenes: current.scenes.map((scene) => (scene.id === sceneId ? patch(scene) : scene)),
    }));
  }

  function updateYaml(next: string) {
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
      setMode("yaml");
      await revalidate(r.fixed_yaml);
    } catch (e) {
      setErrors([{ path: "<root>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setBusy(false);
    }
  }

  async function saveStructuredVersion() {
    if (!script) return;
    setSaving(true);
    setNotice(null);
    try {
      const saved = await api.saveStructuredVersion(projectId, script, {
        label: "结构化保存",
        notes: "用户从剧本编辑界面保存。",
      });
      await loadScript();
      setNotice(saved.validation_status === "valid" ? "已保存为新版本。" : "已保存，但仍有结构问题需要处理。");
    } catch (e) {
      setErrors([{ path: "<root>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setSaving(false);
    }
  }

  async function saveYamlVersion() {
    setSaving(true);
    setNotice(null);
    try {
      const saved = await api.saveVersion(projectId, yaml, {
        label: "源码保存",
        notes: "用户从 YAML 源码保存。",
      });
      setYaml(saved.yaml_content);
      await loadScript();
      setNotice(saved.validation_status === "valid" ? "已保存为新版本。" : "已保存，但仍有结构问题需要处理。");
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
      await loadScript();
      setNotice("已从历史版本恢复，并创建了新的当前版本。");
    } catch (e) {
      setErrors([{ path: "<root>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setSaving(false);
    }
  }

  async function createAgentSuggestion() {
    if (!agentInstruction.trim() || !script) return;
    setAgentBusy(true);
    setNotice(null);
    try {
      const run = await api.createAgentRun(projectId, {
        instruction: agentInstruction,
        scene_ids:
          agentScope === "current_scene" && selectedScene
            ? [selectedScene.id]
            : script?.scenes.map((scene) => scene.id) ?? [],
      }, loadLlmSettings());
      setAgentRun(run);
      await loadAgentRuns();
      setNotice("已生成改编建议，等待确认。");
    } catch (e) {
      setErrors([{ path: "<agent>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setAgentBusy(false);
    }
  }

  async function acceptAgentSuggestion(patchIndexes?: number[]) {
    if (!agentRun) return;
    setAgentBusy(true);
    setNotice(null);
    try {
      const version = await api.acceptAgentRun(agentRun.id, patchIndexes);
      setYaml(version.yaml_content);
      setAgentRun(null);
      setAgentInstruction("");
      await loadScript();
      await loadAgentRuns();
      setAgentRun(null);
      setNotice("已接受 AI 改编，并保存为新版本。");
    } catch (e) {
      setErrors([{ path: "<agent>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setAgentBusy(false);
    }
  }

  async function rejectAgentSuggestion() {
    if (!agentRun) return;
    setAgentBusy(true);
    setNotice(null);
    try {
      const rejected = await api.rejectAgentRun(agentRun.id);
      setAgentRun(rejected);
      await loadAgentRuns();
      setNotice("已放弃 AI 改编建议，当前剧本未改变。");
    } catch (e) {
      setErrors([{ path: "<agent>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setAgentBusy(false);
    }
  }

  async function retryAgentSuggestion() {
    if (!agentRun) return;
    setAgentBusy(true);
    setNotice(null);
    try {
      const retried = await api.retryAgentRun(agentRun.id, loadLlmSettings());
      setAgentRun(retried);
      await loadAgentRuns();
      setNotice("已重新生成改编建议，等待确认。");
    } catch (e) {
      setErrors([{ path: "<agent>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setAgentBusy(false);
    }
  }

  if (loadErr) {
    return <div className="card border-red-500/40 text-red-200">加载剧本失败：{loadErr}</div>;
  }

  return (
    <div className="editor-workspace flex h-[calc(100vh-78px)] min-h-0 flex-col gap-2 overflow-hidden">
      <div className="panel shrink-0 overflow-visible px-3 py-2">
        <div className="flex flex-col gap-2 xl:flex-row xl:items-center xl:justify-between">
          <div className="flex min-w-0 flex-col gap-2 md:flex-row md:items-center">
            <div className="min-w-0 md:w-72">
              <div className="text-xs text-ink-500">剧本工作台</div>
              <h1 className="truncate text-lg font-semibold tracking-tight">
              {script?.title ?? "加载中"}
              </h1>
            </div>
            <div className="whitespace-nowrap text-xs text-ink-400">
              {script?.scenes.length ?? 0} 场 · {script?.characters.length ?? 0} 个角色 · {script?.locations.length ?? 0} 个地点
            </div>
            <div className="flex flex-wrap gap-2 md:pl-2">
              <ModeButton active={mode === "scene"} onClick={() => setMode("scene")}>
                场景编辑
              </ModeButton>
              <ModeButton active={mode === "script"} onClick={() => setMode("script")}>
                全剧资料
              </ModeButton>
              <ModeButton active={mode === "yaml"} onClick={() => setMode("yaml")}>
                源码
              </ModeButton>
            </div>
          </div>
          <div className="flex flex-wrap gap-2">
            <button className="btn-ghost px-3 py-1.5 text-xs" onClick={doRepair} disabled={busy || saving || !yaml}>
              自动修复
            </button>
            <button
              className="btn-primary px-3 py-1.5 text-xs"
              onClick={mode === "yaml" ? saveYamlVersion : saveStructuredVersion}
              disabled={busy || saving || (!script && mode !== "yaml")}
            >
              {saving ? "保存中..." : "保存版本"}
            </button>
            <ExportMenu projectId={projectId} compact />
          </div>
        </div>
      </div>

      {notice && (
        <div className="shrink-0 rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
          {notice}
        </div>
      )}

      <div className="grid min-h-0 flex-1 gap-4 xl:grid-cols-[300px_minmax(0,1fr)_360px]">
        <aside className="min-h-0">
          {script && (
            <ResourcePanel
              script={script}
              locationNames={locationNames}
              selectedSceneId={selectedSceneId}
              setSelectedSceneId={setSelectedSceneId}
            />
          )}
        </aside>

        <main className="min-h-0 min-w-0 overflow-hidden">
          {mode === "scene" && script && selectedScene && (
            <SceneEditor
              script={script}
              scene={selectedScene}
              sceneIndex={selectedSceneIndex}
              characterNames={characterNames}
              locationNames={locationNames}
              updateScene={updateScene}
            />
          )}
          {mode === "script" && script && (
            <ScriptOverview script={script} updateScript={updateScript} />
          )}
          {mode === "yaml" && (
            <textarea
              className="input workspace-scroll h-full min-h-0 resize-none overflow-auto font-mono text-xs leading-relaxed"
              value={yaml}
              onChange={(e) => updateYaml(e.target.value)}
              spellCheck={false}
            />
          )}
          {!script && mode !== "yaml" && <div className="card h-full text-sm text-ink-400">加载中...</div>}
        </main>

        <aside className="workspace-scroll min-h-0 space-y-4 overflow-y-auto pr-1">
          <AgentPanel
            agentBusy={agentBusy}
            saving={saving}
            agentInstruction={agentInstruction}
            agentScope={agentScope}
            agentRun={agentRun}
            agentRuns={agentRuns}
            scriptReady={Boolean(script)}
            selectedScene={selectedScene}
            setAgentInstruction={setAgentInstruction}
            setAgentScope={setAgentScope}
            setAgentRun={setAgentRun}
            createAgentSuggestion={createAgentSuggestion}
            acceptAgentSuggestion={acceptAgentSuggestion}
            rejectAgentSuggestion={rejectAgentSuggestion}
            retryAgentSuggestion={retryAgentSuggestion}
          />

          <ValidationPanel busy={busy} errors={errors} />
          <VersionPanel versions={versions} saving={saving} restoreVersion={restoreVersion} />

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

function ModeButton({
  active,
  children,
  onClick,
}: {
  active: boolean;
  children: React.ReactNode;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      className={active ? "btn-primary px-3 py-1.5" : "btn-ghost px-3 py-1.5"}
      onClick={onClick}
    >
      {children}
    </button>
  );
}

function ResourcePanel({
  script,
  locationNames,
  selectedSceneId,
  setSelectedSceneId,
}: {
  script: ScriptDocument;
  locationNames: Record<string, string>;
  selectedSceneId: string;
  setSelectedSceneId: (id: string) => void;
}) {
  return (
    <div className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <div className="panel-header">
        <div className="text-sm font-medium text-ink-100">资源</div>
      </div>
      <div className="border-b border-ink-600/30 px-4 py-3">
        <div className="grid grid-cols-3 gap-2 text-center text-xs">
          <ResourceMetric label="场景" value={script.scenes.length} />
          <ResourceMetric label="角色" value={script.characters.length} />
          <ResourceMetric label="地点" value={script.locations.length} />
        </div>
      </div>
      <div className="workspace-scroll min-h-0 flex-1 overflow-auto p-3">
        <div className="mb-2 text-xs font-medium text-ink-500">场景目录</div>
        <ul className="space-y-2">
          {script.scenes.map((item, index) => (
            <li key={item.id}>
              <button
                type="button"
                className={`w-full rounded-md border px-3 py-2 text-left text-sm transition-colors ${
                  item.id === selectedSceneId
                    ? "border-accent-500/70 bg-accent-500/10 text-ink-50"
                    : "border-ink-600/30 bg-ink-900/50 text-ink-300 hover:border-ink-500 hover:bg-ink-800"
                }`}
                onClick={() => setSelectedSceneId(item.id)}
              >
                <div className="flex items-center justify-between gap-2">
                  <span className="font-medium">{sceneDisplayTitle(item, index)}</span>
                  <span className="text-[11px] text-ink-500">{index + 1}</span>
                </div>
                <div className="mt-1 truncate text-xs text-ink-400">
                  {sceneMeta(item, locationNames)}
                </div>
                {item.purpose && (
                  <div className="mt-2 line-clamp-2 text-xs leading-5 text-ink-500">
                    {item.purpose}
                  </div>
                )}
              </button>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}

function ResourceMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md bg-ink-900/70 px-2 py-2">
      <div className="text-sm font-semibold text-ink-100">{value}</div>
      <div className="mt-0.5 text-ink-500">{label}</div>
    </div>
  );
}

function SceneEditor({
  script,
  scene,
  sceneIndex,
  characterNames,
  locationNames,
  updateScene,
}: {
  script: ScriptDocument;
  scene: ScriptScene;
  sceneIndex: number;
  characterNames: Record<string, string>;
  locationNames: Record<string, string>;
  updateScene: (sceneId: string, patch: (scene: ScriptScene) => ScriptScene) => void;
}) {
  return (
      <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-ink-600/30 p-5">
          <div className="flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="text-xs text-ink-500">当前场景</div>
            <h2 className="mt-1 text-xl font-semibold text-ink-50">
              {sceneDisplayTitle(scene, sceneIndex)}
            </h2>
            <p className="mt-1 text-sm text-ink-400">{sceneMeta(scene, locationNames)}</p>
          </div>
          <div className="text-sm text-ink-500">{script.scenes.length} 场</div>
          </div>
        </div>
        <div className="workspace-scroll min-h-0 flex-1 overflow-auto p-5">
        <div className="grid gap-4 md:grid-cols-[1fr_180px]">
          <Field
            label="场景标题"
            value={scene.title}
            onChange={(value) => updateScene(scene.id, (next) => ({ ...next, title: value }))}
          />
          <Field
            label="时间"
            value={scene.time ?? ""}
            onChange={(value) => updateScene(scene.id, (next) => ({ ...next, time: value }))}
          />
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <TextareaField
            label="场景目的"
            value={scene.purpose}
            onChange={(value) => updateScene(scene.id, (next) => ({ ...next, purpose: value }))}
          />
          <TextareaField
            label="核心冲突"
            value={scene.conflict}
            onChange={(value) => updateScene(scene.id, (next) => ({ ...next, conflict: value }))}
          />
        </div>

        <div className="mt-4 grid gap-4 md:grid-cols-2">
          <TextareaField
            label="入场状态"
            value={scene.entry_state ?? ""}
            onChange={(value) => updateScene(scene.id, (next) => ({ ...next, entry_state: value }))}
          />
          <TextareaField
            label="离场状态"
            value={scene.exit_state ?? ""}
            onChange={(value) => updateScene(scene.id, (next) => ({ ...next, exit_state: value }))}
          />
        </div>

        <div className="mt-5">
          <div className="mb-2 flex items-center justify-between">
            <div className="label mb-0">出场角色</div>
            <span className="text-xs text-ink-500">{scene.characters.length} 人</span>
          </div>
          <div className="flex flex-wrap gap-2">
            {scene.characters.map((id) => (
              <span key={id} className="rounded bg-ink-900 px-2 py-1 text-xs text-ink-300">
                {characterNames[id] ?? "未命名角色"}
              </span>
            ))}
          </div>
        </div>

        <ActionEditor scene={scene} updateScene={updateScene} />
        <DialogueEditor scene={scene} characterNames={characterNames} updateScene={updateScene} />
        </div>
      </section>
  );
}

function ScriptOverview({
  script,
  updateScript,
}: {
  script: ScriptDocument;
  updateScript: (patch: (current: ScriptDocument) => ScriptDocument) => void;
}) {
  return (
    <section className="panel workspace-scroll h-full overflow-auto p-5">
      <div className="grid gap-4 md:grid-cols-[1fr_160px]">
        <Field
          label="剧名"
          value={script.title}
          onChange={(value) => updateScript((current) => ({ ...current, title: value }))}
        />
        <Field
          label="语言"
          value={script.language}
          onChange={(value) => updateScript((current) => ({ ...current, language: value }))}
        />
      </div>
      <div className="mt-4">
        <TextareaField
          label="一句话梗概"
          value={script.logline}
          onChange={(value) => updateScript((current) => ({ ...current, logline: value }))}
        />
      </div>
      <div className="mt-4">
        <TextareaField
          label="主题"
          value={script.themes.join("\n")}
          onChange={(value) =>
            updateScript((current) => ({
              ...current,
              themes: value.split("\n").map((item) => item.trim()).filter(Boolean),
            }))
          }
        />
      </div>

      <div className="mt-6 grid gap-4 lg:grid-cols-2">
        <section>
          <div className="mb-3 text-sm font-medium text-ink-100">角色</div>
          <ul className="space-y-2">
            {script.characters.map((character) => (
              <li key={character.id} className="rounded border border-white/10 bg-white/[0.02] p-3">
                <div className="font-medium">{character.name}</div>
                <div className="mt-2 text-sm text-ink-400">{character.goal || character.motivation || character.arc}</div>
              </li>
            ))}
          </ul>
        </section>
        <section>
          <div className="mb-3 text-sm font-medium text-ink-100">地点</div>
          <ul className="space-y-2">
            {script.locations.map((location) => (
              <li key={location.id} className="rounded border border-white/10 bg-white/[0.02] p-3">
                <div className="font-medium">{location.name}</div>
                {location.description && <div className="mt-2 text-sm text-ink-400">{location.description}</div>}
              </li>
            ))}
          </ul>
        </section>
      </div>
    </section>
  );
}

function ActionEditor({
  scene,
  updateScene,
}: {
  scene: ScriptScene;
  updateScene: (sceneId: string, patch: (scene: ScriptScene) => ScriptScene) => void;
}) {
  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-ink-100">动作</div>
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-xs"
          onClick={() => updateScene(scene.id, (next) => ({ ...next, action: [...next.action, ""] }))}
        >
          添加
        </button>
      </div>
      <ul className="space-y-2">
        {scene.action.map((line, index) => (
          <li key={index} className="flex gap-2">
            <textarea
              className="input min-h-[52px] text-sm"
              value={line}
              onChange={(e) =>
                updateScene(scene.id, (next) => ({
                  ...next,
                  action: next.action.map((item, i) => (i === index ? e.target.value : item)),
                }))
              }
            />
            <button
              type="button"
              className="btn-ghost h-10 px-2 text-xs"
              onClick={() =>
                updateScene(scene.id, (next) => ({
                  ...next,
                  action: next.action.filter((_, i) => i !== index),
                }))
              }
            >
              删除
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}

function DialogueEditor({
  scene,
  characterNames,
  updateScene,
}: {
  scene: ScriptScene;
  characterNames: Record<string, string>;
  updateScene: (sceneId: string, patch: (scene: ScriptScene) => ScriptScene) => void;
}) {
  function updateLine(index: number, patch: Partial<DialogueLine>) {
    updateScene(scene.id, (next) => ({
      ...next,
      dialogue: next.dialogue.map((line, i) => (i === index ? { ...line, ...patch } : line)),
    }));
  }

  return (
    <div className="mt-6">
      <div className="mb-3 flex items-center justify-between">
        <div className="text-sm font-medium text-ink-100">对白</div>
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-xs"
          onClick={() =>
            updateScene(scene.id, (next) => ({
              ...next,
              dialogue: [...next.dialogue, { speaker: next.characters[0] || "", line: "" }],
            }))
          }
        >
          添加
        </button>
      </div>
      <ul className="space-y-3">
        {scene.dialogue.map((line, index) => (
          <li key={index} className="rounded border border-white/10 bg-white/[0.02] p-3">
            <div className="grid gap-3 md:grid-cols-[180px_1fr]">
              <select
                className="input"
                value={line.speaker}
                onChange={(e) => updateLine(index, { speaker: e.target.value })}
              >
                {scene.characters.map((id) => (
                  <option key={id} value={id}>
                    {characterNames[id] ?? "未命名角色"}
                  </option>
                ))}
              </select>
              <input
                className="input"
                value={line.emotion ?? ""}
                onChange={(e) => updateLine(index, { emotion: e.target.value })}
                placeholder="情绪"
              />
            </div>
            <textarea
              className="input mt-3 min-h-[72px] text-sm"
              value={line.line}
              onChange={(e) => updateLine(index, { line: e.target.value })}
            />
            <div className="mt-3 flex gap-2">
              <input
                className="input"
                value={line.subtext ?? ""}
                onChange={(e) => updateLine(index, { subtext: e.target.value })}
                placeholder="潜台词"
              />
              <button
                type="button"
                className="btn-ghost px-2 text-xs"
                onClick={() =>
                  updateScene(scene.id, (next) => ({
                    ...next,
                    dialogue: next.dialogue.filter((_, i) => i !== index),
                  }))
                }
              >
                删除
              </button>
            </div>
          </li>
        ))}
      </ul>
    </div>
  );
}

function Field({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <input className="input" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

function TextareaField({
  label,
  value,
  onChange,
}: {
  label: string;
  value: string;
  onChange: (value: string) => void;
}) {
  return (
    <div>
      <label className="label">{label}</label>
      <textarea className="input min-h-[96px] text-sm leading-relaxed" value={value} onChange={(e) => onChange(e.target.value)} />
    </div>
  );
}

const AGENT_INTENT_PRESETS = [
  "强化前三秒钩子",
  "减少解释性对白",
  "加强人物冲突",
  "对白更口语",
  "节奏更紧",
];

const AGENT_CONSTRAINT_PRESETS = [
  "不改变人物关系",
  "不改变结局",
  "不新增角色",
  "保留核心线索",
];

function AgentPanel({
  agentBusy,
  saving,
  agentInstruction,
  agentScope,
  agentRun,
  agentRuns,
  scriptReady,
  selectedScene,
  setAgentInstruction,
  setAgentScope,
  setAgentRun,
  createAgentSuggestion,
  acceptAgentSuggestion,
  rejectAgentSuggestion,
  retryAgentSuggestion,
}: {
  agentBusy: boolean;
  saving: boolean;
  agentInstruction: string;
  agentScope: "current_scene" | "whole_script";
  agentRun: AgentRunSummary | null;
  agentRuns: AgentRunSummary[];
  scriptReady: boolean;
  selectedScene: ScriptScene | null;
  setAgentInstruction: (value: string) => void;
  setAgentScope: (value: "current_scene" | "whole_script") => void;
  setAgentRun: (value: AgentRunSummary) => void;
  createAgentSuggestion: () => void;
  acceptAgentSuggestion: (patchIndexes?: number[]) => void;
  rejectAgentSuggestion: () => void;
  retryAgentSuggestion: () => void;
}) {
  const patchCount = agentRun?.patch?.length ?? 0;
  const [selectedPatchIndexes, setSelectedPatchIndexes] = useState<number[]>([]);

  useEffect(() => {
    setSelectedPatchIndexes(agentRun?.patch?.map((_, index) => index) ?? []);
  }, [agentRun?.id, agentRun?.patch]);

  function togglePatchIndex(index: number) {
    setSelectedPatchIndexes((current) =>
      current.includes(index)
        ? current.filter((item) => item !== index)
        : [...current, index].sort((a, b) => a - b),
    );
  }

  function setAllPatchIndexes(selected: boolean) {
    setSelectedPatchIndexes(selected ? agentRun?.patch?.map((_, index) => index) ?? [] : []);
  }

  function appendInstruction(text: string) {
    const current = agentInstruction.trim();
    setAgentInstruction(current ? `${current}；${text}` : text);
  }

  return (
    <div className="card space-y-3">
      <div className="label">AI 改编助手</div>
      <div className="space-y-2">
        <div className="text-xs text-ink-500">改编重点</div>
        <div className="flex flex-wrap gap-1.5">
          {AGENT_INTENT_PRESETS.map((item) => (
            <button
              key={item}
              type="button"
              className="rounded-md border border-ink-600/40 bg-ink-900 px-2 py-1 text-xs text-ink-300 hover:border-accent-500/60 hover:text-ink-50"
              onClick={() => appendInstruction(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      <div className="space-y-2">
        <div className="text-xs text-ink-500">约束</div>
        <div className="flex flex-wrap gap-1.5">
          {AGENT_CONSTRAINT_PRESETS.map((item) => (
            <button
              key={item}
              type="button"
              className="rounded-md border border-ink-600/40 bg-ink-900 px-2 py-1 text-xs text-ink-300 hover:border-accent-500/60 hover:text-ink-50"
              onClick={() => appendInstruction(item)}
            >
              {item}
            </button>
          ))}
        </div>
      </div>
      <textarea
        className="input min-h-[96px] text-sm"
        value={agentInstruction}
        onChange={(e) => setAgentInstruction(e.target.value)}
        placeholder="例如：强化前三秒钩子；减少解释性对白；不改变人物关系。"
      />
      <div className="rounded-md border border-ink-600/40 bg-ink-900 p-2">
        <div className="mb-2 text-xs text-ink-500">改编范围</div>
        <div className="grid grid-cols-2 gap-2">
          <button
            type="button"
            className={agentScope === "current_scene" ? "btn-primary px-2 py-1.5 text-xs" : "btn-ghost px-2 py-1.5 text-xs"}
            onClick={() => setAgentScope("current_scene")}
            disabled={!selectedScene}
          >
            当前场景
          </button>
          <button
            type="button"
            className={agentScope === "whole_script" ? "btn-primary px-2 py-1.5 text-xs" : "btn-ghost px-2 py-1.5 text-xs"}
            onClick={() => setAgentScope("whole_script")}
          >
            全剧
          </button>
        </div>
        <div className="mt-2 truncate text-xs text-ink-400">
          {agentScope === "current_scene"
            ? selectedScene
              ? selectedScene.title
              : "请先选择一个场景"
            : "将基于当前版本生成整体改编建议"}
        </div>
      </div>
      <button
        className="btn-ghost w-full"
        onClick={createAgentSuggestion}
        disabled={agentBusy || saving || !scriptReady || !agentInstruction.trim() || (agentScope === "current_scene" && !selectedScene)}
      >
        {agentBusy ? "生成中..." : "生成建议"}
      </button>
      {agentRuns.length > 0 && (
        <div className="rounded-md border border-ink-600/40 bg-ink-950/40 p-2">
          <div className="mb-2 flex items-center justify-between text-xs">
            <span className="text-ink-500">最近建议</span>
            <span className="text-ink-600">{agentRuns.length}</span>
          </div>
          <ul className="space-y-1">
            {agentRuns.slice(0, 5).map((run) => (
              <li key={run.id}>
                <button
                  type="button"
                  className={`w-full rounded px-2 py-1.5 text-left text-xs transition-colors ${
                    run.id === agentRun?.id
                      ? "bg-accent-500/10 text-ink-50"
                      : "text-ink-400 hover:bg-ink-800 hover:text-ink-100"
                  }`}
                  onClick={() => setAgentRun(run)}
                >
                  <div className="flex items-center justify-between gap-2">
                    <span className="truncate">{run.user_prompt}</span>
                    <span className="shrink-0 text-[10px] text-ink-500">
                      {formatAgentStatus(run.status)}
                    </span>
                  </div>
                  <div className="mt-0.5 text-[10px] text-ink-600">
                    {formatDate(run.created_at)}
                  </div>
                </button>
              </li>
            ))}
          </ul>
        </div>
      )}
      {agentRun && (
        <div className="space-y-4 rounded border border-white/10 bg-ink-900/60 p-3 text-xs">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-medium text-ink-100">{formatAgentStatus(agentRun.status)}</div>
              <div className="mt-1 text-ink-500">{formatAgentModel(agentRun.model)}</div>
            </div>
            <span className="rounded bg-ink-800 px-2 py-1 font-mono text-ink-400">
              AI 助手
            </span>
          </div>
          {agentRun.error_message && (
            <div className="rounded border border-amber-500/30 bg-amber-500/10 px-2 py-1.5 text-amber-200">
              {agentRun.error_message}
            </div>
          )}
          {agentRun.plan && (
            <ol className="space-y-1 text-ink-300">
              {agentRun.plan.map((item, index) => (
                <li key={index} className="flex gap-2">
                  <span className="text-ink-600">{index + 1}</span>
                  <span>{String(item)}</span>
                </li>
              ))}
            </ol>
          )}
          {agentRun.patch && agentRun.patch.length > 0 && (
            <div className="space-y-2">
              {agentRun.status === "waiting_review" && patchCount > 1 && (
                <div className="flex items-center justify-between border-t border-white/10 pt-3 text-[11px] text-ink-400">
                  <span>
                    已选 {selectedPatchIndexes.length}/{patchCount} 项
                  </span>
                  <div className="flex gap-2">
                    <button
                      type="button"
                      className="text-accent-400 hover:text-accent-500"
                      onClick={() => setAllPatchIndexes(true)}
                    >
                      全选
                    </button>
                    <button
                      type="button"
                      className="text-ink-400 hover:text-ink-200"
                      onClick={() => setAllPatchIndexes(false)}
                    >
                      清空
                    </button>
                  </div>
                </div>
              )}
              <ul className="space-y-2">
              {agentRun.patch.map((item, index) => (
                <li key={index} className="rounded border border-white/10 bg-white/[0.02] p-2">
                  <div className="flex items-center justify-between gap-2">
                    <label className="flex min-w-0 items-center gap-2 text-ink-200">
                      {agentRun.status === "waiting_review" && patchCount > 1 && (
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 accent-accent-500"
                          checked={selectedPatchIndexes.includes(index)}
                          onChange={() => togglePatchIndex(index)}
                        />
                      )}
                      <span className="truncate">{item.scene_title || `变更 ${index + 1}`}</span>
                    </label>
                    <span className="rounded bg-ink-800 px-1.5 py-0.5 font-mono text-[10px] uppercase text-ink-400">
                      {formatPatchField(item)}
                    </span>
                  </div>
                  <PatchValue label="修改前" value={item.before} />
                  <PatchValue label="修改后" value={item.after ?? item.value} />
                </li>
              ))}
              </ul>
            </div>
          )}
          {agentRun.status === "waiting_review" && (
            <div className="grid grid-cols-2 gap-2 border-t border-white/10 pt-3">
              <button
                className="btn-primary col-span-2"
                onClick={() =>
                  acceptAgentSuggestion(patchCount > 1 ? selectedPatchIndexes : undefined)
                }
                disabled={agentBusy || saving || (patchCount > 1 && selectedPatchIndexes.length === 0)}
              >
                {patchCount > 1 ? "接受选中并保存" : "接受并保存"}
              </button>
              <button className="btn-ghost" onClick={retryAgentSuggestion} disabled={agentBusy || saving}>
                重新生成
              </button>
              <button className="btn-ghost" onClick={rejectAgentSuggestion} disabled={agentBusy || saving}>
                放弃
              </button>
            </div>
          )}
          {agentRun.status !== "waiting_review" && (
            <button className="btn-ghost w-full" onClick={retryAgentSuggestion} disabled={agentBusy || saving}>
              重新生成建议
            </button>
          )}
        </div>
      )}
    </div>
  );
}

function ValidationPanel({ busy, errors }: { busy: boolean; errors: ValidationError[] }) {
  return (
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
              <span className="text-ink-400">结构字段</span> - {e.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

function VersionPanel({
  versions,
  saving,
  restoreVersion,
}: {
  versions: ScriptVersionSummary[];
  saving: boolean;
  restoreVersion: (versionId: string) => void;
}) {
  return (
    <div className="card">
      <div className="label">版本历史</div>
      {versions.length === 0 ? (
        <div className="text-sm text-ink-400">暂无历史版本。</div>
      ) : (
        <ul className="space-y-2 text-xs">
          {versions.map((version, index) => (
            <li key={version.id} className="rounded border border-white/10 bg-white/[0.02] p-2">
              <div className="flex items-center justify-between gap-2">
                <span className="font-mono text-ink-200">{index === 0 ? "当前" : `历史 ${index}`}</span>
                <span className={version.validation_status === "valid" ? "text-emerald-300" : "text-amber-300"}>
                  {formatValidation(version.validation_status)}
                </span>
              </div>
              <div className="mt-2 space-y-1 text-ink-400">
                <div>{formatVersionLabel(version.label, version.source_type)}</div>
                <div>来源：{formatSource(version.source_type)}</div>
                {version.notes && <div>备注：{version.notes}</div>}
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
  );
}

function sceneDisplayTitle(scene: ScriptScene, index: number) {
  const title = scene.title.trim();
  const sceneNumber = `第 ${index + 1} 场`;
  if (!title) return sceneNumber;

  const withoutGeneratedNumber = title
    .replace(/^第\s*[\d一二三四五六七八九十百千万两〇零]+\s*场\s*[：:、.-]?\s*/, "")
    .trim();

  return withoutGeneratedNumber ? `${sceneNumber}：${withoutGeneratedNumber}` : sceneNumber;
}

function sceneMeta(scene: ScriptScene, locationNames: Record<string, string>) {
  const location = locationNames[scene.location_id];
  const parts = [location, scene.time].filter(Boolean);
  return parts.length > 0 ? parts.join(" / ") : "未设置地点和时间";
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

function formatVersionLabel(label: string | null, sourceType: string) {
  if (label === "AI generated draft") return "AI 生成初稿";
  return label || formatSource(sourceType);
}

function formatValidation(value: string) {
  return (
    {
      valid: "通过",
      invalid: "待处理",
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

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}

function formatAgentModel(value: string | null) {
  if (value === "local-rule-patch-v1") return "本地建议已生成";
  if (value === "openai-compatible-agent") return "模型改编建议已生成";
  return "改编建议已生成";
}

function formatPatchField(item: AgentPatchOperation) {
  return (
    {
      title: "标题",
      purpose: "目的",
      conflict: "冲突",
      entry_state: "入场",
      exit_state: "离场",
      action: "动作",
      dialogue: "对白",
      "adaptation_notes/reason": "说明",
      "adaptation_notes/fidelity": "方式",
    }[item.field || String(item.path || "").split("/script/scenes/").pop()?.split("/").slice(1).join("/") || ""] ?? "修改"
  );
}

function PatchValue({ label, value }: { label: string; value: unknown }) {
  return (
    <div className="mt-2">
      <div className="mb-1 text-[11px] text-ink-500">{label}</div>
      <div className="max-h-28 overflow-auto rounded bg-ink-950/70 px-2 py-1.5 font-mono text-[11px] leading-relaxed text-ink-300">
        {formatPatchValue(value)}
      </div>
    </div>
  );
}

function formatPatchValue(value: AgentPatchOperation[keyof AgentPatchOperation]) {
  if (value === null || typeof value === "undefined" || value === "") return "空";
  if (typeof value === "string") return value;
  if (Array.isArray(value)) {
    if (value.length === 0) return "空列表";
    if (value.every((item) => typeof item === "string")) {
      return value.map((item, index) => `${index + 1}. ${item}`).join("\n");
    }
    if (value.every(isDialoguePatchValue)) {
      return value
        .map((item) => {
          const emotion = item.emotion ? `（${item.emotion}）` : "";
          const subtext = item.subtext ? `\n  潜台词：${item.subtext}` : "";
          return `${item.speaker}${emotion}：${item.line}${subtext}`;
        })
        .join("\n");
    }
  }
  return JSON.stringify(value, null, 2);
}

function isDialoguePatchValue(value: unknown): value is DialogueLine {
  return (
    typeof value === "object" &&
    value !== null &&
    "speaker" in value &&
    "line" in value &&
    typeof (value as DialogueLine).speaker === "string" &&
    typeof (value as DialogueLine).line === "string"
  );
}
