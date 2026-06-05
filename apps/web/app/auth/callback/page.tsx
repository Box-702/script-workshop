"use client";

import { useRouter, useSearchParams } from "next/navigation";
import { Suspense, useEffect, useState } from "react";
import { exchangeAuthCode, getAuthUser, isSupabaseConfigured } from "@/lib/auth";

export default function AuthCallbackPage() {
  return (
    <Suspense fallback={<div className="card mx-auto max-w-xl text-sm text-ink-400">正在完成登录...</div>}>
      <AuthCallbackContent />
    </Suspense>
  );
}

function AuthCallbackContent() {
  const router = useRouter();
  const params = useSearchParams();
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    let alive = true;
    async function finishLogin() {
      if (!isSupabaseConfigured()) {
        router.replace("/dashboard");
        return;
      }
      const nextPath = safeNextPath(params.get("next"));
      const code = params.get("code");
      try {
        if (code) await exchangeAuthCode(code);
        const user = await getAuthUser();
        if (!user) throw new Error("登录状态未建立，请重新发送登录链接。");
        router.replace(nextPath);
      } catch (err) {
        if (alive) setError((err as Error).message);
      }
    }
    void finishLogin();
    return () => {
      alive = false;
    };
  }, [params, router]);

  if (error) {
    return (
      <div className="card mx-auto max-w-xl border-red-500/40 text-red-200">
        登录失败：{error}
      </div>
    );
  }

  return <div className="card mx-auto max-w-xl text-sm text-ink-400">正在完成登录...</div>;
}

function safeNextPath(value: string | null) {
  if (!value || !value.startsWith("/") || value.startsWith("//")) return "/dashboard";
  return value;
}
