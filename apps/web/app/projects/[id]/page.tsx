"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import { loadLlmSettings } from "@/lib/llm-settings";
import type { EditEventSummary, ProjectDetail } from "@/lib/types";

export default function ProjectDetailPage() {
  const params = useParams<{ id: string }>();
  const router = useRouter();
  const projectId = params.id;
  const [project, setProject] = useState<ProjectDetail | null>(null);
  const [edits, setEdits] = useState<EditEventSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    Promise.all([api.getProject(projectId), api.listEditEvents(projectId, 5)])
      .then(([projectDetail, editEvents]) => {
        setProject(projectDetail);
        setEdits(editEvents);
      })
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, [projectId]);

  async function startGeneration() {
    setBusy(true);
    setError(null);
    try {
      const run = await api.generate(projectId, loadLlmSettings());
      router.push(`/runs/${run.run_id}`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  if (loading) {
    return <div className="card text-sm text-ink-400">加载中...</div>;
  }

  if (!project) {
    return (
      <div className="card border-red-500/40 text-red-200">
        {error ? `加载失败：${error}` : "项目不存在"}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="mb-2">
            <Link href="/dashboard" className="text-sm text-ink-400">
              返回项目
            </Link>
          </div>
          <h1 className="text-2xl font-semibold tracking-tight">{project.title}</h1>
          <p className="mt-1 text-sm text-ink-400">
            {formatAdaptation(project.adaptation_type)} · {project.language} · 更新于{" "}
            {formatDate(project.updated_at)}
          </p>
        </div>
        <div className="flex flex-wrap gap-2">
          <button className="btn-ghost" onClick={startGeneration} disabled={busy}>
            {busy ? "启动中..." : project.version_count > 0 ? "重新生成" : "生成剧本"}
          </button>
          {project.version_count > 0 && (
            <>
              <Link href={`/projects/${project.id}/edit`} className="btn-primary">
                编辑
              </Link>
              <a className="btn-ghost" href={`/api/projects/${project.id}/script.yaml`} download>
                下载 YAML
              </a>
            </>
          )}
        </div>
      </div>

      {error && (
        <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}

      <section className="grid gap-4 md:grid-cols-4">
        <InfoCard label="状态" value={formatStatus(project.status)} />
        <InfoCard label="章节" value={project.chapter_count} />
        <InfoCard label="版本" value={project.version_count} />
        <InfoCard
          label="校验"
          value={project.latest_version?.validation_status ?? "暂无版本"}
        />
      </section>

      <section className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <div className="card">
          <div className="mb-4 flex items-center justify-between">
            <h2 className="text-base font-semibold">章节</h2>
            <span className="text-xs text-ink-500">{project.chapter_count} 章</span>
          </div>
          <ul className="space-y-2">
            {project.chapters.map((chapter) => (
              <li
                key={chapter.id}
                className="flex items-center justify-between gap-3 rounded border border-white/10 bg-white/[0.02] px-3 py-2"
              >
                <div>
                  <div className="text-sm text-ink-100">{chapter.title}</div>
                  <div className="mt-1 font-mono text-xs text-ink-500">{chapter.id}</div>
                </div>
                <span className="text-xs text-ink-400">{chapter.word_count} 字</span>
              </li>
            ))}
          </ul>
        </div>

        <aside className="space-y-4">
          <div className="card">
            <h2 className="text-base font-semibold">最近版本</h2>
            {project.latest_version ? (
              <div className="mt-3 space-y-2 text-sm">
                <div className="font-mono text-xs text-ink-400">
                  {project.latest_version.id}
                </div>
                <div>标签：{project.latest_version.label || formatSource(project.latest_version.source_type)}</div>
                <div>来源：{formatSource(project.latest_version.source_type)}</div>
                <div>状态：{project.latest_version.validation_status}</div>
                <div className="text-ink-400">
                  创建于 {formatDate(project.latest_version.created_at)}
                </div>
              </div>
            ) : (
              <p className="mt-3 text-sm text-ink-400">生成或保存后会出现版本。</p>
            )}
          </div>

          <div className="card">
            <h2 className="text-base font-semibold">最近任务</h2>
            {project.latest_run ? (
              <div className="mt-3 space-y-2 text-sm">
                <div className="font-mono text-xs text-ink-400">{project.latest_run.id}</div>
                <div>
                  {project.latest_run.status} · {project.latest_run.progress}%
                </div>
                <Link href={`/runs/${project.latest_run.id}`} className="btn-ghost mt-2 w-full">
                  查看进度
                </Link>
              </div>
            ) : (
              <p className="mt-3 text-sm text-ink-400">暂无生成任务。</p>
            )}
          </div>

          <div className="card">
            <h2 className="text-base font-semibold">修改记录</h2>
            {edits.length > 0 ? (
              <ul className="mt-3 space-y-3 text-sm">
                {edits.map((event) => (
                  <li key={event.id} className="border-t border-white/10 pt-3 first:border-t-0 first:pt-0">
                    <div className="flex items-center justify-between gap-3">
                      <span>{formatEditType(event.edit_type)}</span>
                      <span className="text-xs text-ink-500">{formatDate(event.created_at)}</span>
                    </div>
                    <div className="mt-1 font-mono text-xs text-ink-500">
                      {event.version_id ?? event.target_path}
                    </div>
                    {event.note && (
                      <div className="mt-1 line-clamp-2 text-xs text-ink-400">{event.note}</div>
                    )}
                  </li>
                ))}
              </ul>
            ) : (
              <p className="mt-3 text-sm text-ink-400">暂无修改记录。</p>
            )}
          </div>
        </aside>
      </section>
    </div>
  );
}

function InfoCard({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="card">
      <div className="text-xs text-ink-500">{label}</div>
      <div className="mt-2 text-lg font-semibold">{value}</div>
    </div>
  );
}

function formatStatus(value: string) {
  return (
    {
      created: "已创建",
      generating: "生成中",
      ready: "可编辑",
      needs_review: "待处理",
      failed: "失败",
    }[value] ?? value
  );
}

function formatAdaptation(value: string) {
  return (
    {
      short_drama: "短剧",
      series: "剧集",
      film: "电影",
      stage: "舞台剧",
      other: "其他",
    }[value] ?? value
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

function formatEditType(value: string) {
  return (
    {
      manual_save: "手动保存",
      restore: "历史恢复",
      ai_patch: "AI 改编",
      repair: "自动修复",
      import: "导入",
    }[value] ?? value
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}
