import { useEffect, useRef, useState } from "react";
import { ChevronDown, ChevronRight, Wrench, Sparkles } from "lucide-react";

import { Badge } from "@/components/ui/badge";
import type { StreamEvent } from "@/lib/events";

type Props = {
  events: StreamEvent[];
  running: boolean;
};

export function TracePanel({ events, running }: Props) {
  const scrollerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const el = scrollerRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [events.length]);

  if (events.length === 0 && !running) {
    return null;
  }

  return (
    <div className="rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <div className="flex items-center gap-2 text-sm font-medium">
          <Sparkles className="size-4 text-muted-foreground" />
          Agent trace
        </div>
        {running && (
          <span className="flex items-center gap-2 text-xs text-muted-foreground">
            <span className="relative flex size-2">
              <span className="absolute inline-flex h-full w-full animate-ping rounded-full bg-emerald-500 opacity-75" />
              <span className="relative inline-flex size-2 rounded-full bg-emerald-500" />
            </span>
            streaming
          </span>
        )}
      </div>

      <div
        ref={scrollerRef}
        className="max-h-[420px] overflow-y-auto px-4 py-4"
      >
        <div className="space-y-3">
          {events.map((e, i) => (
            <EventRow key={i} event={e} />
          ))}
        </div>
      </div>
    </div>
  );
}

function EventRow({ event }: { event: StreamEvent }) {
  switch (event.type) {
    case "iteration":
      return (
        <div className="flex items-center gap-3 pt-1 text-xs uppercase tracking-wider text-muted-foreground">
          <span className="h-px flex-1 bg-border" />
          <span>Iteration {event.iteration}</span>
          <span className="h-px flex-1 bg-border" />
        </div>
      );

    case "assistant": {
      const empty = !event.content?.trim();
      return (
        <div className="rounded-lg border bg-background/60 px-3 py-2 text-sm">
          <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">assistant</span>
            {event.has_tool_calls && <Badge variant="outline">tool calls</Badge>}
          </div>
          {empty ? (
            <span className="text-muted-foreground italic">
              (thinking — routing to tools)
            </span>
          ) : (
            <p className="whitespace-pre-wrap leading-relaxed">
              {event.content}
            </p>
          )}
        </div>
      );
    }

    case "tool_call":
      return (
        <div className="rounded-lg border-l-2 border-l-primary bg-muted/40 px-3 py-2 text-sm">
          <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
            <Wrench className="size-3.5" />
            <span className="font-medium text-foreground">tool call</span>
            <code className="rounded bg-background px-1.5 py-0.5 font-mono text-[11px]">
              {event.name}
            </code>
          </div>
          <JsonBlock value={event.arguments} />
        </div>
      );

    case "tool_result":
      return (
        <div className="rounded-lg border-l-2 border-l-emerald-500/60 bg-muted/40 px-3 py-2 text-sm">
          <div className="mb-1 flex items-center gap-2 text-xs text-muted-foreground">
            <span className="font-medium text-foreground">tool result</span>
            <code className="rounded bg-background px-1.5 py-0.5 font-mono text-[11px]">
              {event.name}
            </code>
          </div>
          <JsonBlock value={event.result} />
        </div>
      );

    case "final":
      return (
        <div className="rounded-lg border bg-background/60 px-3 py-2 text-xs text-muted-foreground">
          {event.success ? "✓ finished" : "× stopped"} —{" "}
          <span className="font-mono">{event.stop_reason}</span> ·{" "}
          {event.iterations_used} iteration{event.iterations_used === 1 ? "" : "s"}
        </div>
      );
  }
}

function JsonBlock({ value }: { value: unknown }) {
  const [open, setOpen] = useState(false);
  const preview = summarize(value);

  return (
    <div>
      <button
        type="button"
        onClick={() => setOpen((o) => !o)}
        className="flex w-full items-center gap-1.5 text-left text-xs text-muted-foreground transition hover:text-foreground"
      >
        {open ? (
          <ChevronDown className="size-3" />
        ) : (
          <ChevronRight className="size-3" />
        )}
        <span className="truncate font-mono">{preview}</span>
      </button>
      {open && (
        <pre className="mt-2 max-h-64 overflow-auto rounded bg-background/80 p-2 font-mono text-[11px] leading-relaxed">
          {JSON.stringify(value, null, 2)}
        </pre>
      )}
    </div>
  );
}

function summarize(value: unknown): string {
  if (value == null) return "null";
  if (typeof value !== "object") return String(value);
  if (Array.isArray(value)) return `Array(${value.length})`;
  const keys = Object.keys(value as Record<string, unknown>);
  if (keys.length === 0) return "{}";
  return `{ ${keys.slice(0, 3).join(", ")}${keys.length > 3 ? ", …" : ""} }`;
}
