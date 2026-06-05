"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { AUTH_REQUIRED_MESSAGE } from "@/lib/api";

export function isAuthRequiredMessage(message: string | null | undefined) {
  return message === AUTH_REQUIRED_MESSAGE;
}

export function AuthRequiredMessage() {
  const pathname = usePathname();
  const href = `/login?next=${encodeURIComponent(pathname || "/dashboard")}`;

  return (
    <div className="card flex flex-col gap-3 border-amber-500/40 bg-amber-500/10 text-amber-100 sm:flex-row sm:items-center sm:justify-between">
      <div>
        <div className="font-medium">需要登录</div>
        <p className="mt-1 text-sm text-amber-100/80">
          当前环境启用了 Supabase Auth，请先登录后继续使用云端项目和模型 key。
        </p>
      </div>
      <Link href={href} className="btn-primary whitespace-nowrap">
        去登录
      </Link>
    </div>
  );
}
