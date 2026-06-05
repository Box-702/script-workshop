import type { Metadata } from "next";
import "../styles/globals.css";

export const metadata: Metadata = {
  title: "Script Workshop — 剧本工坊",
  description: "AI 小说转剧本工作台",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="h-full">
      <body className="min-h-screen">
        <header className="border-b border-ink-600/30 bg-ink-900/70 backdrop-blur">
          <div className="mx-auto flex max-w-6xl items-center justify-between px-6 py-4">
            <a href="/" className="flex items-center gap-2 text-ink-50 hover:text-ink-50">
              <span className="inline-block h-6 w-6 rounded bg-accent-500" />
              <span className="font-semibold tracking-tight">Script Workshop</span>
              <span className="pill">剧本工坊</span>
            </a>
            <nav className="flex items-center gap-4 text-sm text-ink-400">
              <a href="/">新建</a>
              <a href="/settings">模型设置</a>
              <a href="https://github.com/Box-702/script-workshop" target="_blank" rel="noreferrer">
                GitHub
              </a>
            </nav>
          </div>
        </header>
        <main className="mx-auto max-w-6xl px-6 py-10">{children}</main>
        <footer className="mx-auto max-w-6xl px-6 py-10 text-xs text-ink-400">
          第一版脚手架 · 本地优先 · OpenAI 兼容接口
        </footer>
      </body>
    </html>
  );
}
