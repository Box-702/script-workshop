"use client";

import { useEffect, useState } from "react";
import type { AgentPatchOperation, AgentRunSummary, ScriptScene } from "@/lib/types";
import { PatchComparison } from "./PatchComparison";

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

export function AgentPanel({
  agentBusy,
  saving,
  agentInstruction,
  agentInstructionFocused,
  agentScope,
  agentRun,
  agentRuns,
  scriptReady,
  selectedScene,
  selectedSceneLabel,
  characterNames,
  setAgentInstruction,
  setAgentInstructionFocused,
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
  agentInstructionFocused: boolean;
  agentScope: "current_scene" | "whole_script";
  agentRun: AgentRunSummary | null;
  agentRuns: AgentRunSummary[];
  scriptReady: boolean;
  selectedScene: ScriptScene | null;
  selectedSceneLabel: string | null;
  characterNames: Record<string, string>;
  setAgentInstruction: (value: string) => void;
  setAgentInstructionFocused: (value: boolean) => void;
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
    if (!current) {
      setAgentInstruction(text);
      return;
    }
    const parts = current
      .split(/[；;]\s*/)
      .map((item) => item.trim())
      .filter(Boolean);
    if (parts.includes(text)) {
      setAgentInstruction(current);
      return;
    }
    setAgentInstruction([...parts, text].join("；"));
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
        onFocus={() => setAgentInstructionFocused(true)}
        onBlur={() => setAgentInstructionFocused(false)}
        placeholder={agentInstructionFocused ? "" : "例如：强化前三秒钩子；减少解释性对白；不改变人物关系。"}
      />
      {agentInstruction.trim() && (
        <div className="flex justify-end">
          <button
            type="button"
            className="text-xs text-ink-500 hover:text-ink-200"
            onClick={() => setAgentInstruction("")}
          >
            清空需求
          </button>
        </div>
      )}
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
              ? selectedSceneLabel
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
        <div className="space-y-4 rounded-md border surface-line bg-ink-900/70 p-3 text-sm">
          <div className="flex items-start justify-between gap-3">
            <div>
              <div className="font-medium text-ink-100">{formatAgentStatus(agentRun.status)}</div>
              <div className="mt-1 text-ink-500">{formatAgentModel(agentRun.model)}</div>
            </div>
            <span className="rounded bg-ink-800 px-2 py-1 font-mono text-ink-400">
              AI 助手
            </span>
          </div>
          <div className="rounded-md bg-ink-950/70 px-2.5 py-2 leading-5 text-ink-200">
            <span className="text-ink-500">需求：</span>
            {agentRun.user_prompt}
          </div>
          {agentRun.error_message && (
            <div className="notice-warning px-2.5 py-2">
              {agentRun.error_message}
            </div>
          )}
          {agentRun.plan && (
            <ol className="space-y-1.5 text-sm leading-5 text-ink-200">
              {agentRun.plan.map((item, index) => (
                <li key={index} className="flex gap-2">
                  <span className="shrink-0 text-ink-500">{index + 1}</span>
                  <span>{String(item)}</span>
                </li>
              ))}
            </ol>
          )}
          {agentRun.patch && agentRun.patch.length > 0 && (
            <div className="space-y-2">
              {agentRun.status === "waiting_review" && patchCount > 1 && (
                <div className="flex items-center justify-between border-t surface-line pt-3 text-[11px] text-ink-400">
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
                <li key={index} className="rounded-md border surface-line surface-soft p-2.5">
                  <div className="flex items-center justify-between gap-2">
                    <label className="flex min-w-0 items-center gap-2 text-sm text-ink-100">
                      {agentRun.status === "waiting_review" && patchCount > 1 && (
                        <input
                          type="checkbox"
                          className="h-3.5 w-3.5 accent-accent-500"
                          checked={selectedPatchIndexes.includes(index)}
                          onChange={() => togglePatchIndex(index)}
                        />
                      )}
                      <span className="truncate">{formatPatchTitle(item, index)}</span>
                    </label>
                    <span className="rounded bg-ink-800 px-1.5 py-0.5 text-xs text-ink-300">
                      {formatPatchField(item)}
                    </span>
                  </div>
                  {item.risk && item.risk.length > 0 && (
                    <div className="notice-warning mt-2 px-2 py-1.5 text-xs leading-5">
                      {item.risk.join(" ")}
                    </div>
                  )}
                  <PatchComparison item={item} characterNames={characterNames} />
                </li>
              ))}
              </ul>
            </div>
          )}
          {agentRun.status === "waiting_review" && (
            <div className="grid grid-cols-2 gap-2 border-t surface-line pt-3">
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
      beats: "剧本流",
      action: "动作",
      dialogue: "对白",
      "adaptation_notes/reason": "说明",
      "adaptation_notes/fidelity": "方式",
    }[item.field || String(item.path || "").split("/script/scenes/").pop()?.split("/").slice(1).join("/") || ""] ?? "修改"
  );
}

function formatPatchTitle(item: AgentPatchOperation, index: number) {
  if (item.beat_label) {
    return item.scene_title ? `${item.scene_title} · ${item.beat_label}` : item.beat_label;
  }
  return item.scene_title || `变更 ${index + 1}`;
}
