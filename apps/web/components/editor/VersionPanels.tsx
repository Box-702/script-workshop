import type { ScriptVersionSummary, VersionDiffSummary } from "@/lib/types";
import { PatchValue } from "./PatchValue";

export function VersionPanel({
  versions,
  saving,
  diffBusy,
  snapshotName,
  setSnapshotName,
  canSaveSnapshot,
  saveSnapshot,
  restoreVersion,
  compareVersion,
}: {
  versions: ScriptVersionSummary[];
  saving: boolean;
  diffBusy: boolean;
  snapshotName: string;
  setSnapshotName: (value: string) => void;
  canSaveSnapshot: boolean;
  saveSnapshot: () => void;
  restoreVersion: (versionId: string) => void;
  compareVersion: (versionId: string) => void;
}) {
  const currentVersionId = versions[0]?.id;

  return (
    <div className="card space-y-3">
      <div className="label">快照历史</div>
      <div className="space-y-2 rounded-md border border-ink-600/40 bg-ink-900 p-2">
        <div className="text-xs text-ink-500">快照名</div>
        <input
          className="input h-9 text-sm"
          value={snapshotName}
          onChange={(e) => setSnapshotName(e.target.value)}
          placeholder="例如：第一版钩子调整"
          maxLength={80}
        />
        <button
          type="button"
          className="btn-primary w-full px-2 py-1.5 text-xs"
          onClick={saveSnapshot}
          disabled={saving || !canSaveSnapshot}
        >
          {saving ? "保存中..." : "保存当前快照"}
        </button>
      </div>
      {versions.length === 0 ? (
        <div className="text-sm text-ink-400">暂无快照。</div>
      ) : (
        <ul className="space-y-2 text-sm">
          {versions.map((version, index) => (
            <li key={version.id} className="rounded-md border surface-line surface-soft p-2.5">
              <div className="flex items-center justify-between gap-2">
                <span className="min-w-0 truncate font-medium text-ink-100">
                  {formatVersionLabel(version.label, index)}
                </span>
                <span className={version.validation_status === "valid" ? "shrink-0 text-xs state-success-text" : "shrink-0 text-xs state-warning-text"}>
                  {formatValidation(version.validation_status)}
                </span>
              </div>
              <div className="mt-2 space-y-1 text-xs text-ink-400">
                {formatVersionNote(version.notes) && <div>备注：{formatVersionNote(version.notes)}</div>}
                <div className="font-mono">{new Date(version.created_at).toLocaleString()}</div>
              </div>
              {index > 0 && (
                <div className="mt-2 grid grid-cols-2 gap-2">
                  <button
                    className="btn-ghost px-2 py-1 text-xs"
                    onClick={() => compareVersion(version.id)}
                    disabled={saving || diffBusy || !currentVersionId}
                  >
                    {diffBusy ? "对比中..." : "对比当前"}
                  </button>
                  <button
                    className="btn-ghost px-2 py-1 text-xs"
                    onClick={() => restoreVersion(version.id)}
                    disabled={saving}
                  >
                    回退
                  </button>
                </div>
              )}
              {index === 0 && <div className="mt-2 text-xs text-ink-500">当前使用中</div>}
            </li>
          ))}
        </ul>
      )}
    </div>
  );
}

export function DiffPanel({
  diff,
  busy,
  characterNames,
  onClose,
}: {
  diff: VersionDiffSummary | null;
  busy: boolean;
  characterNames: Record<string, string>;
  onClose: () => void;
}) {
  if (!diff && !busy) return null;
  const groups = groupDiffItems(diff?.items ?? []);

  return (
    <div className="card space-y-3">
      <div className="flex items-center justify-between gap-3">
        <div>
          <div className="label mb-0">版本差异</div>
          {diff && (
            <div className="mt-1 text-xs text-ink-500">
              {diff.items.length === 0 ? "两个快照内容一致" : `${diff.items.length} 处变化`}
            </div>
          )}
        </div>
        {diff && (
          <button type="button" className="text-xs text-ink-500 hover:text-ink-200" onClick={onClose}>
            关闭
          </button>
        )}
      </div>
      {busy && !diff ? (
        <div className="text-sm text-ink-400">正在对比快照...</div>
      ) : diff && diff.items.length === 0 ? (
        <div className="rounded-md border surface-line surface-soft p-3 text-sm text-ink-300">
          没有发现内容差异。
        </div>
      ) : (
        <div className="space-y-3">
          {groups.map(([section, items]) => (
            <section key={section} className="space-y-2">
              <div className="flex items-center justify-between text-xs">
                <span className="font-medium text-ink-200">{section}</span>
                <span className="text-ink-500">{items.length}</span>
              </div>
              <ul className="space-y-2">
                {items.map((item) => (
                  <li key={`${item.path}-${item.change_type}`} className="rounded-md border surface-line surface-soft p-2.5">
                    <div className="flex items-center justify-between gap-2">
                      <div className="min-w-0 truncate text-sm font-medium text-ink-100">{item.label}</div>
                      <span className={`shrink-0 rounded px-1.5 py-0.5 text-xs ${diffBadgeClass(item.change_type)}`}>
                        {formatDiffChangeType(item.change_type)}
                      </span>
                    </div>
                    <div className="mt-1 truncate font-mono text-[10px] text-ink-600">{item.path}</div>
                    {item.change_type !== "added" && (
                      <PatchValue label="修改前" value={item.before} characterNames={characterNames} />
                    )}
                    {item.change_type !== "removed" && (
                      <PatchValue label="修改后" value={item.after} characterNames={characterNames} />
                    )}
                  </li>
                ))}
              </ul>
            </section>
          ))}
        </div>
      )}
    </div>
  );
}

function formatVersionLabel(label: string | null, index: number) {
  if (label === "AI generated draft") return "AI 生成初稿";
  return label || (index === 0 ? "当前快照" : `未命名快照 ${index}`);
}

function formatVersionNote(note: string | null) {
  if (!note) return null;
  if (/^Generated by run\s+run_[\w-]+\.?$/i.test(note.trim())) return null;
  return note;
}

function formatValidation(value: string) {
  return (
    {
      valid: "通过",
      invalid: "待处理",
    }[value] ?? value
  );
}

function groupDiffItems(items: VersionDiffSummary["items"]) {
  const grouped = new Map<string, VersionDiffSummary["items"]>();
  for (const item of items) {
    const bucket = grouped.get(item.section) ?? [];
    bucket.push(item);
    grouped.set(item.section, bucket);
  }
  return Array.from(grouped.entries());
}

function formatDiffChangeType(value: string) {
  return (
    {
      added: "新增",
      removed: "删除",
      changed: "修改",
    }[value] ?? value
  );
}

function diffBadgeClass(value: string) {
  if (value === "added") return "state-success";
  if (value === "removed") return "state-danger";
  return "state-warning";
}
