import type { Metadata } from "next";
import Link from "next/link";
import "../styles/globals.css";

export const metadata: Metadata = {
  title: "剧本工坊",
  description: "AI 剧本工作台",
  icons: {
    icon: "/icon.svg",
  },
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="zh-CN" className="h-full">
      <body className="min-h-screen">
        <header className="border-b border-ink-600/30 bg-ink-900/90">
          <div className="mx-auto flex max-w-[1680px] items-center justify-between px-4 py-3 sm:px-6">
            <Link href="/" className="flex items-center gap-2 text-ink-50 hover:text-ink-50">
              <span
                aria-hidden="true"
                className="grid h-8 w-8 place-items-center rounded-md border border-accent-400/40 bg-ink-800 text-accent-300 shadow-sm"
              >
                <svg
                  className="h-5 w-5"
                  viewBox="0 0 24 24"
                  fill="none"
                  xmlns="http://www.w3.org/2000/svg"
                >
                  <path
                    d="M7 4.75h7.15L18 8.6v10.65H7V4.75Z"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M14 4.9V9h4"
                    stroke="currentColor"
                    strokeWidth="1.7"
                    strokeLinejoin="round"
                  />
                  <path
                    d="M9.6 11.4h4.8M9.6 14.2h5.8M9.6 17h3.8"
                    stroke="currentColor"
                    strokeWidth="1.55"
                    strokeLinecap="round"
                  />
                  <path
                    d="M5.25 7.55h5.2M4.75 10.35h4.1"
                    stroke="#E6E2FF"
                    strokeWidth="1.55"
                    strokeLinecap="round"
                  />
                </svg>
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
