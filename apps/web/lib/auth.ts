import type { SupabaseClient, User } from "@supabase/supabase-js";

const supabaseUrl = process.env.NEXT_PUBLIC_SUPABASE_URL || "";
const supabaseAnonKey = process.env.NEXT_PUBLIC_SUPABASE_ANON_KEY || "";

let supabase: SupabaseClient | null | undefined;
let supabaseInit: Promise<SupabaseClient | null> | null = null;

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

export async function getAuthUser(): Promise<AuthUser | null> {
  const client = await getSupabaseClient();
  if (!client) return null;
  const { data } = await client.auth.getUser();
  return normalizeUser(data.user);
}

export async function signInWithEmail(email: string) {
  const client = await getSupabaseClient();
  if (!client) throw new Error("Supabase Auth 尚未配置。");
  const { error } = await client.auth.signInWithOtp({
    email,
    options: {
      emailRedirectTo: `${window.location.origin}/settings`,
    },
  });
  if (error) throw error;
}

export async function signOut() {
  const client = await getSupabaseClient();
  if (!client) return;
  const { error } = await client.auth.signOut();
  if (error) throw error;
}

export async function onAuthStateChanged(callback: (user: AuthUser | null) => void) {
  const client = await getSupabaseClient();
  if (!client) return () => {};
  const { data } = client.auth.onAuthStateChange((_event, session) => {
    callback(normalizeUser(session?.user ?? null));
  });
  return () => data.subscription.unsubscribe();
}

function normalizeUser(user: User | null): AuthUser | null {
  if (!user) return null;
  return {
    id: user.id,
    email: user.email ?? undefined,
  };
}
