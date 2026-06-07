"use client";

import { useEffect, useState } from "react";
import { AuthRequiredMessage, isAuthRequiredMessage } from "@/components/AuthRequiredMessage";
import { api } from "@/lib/api";
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
import {
  clearLlmSettings,
  DEFAULT_LLM_SETTINGS,
  isPlausibleApiKey,
  loadLlmSettings,
  saveLlmSettings,
} from "@/lib/llm-settings";
import type { LlmSettings } from "@/lib/llm-settings";
import type { ModelKeySummary } from "@/lib/types";

export default function SettingsPage() {
  const [settings, setSettings] = useState<LlmSettings>(DEFAULT_LLM_SETTINGS);
  const [keys, setKeys] = useState<ModelKeySummary[]>([]);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setSettings(loadLlmSettings());
    void loadKeys();
  }, []);

  async function loadKeys() {
    try {
      const next = await api.listModelKeys();
      setKeys(next);
    } catch (e) {
      setError((e as Error).message);
    }
  }

  function update<K extends keyof LlmSettings>(key: K, value: LlmSettings[K]) {
    setNotice(null);
    setError(null);
    setSettings((prev) => ({ ...prev, [key]: value }));
  }

  async function saveCloudKey() {
    if (!isPlausibleApiKey(settings.apiKey)) {
      setError("请粘贴完整 API key，不要填写 ****1234 这类遮罩值、端口号或空值。");
      setNotice(null);
      return;
    }
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const saved = await api.saveModelKey({
        provider: "openai",
        api_key: settings.apiKey,
        base_url: settings.baseUrl,
        model: settings.model,
      });
      saveLlmSettings({ ...settings, apiKey: "" });
      setSettings((prev) => ({ ...prev, apiKey: "" }));
      await loadKeys();
      setNotice(`已保存云端模型 key，尾号 ${saved.key_last4}。`);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function saveLocalOnly() {
    if (!isPlausibleApiKey(settings.apiKey)) {
      setError("请粘贴完整 API key，不要填写 ****1234 这类遮罩值、端口号或空值。");
      setNotice(null);
      return;
    }
    saveLlmSettings(settings);
    setNotice("已保存到当前浏览器。");
    setError(null);
  }

  async function revoke(keyId: string) {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      await api.revokeModelKey(keyId);
      await loadKeys();
      setNotice("已撤销模型 key。");
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  async function testKey(keyId: string) {
    setBusy(true);
    setNotice(null);
    setError(null);
    try {
      const result = await api.testModelKey(keyId);
      if (result.ok) setNotice(result.message);
      else setError(result.message);
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  function resetLocal() {
    clearLlmSettings();
    setSettings(DEFAULT_LLM_SETTINGS);
    setNotice("已清空浏览器本地设置。");
    setError(null);
  }

  const activeKey = keys.find((key) => key.status === "active");

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-semibold tracking-tight">模型设置</h1>
        <p className="mt-1 text-sm text-ink-400">
          推荐保存到后端加密存储；也可以只保存到当前浏览器。
        </p>
      </div>

      {notice && (
        <div className="rounded border border-emerald-500/40 bg-emerald-500/10 p-3 text-sm text-emerald-200">
          {notice}
        </div>
      )}
      {isAuthRequiredMessage(error) ? (
        <AuthRequiredMessage />
      ) : error ? (
        <div className="rounded border border-red-500/40 bg-red-500/10 p-3 text-sm text-red-200">
          {error}
        </div>
      ) : null}

      <AuthPanel />

      <div className="grid gap-4 lg:grid-cols-[1fr_360px]">
        <section className="card space-y-4">
          <div>
            <label className="label" htmlFor="apiKey">API key</label>
            <input
              id="apiKey"
              className="input font-mono"
              type="password"
              value={settings.apiKey}
              onChange={(e) => update("apiKey", e.target.value)}
              placeholder={activeKey ? `已保存云端 key，尾号 ${activeKey.key_last4}` : "sk-..."}
              autoComplete="off"
            />
          </div>

          <div className="grid gap-4 md:grid-cols-2">
            <div>
              <label className="label" htmlFor="baseUrl">接口地址</label>
              <input
                id="baseUrl"
                className="input font-mono"
                value={settings.baseUrl}
                onChange={(e) => update("baseUrl", e.target.value)}
              />
            </div>
            <div>
              <label className="label" htmlFor="model">模型名称</label>
              <input
                id="model"
                className="input font-mono"
                value={settings.model}
                onChange={(e) => update("model", e.target.value)}
              />
            </div>
          </div>

          <div className="flex flex-wrap justify-end gap-2">
            <button type="button" className="btn-ghost" onClick={resetLocal} disabled={busy}>
              清空本地
            </button>
            <button type="button" className="btn-ghost" onClick={saveLocalOnly} disabled={busy}>
              仅保存本地
            </button>
            <button
              type="button"
              className="btn-primary"
              onClick={saveCloudKey}
              disabled={busy || !isPlausibleApiKey(settings.apiKey)}
            >
              {busy ? "保存中..." : "保存到云端"}
            </button>
          </div>
        </section>

        <aside className="card">
          <div className="label">已保存 key</div>
          {keys.length === 0 ? (
            <p className="text-sm text-ink-400">暂无云端 key。</p>
          ) : (
            <ul className="space-y-2 text-sm">
              {keys.map((key) => (
                <li key={key.id} className="rounded border surface-line surface-soft p-3">
                  <div className="flex items-center justify-between gap-3">
                    <div>
                      <div className="font-medium">{key.provider}</div>
                      <div className="mt-1 font-mono text-xs text-ink-500">
                        {key.default_model || "未设置模型"} · ****{key.key_last4}
                      </div>
                    </div>
                    <span className={key.status === "active" ? "text-emerald-300" : "text-ink-500"}>
                      {key.status}
                    </span>
                  </div>
                  <div className="mt-3 flex gap-2">
                    {key.status === "active" && (
                      <>
                        <button
                          type="button"
                          className="btn-ghost px-3 py-1.5 text-xs"
                          onClick={() => testKey(key.id)}
                          disabled={busy}
                        >
                          测试
                        </button>
                        <button
                          type="button"
                          className="btn-ghost px-3 py-1.5 text-xs"
                          onClick={() => revoke(key.id)}
                          disabled={busy}
                        >
                          撤销
                        </button>
                      </>
                    )}
                  </div>
                </li>
              ))}
            </ul>
          )}
        </aside>
      </div>
    </div>
  );
}

function AuthPanel() {
  const [email, setEmail] = useState("");
  const [code, setCode] = useState("");
  const [sentEmail, setSentEmail] = useState<string | null>(null);
  const [user, setUser] = useState<AuthUser | null>(null);
  const [busy, setBusy] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [resendSeconds, setResendSeconds] = useState(0);
  const configured = isSupabaseConfigured();

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

  async function sendCode() {
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
      await sendEmailOtp(value);
      setSentEmail(value);
      setResendSeconds(OTP_RESEND_COOLDOWN_SECONDS);
      setNotice("验证码已发送，请查看邮箱。");
    } catch (e) {
      if (isAuthRateLimitError(e)) setResendSeconds(OTP_RESEND_COOLDOWN_SECONDS);
      setError(getAuthErrorMessage(e));
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
      setNotice("登录成功。");
      setCode("");
      setSentEmail(null);
      setResendSeconds(0);
    } catch (e) {
      setError(getAuthErrorMessage(e));
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
    } catch (e) {
      if (isAuthRateLimitError(e)) setResendSeconds(OTP_RESEND_COOLDOWN_SECONDS);
      setError(getAuthErrorMessage(e));
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

  async function logout() {
    setBusy(true);
    setError(null);
    setNotice(null);
    try {
      await signOut();
      setUser(null);
      setNotice("已退出登录。");
    } catch (e) {
      setError(getAuthErrorMessage(e));
    } finally {
      setBusy(false);
    }
  }

  return (
    <section className="card space-y-3">
      <div className="flex flex-col gap-2 sm:flex-row sm:items-center sm:justify-between">
        <div>
          <div className="label mb-0">账号</div>
          <div className="text-sm text-ink-300">
            {configured
              ? user
                ? user.email || user.id
                : "使用 Supabase Auth 登录后启用云端用户隔离。"
              : "当前未配置 Supabase，使用本地单用户模式。"}
          </div>
        </div>
        {user && (
          <button type="button" className="btn-ghost px-3 py-1.5 text-xs" onClick={logout} disabled={busy}>
            退出登录
          </button>
        )}
      </div>

      {configured && !user && (
        <div className="flex flex-col gap-2">
          <input
            className="input"
            type="email"
            value={email}
            onChange={(e) => setEmail(e.target.value)}
            placeholder="you@example.com"
            autoComplete="email"
            disabled={busy || Boolean(sentEmail)}
          />
          {sentEmail && (
            <input
              className="input font-mono tracking-widest"
              type="text"
              value={code}
              onChange={(e) => setCode(e.target.value)}
              placeholder="输入 6 位验证码"
              autoComplete="one-time-code"
              inputMode="numeric"
              disabled={busy}
            />
          )}
          <div className="flex flex-wrap gap-2">
            <button type="button" className="btn-primary whitespace-nowrap" onClick={sentEmail ? verifyCode : sendCode} disabled={busy || (!sentEmail && resendSeconds > 0)}>
              {busy ? "处理中..." : sentEmail ? "登录" : resendSeconds > 0 ? `稍后再试 ${resendSeconds}s` : "发送验证码"}
            </button>
            {sentEmail && (
              <>
                <button type="button" className="btn-ghost whitespace-nowrap" onClick={resendCode} disabled={busy || resendSeconds > 0}>
                  {resendSeconds > 0 ? `重新发送 ${resendSeconds}s` : "重新发送"}
                </button>
                <button type="button" className="btn-ghost whitespace-nowrap" onClick={changeEmail} disabled={busy}>
                  更换邮箱
                </button>
              </>
            )}
          </div>
        </div>
      )}

      {notice && <div className="text-sm text-emerald-300">{notice}</div>}
      {error && <div className="text-sm text-red-300">{error}</div>}
    </section>
  );
}
