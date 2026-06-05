import Link from "next/link";

export default function HomePage() {
  return (
    <div className="space-y-8">
      <section className="card">
        <h1 className="text-2xl font-semibold tracking-tight">把小说，改成剧本</h1>
        <p className="mt-2 text-sm text-ink-400">
          粘贴至少 3 章小说文本，ScriptForge AI 会自动拆解为人物、场景、对白，
          并输出可编辑、可校验、可追溯的 YAML 剧本初稿。
        </p>
        <div className="mt-6 flex gap-3">
          <Link href="/new" className="btn-primary">开始创建项目</Link>
          <a
            href="https://github.com/Box-702/script-workshop/blob/main/DESIGN.md"
            target="_blank"
            rel="noreferrer"
            className="btn-ghost"
          >
            阅读设计文档
          </a>
        </div>
      </section>

      <section className="grid gap-4 md:grid-cols-3">
        <Step n={1} title="输入小说" desc="粘贴文本或上传 .txt / .md，至少 3 章。" />
        <Step n={2} title="AI 改编" desc="8 阶段 pipeline：章节摘要 → 故事圣经 → 人物 → 场景 → 校验 → 修复。" />
        <Step n={3} title="编辑与导出" desc="YAML 编辑器实时校验、一键修复、导出 Markdown / JSON。" />
      </section>
    </div>
  );
}

function Step({ n, title, desc }: { n: number; title: string; desc: string }) {
  return (
    <div className="card">
      <div className="text-accent-400 text-sm font-semibold">第 {n} 步</div>
      <div className="mt-1 text-base font-medium">{title}</div>
      <p className="mt-1 text-sm text-ink-400">{desc}</p>
    </div>
  );
}
