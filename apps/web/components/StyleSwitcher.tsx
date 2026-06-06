"use client";

import { useEffect, useState } from "react";

type UiStyle = "studio" | "paper";

const STORAGE_KEY = "script-workshop-ui-style";

export function StyleSwitcher() {
  const [style, setStyle] = useState<UiStyle>("studio");

  useEffect(() => {
    const saved = window.localStorage.getItem(STORAGE_KEY);
    const next = saved === "paper" ? "paper" : "studio";
    setStyle(next);
    document.documentElement.dataset.uiStyle = next;
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
