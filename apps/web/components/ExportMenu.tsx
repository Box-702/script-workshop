"use client";

import { useEffect, useRef, useState } from "react";

export function ExportMenu({
  projectId,
  compact = false,
}: {
  projectId: string;
  compact?: boolean;
}) {
  const detailsRef = useRef<HTMLDetailsElement>(null);
  const [open, setOpen] = useState(false);
  const encodedProjectId = encodeURIComponent(projectId);
  const buttonClassName = compact
    ? "btn-ghost cursor-pointer select-none gap-1.5 px-3 py-1.5 text-xs"
    : "btn-ghost cursor-pointer select-none gap-1.5";

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
        <ExportLink
          href={`/api/projects/${encodedProjectId}/script.md`}
          title="文稿"
          format="Markdown"
          onClick={() => setOpen(false)}
        />
        <ExportLink
          href={`/api/projects/${encodedProjectId}/script.yaml`}
          title="源码"
          format="YAML"
          onClick={() => setOpen(false)}
        />
        <ExportLink
          href={`/api/projects/${encodedProjectId}/script.json`}
          title="数据"
          format="JSON"
          onClick={() => setOpen(false)}
        />
      </div>
    </details>
  );
}

function ExportLink({
  href,
  title,
  format,
  onClick,
}: {
  href: string;
  title: string;
  format: string;
  onClick: () => void;
}) {
  return (
    <a
      className="flex items-center justify-between gap-3 px-3 py-2 text-sm text-ink-100 hover:bg-ink-800 hover:text-ink-50 focus:bg-ink-800 focus:text-ink-50 focus:outline-none"
      href={href}
      download
      onClick={onClick}
    >
      <span>{title}</span>
      <span className="text-xs text-ink-500">{format}</span>
    </a>
  );
}
