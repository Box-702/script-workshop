"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { AuthRequiredMessage, isAuthRequiredMessage } from "@/components/AuthRequiredMessage";
import { api } from "@/lib/api";
import type { RunOut } from "@/lib/types";

const STAGES = [
  {
    key: "queued",
    title: "任务排队",
    desc: "创建生成任务，等待后端开始处理。",
  },
  {
    key: "chapter_summary",
    title: "章节摘要",
    desc: "拆分并概括每章的主要事件、人物和冲突。",
  },
  {
    key: "story_bible",
    title: "故事圣经",
    desc: "整理全局设定、主题、主线冲突和叙事基调。",
  },
  {
    key: "character_extraction",
    title: "人物提取",
    desc: "生成人物卡，统一角色 id、目标和台词风格。",
  },
  {
    key: "scene_planning",
    title: "场景规划",
    desc: "把小说情节改写为可追溯的剧本场景。",
  },
  {
    key: "script_generation",
    title: "逐场成稿",
    desc: "补全动作、对白、情绪和改编说明。",
  },
  {
    key: "validation",
    title: "结构校验",
    desc: "检查 YAML Schema 与人物、地点、章节引用。",
  },
  {
    key: "done",
    title: "生成完成",
    desc: "保存脚本版本，可以进入编辑器继续打磨。",
  },
];

const STATUS_LABEL: Record<RunOut["status"], string> = {
  queued: "等待中",
  running: "生成中",
  done: "已完成",
  failed: "失败",
};

type StepState = "pending" | "active" | "done" | "error";

function activeStageIndex(step: string, status: RunOut["status"]) {
  if (status === "done") return STAGES.length - 1;
  if (status === "failed") {
    const failedIndex = STAGES.findIndex((stage) => step.startsWith(stage.key));
    return failedIndex >= 0 ? failedIndex : 0;
  }
  const index = STAGES.findIndex((stage) => step.startsWith(stage.key));
  return index >= 0 ? index : 0;
}

function stepState(index: number, activeIndex: number, status: RunOut["status"]): StepState {
  if (status === "failed" && index === activeIndex) return "error";
  if (index < activeIndex || status === "done") return "done";
  if (index === activeIndex) return "active";
  return "pending";
}

function stepClass(state: StepState) {
  if (state === "done") return "state-success";
  if (state === "active") return "border-accent-500/70 bg-accent-500/10 text-ink-50";
  if (state === "error") return "state-danger";
  return "border-ink-600/30 bg-ink-900/40 text-ink-400";
}

function stepBadge(state: StepState, index: number) {
  if (state === "done") return "完成";
  if (state === "active") return "进行中";
  if (state === "error") return "异常";
  return `第 ${index + 1} 步`;
}

function stageLabel(step: string) {
  const stage = STAGES.find((item) => step.startsWith(item.key));
  return stage?.title ?? "等待开始";
}

export default function RunPage() {
  const params = useParams<{ id: string }>();
  const [run, setRun] = useState<RunOut | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let timer: ReturnType<typeof setTimeout> | null = null;
    let alive = true;
    async function tick() {
      try {
        const r = await api.getRun(params.id);
        if (!alive) return;
        setRun(r);
        if (r.status === "running" || r.status === "queued") {
          timer = setTimeout(tick, 800);
        }
      } catch (e) {
        if (alive) setError((e as Error).message);
      }
    }
    tick();
    return () => {
      alive = false;
      if (timer) clearTimeout(timer);
    };
  }, [params.id]);

  if (error) {
    if (isAuthRequiredMessage(error)) return <AuthRequiredMessage />;
    return (
      <div className="notice-danger">
        加载失败：{error}
      </div>
    );
  }
  if (!run) return <div className="text-ink-400">加载中…</div>;
  const activeIndex = activeStageIndex(run.current_step, run.status);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">生成进度</h1>
          <p className="mt-1 text-sm text-ink-400">
            任务编号 <code className="font-mono text-ink-200">{run.id}</code>
          </p>
        </div>
        <Link href="/new" className="btn-ghost">
          新建项目
        </Link>
      </div>

      <div className="card space-y-5">
        <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="flex items-center gap-3 text-sm">
              <span className="pill">{STATUS_LABEL[run.status]}</span>
              <span className="text-ink-400">当前阶段：{stageLabel(run.current_step)}</span>
            </div>
            <p className="mt-2 text-sm text-ink-400">
              系统会依次完成章节理解、人物和场景规划、剧本成稿与结构校验。
            </p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-semibold text-ink-50">{run.progress}%</div>
            <div className="text-xs text-ink-400">整体进度</div>
          </div>
        </div>
        <div className="h-2 w-full overflow-hidden rounded bg-ink-700">
          <div
            className="h-full bg-accent-500 transition-all"
            style={{ width: `${run.progress}%` }}
          />
        </div>

        <ul className="grid gap-3 md:grid-cols-2">
          {STAGES.map((stage, index) => {
            const state = stepState(index, activeIndex, run.status);
            return (
              <li
                key={stage.key}
                className={`rounded-md border p-4 transition-colors ${stepClass(state)}`}
              >
                <div className="flex items-start justify-between gap-3">
                  <div>
                    <div className="font-medium">{stage.title}</div>
                    <p className="mt-1 text-sm text-ink-400">{stage.desc}</p>
                  </div>
                  <span className="shrink-0 rounded bg-ink-800 px-2 py-1 text-xs text-ink-200">
                    {stepBadge(state, index)}
                  </span>
                </div>
              </li>
            );
          })}
        </ul>
      </div>

      {run.status === "failed" && (
        <div className="notice-danger">
          生成失败：{run.error_message}
        </div>
      )}

      {run.status === "done" && (
        <div className="card flex items-center justify-between">
          <div>
            <div className="text-sm font-medium">剧本初稿已生成</div>
            <p className="mt-1 text-sm text-ink-400">进入编辑器查看 YAML、修复结构或下载结果。</p>
          </div>
          <Link href={`/projects/${run.project_id}/edit`} className="btn-primary">
            打开编辑器
          </Link>
        </div>
      )}
    </div>
  );
}
