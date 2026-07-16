import { useRef, useState } from "react";
import {
  ArrowLeft,
  CornerDownLeft,
  Loader2,
  Sparkles,
  X,
} from "lucide-react";
import { toast } from "sonner";

import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Textarea } from "@/components/ui/textarea";
import { ResultsTable } from "@/components/ResultsTable";
import { TracePanel } from "@/components/TracePanel";
import type { ConnectionInfo } from "@/lib/api";
import type { FinalEvent, StreamEvent } from "@/lib/events";
import { askStream } from "@/lib/sse";

const EXAMPLES = [
  "How many rows are in the largest table?",
  "Which columns look like they could be foreign keys?",
  "Show me the first few rows of every table.",
];

type Props = {
  connection: ConnectionInfo;
  onBack: () => void;
};

export function AskScreen({ connection, onBack }: Props) {
  const [question, setQuestion] = useState("");
  const [events, setEvents] = useState<StreamEvent[]>([]);
  const [running, setRunning] = useState(false);
  const abortRef = useRef<AbortController | null>(null);

  const finalEvent = events.find((e): e is FinalEvent => e.type === "final");

  async function submit() {
    const q = question.trim();
    if (!q || running) return;

    const controller = new AbortController();
    abortRef.current = controller;
    setEvents([]);
    setRunning(true);

    try {
      for await (const evt of askStream({
        connectionId: connection.connection_id,
        question: q,
        signal: controller.signal,
      })) {
        setEvents((prev) => [...prev, evt]);
      }
    } catch (e) {
      if (controller.signal.aborted) {
        toast.info("Cancelled");
      } else {
        toast.error(e instanceof Error ? e.message : "Stream failed");
      }
    } finally {
      setRunning(false);
      abortRef.current = null;
    }
  }

  function cancel() {
    abortRef.current?.abort();
  }

  function onKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if ((e.metaKey || e.ctrlKey) && e.key === "Enter") {
      e.preventDefault();
      void submit();
    }
  }

  return (
    <div className="mx-auto w-full max-w-4xl px-6 py-8">
      <div className="mb-6 flex items-center justify-between">
        <div className="flex items-center gap-3">
          <Button variant="ghost" size="sm" onClick={onBack} disabled={running}>
            <ArrowLeft className="mr-1.5 size-4" />
            Connections
          </Button>
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="uppercase tracking-wide">
              {connection.kind}
            </Badge>
            <span className="text-sm font-medium">
              {connection.label ?? "(unnamed)"}
            </span>
          </div>
        </div>
      </div>

      <div className="rounded-2xl border bg-card p-4 shadow-sm">
        <Textarea
          value={question}
          onChange={(e) => setQuestion(e.target.value)}
          onKeyDown={onKeyDown}
          placeholder="Ask a question about this database…"
          className="min-h-24 resize-none border-0 bg-transparent p-2 text-base shadow-none focus-visible:ring-0"
          disabled={running}
        />
        <div className="flex items-center justify-between border-t pt-3">
          <span className="text-xs text-muted-foreground">
            <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">
              Ctrl
            </kbd>{" "}
            +{" "}
            <kbd className="rounded border bg-muted px-1.5 py-0.5 font-mono text-[10px]">
              Enter
            </kbd>{" "}
            to send
          </span>
          {running ? (
            <Button size="sm" variant="outline" onClick={cancel}>
              <X className="mr-1.5 size-3.5" />
              Cancel
            </Button>
          ) : (
            <Button size="sm" onClick={() => void submit()} disabled={!question.trim()}>
              <CornerDownLeft className="mr-1.5 size-3.5" />
              Ask
            </Button>
          )}
        </div>
      </div>

      {events.length === 0 && !running && (
        <div className="mt-6">
          <p className="mb-2 flex items-center gap-2 text-xs uppercase tracking-wide text-muted-foreground">
            <Sparkles className="size-3.5" /> Try one of these
          </p>
          <div className="flex flex-wrap gap-2">
            {EXAMPLES.map((ex) => (
              <button
                key={ex}
                type="button"
                onClick={() => setQuestion(ex)}
                className="rounded-full border bg-card px-3 py-1.5 text-sm text-muted-foreground transition hover:border-foreground/30 hover:text-foreground"
              >
                {ex}
              </button>
            ))}
          </div>
        </div>
      )}

      <div className="mt-8 space-y-6">
        <TracePanel events={events} running={running} />
        {finalEvent && <ResultsTable final={finalEvent} />}
        {running && !finalEvent && events.length === 0 && (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="size-4 animate-spin" />
            Connecting to the agent…
          </div>
        )}
      </div>
    </div>
  );
}
