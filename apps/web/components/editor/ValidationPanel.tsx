import type { ValidationError } from "@/lib/types";

export function ValidationPanel({ busy, errors }: { busy: boolean; errors: ValidationError[] }) {
  return (
    <div className="card">
      <div className="label">校验</div>
      {busy ? (
        <div className="text-sm text-ink-400">校验中...</div>
      ) : errors.length === 0 ? (
        <div className="text-sm text-emerald-400">通过</div>
      ) : (
        <ul className="space-y-1 text-xs">
          {errors.map((e, i) => (
            <li key={i} className="font-mono text-red-300">
              <span className="text-ink-400">结构字段</span> - {e.message}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

