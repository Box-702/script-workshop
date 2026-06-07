"use client";

import Link from "next/link";
import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import {
  getAuthErrorMessage,
  getAuthUser,
  isSupabaseConfigured,
  isAuthRateLimitError,
  onAuthStateChanged,
  OTP_RESEND_COOLDOWN_SECONDS,
  sendEmailOtp,
  signOut,
  type AuthUser,
  verifyEmailOtp,
} from "@/lib/auth";

export default function LoginPage() {
  return (
    <Suspense fallback={<div className="card mx-auto max-w-xl text-sm text-ink-400">加载中...</div>}>
      <LoginContent />
    </Suspense>
  );
}

function LoginContent() {
  const router = useRouter();
  const params = useSearchParams();
  const nextPath = safeNextPath(params.get("next"));
  const configured = isSupabaseConfigured();
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sentEmail, setSentEmail] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resendSeconds, setResendSeconds] = useState(0);

  useEffect(() => {
    if (!configured) return;
    let unsubscribe = () => {};
    void getAuthUser().then(setUser).catch(() => setUser(null));
    void onAuthStateChanged(setUser).then((next) => {
      unsubscribe = next;
    });
    return () => unsubscribe();
  }, [configured]);

  useEffect(() => {
    if (resendSeconds <= 0) return;
    const timer = window.setTimeout(() => {
      setResendSeconds((value) => Math.max(0, value - 1));
    }, 1000);
    return () => window.clearTimeout(timer);
  }, [resendSeconds]);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    const value = email.trim();
    if (!value) {
      setError("请输入邮箱。");
      setNotice(null);
      return;
    }
    if (sentEmail) {
      await verifyCode();
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    setSentEmail(value);
    try {
      await sendEmailOtp(value);
      setResendSeconds(OTP_RESEND_COOLDOWN_SECONDS);
      setNotice("验证码已发送，请查看邮箱。");
    } catch (err) {
      if (isAuthRateLimitError(err)) setResendSeconds(OTP_RESEND_COOLDOWN_SECONDS);
      setError(getAuthErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function verifyCode() {
    const value = sentEmail || email.trim();
    const token = code.trim().replace(/\s+/g, "");
    if (!value) {
      setError("请输入邮箱。");
      setNotice(null);
      return;
    }
    if (!token) {
      setError("请输入邮箱验证码。");
      setNotice(null);
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await verifyEmailOtp(value, token);
      const nextUser = await getAuthUser();
      if (!nextUser) throw new Error("登录状态未建立，请重新获取验证码。");
      setUser(nextUser);
      setNotice("登录成功，正在跳转。");
      router.replace(nextPath);
    } catch (err) {
      setError(getAuthErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  async function resendCode() {
    const value = sentEmail || email.trim();
    if (!value) {
      setError("请输入邮箱。");
      setNotice(null);
      return;
    }
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await sendEmailOtp(value);
      setSentEmail(value);
      setCode("");
      setResendSeconds(OTP_RESEND_COOLDOWN_SECONDS);
      setNotice("新的验证码已发送，请查看邮箱。");
    } catch (err) {
      if (isAuthRateLimitError(err)) setResendSeconds(OTP_RESEND_COOLDOWN_SECONDS);
      setError(getAuthErrorMessage(err));
    } finally {
      setBusy(false);
    }
  }

  function changeEmail() {
    setSentEmail(null);
    setCode("");
    setResendSeconds(0);
    setNotice(null);
    setError(null);
  }

  function useExistingCode() {
    const value = email.trim();
    if (!value) {
      setError("请先输入邮箱。");
      setNotice(null);
      return;
    }
    setSentEmail(value);
    setNotice(null);
    setError(null);
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
      setError(getAuthErrorMessage(err));
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
        <div className="notice-warning">
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
              disabled={busy || Boolean(sentEmail)}
            />
          </div>
          {!sentEmail && (
            <button type="button" className="text-xs text-ink-400 underline-offset-4 hover:text-ink-100 hover:underline" onClick={useExistingCode} disabled={busy}>
              已有验证码？输入验证码
            </button>
          )}
          {sentEmail && (
            <div className="space-y-2">
              <div className="flex items-center justify-between gap-3">
                <label className="label mb-0" htmlFor="code">验证码</label>
                <button type="button" className="text-xs text-ink-400 underline-offset-4 hover:text-ink-100 hover:underline" onClick={changeEmail} disabled={busy}>
                  更换邮箱
                </button>
              </div>
              <input
                id="code"
                className="input font-mono tracking-widest"
                type="text"
                value={code}
                onChange={(e) => setCode(e.target.value)}
                placeholder="输入 6 位验证码"
                autoComplete="one-time-code"
                inputMode="numeric"
                disabled={busy}
              />
              <button type="button" className="text-xs text-ink-400 underline-offset-4 hover:text-ink-100 hover:underline disabled:cursor-not-allowed disabled:opacity-60" onClick={resendCode} disabled={busy || resendSeconds > 0}>
                {resendSeconds > 0 ? `重新发送 ${resendSeconds}s` : "重新发送验证码"}
              </button>
            </div>
          )}
          <button type="submit" className="btn-primary w-full" disabled={busy || (!sentEmail && resendSeconds > 0)}>
            {busy ? "处理中..." : sentEmail ? "登录" : resendSeconds > 0 ? `稍后再试 ${resendSeconds}s` : "发送验证码"}
          </button>
        </form>
      )}

      {notice && (
        <div className="notice-success">
          {notice}
        </div>
      )}
      {error && (
        <div className="notice-danger">
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
