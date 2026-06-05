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
        <header className="border-b border-ink-600/30 bg-ink-900/90">
          <div className="mx-auto flex max-w-[1680px] items-center justify-between px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2 text-ink-50 hover:text-ink-50">
              <span aria-hidden="true" className="grid h-7 w-7 place-items-center rounded-md bg-accent-500 text-xs font-semibold text-ink-50">
                剧
              </span>
              <span className="font-semibold tracking-tight">剧本工坊</span>
            </Link>
            <nav className="flex items-center gap-2 text-sm text-ink-400 sm:gap-4">
              <Link href="/dashboard">项目</Link>
              <Link href="/new">新建</Link>
              <Link href="/settings">模型设置</Link>
              <a href="https://github.com/Box-702/script-workshop" target="_blank" rel="noreferrer">
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto min-h-[calc(100vh-112px)] w-full max-w-[1680px] px-4 py-6 sm:px-6">
          {children}
        </main>
        <footer className="mx-auto max-w-[1680px] px-4 pb-8 text-xs text-ink-500 sm:px-6">
          本地优先 · OpenAI 兼容接口 · 结构化剧本资产
        </footer>
      </body>
    </html>
  );
}
