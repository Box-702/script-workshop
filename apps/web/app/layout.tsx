import type { Metadata } from "next";
import Link from "next/link";
import { AuthStatus } from "@/components/AuthStatus";
import { LocalModeNotice } from "@/components/LocalModeNotice";
import { StyleSwitcher } from "@/components/StyleSwitcher";
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
      <head>
        {/*
          Read the saved UI style from localStorage and apply it to
          <html data-ui-style="..."> BEFORE the first paint, so the user
          never sees a 0.5s flash of the default theme on reload. This
          must run synchronously in the document head, before any
          stylesheet evaluation.
        */}
        <script
          dangerouslySetInnerHTML={{
            __html: `(function(){try{var s=localStorage.getItem('script-workshop-ui-style');if(s==='paper'||s==='studio'){document.documentElement.dataset.uiStyle=s;}}catch(e){}})();`,
          }}
        />
      </head>
      <body className="min-h-screen">
        <header className="app-header">
          <div className="app-header-inner">
            <Link href="/" className="brand-mark group">
              <span
                aria-hidden="true"
                className="brand-icon"
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
                    stroke="currentColor"
                    strokeWidth="1.55"
                    strokeLinecap="round"
                  />
                </svg>
              </span>
              <span className="brand-text">剧本工坊</span>
            </Link>
            <nav className="app-nav" aria-label="主导航">
              <Link href="/dashboard">项目</Link>
              <Link href="/new">新建</Link>
              <Link href="/settings">模型设置</Link>
              <a href="https://github.com/Box-702/script-workshop" target="_blank" rel="noreferrer">
                GitHub
              </a>
              <StyleSwitcher />
              <AuthStatus />
            </nav>
          </div>
        </header>
        <main className="app-main">
          <LocalModeNotice />
          {children}
        </main>
        <footer className="app-footer">
          本地优先 · OpenAI 兼容接口 · 结构化剧本资产
        </footer>
      </body>
    </html>
  );
}
