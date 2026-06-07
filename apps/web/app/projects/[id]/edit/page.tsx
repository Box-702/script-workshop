"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  ScriptBeat,
  ScriptCharacter,
  ScriptDocument,
  ScriptLocation,
  ScriptScene,
  ScriptVersionSummary,
  ValidationError,
  VersionDiffSummary,
} from "@/lib/types";

type EditorMode = "script" | "scene" | "yaml";
type EntityPrefix = "char" | "loc";

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
  const [validating, setValidating] = useState(false);
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
  const structuredValidationSeq = useRef(0);

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
    const validation = await api.validateScript(jsonDoc.script);
    setErrors(validation.errors);
  }, [projectId, loadVersions, loadAgentRuns]);

  useEffect(() => {
    loadScript().catch((e) => setLoadErr((e as Error).message));
  }, [loadScript]);

  useEffect(() => {
    if (!script || mode === "yaml") {
      structuredValidationSeq.current += 1;
      setValidating(false);
      return;
    }
    const timeout = window.setTimeout(() => {
      const seq = structuredValidationSeq.current + 1;
      structuredValidationSeq.current = seq;
      setValidating(true);
      api.validateScript(script)
        .then((validation) => {
          if (structuredValidationSeq.current === seq) setErrors(validation.errors);
        })
        .catch((e) => {
          if (structuredValidationSeq.current === seq) {
            setErrors([{ path: "<script>", message: (e as Error).message, severity: "error" }]);
          }
        })
        .finally(() => {
          if (structuredValidationSeq.current === seq) setValidating(false);
        });
    }, 350);
    return () => window.clearTimeout(timeout);
  }, [script, mode]);

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

  function addSceneAfter(afterSceneId?: string, options: { continueFromScene?: boolean } = {}) {
    if (!script) return;
    const id = nextNumberedId("scene", script.scenes.map((scene) => scene.id));

    updateScript((current) => {
      const prepared = ensureSceneDependencies(current);
      const currentSourceIndex = afterSceneId
        ? prepared.scenes.findIndex((scene) => scene.id === afterSceneId)
        : prepared.scenes.length - 1;
      const insertIndex = currentSourceIndex >= 0 ? currentSourceIndex + 1 : prepared.scenes.length;
      const sourceScene = currentSourceIndex >= 0 ? prepared.scenes[currentSourceIndex] : undefined;
      const draft = createDraftScene(id, prepared, sourceScene, options.continueFromScene);
      const scenes = [...prepared.scenes];
      scenes.splice(insertIndex, 0, draft);
      return { ...prepared, scenes };
    });
    setSelectedSceneId(id);
    setMode("scene");
  }

  function deleteScene(sceneId: string) {
    if (!script || script.scenes.length <= 1) return;
    const index = script.scenes.findIndex((scene) => scene.id === sceneId);
    const fallbackSceneId = script.scenes[index + 1]?.id ?? script.scenes[index - 1]?.id ?? "";
    updateScript((current) => ({
      ...current,
      scenes: current.scenes.filter((scene) => scene.id !== sceneId),
    }));
    setSelectedSceneId(fallbackSceneId);
    setMode("scene");
  }

  function addCharacterToScene(sceneId: string) {
    if (!script) return;
    const id = nextEntityIdFromNameFallback(
      "char",
      `新角色 ${script.characters.length + 1}`,
      script.characters.map((character) => character.id),
    );
    updateScript((current) => ({
      ...current,
      characters: [
        ...current.characters,
        { id, name: `新角色 ${current.characters.length + 1}`, role: "supporting" },
      ],
      scenes: current.scenes.map((scene) =>
        scene.id === sceneId
          ? { ...scene, characters: uniqueStrings([...scene.characters, id]) }
          : scene,
      ),
    }));
  }

  function updateYaml(next: string) {
    setYaml(next);
    setNotice(null);
    void revalidate(next);
  }

  async function showYamlMode() {
    if (!script) {
      setMode("yaml");
      return;
    }
    setMode("yaml");
    setValidating(true);
    try {
      const serialized = await api.scriptToYaml(script);
      setYaml(serialized.yaml);
      const validation = await api.validateScript(script);
      setErrors(validation.errors);
    } catch (e) {
      setErrors([{ path: "<script>", message: (e as Error).message, severity: "error" }]);
    } finally {
      setValidating(false);
    }
  }

  async function doRepair() {
    setBusy(true);
    setNotice(null);
    try {
      const sourceYaml = mode === "yaml" || !script ? yaml : (await api.scriptToYaml(script)).yaml;
      const r = await api.repair(sourceYaml);
      setYaml(r.fixed_yaml);
      setChanges(r.changes.map(formatRepairChange));
      setMode("yaml");
      const validation = await api.validate(r.fixed_yaml);
      setErrors(validation.errors);
      setNotice(
        validation.errors.length === 0
          ? "自动修复完成，校验已通过。"
          : `自动修复已处理能确认的问题，但还有 ${validation.errors.length} 个需要手动确认。请看右侧校验建议。`,
      );
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
    return <div className="notice-danger">加载剧本失败：{loadErr}</div>;
  }

  return (
    <div className="editor-workspace flex min-h-0 flex-col gap-2 overflow-visible xl:flex-1 xl:overflow-hidden">
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
              <ModeButton active={mode === "yaml"} onClick={() => void showYamlMode()}>
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
        <div className="notice-success flex shrink-0 items-center justify-between gap-3">
          <span className="min-w-0">{notice}</span>
          <button
            type="button"
            className="shrink-0 rounded px-1.5 text-lg leading-none text-current opacity-70 hover:bg-ink-50/10 hover:opacity-100"
            onClick={() => setNotice(null)}
            aria-label="关闭通知"
            title="关闭通知"
          >
            ×
          </button>
        </div>
      )}

      <div className="grid gap-4 xl:min-h-0 xl:flex-1 xl:grid-cols-[300px_minmax(0,1fr)_360px]">
        <aside className="order-2 min-h-[220px] xl:order-none xl:min-h-0">
          {script && (
            <ResourcePanel
              script={script}
              locationNames={locationNames}
              selectedSceneId={selectedSceneId}
              setSelectedSceneId={setSelectedSceneId}
              onAddSceneAfter={(sceneId) => addSceneAfter(sceneId)}
            />
          )}
        </aside>

        <main className="order-1 min-h-[640px] min-w-0 overflow-hidden xl:order-none xl:min-h-0">
          {mode === "scene" && script && selectedScene && (
            <SceneEditor
              script={script}
              scene={selectedScene}
              sceneIndex={selectedSceneIndex}
              characterNames={characterNames}
              locationNames={locationNames}
              updateScene={updateScene}
              addSceneAfter={(sceneId) => addSceneAfter(sceneId)}
              continueScene={(sceneId) => addSceneAfter(sceneId, { continueFromScene: true })}
              deleteScene={deleteScene}
              addCharacterToScene={addCharacterToScene}
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

        <aside className="workspace-scroll order-3 max-h-[520px] min-h-[320px] space-y-4 overflow-y-auto pr-1 xl:order-none xl:max-h-none xl:min-h-0">
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

          <ValidationPanel busy={busy || validating} errors={errors} />
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
            <div className="card space-y-2">
              <div className="label">最近修复</div>
              <ul className="space-y-1.5 text-xs text-ink-200">
                {changes.map((change, i) => (
                  <li key={i} className="rounded border surface-line surface-soft px-2 py-1.5">
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
  onAddSceneAfter,
}: {
  script: ScriptDocument;
  locationNames: Record<string, string>;
  selectedSceneId: string;
  setSelectedSceneId: (id: string) => void;
  onAddSceneAfter: (sceneId?: string) => void;
}) {
  return (
    <div className="panel flex h-full min-h-0 flex-col overflow-hidden">
      <div className="panel-header flex items-center justify-between gap-3">
        <div className="text-sm font-medium text-ink-100">资源</div>
        <button
          type="button"
          className="btn-ghost h-8 px-2 text-xs"
          onClick={() => onAddSceneAfter()}
          title="新增场景"
          aria-label="新增场景"
        >
          + 场景
        </button>
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
              <div
                className={`rounded-md border transition-colors ${
                  item.id === selectedSceneId
                    ? "border-accent-500/70 bg-accent-500/10 text-ink-50"
                    : "border-ink-600/30 bg-ink-900/50 text-ink-300 hover:border-ink-500 hover:bg-ink-800"
                }`}
              >
                <div className="flex items-start gap-2 px-3 py-2">
                  <button
                    type="button"
                    className="min-w-0 flex-1 text-left text-sm"
                    onClick={() => setSelectedSceneId(item.id)}
                  >
                    <div className="flex min-w-0 items-center gap-2">
                      <span className="min-w-0 flex-1 truncate font-medium">
                        {sceneDisplayTitle(item, index)}
                      </span>
                      <span className="shrink-0 text-[11px] text-ink-500">{index + 1}</span>
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
                  <button
                    type="button"
                    className="mt-0.5 inline-flex h-7 w-7 shrink-0 items-center justify-center rounded text-sm text-ink-400 transition-colors hover:bg-ink-700 hover:text-ink-100 focus:outline-none focus:ring-1 focus:ring-accent-500"
                    onClick={() => onAddSceneAfter(item.id)}
                    title="在此场后新增"
                    aria-label={`在${sceneDisplayTitle(item, index)}后新增场景`}
                  >
                    +
                  </button>
                </div>
              </div>
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
  addSceneAfter,
  continueScene,
  deleteScene,
  addCharacterToScene,
}: {
  script: ScriptDocument;
  scene: ScriptScene;
  sceneIndex: number;
  characterNames: Record<string, string>;
  locationNames: Record<string, string>;
  updateScene: (sceneId: string, patch: (scene: ScriptScene) => ScriptScene) => void;
  addSceneAfter: (sceneId?: string) => void;
  continueScene: (sceneId: string) => void;
  deleteScene: (sceneId: string) => void;
  addCharacterToScene: (sceneId: string) => void;
}) {
  const [confirmingDelete, setConfirmingDelete] = useState(false);
  const canDeleteScene = script.scenes.length > 1;

  useEffect(() => {
    setConfirmingDelete(false);
  }, [scene.id]);

  return (
      <section className="panel flex h-full min-h-0 flex-col overflow-hidden">
        <div className="shrink-0 border-b border-ink-600/30 p-5">
          <div className="flex flex-col gap-3 sm:flex-row sm:items-start sm:justify-between">
          <div>
            <div className="text-xs text-ink-500">当前场景</div>
            <h2 className="mt-1 text-xl font-semibold text-ink-50">
              {sceneDisplayTitle(scene, sceneIndex)}
            </h2>
            <p className="mt-1 text-sm text-ink-400">{sceneMeta(scene, locationNames)}</p>
          </div>
          <div className="flex flex-wrap items-center gap-2 sm:justify-end">
            <button
              type="button"
              className="btn-ghost h-8 px-2 text-xs"
              onClick={() => continueScene(scene.id)}
            >
              续写一场
            </button>
            <button
              type="button"
              className="btn-ghost h-8 px-2 text-xs"
              onClick={() => addSceneAfter(scene.id)}
            >
              在后面新增
            </button>
            <button
              type="button"
              className="btn-ghost h-8 px-2 text-xs"
              onClick={() => setConfirmingDelete((value) => !value)}
              disabled={!canDeleteScene}
              title={canDeleteScene ? undefined : "至少保留一个场景"}
            >
              删除场景
            </button>
          </div>
          </div>
          {confirmingDelete && (
            <div className="danger-panel mt-4 flex flex-col gap-3 p-3 sm:flex-row sm:items-center sm:justify-between">
              <div>
                <div className="text-sm font-medium text-ink-100">确认删除当前场景？</div>
                <div className="mt-1 text-xs text-ink-400">会同时移除这一场的节拍、动作和对白。</div>
              </div>
              <div className="flex shrink-0 gap-2">
                <button type="button" className="btn-ghost h-8 px-2 text-xs" onClick={() => setConfirmingDelete(false)}>
                  取消
                </button>
                <button
                  type="button"
                  className="btn-danger h-8 px-2 text-xs"
                  onClick={() => {
                    setConfirmingDelete(false);
                    deleteScene(scene.id);
                  }}
                >
                  确认删除
                </button>
              </div>
            </div>
          )}
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
          <div className="mb-2 flex items-center justify-between gap-3">
            <div>
              <div className="label mb-0">出场角色</div>
              <div className="mt-0.5 text-xs text-ink-500">{scene.characters.length} 人</div>
            </div>
            <button
              type="button"
              className="btn-ghost h-8 px-2 text-xs"
              onClick={() => addCharacterToScene(scene.id)}
            >
              添加并出场
            </button>
          </div>
          <div className="grid gap-2 sm:grid-cols-2 lg:grid-cols-3">
            {script.characters.map((character) => {
              const checked = scene.characters.includes(character.id);
              const appearsInScriptFlow =
                scene.dialogue.some((line) => line.speaker === character.id) ||
                (scene.beats ?? []).some(
                  (beat) => beat.type === "dialogue" && beat.speaker === character.id,
                );
              const removalDisabled = checked && (scene.characters.length <= 1 || appearsInScriptFlow);
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
                      ? appearsInScriptFlow
                        ? "该角色已有对白，先调整剧本流中的说话人后再移出场景"
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

        <ScriptFlowEditor scene={scene} characterNames={characterNames} updateScene={updateScene} />

        <details className="mt-6 rounded-md border surface-line surface-soft p-3">
          <summary className="cursor-pointer text-sm font-medium text-ink-100">
            兼容结构
          </summary>
          <LegacyStructurePreview scene={scene} characterNames={characterNames} />
        </details>
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
      for (const beat of scene.beats ?? []) {
        if (beat.type === "dialogue" && beat.speaker) ids.add(beat.speaker);
      }
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

  function updateCharacterName(characterId: string, name: string) {
    const previous = script.characters.find((item) => item.id === characterId);
    updateScript((current) => {
      const character = current.characters.find((item) => item.id === characterId);
      if (!character) return current;
      return renameCharacterInScript(current, characterId, characterId, { name });
    });
    if (previous) {
      void syncEntityIdAfterNameChange("char", previous.id, previous.name, name, updateScript);
    }
  }

  function renameCharacter(characterId: string, nextId: string) {
    void (async () => {
      const character = script.characters.find((item) => item.id === characterId);
      const trimmed = await normalizeEntityId(
        "char",
        nextId,
        character?.name ?? "角色",
        script.characters.map((item) => item.id),
        characterId,
      );
      updateScript((current) => renameCharacterInScript(current, characterId, trimmed));
    })();
  }

  function addCharacter() {
    updateScript((current) => {
      const name = `新角色 ${current.characters.length + 1}`;
      const id = nextEntityIdFromNameFallback("char", name, current.characters.map((item) => item.id));
      return {
        ...current,
        characters: [
          ...current.characters,
          { id, name, role: "supporting" },
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

  function updateLocationName(locationId: string, name: string) {
    const previous = script.locations.find((item) => item.id === locationId);
    updateScript((current) => {
      const location = current.locations.find((item) => item.id === locationId);
      if (!location) return current;
      return renameLocationInScript(current, locationId, locationId, { name });
    });
    if (previous) {
      void syncEntityIdAfterNameChange("loc", previous.id, previous.name, name, updateScript);
    }
  }

  function renameLocation(locationId: string, nextId: string) {
    void (async () => {
      const location = script.locations.find((item) => item.id === locationId);
      const trimmed = await normalizeEntityId(
        "loc",
        nextId,
        location?.name ?? "地点",
        script.locations.map((item) => item.id),
        locationId,
      );
      updateScript((current) => renameLocationInScript(current, locationId, trimmed));
    })();
  }

  function addLocation() {
    updateScript((current) => {
      const name = `新地点 ${current.locations.length + 1}`;
      const id = nextEntityIdFromNameFallback("loc", name, current.locations.map((item) => item.id));
      return {
        ...current,
        locations: [...current.locations, { id, name }],
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
                  onNameChange={(value) => updateCharacterName(character.id, value)}
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
                  onNameChange={(value) => updateLocationName(location.id, value)}
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
  onNameChange,
  onRename,
  onDelete,
}: {
  character: ScriptCharacter;
  isReferenced: boolean;
  onChange: (patch: Partial<ScriptCharacter>) => void;
  onNameChange: (value: string) => void;
  onRename: (value: string) => void;
  onDelete: () => void;
}) {
  return (
    <div className="space-y-3">
      <div className="grid gap-3 md:grid-cols-[1fr_140px]">
        <Field label="角色名" value={character.name} onChange={onNameChange} />
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
      <DraftIdField
        label="角色 ID"
        value={character.id}
        prefix="char"
        sourceName={character.name}
        onCommit={onRename}
      />
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
  onNameChange,
  onRename,
  onDelete,
}: {
  location: ScriptLocation;
  isReferenced: boolean;
  onChange: (patch: Partial<ScriptLocation>) => void;
  onNameChange: (value: string) => void;
  onRename: (value: string) => void;
  onDelete: () => void;
}) {
  return (
    <div className="space-y-3">
      <Field label="地点名" value={location.name} onChange={onNameChange} />
      <DraftIdField
        label="地点 ID"
        value={location.id}
        prefix="loc"
        sourceName={location.name}
        onCommit={onRename}
      />
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

function ScriptFlowEditor({
  scene,
  characterNames,
  updateScene,
}: {
  scene: ScriptScene;
  characterNames: Record<string, string>;
  updateScene: (sceneId: string, patch: (scene: ScriptScene) => ScriptScene) => void;
}) {
  const beats = sceneBeats(scene);
  const [draggedBeatId, setDraggedBeatId] = useState<string | null>(null);
  const [dragOverBeatId, setDragOverBeatId] = useState<string | null>(null);
  const dragScrollFrameRef = useRef<number | null>(null);

  function commit(nextBeats: ScriptBeat[]) {
    updateScene(scene.id, (next) => syncSceneFromBeats(next, nextBeats));
  }

  function addBeat(type: ScriptBeat["type"]) {
    commit([...beats, createDraftBeat(nextBeatId(beats), type, scene)]);
  }

  function addBeatAfter(index: number) {
    const sourceBeat = beats[index];
    const next = [...beats];
    next.splice(
      index + 1,
      0,
      createDraftBeat(nextBeatId(beats), sourceBeat?.type ?? "action", scene, sourceBeat),
    );
    commit(next);
  }

  function updateBeat(index: number, patch: Partial<ScriptBeat>) {
    commit(beats.map((beat, i) => (i === index ? normalizeBeat({ ...beat, ...patch }, scene) : beat)));
  }

  function moveBeat(index: number, direction: -1 | 1) {
    const target = index + direction;
    if (target < 0 || target >= beats.length) return;
    const next = [...beats];
    [next[index], next[target]] = [next[target], next[index]];
    commit(next);
  }

  function dropBeat(targetBeatId: string) {
    if (!draggedBeatId || draggedBeatId === targetBeatId) {
      setDraggedBeatId(null);
      setDragOverBeatId(null);
      cancelDragAutoScroll(dragScrollFrameRef);
      return;
    }
    const fromIndex = beats.findIndex((beat) => beat.id === draggedBeatId);
    const toIndex = beats.findIndex((beat) => beat.id === targetBeatId);
    if (fromIndex < 0 || toIndex < 0) return;
    commit(moveArrayItem(beats, fromIndex, toIndex));
    setDraggedBeatId(null);
    setDragOverBeatId(null);
    cancelDragAutoScroll(dragScrollFrameRef);
  }

  return (
    <div className="mt-6">
      <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="text-sm font-medium text-ink-100">剧本流</div>
          <div className="mt-0.5 text-xs text-ink-500">{beats.length} 个节拍</div>
        </div>
        <div className="flex flex-wrap gap-2">
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => addBeat("action")}>
            动作
          </button>
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => addBeat("dialogue")}>
            对白
          </button>
          <button type="button" className="btn-ghost px-2 py-1 text-xs" onClick={() => addBeat("cue")}>
            提示
          </button>
        </div>
      </div>

      <ul className="space-y-3">
        {beats.map((beat, index) => (
          <li
            key={beat.id}
            className={`script-beat ${beatTypeClass(beat.type)} ${
              draggedBeatId === beat.id ? "script-beat-dragging" : ""
            } ${dragOverBeatId === beat.id && draggedBeatId !== beat.id ? "script-beat-drop-target" : ""}`}
            onDragOver={(e) => {
              if (!draggedBeatId) return;
              e.preventDefault();
              setDragOverBeatId(beat.id);
              scheduleDragAutoScroll(e.currentTarget, e.clientY, dragScrollFrameRef);
            }}
            onDragLeave={() => setDragOverBeatId((current) => (current === beat.id ? null : current))}
            onDrop={(e) => {
              e.preventDefault();
              dropBeat(beat.id);
            }}
          >
            <div className="mb-3 flex flex-col gap-2 sm:flex-row sm:items-start sm:justify-between">
              <div className="flex min-w-0 items-center gap-2">
                <span
                  role="button"
                  tabIndex={0}
                  draggable
                  className="script-drag-handle"
                  title="拖拽排序"
                  aria-label={`拖拽移动第 ${index + 1} 个节拍`}
                  onDragStart={(e) => {
                    e.dataTransfer.effectAllowed = "move";
                    e.dataTransfer.setData("text/plain", beat.id);
                    setDraggedBeatId(beat.id);
                  }}
                  onDragEnd={() => {
                    setDraggedBeatId(null);
                    setDragOverBeatId(null);
                    cancelDragAutoScroll(dragScrollFrameRef);
                  }}
                >
                  ::
                </span>
                <span className="script-beat-number">
                  {String(index + 1).padStart(2, "0")}
                </span>
                <span className="script-beat-kind">{beatTypeLabel(beat.type)}</span>
              </div>
              <div className="script-beat-actions">
                <button
                  type="button"
                  className="script-beat-add-after"
                  onClick={() => addBeatAfter(index)}
                  title="在此节拍后新增"
                  aria-label={`在第 ${index + 1} 个节拍后新增`}
                >
                  +
                </button>
                <details className="script-beat-menu">
                  <summary aria-label={`打开第 ${index + 1} 个节拍操作菜单`} title="节拍操作">
                    ⋯
                  </summary>
                  <div className="script-beat-menu-popover">
                    <label className="script-beat-menu-label" htmlFor={`beat-type-${beat.id}`}>
                      更改类型
                    </label>
                    <select
                      id={`beat-type-${beat.id}`}
                      className="input h-8 py-1 text-xs"
                      value={beat.type}
                      onChange={(e) => {
                        updateBeat(index, normalizeBeatType(beat, e.target.value as ScriptBeat["type"], scene));
                        closeBeatActionMenu(e.currentTarget);
                      }}
                    >
                      <option value="action">动作</option>
                      <option value="dialogue">对白</option>
                      <option value="cue">提示</option>
                    </select>
                    <div className="my-1 border-t surface-line" />
                    <button
                      type="button"
                      className="script-beat-menu-item"
                      onClick={(e) => {
                        moveBeat(index, -1);
                        closeBeatActionMenu(e.currentTarget);
                      }}
                      disabled={index === 0}
                    >
                      上移
                    </button>
                    <button
                      type="button"
                      className="script-beat-menu-item"
                      onClick={(e) => {
                        moveBeat(index, 1);
                        closeBeatActionMenu(e.currentTarget);
                      }}
                      disabled={index === beats.length - 1}
                    >
                      下移
                    </button>
                    <button
                      type="button"
                      className="script-beat-menu-item script-beat-menu-danger"
                      onClick={(e) => {
                        commit(beats.filter((_, i) => i !== index));
                        closeBeatActionMenu(e.currentTarget);
                      }}
                    >
                      删除
                    </button>
                  </div>
                </details>
              </div>
            </div>

            {beat.type === "dialogue" ? (
              <div className="script-dialogue-grid">
                <div className="script-speaker-block">
                  <label className="label">说话人</label>
                  <select
                    className="input"
                    value={beat.speaker ?? scene.characters[0] ?? ""}
                    onChange={(e) => updateBeat(index, { speaker: e.target.value })}
                  >
                    {scene.characters.map((id) => (
                      <option key={id} value={id}>
                        {characterNames[id] ?? "未命名角色"}
                      </option>
                    ))}
                  </select>
                  <input
                    className="input mt-2"
                    value={beat.emotion ?? ""}
                    onChange={(e) => updateBeat(index, { emotion: e.target.value })}
                    placeholder="情绪"
                  />
                </div>
                <div className="space-y-2">
                  <label className="label">台词</label>
                  <textarea
                    className="input script-dialogue-line"
                    value={beat.line ?? ""}
                    onChange={(e) => updateBeat(index, { line: e.target.value })}
                    placeholder="输入角色台词"
                  />
                  <input
                    className="input"
                    value={beat.subtext ?? ""}
                    onChange={(e) => updateBeat(index, { subtext: e.target.value })}
                    placeholder="潜台词"
                  />
                </div>
              </div>
            ) : (
              <textarea
                className="input script-action-textarea"
                value={beat.text ?? ""}
                onChange={(e) => updateBeat(index, { text: e.target.value })}
                placeholder={beat.type === "cue" ? "灯光、音效、道具或节奏提示" : "动作描写"}
              />
            )}
          </li>
        ))}
      </ul>
    </div>
  );
}

function LegacyStructurePreview({
  scene,
  characterNames,
}: {
  scene: ScriptScene;
  characterNames: Record<string, string>;
}) {
  return (
    <div className="mt-4 grid gap-4 lg:grid-cols-2">
      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-medium text-ink-400">action</div>
          <span className="text-[11px] text-ink-500">{scene.action.length}</span>
        </div>
        {scene.action.length > 0 ? (
          <ol className="space-y-2">
            {scene.action.map((line, index) => (
              <li key={`${index}-${line}`} className="rounded-md bg-ink-950/50 px-2.5 py-2 text-sm leading-5 text-ink-200">
                <span className="mr-2 font-mono text-[11px] text-ink-500">{index + 1}</span>
                {line}
              </li>
            ))}
          </ol>
        ) : (
          <div className="rounded-md bg-ink-950/50 px-2.5 py-2 text-sm text-ink-500">空</div>
        )}
      </section>
      <section className="space-y-2">
        <div className="flex items-center justify-between gap-2">
          <div className="text-xs font-medium text-ink-400">dialogue</div>
          <span className="text-[11px] text-ink-500">{scene.dialogue.length}</span>
        </div>
        {scene.dialogue.length > 0 ? (
          <ol className="space-y-2">
            {scene.dialogue.map((line, index) => (
              <li key={`${index}-${line.speaker}-${line.line}`} className="rounded-md bg-ink-950/50 px-2.5 py-2 text-sm leading-5 text-ink-200">
                <div className="font-medium text-ink-100">
                  {characterNames[line.speaker] ?? line.speaker}
                  {line.emotion ? <span className="font-normal text-ink-500">（{line.emotion}）</span> : null}
                </div>
                <div className="mt-1">{line.line}</div>
                {line.subtext ? <div className="mt-1 text-xs text-ink-500">潜台词：{line.subtext}</div> : null}
              </li>
            ))}
          </ol>
        ) : (
          <div className="rounded-md bg-ink-950/50 px-2.5 py-2 text-sm text-ink-500">空</div>
        )}
      </section>
    </div>
  );
}

function beatTypeLabel(type: ScriptBeat["type"]) {
  return (
    {
      action: "动作",
      dialogue: "对白",
      cue: "提示",
    }[type] ?? type
  );
}

function beatTypeClass(type: ScriptBeat["type"]) {
  return (
    {
      action: "script-beat-action",
      dialogue: "script-beat-dialogue",
      cue: "script-beat-cue",
    }[type] ?? "script-beat-action"
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

function DraftIdField({
  label,
  value,
  prefix,
  sourceName,
  onCommit,
}: {
  label: string;
  value: string;
  prefix: EntityPrefix;
  sourceName: string;
  onCommit: (value: string) => void;
}) {
  const [draft, setDraft] = useState(value);
  const [suggestion, setSuggestion] = useState(() => entityIdFromNameFallback(prefix, sourceName));

  useEffect(() => {
    setDraft(value);
  }, [value]);

  useEffect(() => {
    let cancelled = false;
    setSuggestion(entityIdFromNameFallback(prefix, sourceName));
    void entityIdFromName(prefix, sourceName).then((next) => {
      if (!cancelled) setSuggestion(next);
    });
    return () => {
      cancelled = true;
    };
  }, [prefix, sourceName]);

  function commit(nextValue = draft) {
    const trimmed = nextValue.trim();
    if (!trimmed || trimmed === value) {
      setDraft(value);
      return;
    }
    onCommit(trimmed);
  }

  return (
    <div>
      <div className="mb-1 flex items-center justify-between gap-2">
        <label className="label mb-0">{label}</label>
        {suggestion !== value && (
          <button
            type="button"
            className="rounded px-1.5 py-0.5 text-[11px] text-ink-500 transition-colors hover:bg-ink-700 hover:text-ink-100"
            onClick={() => {
              setDraft(suggestion);
              onCommit(suggestion);
            }}
            title={`使用 ${suggestion}`}
          >
            用拼音
          </button>
        )}
      </div>
      <input
        className="input"
        value={draft}
        onChange={(e) => setDraft(e.target.value)}
        onBlur={() => commit()}
        onKeyDown={(e) => {
          if (e.key === "Enter") {
            e.preventDefault();
            commit();
            e.currentTarget.blur();
          }
          if (e.key === "Escape") {
            setDraft(value);
            e.currentTarget.blur();
          }
        }}
        spellCheck={false}
      />
      <div className="mt-1 text-[11px] text-ink-500">建议：{suggestion}</div>
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

function formatRepairChange(change: string) {
  const remaining = change.match(/repair finished with (\d+) remaining errors/i);
  if (remaining) return `自动修复后仍有 ${remaining[1]} 个问题，需要你手动确认。`;

  if (/yaml parse error/i.test(change)) {
    return "YAML 格式有问题，自动修复暂时读不出结构。请先按右侧校验建议修正缩进、冒号或引号。";
  }

  if (/payload is not a mapping/i.test(change)) {
    return "最外层结构不是对象。请让源码以 script: 开头，再把剧本内容缩进放在下面。";
  }

  const snappedKnown = change.match(/^(.+): snapped to known id '([^']+)'$/i);
  if (snappedKnown) return `已把 ${formatRepairPath(snappedKnown[1])} 对齐到已有 ID：${snappedKnown[2]}。`;

  const snappedPair = change.match(/^(.+): snapped '([^']+)' -> '([^']+)'$/i);
  if (snappedPair) return `已把 ${formatRepairPath(snappedPair[1])} 里的 ${snappedPair[2]} 改成已有 ID：${snappedPair[3]}。`;

  const snappedTo = change.match(/^(.+): snapped to '([^']+)'$/i);
  if (snappedTo) return `已把 ${formatRepairPath(snappedTo[1])} 改成已有 ID：${snappedTo[2]}。`;

  const removedId = change.match(/^(.+): removed unknown id '([^']+)'$/i);
  if (removedId) return `已从 ${formatRepairPath(removedId[1])} 移除不存在的 ID：${removedId[2]}。`;

  if (/removed unknown speaker/i.test(change)) {
    const path = change.split(":")[0] || "";
    return `已移除 ${formatRepairPath(path)} 里找不到角色的对白或节拍。`;
  }

  if (/pruned unknown chapter ids/i.test(change)) {
    const path = change.split(":")[0] || "";
    return `已从 ${formatRepairPath(path)} 移除不存在的来源章节。`;
  }

  return change;
}

function formatRepairPath(path: string) {
  const scene = path.match(/script\.scenes\[(\d+)\]/);
  if (scene) {
    const index = Number(scene[1]) + 1;
    if (path.includes(".location_id")) return `第 ${index} 场的地点`;
    if (path.includes(".characters")) return `第 ${index} 场的出场角色`;
    if (path.includes(".dialogue")) return `第 ${index} 场的对白说话人`;
    if (path.includes(".beats")) return `第 ${index} 场的节拍说话人`;
    if (path.includes(".chapter_refs")) return `第 ${index} 场的来源章节`;
    return `第 ${index} 场`;
  }
  return path;
}

function uniqueStrings(values: string[]) {
  return Array.from(new Set(values.filter(Boolean)));
}

function sceneBeats(scene: ScriptScene): ScriptBeat[] {
  if (scene.beats?.length) return scene.beats;
  const beats: ScriptBeat[] = [];
  for (const text of scene.action) {
    beats.push({
      id: `beat_${String(beats.length + 1).padStart(3, "0")}`,
      type: "action",
      text,
    });
  }
  for (const line of scene.dialogue) {
    beats.push({
      id: `beat_${String(beats.length + 1).padStart(3, "0")}`,
      type: "dialogue",
      speaker: line.speaker,
      line: line.line,
      emotion: line.emotion,
      subtext: line.subtext,
    });
  }
  return beats;
}

function nextBeatId(beats: ScriptBeat[]) {
  const max = beats.reduce((current, beat) => {
    const match = /^beat_(\d+)$/.exec(beat.id);
    return match ? Math.max(current, Number(match[1])) : current;
  }, 0);
  return `beat_${String(max + 1).padStart(3, "0")}`;
}

function createDraftBeat(
  id: string,
  type: ScriptBeat["type"],
  scene: ScriptScene,
  sourceBeat?: ScriptBeat,
): ScriptBeat {
  if (type === "dialogue") {
    return {
      id,
      type,
      speaker: sourceBeat?.speaker || scene.characters[0] || "",
      line: "",
    };
  }
  return {
    id,
    type,
    text: "",
  };
}

function normalizeBeat(beat: ScriptBeat, scene: ScriptScene): ScriptBeat {
  if (beat.type === "dialogue") {
    return {
      id: beat.id,
      type: "dialogue",
      speaker: beat.speaker || scene.characters[0] || "",
      line: beat.line ?? "",
      emotion: beat.emotion || undefined,
      subtext: beat.subtext || undefined,
    };
  }
  return {
    id: beat.id,
    type: beat.type,
    text: beat.text ?? beat.line ?? "",
  };
}

function normalizeBeatType(
  beat: ScriptBeat,
  type: ScriptBeat["type"],
  scene: ScriptScene,
): ScriptBeat {
  if (type === "dialogue") {
    return normalizeBeat(
      {
        id: beat.id,
        type,
        speaker: beat.speaker || scene.characters[0] || "",
        line: beat.line ?? beat.text ?? "",
        emotion: beat.emotion,
        subtext: beat.subtext,
      },
      scene,
    );
  }
  return normalizeBeat(
    {
      id: beat.id,
      type,
      text: beat.text ?? beat.line ?? "",
    },
    scene,
  );
}

function syncSceneFromBeats(scene: ScriptScene, beats: ScriptBeat[]): ScriptScene {
  const normalized = beats.map((beat) => normalizeBeat(beat, scene));
  const action = normalized
    .filter((beat) => beat.type === "action")
    .map((beat) => (beat.text ?? "").trim())
    .filter(Boolean);
  const dialogue = normalized
    .filter((beat) => beat.type === "dialogue")
    .map((beat): DialogueLine | null => {
      const line = (beat.line ?? "").trim();
      const speaker = beat.speaker || scene.characters[0] || "";
      if (!line || !speaker) return null;
      return {
        speaker,
        line,
        emotion: beat.emotion || undefined,
        subtext: beat.subtext || undefined,
      };
    })
    .filter((line): line is DialogueLine => Boolean(line));
  return {
    ...scene,
    beats: normalized,
    action,
    dialogue,
  };
}

function normalizeIdInput(value: string) {
  return value
    .trim()
    .toLowerCase()
    .replace(/[^a-z0-9_]/g, "_")
    .replace(/_+/g, "_");
}

function entityIdFromNameFallback(prefix: EntityPrefix, name: string) {
  const normalized = normalizeIdInput(name).replace(/^_+|_+$/g, "");
  return `${prefix}_${normalized || "new"}`;
}

async function entityIdFromName(prefix: EntityPrefix, name: string) {
  const { pinyin: toPinyin } = await import("pinyin-pro");
  const normalized = normalizeIdInput(
    toPinyin(name, { toneType: "none", type: "array", nonZh: "consecutive" })
      .join("_")
      .replace(/\s+/g, "_"),
  ).replace(/^_+|_+$/g, "");
  return `${prefix}_${normalized || "new"}`;
}

function nextEntityIdFromNameFallback(
  prefix: EntityPrefix,
  name: string,
  existingIds: string[],
  currentId?: string,
) {
  return nextAvailableId(
    entityIdFromNameFallback(prefix, name),
    existingIds.filter((id) => id !== currentId),
  );
}

async function nextEntityIdFromName(
  prefix: EntityPrefix,
  name: string,
  existingIds: string[],
  currentId?: string,
) {
  return nextAvailableId(
    await entityIdFromName(prefix, name),
    existingIds.filter((id) => id !== currentId),
  );
}

async function normalizeEntityId(
  prefix: EntityPrefix,
  value: string,
  fallbackName: string,
  existingIds: string[],
  currentId?: string,
) {
  const normalized = normalizeIdInput(value).replace(/^_+|_+$/g, "");
  const withoutPrefix = normalized.replace(new RegExp(`^${prefix}_?`), "");
  const base = withoutPrefix
    ? `${prefix}_${withoutPrefix}`
    : await entityIdFromName(prefix, fallbackName);
  return nextAvailableId(base, existingIds.filter((id) => id !== currentId));
}

function shouldAutoSyncEntityId(prefix: EntityPrefix, id: string, suggested: string) {
  return id === suggested || id === `${prefix}_new` || /^.+_new(_\d+)?$/.test(id);
}

async function syncEntityIdAfterNameChange(
  prefix: EntityPrefix,
  previousId: string,
  previousName: string,
  nextName: string,
  updateScript: (patch: (current: ScriptDocument) => ScriptDocument) => void,
) {
  const previousSuggestion = await entityIdFromName(prefix, previousName);
  if (!shouldAutoSyncEntityId(prefix, previousId, previousSuggestion)) return;
  const nextSuggested = await entityIdFromName(prefix, nextName);

  updateScript((current) => {
    if (prefix === "char") {
      const character = current.characters.find((item) => item.id === previousId);
      if (!character || character.name !== nextName) return current;
      const nextId = nextAvailableId(
        nextSuggested,
        current.characters.map((item) => item.id).filter((id) => id !== previousId),
      );
      return renameCharacterInScript(current, previousId, nextId);
    }

    const location = current.locations.find((item) => item.id === previousId);
    if (!location || location.name !== nextName) return current;
    const nextId = nextAvailableId(
      nextSuggested,
      current.locations.map((item) => item.id).filter((id) => id !== previousId),
    );
    return renameLocationInScript(current, previousId, nextId);
  });
}

function renameCharacterInScript(
  script: ScriptDocument,
  characterId: string,
  nextId: string,
  patch: Partial<ScriptCharacter> = {},
): ScriptDocument {
  return {
    ...script,
    characters: script.characters.map((character) =>
      character.id === characterId
        ? compactCharacter({ ...character, ...patch, id: nextId })
        : character,
    ),
    scenes: script.scenes.map((scene) => ({
      ...scene,
      characters: scene.characters.map((id) => (id === characterId ? nextId : id)),
      dialogue: scene.dialogue.map((line) => ({
        ...line,
        speaker: line.speaker === characterId ? nextId : line.speaker,
      })),
      beats: scene.beats?.map((beat) =>
        beat.type === "dialogue" && beat.speaker === characterId
          ? { ...beat, speaker: nextId }
          : beat,
      ),
    })),
  };
}

function renameLocationInScript(
  script: ScriptDocument,
  locationId: string,
  nextId: string,
  patch: Partial<ScriptLocation> = {},
): ScriptDocument {
  return {
    ...script,
    locations: script.locations.map((location) =>
      location.id === locationId
        ? compactLocation({ ...location, ...patch, id: nextId })
        : location,
    ),
    scenes: script.scenes.map((scene) => ({
      ...scene,
      location_id: scene.location_id === locationId ? nextId : scene.location_id,
    })),
  };
}

function nextAvailableId(base: string, existingIds: string[]) {
  const used = new Set(existingIds);
  if (!used.has(base)) return base;
  let index = 2;
  while (used.has(`${base}_${index}`)) index += 1;
  return `${base}_${index}`;
}

function nextNumberedId(prefix: string, existingIds: string[]) {
  const pattern = new RegExp(`^${prefix}_(\\d+)$`);
  const max = existingIds.reduce((current, id) => {
    const match = pattern.exec(id);
    return match ? Math.max(current, Number(match[1])) : current;
  }, 0);
  return `${prefix}_${String(max + 1).padStart(3, "0")}`;
}

function createDraftScene(
  id: string,
  script: ScriptDocument,
  sourceScene?: ScriptScene,
  continueFromScene = false,
): ScriptScene {
  const chapterRefs =
    sourceScene?.chapter_refs.length
      ? sourceScene.chapter_refs
      : script.source.chapter_ids.slice(0, 1);
  const characters =
    sourceScene?.characters.length
      ? sourceScene.characters
      : script.characters[0]
        ? [script.characters[0].id]
        : [];
  const sourceTitle = sourceScene ? sceneTitleWithoutNumber(sourceScene.title) : "";

  return {
    id,
    title: continueFromScene && sourceTitle ? `续写：${sourceTitle}` : `新场景 ${script.scenes.length + 1}`,
    chapter_refs: chapterRefs,
    location_id: sourceScene?.location_id || script.locations[0]?.id || "loc_new",
    time: sourceScene?.time ?? "",
    characters,
    purpose: continueFromScene ? "承接上一场，推进新的行动。" : "",
    conflict: "",
    entry_state: continueFromScene ? sourceScene?.exit_state ?? "" : "",
    exit_state: "",
    action: [],
    dialogue: [],
    beats: [
      {
        id: "beat_001",
        type: "action",
        text: continueFromScene ? "继续上一场的情绪与行动。" : "",
      },
    ],
  };
}

function ensureSceneDependencies(script: ScriptDocument): ScriptDocument {
  const characters =
    script.characters.length > 0
      ? script.characters
      : [{ id: "char_new", name: "新角色 1", role: "supporting" }];
  const locations =
    script.locations.length > 0
      ? script.locations
      : [{ id: "loc_new", name: "新地点 1" }];
  if (characters === script.characters && locations === script.locations) return script;
  return { ...script, characters, locations };
}

function sceneTitleWithoutNumber(title: string) {
  return title
    .replace(/^第\s*[\d一二三四五六七八九十百千万两〇零]+\s*场\s*[：:、.-]?\s*/, "")
    .trim();
}

function moveArrayItem<T>(items: T[], fromIndex: number, toIndex: number) {
  const next = [...items];
  const [item] = next.splice(fromIndex, 1);
  next.splice(toIndex, 0, item);
  return next;
}

function closeBeatActionMenu(element: HTMLElement) {
  element.closest("details")?.removeAttribute("open");
}

function scheduleDragAutoScroll(
  element: HTMLElement,
  clientY: number,
  frameRef: { current: number | null },
) {
  const container = element.closest(".workspace-scroll");
  if (!(container instanceof HTMLElement)) return;
  const rect = container.getBoundingClientRect();
  const edgeSize = Math.min(120, rect.height / 3);
  const distanceToTop = clientY - rect.top;
  const distanceToBottom = rect.bottom - clientY;
  const direction =
    distanceToTop < edgeSize ? -1 : distanceToBottom < edgeSize ? 1 : 0;

  if (direction === 0) {
    cancelDragAutoScroll(frameRef);
    return;
  }

  const distance = direction < 0 ? distanceToTop : distanceToBottom;
  const intensity = Math.max(0.2, Math.min(1, (edgeSize - distance) / edgeSize));
  const speed = Math.round(8 + intensity * 28) * direction;

  if (frameRef.current !== null) cancelAnimationFrame(frameRef.current);
  frameRef.current = requestAnimationFrame(() => {
    container.scrollBy({ top: speed, behavior: "auto" });
    frameRef.current = null;
  });
}

function cancelDragAutoScroll(frameRef: { current: number | null }) {
  if (frameRef.current === null) return;
  cancelAnimationFrame(frameRef.current);
  frameRef.current = null;
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
