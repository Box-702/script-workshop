import { rmSync } from "node:fs";
import { dirname, resolve } from "node:path";
import { fileURLToPath } from "node:url";

const root = resolve(dirname(fileURLToPath(import.meta.url)), "..");
const targets = [
  ".ruff_cache",
  ".pytest_cache",
  "apps/api/.pytest_cache",
  "apps/api/.ruff_cache",
  "apps/api/script_workshop_api.egg-info",
  "apps/api/app/__pycache__",
  "apps/api/app/providers/__pycache__",
  "apps/api/app/routers/__pycache__",
  "apps/api/app/services/__pycache__",
  "apps/api/alembic/__pycache__",
  "apps/api/alembic/versions/__pycache__",
  "apps/api/tests/__pycache__",
  "apps/web/.next",
  "apps/web/.next-dev",
  "apps/web/.next-dev.log",
  "apps/web/.next-dev.err.log",
  "apps/web/tsconfig.tsbuildinfo",
];

for (const target of targets) {
  rmSync(resolve(root, target), { recursive: true, force: true });
}
