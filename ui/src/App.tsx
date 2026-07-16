import { useEffect, useState } from "react";

import { AskScreen } from "@/components/AskScreen";
import { ConnectionsScreen } from "@/components/ConnectionsScreen";
import { StatusBar } from "@/components/StatusBar";
import { Toaster } from "@/components/ui/sonner";
import { API_BASE } from "@/lib/config";
import type { ConnectionInfo } from "@/lib/api";

function useSystemDarkMode() {
  useEffect(() => {
    const media = window.matchMedia("(prefers-color-scheme: dark)");
    const apply = () =>
      document.documentElement.classList.toggle("dark", media.matches);
    apply();
    media.addEventListener("change", apply);
    return () => media.removeEventListener("change", apply);
  }, []);
}

export default function App() {
  useSystemDarkMode();
  const [selected, setSelected] = useState<ConnectionInfo | null>(null);
  const [backendHost] = useState(() => {
    try {
      return new URL(API_BASE).host;
    } catch {
      return API_BASE;
    }
  });

  return (
    <div className="flex min-h-screen flex-col bg-[color:var(--bg)] text-[color:var(--ink)]">
      <TopBar backendHost={backendHost} />
      <main className="flex-1">
        {selected ? (
          <AskScreen
            connection={selected}
            onBack={() => setSelected(null)}
          />
        ) : (
          <ConnectionsScreen onSelect={setSelected} />
        )}
      </main>
      <StatusBar selected={selected} onNav={() => setSelected(null)} />
      <Toaster />
    </div>
  );
}

function TopBar({ backendHost }: { backendHost: string }) {
  return (
    <header className="sticky top-0 z-20 border-b border-[color:var(--border)] bg-[color:var(--bg)]/85 backdrop-blur">
      <div className="mx-auto flex h-11 max-w-6xl items-center justify-between gap-6 px-5 text-[12px] leading-none">
        <div className="flex items-center gap-3">
          <span className="text-[color:var(--accent)]">▍</span>
          <span className="font-medium tracking-tight">agentic-sql</span>
          <span className="text-[color:var(--dim)]">v0.1</span>
        </div>
        <div className="flex items-center gap-4 text-[color:var(--muted)]">
          <span className="flex items-center gap-1.5">
            <span
              className="inline-block size-1.5 rounded-full bg-[color:var(--ok)]"
              aria-hidden
            />
            backend
            <code className="text-[color:var(--ink)]">{backendHost}</code>
          </span>
        </div>
      </div>
    </header>
  );
}
