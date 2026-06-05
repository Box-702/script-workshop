import Link from "next/link";

export default function HomePage() {
  return (
    <div className="grid min-h-[70vh] gap-6 lg:grid-cols-[minmax(0,1fr)_360px]">
      <section className="panel flex flex-col justify-between overflow-hidden">
        <div className="panel-body max-w-3xl py-10">
          <div className="text-sm text-ink-400">AI 剧本 IDE 与改编工作台</div>
          <h1 className="mt-3 text-3xl font-semibold tracking-tight text-ink-50">
            剧本工坊
          </h1>
          <p className="mt-4 max-w-2xl text-base leading-7 text-ink-300">
            从小说生成结构化剧本初稿，再进入可保存、可校验、可导出的编辑工作流。创作界面优先展示编剧能读懂的场景、动作和对白，源码只作为高级入口保留。
          </p>
          <div className="mt-8 flex flex-wrap gap-3">
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
        </div>
        <div className="grid border-t border-ink-600/30 md:grid-cols-3">
          <WorkflowStep title="导入" desc="小说正文、章节文本或故事素材。" />
          <WorkflowStep title="生成" desc="角色、地点、场景、动作、对白。" />
          <WorkflowStep title="打磨" desc="结构化编辑、AI 改编、版本回退。" />
        </div>
      </section>

      <aside className="panel">
        <div className="panel-header">
          <h2 className="text-sm font-medium text-ink-100">当前工作区</h2>
        </div>
        <div className="panel-body space-y-4 text-sm">
          <QuickLink title="项目看板" desc="查看所有剧本、版本状态和生成结果。" href="/dashboard" />
          <QuickLink title="新建项目" desc="上传或粘贴三章以上小说文本。" href="/new" />
          <QuickLink title="模型设置" desc="保存云端模型密钥，或只在当前浏览器使用。" href="/settings" />
        </div>
      </aside>
    </div>
  );
}

function WorkflowStep({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="border-b border-ink-600/30 p-4 last:border-b-0 md:border-b-0 md:border-r md:last:border-r-0">
      <div className="text-sm font-medium text-ink-100">{title}</div>
      <p className="mt-1 text-sm leading-6 text-ink-400">{desc}</p>
    </div>
  );
}

function QuickLink({ title, desc, href }: { title: string; desc: string; href: string }) {
  return (
    <Link
      href={href}
      className="block rounded-md border border-ink-600/30 bg-ink-900/60 p-3 text-ink-200 hover:border-accent-500/50 hover:bg-ink-800"
    >
      <div className="font-medium">{title}</div>
      <p className="mt-1 leading-6 text-ink-400">{desc}</p>
    </Link>
  );
}
