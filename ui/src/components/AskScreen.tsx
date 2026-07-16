import { useCallback, useRef, useState } from "react";
import { toast } from "sonner";

import { ResultsTable } from "@/components/ResultsTable";
import { TracePanel, type TimedEvent } from "@/components/TracePanel";
import type { ConnectionInfo } from "@/lib/api";
import type { FinalEvent } from "@/lib/events";
import { useShortcut } from "@/lib/shortcuts";
import { askStream } from "@/lib/sse";

const EXAMPLES = [
  "how many customers are from the US?",
  "which columns look like foreign keys?",
  "show me the top 3 orders by total",
];

type Props = {
  connection: ConnectionInfo;
  onBack: () => void;
};

export function AskScreen({ connection, onBack }: Props) {
  const [question, setQuestion] = useState("");
  const [events, setEvents] = useState<TimedEvent[]>([]);
  const [running, setRunning] = useState(false);
  const [startedAt, setStartedAt] = useState<number | null>(null);

  const abortRef = useRef<AbortController | null>(null);
  const inputRef = useRef<HTMLInputElement>(null);

  const finalEvent = events
    .map((te) => te.event)
    .find((e): e is FinalEvent => e.type === "final");

  const cancel = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const submit = useCallback(async () => {
    const q = question.trim();
    if (!q || running) return;

    const controller = new AbortController();
    abortRef.current = controller;
    const t0 = performance.now();
    setEvents([]);
    setRunning(true);
    setStartedAt(t0);

    try {
      for await (const evt of askStream({
        connectionId: connection.connection_id,
        question: q,
        signal: controller.signal,
      })) {
        setEvents((prev) => [
          ...prev,
          { event: evt, receivedAt: performance.now() },
        ]);
      }
    } catch (e) {
      if (controller.signal.aborted) {
        toast.info("cancelled");
      } else {
        toast.error(e instanceof Error ? e.message : "stream failed");
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }, [connection.connection_id, question, running]);

  // Global shortcuts.
  useShortcut("/", (e) => {
    e.preventDefault();
    inputRef.current?.focus();
  });
  useShortcut("Escape", () => {
    if (running) cancel();
    else inputRef.current?.blur();
  });
  useShortcut("n", () => {
    if (!running) onBack();
  });

  return (
    <div className="mx-auto w-full max-w-4xl px-5 py-8">
      <Breadcrumb connection={connection} onBack={onBack} running={running} />

      <PromptBar
        value={question}
        onChange={setQuestion}
        onSubmit={submit}
        onCancel={cancel}
        inputRef={inputRef}
        running={running}
      />

      {events.length === 0 && !running && (
        <ExampleList
          examples={EXAMPLES}
          onPick={(ex) => {
            setQuestion(ex);
            inputRef.current?.focus();
          }}
        />
      )}

      {(events.length > 0 || running) && (
        <div className="mt-8 space-y-5">
          <TracePanel events={events} running={running} startedAt={startedAt} />
          {finalEvent && <ResultsTable final={finalEvent} />}
        </div>
      )}
    </div>
  );
}

/* ---------------------------- breadcrumb --------------------------------- */

function Breadcrumb({
  connection,
  onBack,
  running,
}: {
  connection: ConnectionInfo;
  onBack: () => void;
  running: boolean;
}) {
  return (
    <nav
      aria-label="context"
      className="mb-6 flex items-center gap-2 text-[11px] text-[color:var(--muted)]"
    >
      <button
        type="button"
        onClick={onBack}
        disabled={running}
        className="transition-colors hover:text-[color:var(--accent)] disabled:opacity-50"
      >
        connections
      </button>
      <span className="text-[color:var(--dim)]">/</span>
      <span className="rounded-sm border border-[color:var(--border)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider">
        {connection.kind}
      </span>
      <span className="truncate text-[color:var(--ink)]">
        {connection.label ?? connection.connection_id}
      </span>
    </nav>
  );
}

/* ---------------------------- prompt bar --------------------------------- */

function PromptBar({
  value,
  onChange,
  onSubmit,
  onCancel,
  inputRef,
  running,
}: {
  value: string;
  onChange: (v: string) => void;
  onSubmit: () => void;
  onCancel: () => void;
  inputRef: React.RefObject<HTMLInputElement | null>;
  running: boolean;
}) {
  const empty = value.length === 0;

  return (
    <div>
      <form
        onSubmit={(e) => {
          e.preventDefault();
          onSubmit();
        }}
        className="group relative flex items-center gap-2 rounded-md border border-[color:var(--border)] bg-[color:var(--bg-elev)] px-3 py-2.5 transition-colors focus-within:border-[color:var(--accent)]"
      >
        <span
          aria-hidden
          className="select-none text-[13px] text-[color:var(--accent)]"
        >
          $
        </span>
        <input
          ref={inputRef}
          value={value}
          onChange={(e) => onChange(e.target.value)}
          onKeyDown={(e) => {
            if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
              e.preventDefault();
              onSubmit();
            }
          }}
          placeholder={running ? "" : "ask a question…"}
          disabled={running}
          spellCheck={false}
          autoComplete="off"
          className="flex-1 bg-transparent font-mono text-[13px] text-[color:var(--ink)] placeholder:text-[color:var(--dim)] focus:outline-none disabled:cursor-progress"
          aria-label="question"
        />
        {empty && !running && (
          <span
            aria-hidden
            className="cursor-blink pointer-events-none absolute left-[calc(1.5rem+0.5ch)] top-1/2 -translate-y-1/2 text-[13px]"
          />
        )}
        {running ? (
          <button
            type="button"
            onClick={onCancel}
            className="rounded-sm border border-[color:var(--border)] px-2 py-1 text-[11px] text-[color:var(--muted)] transition-colors hover:border-[color:var(--err)] hover:text-[color:var(--err)]"
          >
            <span className="mr-1" aria-hidden>×</span>
            cancel
          </button>
        ) : (
          <button
            type="submit"
            disabled={empty}
            className="rounded-sm border border-[color:var(--accent)] bg-[color:var(--accent)] px-2.5 py-1 text-[11px] font-medium text-[color:var(--accent-ink)] transition-colors hover:brightness-110 disabled:cursor-not-allowed disabled:border-[color:var(--border)] disabled:bg-transparent disabled:text-[color:var(--dim)]"
          >
            <span className="mr-1" aria-hidden>↵</span>
            ask
          </button>
        )}
      </form>
      <div className="mt-2 flex items-center justify-between px-1 text-[11px] text-[color:var(--dim)]">
        <span className="flex items-center gap-2">
          <Kbd>⌘</Kbd>
          <span aria-hidden>+</span>
          <Kbd>↵</Kbd>
          <span>submit</span>
          <span className="mx-1 text-[color:var(--dim)]/60">·</span>
          <Kbd>esc</Kbd>
          <span>{running ? "cancel" : "blur"}</span>
        </span>
        <span className="hidden sm:inline">
          agent max 5 iterations · read-only
        </span>
      </div>
    </div>
  );
}

function Kbd({ children }: { children: React.ReactNode }) {
  return (
    <kbd className="rounded-sm border border-[color:var(--border)] bg-[color:var(--bg)] px-1 py-0.5 text-[10px] font-normal text-[color:var(--muted)]">
      {children}
    </kbd>
  );
}

/* --------------------------- examples ------------------------------------ */

function ExampleList({
  examples,
  onPick,
}: {
  examples: string[];
  onPick: (ex: string) => void;
}) {
  return (
    <div className="mt-8">
      <div className="mb-2 flex items-center gap-2 pl-3 text-[11px] uppercase tracking-wider text-[color:var(--dim)]">
        <span aria-hidden>—</span>
        <span>try</span>
      </div>
      <ul className="space-y-1">
        {examples.map((ex) => (
          <li key={ex}>
            <button
              type="button"
              onClick={() => onPick(ex)}
              className="group flex w-full items-center gap-3 rounded-sm px-3 py-1.5 text-left text-[12px] text-[color:var(--muted)] transition-colors hover:bg-[color:var(--hover)] hover:text-[color:var(--ink)]"
            >
              <span className="text-[color:var(--dim)] group-hover:text-[color:var(--accent)]">
                →
              </span>
              <span className="truncate">{ex}</span>
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
