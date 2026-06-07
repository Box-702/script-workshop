import type { SupabaseClient, User } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

let supabase: SupabaseClient | null | undefined;
let supabaseInit: Promise<SupabaseClient | null> | null = null;

export const OTP_RESEND_COOLDOWN_SECONDS = 60;

export interface AuthUser {
  id: string;
  email?: string;
}

export function isSupabaseConfigured() {
  return Boolean(supabaseUrl && supabaseAnonKey);
}

export async function getSupabaseClient() {
  if (typeof window === "undefined" || !isSupabaseConfigured()) return null;
  if (typeof supabase !== "undefined") return supabase;
  if (!supabaseInit) {
    supabaseInit = import("@supabase/supabase-js").then(({ createClient }) => {
      supabase = createClient(supabaseUrl, supabaseAnonKey);
      return supabase;
    });
  }
  return supabaseInit;
}

export async function getAccessToken() {
  const client = await getSupabaseClient();
  if (!client) return "";
  const { data } = await client.auth.getSession();
  return data.session?.access_token ?? "";
}

export async function getSessionUser(): Promise<AuthUser | null> {
  const client = await getSupabaseClient();
  if (!client) return null;
  const { data } = await client.auth.getSession();
  return normalizeUser(data.session?.user ?? null);
}

export async function getAuthUser(): Promise<AuthUser | null> {
  const client = await getSupabaseClient();
  if (!client) return null;
  const { data } = await client.auth.getUser();
  return normalizeUser(data.user);
}

export async function sendEmailOtp(email: string) {
  const client = await getSupabaseClient();
  if (!client) throw new Error("Supabase Auth 尚未配置。");
  const { error } = await client.auth.signInWithOtp({
    email,
  });
  if (error) throw error;
}

export async function verifyEmailOtp(email: string, token: string) {
  const client = await getSupabaseClient();
  if (!client) throw new Error("Supabase Auth 尚未配置。");
  const { error } = await client.auth.verifyOtp({
    email,
    token,
    type: "email",
  });
  if (error) throw error;
}

export async function exchangeAuthCode(code: string) {
  const client = await getSupabaseClient();
  if (!client) throw new Error("Supabase Auth 尚未配置。");
  const { error } = await client.auth.exchangeCodeForSession(code);
  if (error) throw error;
}

export async function signOut() {
  const client = await getSupabaseClient();
  if (!client) return;
  const { error } = await client.auth.signOut();
  if (error) throw error;
}

export async function onAuthStateChanged(callback: (user: AuthUser | null, event: string) => void) {
  const client = await getSupabaseClient();
  if (!client) return () => {};
  const { data } = client.auth.onAuthStateChange((event, session) => {
    callback(normalizeUser(session?.user ?? null), event);
  });
  return () => data.subscription.unsubscribe();
}

export function getAuthErrorMessage(error: unknown) {
  const message = getErrorText(error);
  const normalized = message.toLowerCase();
  if (isAuthRateLimitMessage(normalized)) {
    return "验证码邮件发送过于频繁，请稍后再试。";
  }
  if (normalized.includes("token has expired") || normalized.includes("otp_expired")) {
    return "验证码已过期，请重新获取。";
  }
  if (normalized.includes("invalid") && normalized.includes("otp")) {
    return "验证码不正确，请检查后重试。";
  }
  return message || "认证失败，请稍后重试。";
}

export function isAuthRateLimitError(error: unknown) {
  return isAuthRateLimitMessage(getErrorText(error).toLowerCase());
}

function normalizeUser(user: User | null): AuthUser | null {
  if (!user) return null;
  return {
    id: user.id,
    email: user.email ?? undefined,
  };
}

function getErrorText(error: unknown) {
  if (error instanceof Error) return error.message;
  if (typeof error === "string") return error;
  if (error && typeof error === "object") {
    const value = error as { code?: unknown; message?: unknown; error_description?: unknown };
    return [value.code, value.message, value.error_description].filter(Boolean).join(" ");
  }
  return "";
}

function isAuthRateLimitMessage(message: string) {
  return message.includes("rate limit") || message.includes("over_email_send_rate_limit");
}
