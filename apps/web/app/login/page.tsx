"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  getAuthUser,
  isSupabaseConfigured,
  onAuthStateChanged,
  signInWithEmail,
  signOut,
  type AuthUser,
} from "@/lib/auth";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="card mx-auto max-w-xl text-sm text-ink-400">加载中...</div>}>
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const params = useSearchParams();
  const nextPath = safeNextPath(params.get("next"));
  const configured = isSupabaseConfigured();
  const [email, setEmail] = useState("");
  const [user, setUser] = useState<AuthUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    if (!configured) return;
    let unsubscribe = () => {};
    void getAuthUser().then(setUser).catch(() => setUser(null));
    void onAuthStateChanged(setUser).then((next) => {
      unsubscribe = next;
    });
    return () => unsubscribe();
  }, [configured]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = email.trim();
    if (!value) {
      setError("请输入邮箱。");
      setNotice(null);
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await signInWithEmail(value, nextPath);
      setNotice("登录链接已发送，请查看邮箱。");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function logout() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await signOut();
      setUser(null);
      setNotice("已退出登录。");
    } catch (err) {
      setError((err as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="mx-auto max-w-xl space-y-5">
      <div>
        <div className="text-sm text-ink-400">账号</div>
        <h1 className="mt-1 text-2xl font-semibold tracking-tight">登录剧本工坊</h1>
        <p className="mt-1 text-sm text-ink-400">
          登录后项目、版本、模型 key 和 AI 改编记录会按账号隔离。
        </p>
      </div>

      {!configured ? (
        <div className="card border-amber-500/40 bg-amber-500/10 text-amber-100">
          当前未配置 Supabase，应用会继续使用本地单用户模式。
        </div>
      ) : user ? (
        <section className="card space-y-4">
          <div>
            <div className="label">当前账号</div>
            <div className="font-mono text-sm text-ink-100">{user.email || user.id}</div>
          </div>
          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className="btn-ghost" onClick={logout} disabled={busy}>
              退出登录
            </button>
            <Link href={nextPath} className="btn-primary">
              继续
            </Link>
          </div>
        </section>
      ) : (
        <form className="card space-y-4" onSubmit={submit}>
          <div>
            <label className="label" htmlFor="email">邮箱</label>
            <input
              id="email"
              className="input"
              type="email"
              value={email}
              onChange={(e) => setEmail(e.target.value)}
              placeholder="you@example.com"
              autoComplete="email"
            />
          </div>
          <button type="submit" className="btn-primary w-full" disabled={busy}>
            {busy ? "发送中..." : "发送登录链接"}
          </button>
        </form>
      )}

      {notice && (
        <div className="rounded border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          {notice}
        </div>
      )}
      {error && (
        <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          {error}
        </div>
      )}
    </div>
  );
}

function safeNextPath(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/dashboard";
  return value;
}
