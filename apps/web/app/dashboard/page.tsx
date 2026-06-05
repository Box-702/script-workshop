"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AuthRequiredMessage, isAuthRequiredMessage } from "@/components/AuthRequiredMessage";
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

  async function deleteProject(project: ProjectSummary) {
    const ok = window.confirm(`确定删除《${project.title}》吗？项目章节、生成记录和剧本版本都会一并删除。`);
    if (!ok) return;
    setError(null);
    try {
      await api.deleteProject(project.id);
      setProjects((current) => current.filter((item) => item.id !== project.id));
    } catch (e) {
      setError((e as Error).message);
    }
  }

  return (
    <div className="space-y-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="text-sm text-ink-400">工作台</div>
          <h1 className="mt-1 text-2xl font-semibold tracking-tight">项目看板</h1>
          <p className="mt-1 text-sm text-ink-400">管理剧本项目、生成结果、版本历史和导出入口。</p>
        </div>
        <Link href="/new" className="btn-primary">
          新建项目
        </Link>
      </div>

      {isAuthRequiredMessage(error) ? (
        <AuthRequiredMessage />
      ) : error ? (
        <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          加载失败：{error}
        </div>
      ) : null}

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
        <div className="panel overflow-hidden">
          <div className="grid grid-cols-[minmax(0,1.5fr)_120px_100px_100px_220px] gap-4 border-b border-ink-600/30 px-4 py-3 text-xs text-ink-500 max-lg:hidden">
            <div>项目</div>
            <div>状态</div>
            <div>章节</div>
            <div>版本</div>
            <div>操作</div>
          </div>
          {projects.map((project) => (
            <ProjectCard key={project.id} project={project} deleteProject={deleteProject} />
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectCard({
  project,
  deleteProject,
}: {
  project: ProjectSummary;
  deleteProject: (project: ProjectSummary) => void;
}) {
  return (
    <div className="grid gap-3 border-b border-ink-600/30 px-4 py-4 last:border-b-0 lg:grid-cols-[minmax(0,1.5fr)_120px_100px_100px_220px] lg:items-center">
      <div className="min-w-0">
        <div className="flex items-start justify-between gap-3 lg:block">
          <Link
            href={`/projects/${project.id}`}
            className="text-lg font-semibold text-ink-50 hover:text-accent-400"
          >
            {project.title}
          </Link>
          <div className="mt-1 text-sm text-ink-400">
            {formatAdaptation(project.adaptation_type)} · 更新于 {formatDate(project.updated_at)}
          </div>
          <div className="lg:hidden">
            <StatusPill value={displayProjectStatus(project)} />
          </div>
        </div>
      </div>

      <div className="hidden lg:block">
        <StatusPill value={displayProjectStatus(project)} />
      </div>
      <Metric label="章节" value={project.chapter_count} />
      <Metric label="版本" value={project.version_count} />
      <div className="text-sm text-ink-400 max-lg:rounded-md max-lg:border max-lg:border-ink-600/30 max-lg:bg-ink-900/50 max-lg:p-3 lg:col-span-4 lg:col-start-1 lg:mt-[-10px]">
        {project.latest_version
          ? `当前版本：${formatVersionLabel(project.latest_version.label, project.latest_version.source_type)} · ${formatValidation(project.latest_version.validation_status)}`
          : "暂无剧本版本"}
      </div>
      <div className="flex flex-wrap gap-2 lg:col-start-5 lg:row-start-1">
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
        <button
          type="button"
          className="btn-ghost px-3 py-1.5 text-xs text-red-200 hover:bg-red-500/15"
          onClick={() => deleteProject(project)}
        >
          删除
        </button>
      </div>
    </div>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="text-sm">
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
        : value === "failed"
          ? "bg-red-500/15 text-red-300"
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

function displayProjectStatus(project: ProjectSummary) {
  if (project.latest_run?.status === "failed") return "failed";
  if (project.latest_run?.status === "queued" || project.latest_run?.status === "running") {
    return "generating";
  }
  return project.status;
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

function formatVersionLabel(label: string | null, sourceType: string) {
  if (label === "AI generated draft") return "AI 生成初稿";
  return label || formatSource(sourceType);
}

function formatValidation(value: string) {
  return (
    {
      valid: "校验通过",
      invalid: "待处理",
    }[value] ?? value
  );
}

function formatDate(value: string) {
  return new Date(value).toLocaleString();
}
