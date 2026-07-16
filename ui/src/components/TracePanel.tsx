import { useEffect, useMemo, useRef, useState } from "react";

import type { StreamEvent } from "@/lib/events";

export type TimedEvent = {
  event: StreamEvent;
  receivedAt: number;
};

type Props = {
  events: TimedEvent[];
  running: boolean;
  startedAt: number | null;
};

export function TracePanel({ events, running, startedAt }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  const timeline = useMemo(() => buildTimeline(events, startedAt), [
    events,
    startedAt,
  ]);

  if (events.length === 0 && !running) return null;

  return (
    <section
      aria-label="agent trace"
      className="rounded-md border border-[color:var(--border)] bg-[color:var(--bg-elev)]"
    >
      <header className="flex items-center justify-between border-b border-[color:var(--border)] px-4 py-2 text-[11px] text-[color:var(--muted)]">
        <div className="flex items-center gap-3">
          <span className="text-[color:var(--accent)]">▍</span>
          <span>agent trace</span>
          <span className="text-[color:var(--dim)]">
            {events.length} event{events.length === 1 ? "" : "s"}
          </span>
        </div>
        {running && (
          <span className="flex items-center gap-2 text-[color:var(--ok)]">
            <span
              className="inline-block size-1.5 animate-pulse rounded-full bg-current"
              aria-hidden
            />
            streaming
          </span>
        )}
      </header>
      <div
        ref={scrollerRef}
        className="max-h-[440px] overflow-y-auto py-2 font-mono text-[12px]"
      >
        <ul>
          {timeline.map((row, i) => (
            <TimelineRow key={i} row={row} />
          ))}
        </ul>
      </div>
    </section>
  );
}

/* ------------------------------ timeline --------------------------------- */

type Row =
  | { kind: "iteration"; t: number; iteration: number }
  | { kind: "assistant-text"; t: number; iteration: number; text: string }
  | {
      kind: "thinking";
      t: number;
      iteration: number;
    }
  | {
      kind: "tool-call";
      t: number;
      iteration: number;
      name: string;
      args: Record<string, unknown>;
    }
  | {
      kind: "tool-result";
      t: number;
      iteration: number;
      name: string;
      result: Record<string, unknown>;
    }
  | {
      kind: "final";
      t: number;
      success: boolean;
      stopReason: string;
      iterations: number;
    };

function buildTimeline(
  events: TimedEvent[],
  startedAt: number | null,
): Row[] {
  const out: Row[] = [];
  const t0 = startedAt ?? (events[0]?.receivedAt ?? performance.now());
  for (const { event: e, receivedAt } of events) {
    const t = (receivedAt - t0) / 1000;
    switch (e.type) {
      case "iteration":
        out.push({ kind: "iteration", t, iteration: e.iteration });
        break;
      case "assistant":
        if (e.content && e.content.trim()) {
          out.push({
            kind: "assistant-text",
            t,
            iteration: e.iteration,
            text: e.content,
          });
        } else if (e.has_tool_calls) {
          out.push({ kind: "thinking", t, iteration: e.iteration });
        }
        break;
      case "tool_call":
        out.push({
          kind: "tool-call",
          t,
          iteration: e.iteration,
          name: e.name,
          args: e.arguments,
        });
        break;
      case "tool_result":
        out.push({
          kind: "tool-result",
          t,
          iteration: e.iteration,
          name: e.name,
          result: e.result,
        });
        break;
      case "final":
        out.push({
          kind: "final",
          t,
          success: e.success,
          stopReason: e.stop_reason,
          iterations: e.iterations_used,
        });
        break;
    }
  }
  return out;
}

function TimelineRow({ row }: { row: Row }) {
  const timeCell = (
    <span
      className="w-[52px] shrink-0 pr-3 text-right tabular-nums text-[color:var(--dim)]"
      aria-hidden
    >
      {formatT(row.t)}
    </span>
  );

  switch (row.kind) {
    case "iteration":
      return (
        <li className="flex items-center px-4 py-1.5">
          {timeCell}
          <span className="mr-2 text-[color:var(--accent)]">▶</span>
          <span className="uppercase tracking-wider text-[color:var(--muted)]">
            iteration {row.iteration}
          </span>
          <span className="ml-3 flex-1 border-t border-dashed border-[color:var(--border)]" />
        </li>
      );

    case "thinking":
      return (
        <li className="flex px-4 py-0.5">
          {timeCell}
          <span className="mr-2 w-4 text-[color:var(--dim)]" aria-hidden>
            ·
          </span>
          <span className="text-[color:var(--dim)] italic">
            routing to tools…
          </span>
        </li>
      );

    case "assistant-text":
      return (
        <li className="flex px-4 py-1.5">
          {timeCell}
          <span className="mr-2 w-4 text-[color:var(--accent)]" aria-hidden>
            ⚑
          </span>
          <p className="whitespace-pre-wrap leading-relaxed text-[color:var(--ink)]">
            {row.text}
          </p>
        </li>
      );

    case "tool-call":
      return (
        <li className="px-4 py-0.5">
          <div className="flex items-baseline">
            {timeCell}
            <span
              className="mr-2 w-4 text-[color:var(--accent)]"
              aria-hidden
              title="tool call"
            >
              →
            </span>
            <span className="text-[color:var(--ink)]">{row.name}</span>
            <ArgsInline args={row.args} />
          </div>
          <Expandable value={row.args} />
        </li>
      );

    case "tool-result":
      return (
        <li className="px-4 py-0.5">
          <div className="flex items-baseline">
            {timeCell}
            <span
              className="mr-2 w-4 text-[color:var(--ok)]"
              aria-hidden
              title="tool result"
            >
              ←
            </span>
            <span className="text-[color:var(--muted)]">{row.name}</span>
            <ResultInline result={row.result} />
          </div>
          <Expandable value={row.result} />
        </li>
      );

    case "final":
      return (
        <li className="mt-1 flex items-center gap-3 border-t border-[color:var(--border)] px-4 py-2 text-[11px]">
          {timeCell}
          <span
            className={
              row.success
                ? "text-[color:var(--ok)]"
                : "text-[color:var(--err)]"
            }
            aria-hidden
          >
            {row.success ? "✓" : "×"}
          </span>
          <span className="text-[color:var(--ink)]">
            {row.success ? "finished" : "stopped"}
          </span>
          <span className="text-[color:var(--dim)]">·</span>
          <span className="text-[color:var(--muted)]">{row.stopReason}</span>
          <span className="text-[color:var(--dim)]">·</span>
          <span className="text-[color:var(--muted)]">
            {row.iterations} iter{row.iterations === 1 ? "" : "s"}
          </span>
        </li>
      );
  }
}

function ArgsInline({ args }: { args: Record<string, unknown> }) {
  const keys = Object.keys(args);
  if (keys.length === 0)
    return <span className="ml-1 text-[color:var(--dim)]">()</span>;
  return (
    <span className="ml-1 truncate text-[color:var(--muted)]">
      {"("}
      {keys.map((k, i) => (
        <span key={k}>
          {i > 0 && <span className="text-[color:var(--dim)]">, </span>}
          <span className="text-[color:var(--muted)]">{k}</span>
          {isScalar(args[k]) && (
            <>
              <span className="text-[color:var(--dim)]">=</span>
              <span className="text-[color:var(--ink)]">
                {previewScalar(args[k])}
              </span>
            </>
          )}
        </span>
      ))}
      {")"}
    </span>
  );
}

function ResultInline({ result }: { result: Record<string, unknown> }) {
  const rc = result["row_count"];
  const cols = result["columns"];
  const err = result["error"];
  if (typeof err === "string" && err) {
    return (
      <span className="ml-2 truncate text-[color:var(--err)]">{err}</span>
    );
  }
  const parts: string[] = [];
  if (Array.isArray(cols)) parts.push(`${cols.length} cols`);
  if (typeof rc === "number") parts.push(`${rc} row${rc === 1 ? "" : "s"}`);
  if (Array.isArray(result["tables"]))
    parts.push(`${(result["tables"] as unknown[]).length} tables`);
  if (parts.length === 0) parts.push(summarize(result));
  return (
    <span className="ml-2 truncate text-[color:var(--muted)]">
      {parts.join(" · ")}
    </span>
  );
}

function Expandable({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  return (
    <div className="pl-[68px]">
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        aria-expanded={open}
        className="text-[10px] uppercase tracking-wider text-[color:var(--dim)] transition-colors hover:text-[color:var(--muted)]"
      >
        {open ? "hide raw" : "show raw"}
      </button>
      {open && (
        <pre className="mt-1 max-h-56 overflow-auto rounded-sm border border-[color:var(--border)] bg-[color:var(--bg-sunken)] p-2 text-[11px] leading-relaxed text-[color:var(--muted)]">
          {JSON.stringify(value, null, 2)}
        </pre>
      )}
    </div>
  );
}

/* ------------------------------ helpers ---------------------------------- */

function formatT(seconds: number): string {
  if (seconds < 10) return `${seconds.toFixed(2)}s`;
  if (seconds < 100) return `${seconds.toFixed(1)}s`;
  return `${Math.round(seconds)}s`;
}

function isScalar(v: unknown): boolean {
  return (
    v == null ||
    typeof v === "string" ||
    typeof v === "number" ||
    typeof v === "boolean"
  );
}

function previewScalar(v: unknown): string {
  if (v == null) return "null";
  if (typeof v === "string") {
    const s = v.length > 32 ? `${v.slice(0, 31)}…` : v;
    return `"${s}"`;
  }
  return String(v);
}

function summarize(v: unknown): string {
  if (v == null) return "null";
  if (typeof v !== "object") return String(v);
  if (Array.isArray(v)) return `[${v.length}]`;
  const keys = Object.keys(v as Record<string, unknown>);
  return `{${keys.slice(0, 3).join(", ")}${keys.length > 3 ? ", …" : ""}}`;
}
