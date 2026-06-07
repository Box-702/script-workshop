"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { getAuthUser, isSupabaseConfigured, onAuthStateChanged, type AuthUser } from "@/lib/auth";

export function LocalModeNotice() {
  const pathname = usePathname();
  const configured = isSupabaseConfigured();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [ready, setReady] = useState(false);

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

  if (!ready || !configured || user || pathname?.startsWith("/login")) return null;

  return (
    <div className="card mb-5 flex flex-col gap-3 border-amber-500/40 bg-amber-500/10 text-amber-100 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="font-medium">当前为本地模式</div>
        <p className="mt-1 text-sm text-amber-100/80">
          项目绑定此浏览器的本地身份，模型 key 可只保存到当前浏览器；登录后可使用云端账号隔离和跨设备同步。
        </p>
      </div>
      <Link href={`/login?next=${encodeURIComponent(pathname || "/dashboard")}`} className="btn-primary whitespace-nowrap">
        登录同步
      </Link>
    </div>
  );
}
