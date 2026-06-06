"use client";

import { useEffect, useState } from "react";

type UiStyle = "studio" | "paper";

const STORAGE_KEY = "script-workshop-ui-style";

function readInitialStyle(): UiStyle {
  // The layout's <head> script has already applied the saved theme to
  // <html data-ui-style="..."> before React mounts. Read it back so
  // the active button matches the live theme on first render.
  if (typeof document !== "undefined") {
    const fromDom = document.documentElement.dataset.uiStyle;
    if (fromDom === "paper" || fromDom === "studio") return fromDom;
  }
  return "studio";
}

export function StyleSwitcher() {
  const [style, setStyle] = useState<UiStyle>(readInitialStyle);

  // Keep the dataset in sync if anything else (e.g. another tab) changes
  // the stored preference. The user-triggered `choose` path below already
  // updates both state and dataset synchronously.
  useEffect(() => {
    const onStorage = (e: StorageEvent) => {
      if (e.key !== STORAGE_KEY) return;
      const next = e.newValue === "paper" ? "paper" : "studio";
      setStyle(next);
      document.documentElement.dataset.uiStyle = next;
    };
    window.addEventListener("storage", onStorage);
    return () => window.removeEventListener("storage", onStorage);
  }, []);

  function choose(next: UiStyle) {
    setStyle(next);
    window.localStorage.setItem(STORAGE_KEY, next);
    document.documentElement.dataset.uiStyle = next;
  }

  return (
    <div className="style-switcher" aria-label="界面风格">
      <button
        type="button"
        className={style === "studio" ? "is-active" : ""}
        onClick={() => choose("studio")}
        aria-pressed={style === "studio"}
      >
        Studio
      </button>
      <button
        type="button"
        className={style === "paper" ? "is-active" : ""}
        onClick={() => choose("paper")}
        aria-pressed={style === "paper"}
      >
        Paper
      </button>
    </div>
  );
}
