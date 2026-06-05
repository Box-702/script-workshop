import Link from "next/link";

export default function HomePage() {
  return (
    <div className="space-y-6">
      <section className="card">
        <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">剧本工坊</h1>
            <p className="mt-2 text-sm text-ink-400">
              AI 剧本工作台：生成、编辑、校验并保存剧本版本。
            </p>
          </div>
          <div className="flex flex-wrap gap-2">
            <Link href="/dashboard" className="btn-primary">
              项目
            </Link>
            <Link href="/new" className="btn-ghost">
              新建
            </Link>
          </div>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Step title="导入" desc="粘贴或上传三章以上小说文本。" />
        <Step title="生成" desc="生成角色、场景、对白和结构化 YAML。" />
        <Step title="打磨" desc="编辑剧本并保存历史版本。" />
      </section>
    </div>
  );
}

function Step({ title, desc }: { title: string; desc: string }) {
  return (
    <div className="card">
      <div className="text-base font-medium">{title}</div>
      <p className="mt-1 text-sm text-ink-400">{desc}</p>
    </div>
  );
}
