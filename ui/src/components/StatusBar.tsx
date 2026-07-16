import type { ConnectionInfo } from "@/lib/api";

type Props = {
  selected: ConnectionInfo | null;
  onNav: () => void;
};

export function StatusBar({ selected, onNav }: Props) {
  return (
    <footer className="sticky bottom-0 z-20 border-t border-[color:var(--border)] bg-[color:var(--bg-sunken)]/95 backdrop-blur">
      <div className="mx-auto flex h-7 max-w-6xl items-center justify-between gap-4 px-5 text-[11px] leading-none text-[color:var(--muted)]">
        <div className="flex items-center gap-4 truncate">
          <span className="flex items-center gap-1.5">
            <span className="text-[color:var(--dim)]">model</span>
            <span className="text-[color:var(--ink)]">
              nemotron-3-nano
            </span>
          </span>
          <Separator />
          <span className="flex items-center gap-1.5 truncate">
            <span className="text-[color:var(--dim)]">conn</span>
            {selected ? (
              <button
                type="button"
                onClick={onNav}
                className="truncate text-[color:var(--ink)] transition-colors hover:text-[color:var(--accent)]"
                title="Back to connections"
              >
                [{selected.kind}] {selected.label ?? selected.connection_id}
              </button>
            ) : (
              <span className="text-[color:var(--dim)]">none</span>
            )}
          </span>
        </div>
        <div className="hidden shrink-0 items-center gap-3 sm:flex">
          <Hint keys={["/"]} label="focus prompt" />
          <Hint keys={["esc"]} label="cancel" />
          <Hint keys={["n"]} label="connections" />
        </div>
      </div>
    </footer>
  );
}

function Separator() {
  return <span className="text-[color:var(--dim)]">·</span>;
}

function Hint({ keys, label }: { keys: string[]; label: string }) {
  return (
    <span className="flex items-center gap-1.5">
      {keys.map((k) => (
        <kbd
          key={k}
          className="rounded border border-[color:var(--border)] bg-[color:var(--bg)] px-1.5 py-0.5 text-[10px] text-[color:var(--muted)]"
        >
          {k}
        </kbd>
      ))}
      <span className="text-[color:var(--dim)]">{label}</span>
    </span>
  );
}
