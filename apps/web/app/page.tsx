"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";
import { isAuthRequiredMessage } from "@/components/AuthRequiredMessage";
import { api } from "@/lib/api";
import { getSessionUser, onAuthStateChanged, type AuthUser } from "@/lib/auth";
import type { ProjectSummary } from "@/lib/types";

type WorkspaceState = "loading" | "ready" | "auth" | "error";

export default function HomePage() {
  const [projects, setProjects] = useState<ProjectSummary[]>([]);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [state, setState] = useState<WorkspaceState>("loading");
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    let requestId = 0;

    async function loadWorkspace(nextUser?: AuthUser | null) {
      const currentRequestId = ++requestId;
      setState("loading");
      setError(null);
      try {
        const currentUser = typeof nextUser === "undefined" ? await getSessionUser() : nextUser;
        const nextProjects = await api.listProjects();
        if (!alive || currentRequestId !== requestId) return;
        setUser(currentUser);
        setProjects(nextProjects);
        setState("ready");
      } catch (e) {
        if (!alive || currentRequestId !== requestId) return;
        const message = (e as Error).message;
        setProjects([]);
        setState(isAuthRequiredMessage(message) ? "auth" : "error");
        setError(message);
      }
    }

    void loadWorkspace();
    let unsubscribe: (() => void) | undefined;
    onAuthStateChanged((nextUser, event) => {
      if (!alive) return;
      if (event === "INITIAL_SESSION") {
        setUser(nextUser);
        return;
      }
      setUser(nextUser);
      void loadWorkspace(nextUser);
    }).then((cleanup) => {
      unsubscribe = cleanup;
    });

    return () => {
      alive = false;
      unsubscribe?.();
    };
  }, []);

  const workspaceStats = useMemo(() => {
    return {
      chapters: projects.reduce((sum, project) => sum + project.chapter_count, 0),
      versions: projects.reduce((sum, project) => sum + project.version_count, 0),
      ready: projects.filter((project) => project.version_count > 0).length,
    };
  }, [projects]);

  const recentProjects = useMemo(
    () =>
      [...projects]
        .sort((a, b) => new Date(b.updated_at).getTime() - new Date(a.updated_at).getTime())
        .slice(0, 3),
    [projects],
  );

  return (
    <div className="grid min-h-[70vh] gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="panel flex flex-col justify-between overflow-hidden">
        <div className="panel-body relative z-10 max-w-3xl py-10">
          <div
            className="sw-anim-in text-xs font-medium uppercase tracking-[0.2em] text-accent-400"
            style={{ "--sw-delay": "0ms" } as React.CSSProperties}
          >
            AI 剧本 IDE · 改编工作台
          </div>
          <h1
            className="sw-anim-in-up mt-4 text-4xl font-semibold tracking-tight text-ink-50 sm:text-5xl"
            style={{ "--sw-delay": "80ms" } as React.CSSProperties}
          >
            剧本工坊
            <span className="ml-3 inline-block text-2xl text-ink-400 sm:text-3xl">/ Script Workshop</span>
          </h1>
          <p
            className="sw-anim-in-up mt-5 max-w-2xl text-base leading-7 text-ink-300"
            style={{ "--sw-delay": "180ms" } as React.CSSProperties}
          >
            从小说原文到结构化剧本初稿，<span className="text-ink-100">8 阶段 AI 流水线</span> 一次跑完。
            之后你可以在结构化表单里逐场打磨，让 AI 助手按你的提示局部重写，每一步都进入版本系统，
            任何时候都能回滚、对比、导出。
          </p>

          <div
            className="sw-anim-in-up mt-8 flex flex-wrap gap-3"
            style={{ "--sw-delay": "280ms" } as React.CSSProperties}
          >
            <Link href="/dashboard" className="btn-primary">
              进入项目
            </Link>
            <Link href="/new" className="btn-ghost">
              新建剧本
            </Link>
            <Link href="/settings" className="btn-ghost">
              模型设置
            </Link>
          </div>

          <div
            className="sw-anim-in-up mt-10 flex flex-wrap items-center gap-x-6 gap-y-2 text-xs text-ink-500"
            style={{ "--sw-delay": "380ms" } as React.CSSProperties}
          >
            <span className="inline-flex items-center gap-1.5">
              <span className="h-1.5 w-1.5 rounded-full state-success" />
              Next.js 14 · FastAPI · Supabase
            </span>
            <span>·</span>
            <span>支持 OpenAI 兼容 Provider</span>
            <span>·</span>
            <span>免费部署 (Vercel + Render + Supabase)</span>
          </div>
        </div>

        <div className="relative z-10 grid border-t border-ink-600/30 md:grid-cols-3">
          <WorkflowStep
            step="01"
            title="导入"
            desc="小说正文、章节文本或故事素材。"
            delay={0}
          />
          <WorkflowStep
            step="02"
            title="生成"
            desc="角色、地点、场景、动作、对白。"
            delay={120}
          />
          <WorkflowStep
            step="03"
            title="打磨"
            desc="结构化编辑、AI 改编、版本回滚。"
            delay={240}
          />
        </div>
      </section>

      <WorkspacePanel
        state={state}
        error={error}
        user={user}
        projects={projects}
        recentProjects={recentProjects}
        stats={workspaceStats}
      />
    </div>
  );
}

function WorkspacePanel({
  state,
  error,
  user,
  projects,
  recentProjects,
  stats,
}: {
  state: WorkspaceState;
  error: string | null;
  user: AuthUser | null;
  projects: ProjectSummary[];
  recentProjects: ProjectSummary[];
  stats: { chapters: number; versions: number; ready: number };
}) {
  return (
    <aside
      className="sw-anim-scale panel flex min-h-[520px] flex-col"
      style={{ "--sw-delay": "200ms" } as React.CSSProperties}
    >
      <div className="panel-header">
        <div>
          <h2 className="text-sm font-medium text-ink-100">当前工作区</h2>
          <p className="mt-1 text-xs text-ink-500">{workspaceSubtitle(state, user, projects.length)}</p>
        </div>
      </div>

      {state === "loading" ? (
        <div className="panel-body space-y-3">
          <SkeletonLine wide />
          <SkeletonLine />
          <SkeletonLine />
          <div className="grid grid-cols-3 gap-2 pt-2">
            <SkeletonBlock />
            <SkeletonBlock />
            <SkeletonBlock />
          </div>
        </div>
      ) : state === "auth" ? (
        <div className="panel-body flex flex-1 flex-col justify-between gap-6">
          <div className="rounded-md border surface-line surface-soft p-4">
            <div className="text-sm font-medium text-ink-100">请登录后查看工作区</div>
            <p className="mt-2 text-sm leading-6 text-ink-400">
              登录后会显示你的项目数量、最近剧本、版本状态和模型配置入口。不同账号只能看到自己的剧本资产。
            </p>
          </div>
          <div className="space-y-2">
            <Link href="/login" className="btn-primary w-full justify-center">
              登录 / 注册
            </Link>
            <Link href="/dashboard" className="btn-ghost w-full justify-center">
              查看本地工作区
            </Link>
          </div>
        </div>
      ) : state === "error" ? (
        <div className="panel-body flex flex-1 flex-col justify-between gap-6">
          <div className="rounded-md border surface-line surface-soft p-4">
            <div className="text-sm font-medium text-ink-100">工作区暂时没有连上</div>
            <p className="mt-2 text-sm leading-6 text-ink-400">
              可能是后端服务正在冷启动。项目看板和编辑器不受这个面板限制，稍后刷新即可看到项目摘要。
            </p>
            {error && <div className="mt-3 break-all text-xs text-ink-500">{error}</div>}
          </div>
          <Link href="/dashboard" className="btn-ghost w-full justify-center">
            打开项目看板
          </Link>
        </div>
      ) : projects.length === 0 ? (
        <div className="panel-body flex flex-1 flex-col justify-between gap-6">
          <div>
            <WorkspaceMetrics projects={0} chapters={0} versions={0} />
            <div className="mt-4 rounded-md border surface-line surface-soft p-4">
              <div className="text-sm font-medium text-ink-100">还没有保存的项目</div>
              <p className="mt-2 text-sm leading-6 text-ink-400">
                创建第一个剧本后，这里会显示最近项目、章节数量、版本状态和可继续编辑的入口。
              </p>
            </div>
          </div>
          <Link href="/new" className="btn-primary w-full justify-center">
            创建第一个项目
          </Link>
        </div>
      ) : (
        <div className="flex min-h-0 flex-1 flex-col">
          <div className="panel-body space-y-4">
            <WorkspaceMetrics projects={projects.length} chapters={stats.chapters} versions={stats.versions} />
            <div className="rounded-md border surface-line surface-soft p-3">
              <div className="flex items-center justify-between gap-2 text-xs">
                <span className="text-ink-500">可编辑剧本</span>
                <span className="font-medium text-ink-200">{stats.ready} / {projects.length}</span>
              </div>
              <div className="mt-2 h-1.5 overflow-hidden rounded-full bg-ink-800">
                <div
                  className="h-full rounded-full bg-accent-500"
                  style={{ width: `${projects.length ? Math.max(8, (stats.ready / projects.length) * 100) : 0}%` }}
                />
              </div>
            </div>
          </div>

          <div className="border-t border-ink-600/30 px-4 py-4">
            <div className="mb-3 flex items-center justify-between gap-3">
              <div className="text-xs font-medium uppercase tracking-wider text-ink-500">最近项目</div>
              <Link href="/dashboard" className="text-xs text-accent-400 hover:text-accent-500">
                全部
              </Link>
            </div>
            <ul className="space-y-2">
              {recentProjects.map((project) => (
                <li key={project.id}>
                  <Link
                    href={project.version_count > 0 ? `/projects/${project.id}/edit` : `/projects/${project.id}`}
                    className="block rounded-md border surface-line surface-soft p-3 transition-colors hover:border-accent-500/50 hover:bg-ink-800"
                  >
                    <div className="flex items-center justify-between gap-3">
                      <div className="min-w-0 truncate text-sm font-medium text-ink-100">{project.title}</div>
                      <span className="shrink-0 text-xs text-ink-500">{formatProjectStatus(project)}</span>
                    </div>
                    <div className="mt-2 flex flex-wrap gap-x-3 gap-y-1 text-xs text-ink-500">
                      <span>{project.chapter_count} 章</span>
                      <span>{project.version_count} 版</span>
                      <span>{formatDate(project.updated_at)}</span>
                    </div>
                  </Link>
                </li>
              ))}
            </ul>
          </div>
        </div>
      )}
    </aside>
  );
}

function WorkspaceMetrics({ projects, chapters, versions }: { projects: number; chapters: number; versions: number }) {
  return (
    <div className="grid grid-cols-3 gap-2 text-center">
      <WorkspaceMetric label="项目" value={projects} />
      <WorkspaceMetric label="章节" value={chapters} />
      <WorkspaceMetric label="快照" value={versions} />
    </div>
  );
}

function WorkspaceMetric({ label, value }: { label: string; value: number }) {
  return (
    <div className="rounded-md border surface-line surface-soft px-2 py-3">
      <div className="text-lg font-semibold text-ink-100">{value}</div>
      <div className="mt-1 text-xs text-ink-500">{label}</div>
    </div>
  );
}

function WorkflowStep({
  step,
  title,
  desc,
  delay,
}: {
  step: string;
  title: string;
  desc: string;
  delay: number;
}) {
  return (
    <div
      className="sw-anim-in border-b border-ink-600/30 p-4 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0"
      style={{ "--sw-delay": `${delay}ms` } as React.CSSProperties}
    >
      <div className="text-xs font-semibold uppercase tracking-wider text-accent-400">
        {step}
      </div>
      <div className="mt-1 text-sm font-medium text-ink-100">{title}</div>
      <p className="mt-1 text-sm leading-6 text-ink-400">{desc}</p>
    </div>
  );
}

function SkeletonLine({ wide = false }: { wide?: boolean }) {
  return <div className={`h-4 rounded bg-ink-800 ${wide ? "w-3/4" : "w-1/2"}`} />;
}

function SkeletonBlock() {
  return <div className="h-16 rounded-md border surface-line bg-ink-800/60" />;
}

function workspaceSubtitle(state: WorkspaceState, user: AuthUser | null, projectCount: number) {
  if (state === "loading") return "正在读取你的剧本资产";
  if (state === "auth") return "登录后显示项目和资源状态";
  if (state === "error") return "工作区暂时不可用";
  if (user?.email) return `${user.email} · ${projectCount} 个项目`;
  return `${projectCount} 个本地项目`;
}

function formatProjectStatus(project: ProjectSummary) {
  if (project.latest_run?.status === "running" || project.latest_run?.status === "queued") return "生成中";
  if (project.latest_run?.status === "failed") return "失败";
  if (project.version_count > 0) return "可编辑";
  return "草稿";
}

function formatDate(value: string) {
  return new Date(value).toLocaleDateString("zh-CN", {
    month: "numeric",
    day: "numeric",
  });
}
