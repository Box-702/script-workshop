"use client";

import { useEffect, useRef, useState } from "react";
import { downloadBlob } from "@/lib/api";

const EXPORT_FORMATS = [
  { path: "script.md", title: "文稿", format: "Markdown", extension: "md" },
  { path: "script.yaml", title: "源码", format: "YAML", extension: "yaml" },
  { path: "script.json", title: "数据", format: "JSON", extension: "json" },
] as const;

export function ExportMenu({
  projectId,
  compact = false,
}: {
  projectId: string;
  compact?: boolean;
}) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);
  const [downloadingFormat, setDownloadingFormat] = useState<string | null>(null);
  const encodedProjectId = encodeURIComponent(projectId);
  const buttonClassName = compact
    ? "btn-ghost cursor-pointer select-none gap-1.5 px-3 py-1.5 text-xs"
    : "btn-ghost cursor-pointer select-none gap-1.5";

  async function downloadExport(format: (typeof EXPORT_FORMATS)[number]) {
    const url = `/api/projects/${encodedProjectId}/${format.path}`;
    setDownloadingFormat(format.format);
    setOpen(false);
    try {
      const blob = await downloadBlob(url);
      const objectUrl = URL.createObjectURL(blob);
      const anchor = document.createElement("a");
      anchor.href = objectUrl;
      anchor.download = `script-${projectId}.${format.extension}`;
      document.body.append(anchor);
      anchor.click();
      anchor.remove();
      URL.revokeObjectURL(objectUrl);
    } catch (error) {
      const message = error instanceof Error ? error.message : "导出失败，请稍后重试。";
      window.alert(message);
    } finally {
      setDownloadingFormat(null);
    }
  }

  useEffect(() => {
    if (!open) return;

    function closeIfOutside(event: PointerEvent) {
      const details = detailsRef.current;
      if (!details || details.contains(event.target as Node)) return;
      setOpen(false);
    }

    function closeOnEscape(event: KeyboardEvent) {
      if (event.key === "Escape") setOpen(false);
    }

    document.addEventListener("pointerdown", closeIfOutside);
    document.addEventListener("keydown", closeOnEscape);
    return () => {
      document.removeEventListener("pointerdown", closeIfOutside);
      document.removeEventListener("keydown", closeOnEscape);
    };
  }, [open]);

  return (
    <details
      ref={detailsRef}
      className="export-menu relative inline-block"
      open={open}
      onToggle={(event) => setOpen(event.currentTarget.open)}
    >
      <summary className={buttonClassName} aria-haspopup="menu" aria-label="选择导出格式">
        <span>导出</span>
        <span aria-hidden="true" className="text-[10px] text-ink-400">
          ▾
        </span>
      </summary>
      <div className="absolute right-0 z-30 mt-2 w-44 overflow-hidden rounded-md border border-ink-600/40 bg-ink-900 shadow-xl">
        {EXPORT_FORMATS.map((format) => (
          <ExportButton
            key={format.path}
            title={format.title}
            format={format.format}
            disabled={downloadingFormat === format.format}
            onClick={() => void downloadExport(format)}
          />
        ))}
      </div>
    </details>
  );
}

function ExportButton({
  title,
  format,
  disabled,
  onClick,
}: {
  title: string;
  format: string;
  disabled: boolean;
  onClick: () => void;
}) {
  return (
    <button
      className="flex w-full items-center justify-between gap-3 px-3 py-2 text-left text-sm text-ink-100 hover:bg-ink-800 hover:text-ink-50 focus:bg-ink-800 focus:text-ink-50 focus:outline-none disabled:cursor-wait disabled:text-ink-500"
      type="button"
      disabled={disabled}
      onClick={onClick}
    >
      <span>{title}</span>
      <span className="text-xs text-ink-500">{format}</span>
    </button>
  );
}
