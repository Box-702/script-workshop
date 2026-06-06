import Link from "next/link";

export default function HomePage() {
  return (
    <div className="grid min-h-[70vh] gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="panel relative flex flex-col justify-between overflow-hidden">
        {/* Decorative background gradient that softly pulses */}
        <div
          aria-hidden
          className="pointer-events-none absolute inset-0 -z-0 opacity-60"
          style={{
            background:
              "radial-gradient(60% 50% at 20% 0%, rgb(var(--accent-500) / 0.18) 0%, transparent 70%), radial-gradient(40% 30% at 90% 100%, rgb(var(--accent-500) / 0.10) 0%, transparent 70%)",
          }}
        />

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
            之后你可以在结构化表单里逐场打磨，让 AI 助手按你的提示局部重写，每一步都进入版本系统——
            任何时候都能回滚、对比、导出。
          </p>

          <div
            className="sw-anim-in-up mt-8 flex flex-wrap gap-3"
            style={{ "--sw-delay": "280ms" } as React.CSSProperties}
          >
            <Link href="/dashboard" className="btn-primary sw-attention">
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
              <span className="h-1.5 w-1.5 rounded-full bg-emerald-400 sw-pulse" />
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
            desc="结构化编辑、AI 改编、版本回退。"
            delay={240}
          />
        </div>
      </section>

      <aside
        className="sw-anim-scale panel"
        style={{ "--sw-delay": "200ms" } as React.CSSProperties}
      >
        <div className="panel-header">
          <h2 className="text-sm font-medium text-ink-100">当前工作区</h2>
        </div>
        <div className="panel-body space-y-3 text-sm">
          <QuickLink
            title="项目看板"
            desc="查看所有剧本、版本状态和生成结果。"
            href="/dashboard"
            delay={320}
          />
          <QuickLink
            title="新建项目"
            desc="上传或粘贴三章以上小说文本。"
            href="/new"
            delay={400}
          />
          <QuickLink
            title="模型设置"
            desc="保存云端模型密钥，或只在当前浏览器使用。"
            href="/settings"
            delay={480}
          />
        </div>

        <div className="border-t border-ink-600/30 px-4 py-4">
          <div className="text-xs font-medium uppercase tracking-wider text-ink-500">
            快速特性
          </div>
          <ul className="mt-3 space-y-2 text-sm text-ink-300">
            <li className="flex items-start gap-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-500" />
              <span>章节切分 / 摘要 / 故事圣经 / 角色弧光</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-500" />
              <span>结构化编辑 + YAML 源码双视图</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-500" />
              <span>命名快照 / diff / 一键回滚</span>
            </li>
            <li className="flex items-start gap-2">
              <span className="mt-1 h-1.5 w-1.5 shrink-0 rounded-full bg-accent-500" />
              <span>Supabase RLS 多用户隔离</span>
            </li>
          </ul>
        </div>
      </aside>
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

function QuickLink({
  title,
  desc,
  href,
  delay,
}: {
  title: string;
  desc: string;
  href: string;
  delay: number;
}) {
  return (
    <Link
      href={href}
      className="sw-anim-in block rounded-md border border-ink-600/30 bg-ink-900/60 p-3 text-ink-200 transition-all duration-200 ease-out hover:-translate-y-0.5 hover:border-accent-500/50 hover:bg-ink-800 hover:shadow-md hover:shadow-accent-500/10"
      style={{ "--sw-delay": `${delay}ms` } as React.CSSProperties}
    >
      <div className="flex items-center justify-between">
        <span className="font-medium">{title}</span>
        <span
          aria-hidden
          className="text-ink-500 transition-transform duration-200 group-hover:translate-x-1"
        >
          →
        </span>
      </div>
      <p className="mt-1 leading-6 text-ink-400">{desc}</p>
    </Link>
  );
}
