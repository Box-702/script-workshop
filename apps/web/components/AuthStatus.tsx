"use client";

import { useEffect, useState } from "react";
import { getAuthUser, isSupabaseConfigured, onAuthStateChanged, signOut, type AuthUser } from "@/lib/auth";

export function AuthStatus() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);
  const configured = isSupabaseConfigured();

  useEffect(() => {
    if (!configured) {
      setReady(true);
      return;
    }
    let unsubscribe = () => {};
    void getAuthUser()
      .then(setUser)
      .catch(() => setUser(null))
      .finally(() => setReady(true));
    void onAuthStateChanged(setUser).then((next) => {
      unsubscribe = next;
    });
    return () => unsubscribe();
  }, [configured]);

  if (!configured) {
    return <span className="hidden text-xs text-ink-500 md:inline">本地模式</span>;
  }

  if (!ready) {
    return <span className="hidden text-xs text-ink-500 md:inline">...</span>;
  }

  if (!user) {
    return (
      <span className="flex items-center gap-2 text-xs">
        <span className="hidden text-ink-500 md:inline">本地模式</span>
        <a className="text-accent-400 hover:text-accent-500" href="/login">
          登录同步
        </a>
      </span>
    );
  }

  return (
    <button
      type="button"
      className="max-w-40 truncate text-xs text-ink-400 hover:text-ink-100"
      onClick={() => void signOut()}
      title="退出登录"
    >
      {user.email || user.id}
    </button>
  );
}
