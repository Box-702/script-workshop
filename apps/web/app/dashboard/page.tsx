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
  const [projectPendingDelete, setProjectPendingDelete] = useState<ProjectSummary | null>(null);
  const [deletingProjectId, setDeletingProjectId] = useState<string | null>(null);

  useEffect(() => {
    api
      .listProjects()
      .then(setProjects)
      .catch((e) => setError((e as Error).message))
      .finally(() => setLoading(false));
  }, []);

  async function confirmDeleteProject() {
    if (!projectPendingDelete) return;
    setError(null);
    setDeletingProjectId(projectPendingDelete.id);
    try {
      await api.deleteProject(projectPendingDelete.id);
      setProjects((current) => current.filter((item) => item.id !== projectPendingDelete.id));
      setProjectPendingDelete(null);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setDeletingProjectId(null);
    }
  }

  return (
    <div className="dashboard-shell">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <div className="page-kicker">工作台</div>
          <h1 className="page-title">项目看板</h1>
          <p className="page-description">管理剧本项目、生成结果、版本历史和导出入口。</p>
        </div>
        <Link href="/new" className="btn-primary">
          新建项目
        </Link>
      </div>

      {isAuthRequiredMessage(error) ? (
        <AuthRequiredMessage />
      ) : error ? (
        <div className="notice-error">
          加载失败：{error}
        </div>
      ) : null}

      {projectPendingDelete && (
        <DeleteProjectPanel
          project={projectPendingDelete}
          busy={deletingProjectId === projectPendingDelete.id}
          onCancel={() => setProjectPendingDelete(null)}
          onConfirm={confirmDeleteProject}
        />
      )}

      {loading ? (
        <div className="card loading-panel">加载中...</div>
      ) : projects.length === 0 ? (
        <div className="card empty-panel">
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
          <div className="project-table-head">
            <div>项目</div>
            <div>状态</div>
            <div>章节</div>
            <div>版本</div>
            <div>操作</div>
          </div>
          {projects.map((project, index) => (
            <div
              key={project.id}
              className="project-row sw-anim-in"
              style={{ "--sw-delay": `${Math.min(index, 12) * 40}ms` } as React.CSSProperties}
            >
              <ProjectCard
                project={project}
                deleting={deletingProjectId === project.id}
                requestDelete={setProjectPendingDelete}
              />
            </div>
          ))}
        </div>
      )}
    </div>
  );
}

function ProjectCard({
  project,
  deleting,
  requestDelete,
}: {
  project: ProjectSummary;
  deleting: boolean;
  requestDelete: (project: ProjectSummary) => void;
}) {
  return (
    <>
      <div className="min-w-0">
        <Link
          href={`/projects/${project.id}`}
          className="project-title-link"
        >
          {project.title}
        </Link>
        <div className="mt-1 truncate text-sm text-ink-400">
          {formatAdaptation(project.adaptation_type)} · 更新于 {formatDate(project.updated_at)}
        </div>
      </div>

      <div>
        <StatusPill value={displayProjectStatus(project)} />
      </div>
      <div className="hidden sm:block">
        <Metric label="章节" value={project.chapter_count} />
      </div>
      <div className="hidden lg:block">
        <Metric label="版本" value={project.version_count} />
      </div>
      <div className="project-version-note hidden lg:block">
        {project.latest_version
          ? `${formatVersionLabel(project.latest_version.label, project.latest_version.source_type)} · ${formatValidation(project.latest_version.validation_status)}`
          : "暂无版本"}
      </div>
      <div className="project-actions flex flex-wrap items-center gap-2">
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
          className="btn-danger px-3 py-1.5 text-xs"
          onClick={() => requestDelete(project)}
          disabled={deleting}
        >
          {deleting ? "删除中..." : "删除"}
        </button>
      </div>
    </>
  );
}

function DeleteProjectPanel({
  project,
  busy,
  onCancel,
  onConfirm,
}: {
  project: ProjectSummary;
  busy: boolean;
  onCancel: () => void;
  onConfirm: () => void;
}) {
  return (
    <section className="danger-panel">
      <div className="flex flex-col gap-3 md:flex-row md:items-center md:justify-between">
        <div>
          <div className="danger-title">确认删除《{project.title}》？</div>
          <p className="danger-copy">
            项目章节、生成记录、剧本快照和本地版本都会一并删除。
          </p>
        </div>
        <div className="flex shrink-0 gap-2">
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={onCancel} disabled={busy}>
            取消
          </button>
          <button
            type="button"
            className="btn-danger px-3 py-1.5 text-xs"
            onClick={onConfirm}
            disabled={busy}
          >
            {busy ? "删除中..." : "确认删除"}
          </button>
        </div>
      </div>
    </section>
  );
}

function Metric({ label, value }: { label: string; value: string | number }) {
  return (
    <div className="metric">
      <div className="metric-label">{label}</div>
      <div className="metric-value">{value}</div>
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
    <span className={`status-pill ${color}`}>
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
