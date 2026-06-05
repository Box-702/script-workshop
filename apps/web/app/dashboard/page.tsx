"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { api } from "@/lib/api";
import type { ProjectSummary } from "@/lib/types";

export default function DashboardPage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then(setProjects)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  return (
    <div className="space-y-6">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <h1 className="text-2xl font-semibold tracking-tight">项目</h1>
          <p className="mt-1 text-sm text-ink-400">管理剧本项目、生成结果和版本历史。</p>
        </div>
        <Link href="/new" className="btn-primary">
          新建项目
        </Link>
      </div>

      {error && (
        <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          加载失败：{error}
        </div>
      )}

      {loading ? (
        <div className="card text-sm text-ink-400">加载中...</div>
      ) : projects.length === 0 ? (
        <div className="card flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <div className="text-base font-medium">暂无项目</div>
            <p className="mt-1 text-sm text-ink-400">创建第一个剧本项目后会显示在这里。</p>
          </div>
          <Link href="/new" className="btn-primary">
            开始创建
          </Link>
        </div>
      ) : (
        <div className="grid gap-4 md:grid-cols-2">
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectCard({ project }: { project: ProjectSummary }) {
  return (
    <div className="card space-y-4">
      <div className="flex items-start justify-between gap-3">
        <div>
          <Link
            href={`/projects/${project.id}`}
            className="text-lg font-semibold text-ink-50 hover:text-accent-400"
          >
            {project.title}
          </Link>
          <div className="mt-1 text-xs text-ink-500">{project.id}</div>
        </div>
        <StatusPill value={project.status} />
      </div>

      <div className="grid grid-cols-3 gap-3 text-sm">
        <Metric label="章节" value={project.chapter_count} />
        <Metric label="版本" value={project.version_count} />
        <Metric label="类型" value={formatAdaptation(project.adaptation_type)} />
      </div>

      <div className="flex items-center justify-between gap-3 border-t border-ink-600/30 pt-4 text-xs text-ink-400">
        <span>更新于 {formatDate(project.updated_at)}</span>
        <div className="flex gap-2">
          <Link href={`/projects/${project.id}`} className="btn-ghost px-3 py-1.5 text-xs">
            详情
          </Link>
          {project.version_count > 0 && (
            <Link
              href={`/projects/${project.id}/edit`}
              className="btn-primary px-3 py-1.5 text-xs"
            >
              编辑
            </Link>
          )}
        </div>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <div className="text-xs text-ink-500">{label}</div>
      <div className="mt-1 font-medium text-ink-100">{value}</div>
    </div>
  );
}

function StatusPill({ value }: { value: string }) {
  const color =
    value === "ready"
      ? "bg-emerald-500/15 text-emerald-300"
      : value === "generating"
        ? "bg-amber-500/15 text-amber-300"
        : "bg-ink-700 text-ink-100";
  return (
    <span className={`inline-flex items-center rounded-full px-2.5 py-0.5 text-xs font-medium ${color}`}>
      {formatStatus(value)}
    </span>
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

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}
