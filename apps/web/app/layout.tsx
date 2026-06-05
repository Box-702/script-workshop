import type { Metadata } from "next";
import Link from "next/link";
import "../styles/globals.css";

export const metadata: Metadata = {
  title: "剧本工坊",
  description: "AI 剧本工作台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="h-full">
      <body className="min-h-screen">
        <header className="border-b border-ink-600/30 bg-ink-900/70 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <Link href="/" className="flex items-center gap-2 text-ink-50 hover:text-ink-50">
              <span className="inline-block h-6 w-6 rounded bg-accent-500" />
              <span className="font-semibold tracking-tight">剧本工坊</span>
            </Link>
            <nav className="flex items-center gap-4 text-sm text-ink-400">
              <Link href="/dashboard">项目</Link>
              <Link href="/new">新建</Link>
              <Link href="/settings">模型设置</Link>
              <a href="https://github.com/Box-702/script-workshop" target="_blank" rel="noreferrer">
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 py-10 text-xs text-ink-400">
          本地优先 · OpenAI 兼容接口 · YAML 剧本资产
        </footer>
      </body>
    </html>
  );
}
