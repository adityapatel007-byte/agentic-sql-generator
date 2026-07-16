import { useEffect, useState } from "react";
import { Database } from "lucide-react";

import { ConnectionsScreen } from "@/components/ConnectionsScreen";
import { AskScreen } from "@/components/AskScreen";
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

  return (
    <div className="min-h-screen bg-background text-foreground">
      <header className="sticky top-0 z-10 border-b bg-background/80 backdrop-blur">
        <div className="mx-auto flex h-14 max-w-6xl items-center justify-between px-6">
          <div className="flex items-center gap-2.5">
            <div className="grid size-7 place-items-center rounded-md bg-foreground text-background">
              <Database className="size-4" />
            </div>
            <div className="leading-tight">
              <div className="text-sm font-semibold tracking-tight">
                Agentic SQL
              </div>
              <div className="text-[10px] uppercase tracking-wider text-muted-foreground">
                natural language → sql
              </div>
            </div>
          </div>

          <div className="text-xs text-muted-foreground">
            <span className="hidden sm:inline">
              backend{" "}
              <code className="rounded bg-muted px-1.5 py-0.5 font-mono">
                {new URL(API_BASE).host}
              </code>
            </span>
          </div>
        </div>
      </header>

      <main>
        {selected ? (
          <AskScreen connection={selected} onBack={() => setSelected(null)} />
        ) : (
          <ConnectionsScreen onSelect={setSelected} />
        )}
      </main>

      <Toaster />
    </div>
  );
}
