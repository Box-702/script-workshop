"use client";

import { useEffect, useState } from "react";
import { useParams } from "next/navigation";
import Link from "next/link";
import { api } from "@/lib/api";
import type { RunOut } from "@/lib/types";

const STAGES = [
  "queued",
  "chapter_summary",
  "story_bible",
  "character_extraction",
  "scene_planning",
  "script_generation",
  "validation",
  "done",
];

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
    return (
      <div className="card border-red-500/40 text-red-200">
        加载失败：{error}
      </div>
    );
  }
  if (!run) return <div className="text-ink-400">加载中…</div>;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">生成进度</h1>
        <p className="mt-1 text-sm text-ink-400">
          Run <code className="font-mono text-ink-200">{run.id}</code>
        </p>
      </div>

      <div className="card space-y-3">
        <div className="flex items-center justify-between text-sm">
          <div className="flex items-center gap-3">
            <span className="pill">{run.status}</span>
            <span className="text-ink-400">step: {run.current_step || "—"}</span>
          </div>
          <div className="text-ink-400">{run.progress}%</div>
        </div>
        <div className="h-2 w-full overflow-hidden rounded bg-ink-700">
          <div
            className="h-full bg-accent-500 transition-all"
            style={{ width: `${run.progress}%` }}
          />
        </div>
        <ul className="grid grid-cols-2 gap-2 pt-2 text-xs md:grid-cols-4">
          {STAGES.map((s) => (
            <li
              key={s}
              className={`rounded border px-2 py-1 ${
                run.current_step.startsWith(s)
                  ? "border-accent-500 text-accent-400"
                  : "border-ink-600/30 text-ink-400"
              }`}
            >
              {s}
            </li>
          ))}
        </ul>
      </div>

      {run.status === "failed" && (
        <div className="card border-red-500/40 text-red-200">
          生成失败：{run.error_message}
        </div>
      )}

      {run.status === "done" && (
        <div className="card flex items-center justify-between">
          <div className="text-sm">剧本已就绪。</div>
          <Link href={`/projects/${run.project_id}/edit`} className="btn-primary">
            打开编辑器
          </Link>
        </div>
      )}
    </div>
  );
}
