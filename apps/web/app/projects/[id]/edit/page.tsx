"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { useParams } from "next/navigation";
import { AuthRequiredMessage, isAuthRequiredMessage } from "@/components/AuthRequiredMessage";
import { AgentPanel } from "@/components/editor/AgentPanel";
import { ValidationPanel } from "@/components/editor/ValidationPanel";
import { DiffPanel, VersionPanel } from "@/components/editor/VersionPanels";
import { ExportMenu } from "@/components/ExportMenu";
import { api } from "@/lib/api";
import { loadLlmSettings } from "@/lib/llm-settings";
import type {
  AgentRunSummary,
  DialogueLine,
  ScriptCharacter,
  ScriptDocument,
  ScriptLocation,
  ScriptScene,
  ScriptVersionSummary,
  ValidationError,
  VersionDiffSummary,
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
  const [agentInstructionFocused, setAgentInstructionFocused] = useState(false);
  const [agentScope, setAgentScope] = useState<"current_scene" | "whole_script">("current_scene");
  const [agentRun, setAgentRun] = useState<AgentRunSummary | null>(null);
  const [agentRuns, setAgentRuns] = useState<AgentRunSummary[]>([]);
  const [versionDiff, setVersionDiff] = useState<VersionDiffSummary | null>(null);
  const [diffBusy, setDiffBusy] = useState(false);
  const [loadErr, setLoadErr] = useState<string | null>(null);
  const [notice, setNotice] = useState<string | null>(null);
  const [snapshotName, setSnapshotName] = useState("");

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

  const loadScript = useCallback(async ({ restoreAgentRun = true }: { restoreAgentRun?: boolean } = {}) => {
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
    if (restoreAgentRun) {
      setAgentRun((current) => current ?? nextAgentRuns.find((run) => run.status === "waiting_review") ?? null);
    }
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
      const label = snapshotLabel(snapshotName);
      const saved = await api.saveStructuredVersion(projectId, script, {
        label,
        notes: "用户从剧本编辑界面保存快照。",
      });
      setVersionDiff(null);
      await loadScript();
      setSnapshotName("");
      setNotice(saved.validation_status === "valid" ? `已保存快照：${label}` : `已保存快照：${label}，但仍有结构问题需要处理。`);
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
      const label = snapshotLabel(snapshotName);
      const saved = await api.saveVersion(projectId, yaml, {
        label,
        notes: "用户从 YAML 源码保存快照。",
      });
      setYaml(saved.yaml_content);
      setVersionDiff(null);
      await loadScript();
      setSnapshotName("");
      setNotice(saved.validation_status === "valid" ? `已保存快照：${label}` : `已保存快照：${label}，但仍有结构问题需要处理。`);
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
      setVersionDiff(null);
      await loadScript();
      setNotice("已回退到所选快照，并创建了新的当前快照。");
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
      setVersionDiff(null);
      await loadScript({ restoreAgentRun: false });
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

  async function compareVersion(versionId: string) {
    setDiffBusy(true);
    setNotice(null);
    try {
      const diff = await api.getVersionDiff(projectId, versionId);
      setVersionDiff(diff);
    } catch (e) {
      setErrors([{ path: "<diff>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setDiffBusy(false);
    }
  }

  if (loadErr) {
    if (isAuthRequiredMessage(loadErr)) return <AuthRequiredMessage />;
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
              {saving ? "保存中..." : "保存快照"}
            </button>
            <ExportMenu projectId={projectId} compact />
          </div>
        </div>
      </div>

      {notice && (
        <div className="flex shrink-0 items-center justify-between gap-3 rounded border border-emerald-500/40 bg-emerald-500/10 px-3 py-2 text-sm text-emerald-200">
          <span className="min-w-0">{notice}</span>
          <button
            type="button"
            className="shrink-0 rounded px-1.5 text-lg leading-none text-emerald-300 hover:bg-emerald-500/10 hover:text-emerald-100"
            onClick={() => setNotice(null)}
            aria-label="关闭通知"
            title="关闭通知"
          >
            ×
          </button>
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
            agentInstructionFocused={agentInstructionFocused}
            agentScope={agentScope}
            agentRun={agentRun}
            agentRuns={agentRuns}
            scriptReady={Boolean(script)}
            selectedScene={selectedScene}
            selectedSceneLabel={selectedScene ? sceneDisplayTitle(selectedScene, selectedSceneIndex) : null}
            characterNames={characterNames}
            setAgentInstruction={setAgentInstruction}
            setAgentInstructionFocused={setAgentInstructionFocused}
            setAgentScope={setAgentScope}
            setAgentRun={setAgentRun}
            createAgentSuggestion={createAgentSuggestion}
            acceptAgentSuggestion={acceptAgentSuggestion}
            rejectAgentSuggestion={rejectAgentSuggestion}
            retryAgentSuggestion={retryAgentSuggestion}
          />

          <ValidationPanel busy={busy} errors={errors} />
          <VersionPanel
            versions={versions}
            saving={saving}
            diffBusy={diffBusy}
            snapshotName={snapshotName}
            setSnapshotName={setSnapshotName}
            canSaveSnapshot={Boolean(script) || mode === "yaml"}
            saveSnapshot={mode === "yaml" ? saveYamlVersion : saveStructuredVersion}
            restoreVersion={restoreVersion}
            compareVersion={compareVersion}
          />
          <DiffPanel
            diff={versionDiff}
            busy={diffBusy}
            characterNames={characterNames}
            onClose={() => setVersionDiff(null)}
          />

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
        <div className="grid gap-4 md:grid-cols-[1fr_180px_220px]">
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
          <div>
            <label className="label">地点</label>
            <select
              className="input"
              value={scene.location_id}
              onChange={(e) =>
                updateScene(scene.id, (next) => ({ ...next, location_id: e.target.value }))
              }
            >
              {script.locations.map((location) => (
                <option key={location.id} value={location.id}>
                  {location.name || location.id}
                </option>
              ))}
            </select>
          </div>
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
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {script.characters.map((character) => {
              const checked = scene.characters.includes(character.id);
              const appearsInDialogue = scene.dialogue.some((line) => line.speaker === character.id);
              const removalDisabled = checked && (scene.characters.length <= 1 || appearsInDialogue);
              return (
                <label
                  key={character.id}
                  className={`flex items-center gap-2 rounded-md border px-2.5 py-2 text-sm ${
                    checked
                      ? "border-accent-500/50 bg-accent-500/10 text-ink-100"
                      : "border-ink-600/40 bg-ink-900 text-ink-400"
                  }`}
                  title={
                    removalDisabled
                      ? appearsInDialogue
                        ? "该角色已有对白，先调整对白 speaker 后再移出场景"
                        : "场景至少需要一个角色"
                      : undefined
                  }
                >
                  <input
                    type="checkbox"
                    className="h-3.5 w-3.5 accent-accent-500"
                    checked={checked}
                    disabled={removalDisabled}
                    onChange={(e) =>
                      updateScene(scene.id, (next) => ({
                        ...next,
                        characters: e.target.checked
                          ? uniqueStrings([...next.characters, character.id])
                          : next.characters.filter((id) => id !== character.id),
                      }))
                    }
                  />
                  <span className="min-w-0 truncate">{characterNames[character.id] ?? "未命名角色"}</span>
                </label>
              );
            })}
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
  const usedCharacterIds = useMemo(() => {
    const ids = new Set<string>();
    for (const scene of script.scenes) {
      for (const id of scene.characters) ids.add(id);
      for (const line of scene.dialogue) ids.add(line.speaker);
    }
    return ids;
  }, [script.scenes]);

  const usedLocationIds = useMemo(() => {
    return new Set(script.scenes.map((scene) => scene.location_id).filter(Boolean));
  }, [script.scenes]);

  function updateCharacter(characterId: string, patch: Partial<ScriptCharacter>) {
    updateScript((current) => ({
      ...current,
      characters: current.characters.map((character) =>
        character.id === characterId ? compactCharacter({ ...character, ...patch }) : character,
      ),
    }));
  }

  function renameCharacter(characterId: string, nextId: string) {
    const trimmed = normalizeIdInput(nextId);
    updateScript((current) => ({
      ...current,
      characters: current.characters.map((character) =>
        character.id === characterId ? { ...character, id: trimmed } : character,
      ),
      scenes: current.scenes.map((scene) => ({
        ...scene,
        characters: scene.characters.map((id) => (id === characterId ? trimmed : id)),
        dialogue: scene.dialogue.map((line) => ({
          ...line,
          speaker: line.speaker === characterId ? trimmed : line.speaker,
        })),
      })),
    }));
  }

  function addCharacter() {
    updateScript((current) => {
      const id = nextAvailableId("char_new", current.characters.map((item) => item.id));
      return {
        ...current,
        characters: [
          ...current.characters,
          { id, name: `新角色 ${current.characters.length + 1}`, role: "supporting" },
        ],
      };
    });
  }

  function deleteCharacter(characterId: string) {
    if (usedCharacterIds.has(characterId)) return;
    updateScript((current) => ({
      ...current,
      characters: current.characters.filter((character) => character.id !== characterId),
    }));
  }

  function updateLocation(locationId: string, patch: Partial<ScriptLocation>) {
    updateScript((current) => ({
      ...current,
      locations: current.locations.map((location) =>
        location.id === locationId ? compactLocation({ ...location, ...patch }) : location,
      ),
    }));
  }

  function renameLocation(locationId: string, nextId: string) {
    const trimmed = normalizeIdInput(nextId);
    updateScript((current) => ({
      ...current,
      locations: current.locations.map((location) =>
        location.id === locationId ? { ...location, id: trimmed } : location,
      ),
      scenes: current.scenes.map((scene) => ({
        ...scene,
        location_id: scene.location_id === locationId ? trimmed : scene.location_id,
      })),
    }));
  }

  function addLocation() {
    updateScript((current) => {
      const id = nextAvailableId("loc_new", current.locations.map((item) => item.id));
      return {
        ...current,
        locations: [...current.locations, { id, name: `新地点 ${current.locations.length + 1}` }],
      };
    });
  }

  function deleteLocation(locationId: string) {
    if (usedLocationIds.has(locationId)) return;
    updateScript((current) => ({
      ...current,
      locations: current.locations.filter((location) => location.id !== locationId),
    }));
  }

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
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium text-ink-100">角色</div>
            <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={addCharacter}>
              添加角色
            </button>
          </div>
          <ul className="space-y-2">
            {script.characters.map((character) => (
              <li key={character.id} className="rounded border surface-line surface-soft p-3">
                <CharacterCard
                  character={character}
                  isReferenced={usedCharacterIds.has(character.id)}
                  onChange={(patch) => updateCharacter(character.id, patch)}
                  onRename={(value) => renameCharacter(character.id, value)}
                  onDelete={() => deleteCharacter(character.id)}
                />
              </li>
            ))}
          </ul>
        </section>
        <section className="space-y-3">
          <div className="flex items-center justify-between gap-3">
            <div className="text-sm font-medium text-ink-100">地点</div>
            <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={addLocation}>
              添加地点
            </button>
          </div>
          <ul className="space-y-2">
            {script.locations.map((location) => (
              <li key={location.id} className="rounded border surface-line surface-soft p-3">
                <LocationCard
                  location={location}
                  isReferenced={usedLocationIds.has(location.id)}
                  onChange={(patch) => updateLocation(location.id, patch)}
                  onRename={(value) => renameLocation(location.id, value)}
                  onDelete={() => deleteLocation(location.id)}
                />
              </li>
            ))}
          </ul>
        </section>
      </div>
    </section>
  );
}

function CharacterCard({
  character,
  isReferenced,
  onChange,
  onRename,
  onDelete,
}: {
  character: ScriptCharacter;
  isReferenced: boolean;
  onChange: (patch: Partial<ScriptCharacter>) => void;
  onRename: (value: string) => void;
  onDelete: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[1fr_140px]">
        <Field label="角色名" value={character.name} onChange={(value) => onChange({ name: value })} />
        <div>
          <label className="label">类型</label>
          <select
            className="input"
            value={character.role ?? ""}
            onChange={(e) =>
              onChange({ role: (e.target.value || undefined) as ScriptCharacter["role"] })
            }
          >
            <option value="">未设置</option>
            <option value="protagonist">主角</option>
            <option value="antagonist">反派</option>
            <option value="supporting">配角</option>
            <option value="mentor">导师</option>
            <option value="foil">映衬角色</option>
            <option value="other">其他</option>
          </select>
        </div>
      </div>
      <Field label="角色 ID" value={character.id} onChange={onRename} />
      <div className="grid gap-3 md:grid-cols-2">
        <TextareaField
          label="目标"
          value={character.goal ?? ""}
          onChange={(value) => onChange({ goal: value || undefined })}
        />
        <TextareaField
          label="动机"
          value={character.motivation ?? ""}
          onChange={(value) => onChange({ motivation: value || undefined })}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <TextareaField
          label="性格"
          value={character.personality ?? ""}
          onChange={(value) => onChange({ personality: value || undefined })}
        />
        <TextareaField
          label="关系"
          value={character.relationship ?? ""}
          onChange={(value) => onChange({ relationship: value || undefined })}
        />
      </div>
      <div className="grid gap-3 md:grid-cols-2">
        <TextareaField
          label="人物弧光"
          value={character.arc ?? ""}
          onChange={(value) => onChange({ arc: value || undefined })}
        />
        <TextareaField
          label="说话风格"
          value={character.speech_style ?? ""}
          onChange={(value) => onChange({ speech_style: value || undefined })}
        />
      </div>
      <div className="flex items-center justify-between gap-3 border-t surface-line pt-3">
        <span className="text-xs text-ink-500">
          {isReferenced ? "已被场景或对白引用" : "未被引用"}
        </span>
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-xs"
          onClick={onDelete}
          disabled={isReferenced}
          title={isReferenced ? "先从场景和对白中移除引用后才能删除" : undefined}
        >
          删除角色
        </button>
      </div>
    </div>
  );
}

function LocationCard({
  location,
  isReferenced,
  onChange,
  onRename,
  onDelete,
}: {
  location: ScriptLocation;
  isReferenced: boolean;
  onChange: (patch: Partial<ScriptLocation>) => void;
  onRename: (value: string) => void;
  onDelete: () => void;
}) {
  return (
    <div className="space-y-3">
      <Field label="地点名" value={location.name} onChange={(value) => onChange({ name: value })} />
      <Field label="地点 ID" value={location.id} onChange={onRename} />
      <TextareaField
        label="描述"
        value={location.description ?? ""}
        onChange={(value) => onChange({ description: value || undefined })}
      />
      <div className="flex items-center justify-between gap-3 border-t surface-line pt-3">
        <span className="text-xs text-ink-500">
          {isReferenced ? "已被场景引用" : "未被引用"}
        </span>
        <button
          type="button"
          className="btn-ghost px-2 py-1 text-xs"
          onClick={onDelete}
          disabled={isReferenced}
          title={isReferenced ? "先把相关场景切换到其他地点后才能删除" : undefined}
        >
          删除地点
        </button>
      </div>
    </div>
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
          <li key={index} className="rounded border surface-line surface-soft p-3">
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

function snapshotLabel(value: string) {
  const trimmed = value.trim();
  if (trimmed) return trimmed;
  return `剧本快照 ${new Date().toLocaleString()}`;
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function normalizeIdInput(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "_")
    .replace(/_+/g, "_");
}

function nextAvailableId(base: string, existingIds: string[]) {
  const used = new Set(existingIds);
  if (!used.has(base)) return base;
  let index = 2;
  while (used.has(`${base}_${index}`)) index += 1;
  return `${base}_${index}`;
}

function compactCharacter(character: ScriptCharacter): ScriptCharacter {
  return {
    id: character.id,
    name: character.name,
    role: character.role || undefined,
    goal: character.goal || undefined,
    motivation: character.motivation || undefined,
    personality: character.personality || undefined,
    relationship: character.relationship || undefined,
    arc: character.arc || undefined,
    speech_style: character.speech_style || undefined,
  };
}

function compactLocation(location: ScriptLocation): ScriptLocation {
  return {
    id: location.id,
    name: location.name,
    description: location.description || undefined,
  };
}
