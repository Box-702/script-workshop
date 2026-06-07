import fs from "node:fs";
import path from "node:path";

const args = new Set(process.argv.slice(2));
const dryRun = args.has("--dry-run");
const env = loadDotEnv(path.resolve(".env"));

const accessToken =
  process.env.SUPABASE_ACCESS_TOKEN ||
  process.env.SUPABASE_MANAGEMENT_ACCESS_TOKEN ||
  env.SUPABASE_ACCESS_TOKEN ||
  env.SUPABASE_MANAGEMENT_ACCESS_TOKEN ||
  "";
const projectRef =
  process.env.SUPABASE_PROJECT_REF ||
  env.SUPABASE_PROJECT_REF ||
  projectRefFromUrl(process.env.SUPABASE_URL || env.SUPABASE_URL || process.env.NEXT_PUBLIC_SUPABASE_URL || env.NEXT_PUBLIC_SUPABASE_URL || "");

if (!projectRef) {
  fail("Missing SUPABASE_PROJECT_REF, and no Supabase project ref could be inferred from SUPABASE_URL.");
}

const content = [
  "<h2>剧本工坊登录验证码</h2>",
  "<p>请输入下面的验证码完成登录：</p>",
  '<p style="font-size:32px;font-weight:700;letter-spacing:8px;line-height:1.2;margin:24px 0;">{{ .Token }}</p>',
  "<p>验证码会很快过期。如果不是你发起的请求，可以忽略这封邮件。</p>",
].join("");

const payload = {
  mailer_subjects_magic_link: "{{ .Token }} 是你的剧本工坊登录验证码",
  mailer_templates_magic_link_content: content,
  mailer_subjects_confirmation: "{{ .Token }} 是你的剧本工坊登录验证码",
  mailer_templates_confirmation_content: content,
};

if (dryRun) {
  console.log(JSON.stringify({ projectRef, payload }, null, 2));
  process.exit(0);
}

if (!accessToken) {
  fail(
    "Missing SUPABASE_ACCESS_TOKEN. Create a Supabase Management API personal access token, then run: $env:SUPABASE_ACCESS_TOKEN='...'; pnpm supabase:otp-template",
  );
}

const response = await fetch(`https://api.supabase.com/v1/projects/${projectRef}/config/auth`, {
  method: "PATCH",
  headers: {
    Authorization: `Bearer ${accessToken}`,
    "Content-Type": "application/json",
  },
  body: JSON.stringify(payload),
});

if (!response.ok) {
  const text = await response.text();
  fail(`Supabase auth template update failed: HTTP ${response.status}\n${text}`);
}

console.log(`Updated Supabase OTP email templates for project ${projectRef}.`);

function loadDotEnv(filePath) {
  if (!fs.existsSync(filePath)) return {};
  const data = {};
  const text = fs.readFileSync(filePath, "utf8");
  for (const rawLine of text.split(/\r?\n/)) {
    const line = rawLine.trim();
    if (!line || line.startsWith("#")) continue;
    const index = line.indexOf("=");
    if (index < 1) continue;
    const key = line.slice(0, index).trim();
    let value = line.slice(index + 1).trim();
    if (
      (value.startsWith('"') && value.endsWith('"')) ||
      (value.startsWith("'") && value.endsWith("'"))
    ) {
      value = value.slice(1, -1);
    }
    data[key] = value;
  }
  return data;
}

function projectRefFromUrl(value) {
  try {
    const host = new URL(value).hostname;
    const [ref, domain] = host.split(".");
    return domain === "supabase" && ref ? ref : "";
  } catch {
    return "";
  }
}

function fail(message) {
  console.error(message);
  process.exit(1);
}
