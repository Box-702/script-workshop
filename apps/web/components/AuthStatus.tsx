"use client";

import { useEffect, useState } from "react";
import { getAuthUser, isSupabaseConfigured, onAuthStateChanged, signOut, type AuthUser } from "@/lib/auth";

export function AuthStatus() {
  const [user, setUser] = useState<AuthUser | null>(null);
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

  if (!configured) {
    return <span className="hidden text-xs text-ink-500 md:inline">本地模式</span>;
  }

  if (!user) {
    return (
      <a className="text-xs text-accent-400 hover:text-accent-500" href="/settings">
        登录
      </a>
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
