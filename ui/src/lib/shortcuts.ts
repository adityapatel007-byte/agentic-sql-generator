import { useEffect } from "react";

type Handler = (e: KeyboardEvent) => void;

// Global keyboard shortcuts. Skips events targeted at editable elements so /
// and ? don't fight the user while they're typing.
export function useShortcut(keys: string | string[], handler: Handler) {
  useEffect(() => {
    const list = Array.isArray(keys) ? keys : [keys];
    const onKey = (e: KeyboardEvent) => {
      const t = e.target as HTMLElement | null;
      const editable =
        t &&
        (t.tagName === "INPUT" ||
          t.tagName === "TEXTAREA" ||
          t.isContentEditable);
      if (editable && !list.includes("Escape")) return;
      if (list.includes(e.key)) handler(e);
    };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [keys, handler]);
}
