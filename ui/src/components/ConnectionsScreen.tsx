import { useEffect, useState } from "react";
import { toast } from "sonner";

import {
  ApiError,
  deleteConnection,
  listConnections,
  registerPostgres,
  registerSqlite,
  type ConnectionInfo,
} from "@/lib/api";

type Props = {
  onSelect: (conn: ConnectionInfo) => void;
};

type Kind = "sqlite" | "postgres";

export function ConnectionsScreen({ onSelect }: Props) {
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [loading, setLoading] = useState(true);
  const [kind, setKind] = useState<Kind>("sqlite");

  async function refresh() {
    try {
      const res = await listConnections();
      setConnections(res.connections);
    } catch (e) {
      toast.error(errMsg(e, "failed to load connections"));
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void refresh();
  }, []);

  async function handleDelete(id: string) {
    try {
      await deleteConnection(id);
      setConnections((prev) => prev.filter((c) => c.connection_id !== id));
      toast.success("connection removed");
    } catch (e) {
      toast.error(errMsg(e, "delete failed"));
    }
  }

  return (
    <div className="mx-auto grid w-full max-w-6xl gap-5 px-5 py-10 lg:grid-cols-[minmax(0,1fr)_minmax(0,1fr)]">
      <section aria-labelledby="register-heading">
        <SectionHeader
          id="register-heading"
          label="register"
          hint="upload sqlite or paste a postgres conn string"
        />
        <Panel>
          <KindSwitch value={kind} onChange={setKind} />
          <div className="mt-5">
            {kind === "sqlite" ? (
              <SqliteForm onRegistered={refresh} />
            ) : (
              <PostgresForm onRegistered={refresh} />
            )}
          </div>
        </Panel>
        <p className="mt-3 pl-3 text-[11px] leading-relaxed text-[color:var(--dim)]">
          both adapters run read-only. schema is indexed on register so /ask
          works immediately.
        </p>
      </section>

      <section aria-labelledby="conns-heading">
        <SectionHeader
          id="conns-heading"
          label="connections"
          count={connections.length}
        />
        <Panel padded={false}>
          {loading ? (
            <EmptyRow>loading…</EmptyRow>
          ) : connections.length === 0 ? (
            <EmptyRow>
              no connections registered. register one on the left to begin.
            </EmptyRow>
          ) : (
            <ul className="divide-y divide-[color:var(--border)]">
              {connections.map((c) => (
                <ConnectionRow
                  key={c.connection_id}
                  conn={c}
                  onSelect={() => onSelect(c)}
                  onDelete={() => handleDelete(c.connection_id)}
                />
              ))}
            </ul>
          )}
        </Panel>
      </section>
    </div>
  );
}

/* ------------------------------- panels ---------------------------------- */

function SectionHeader({
  id,
  label,
  hint,
  count,
}: {
  id: string;
  label: string;
  hint?: string;
  count?: number;
}) {
  return (
    <div className="mb-3 flex items-baseline justify-between gap-3 pl-3">
      <h2 id={id} className="text-[13px] font-medium text-[color:var(--ink)]">
        <span className="text-[color:var(--accent)]">▍</span> {label}
        {count !== undefined && (
          <span className="ml-2 text-[color:var(--dim)]">
            ({count})
          </span>
        )}
      </h2>
      {hint && (
        <span className="hidden text-[11px] text-[color:var(--dim)] sm:inline">
          {hint}
        </span>
      )}
    </div>
  );
}

function Panel({
  children,
  padded = true,
}: {
  children: React.ReactNode;
  padded?: boolean;
}) {
  return (
    <div
      className={
        "rounded-md border border-[color:var(--border)] bg-[color:var(--bg-elev)]" +
        (padded ? " p-5" : "")
      }
    >
      {children}
    </div>
  );
}

function EmptyRow({ children }: { children: React.ReactNode }) {
  return (
    <div className="px-5 py-8 text-center text-[12px] text-[color:var(--dim)]">
      {children}
    </div>
  );
}

/* ---------------------------- connection list ---------------------------- */

function ConnectionRow({
  conn,
  onSelect,
  onDelete,
}: {
  conn: ConnectionInfo;
  onSelect: () => void;
  onDelete: () => void;
}) {
  return (
    <li className="group flex items-center gap-3 px-4 py-3 transition-colors hover:bg-[color:var(--hover)]">
      <KindTag kind={conn.kind} />
      <div className="min-w-0 flex-1">
        <div className="truncate text-[13px] text-[color:var(--ink)]">
          {conn.label ?? <span className="text-[color:var(--dim)]">unnamed</span>}
        </div>
        <div className="truncate text-[11px] text-[color:var(--dim)]">
          {conn.connection_id}
        </div>
      </div>
      <div className="flex items-center gap-1 text-[11px]">
        <button
          type="button"
          onClick={onSelect}
          className="rounded-sm border border-transparent px-2 py-1 text-[color:var(--muted)] transition-colors hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
        >
          use →
        </button>
        <button
          type="button"
          onClick={onDelete}
          aria-label="remove connection"
          className="rounded-sm px-2 py-1 text-[color:var(--dim)] opacity-0 transition-colors hover:text-[color:var(--err)] group-hover:opacity-100 focus:opacity-100"
        >
          ×
        </button>
      </div>
    </li>
  );
}

function KindTag({ kind }: { kind: Kind }) {
  return (
    <span className="shrink-0 rounded-sm border border-[color:var(--border)] px-1.5 py-0.5 text-[10px] uppercase tracking-wider text-[color:var(--muted)]">
      {kind}
    </span>
  );
}

/* ------------------------------- forms ----------------------------------- */

function KindSwitch({
  value,
  onChange,
}: {
  value: Kind;
  onChange: (k: Kind) => void;
}) {
  return (
    <div
      role="tablist"
      aria-label="database kind"
      className="inline-flex rounded-md border border-[color:var(--border)] bg-[color:var(--bg-sunken)] p-0.5 text-[12px]"
    >
      {(["sqlite", "postgres"] as const).map((k) => (
        <button
          key={k}
          role="tab"
          aria-selected={value === k}
          onClick={() => onChange(k)}
          className={
            "rounded-sm px-3 py-1 transition-colors " +
            (value === k
              ? "bg-[color:var(--bg-elev)] text-[color:var(--ink)]"
              : "text-[color:var(--muted)] hover:text-[color:var(--ink)]")
          }
        >
          {k}
        </button>
      ))}
    </div>
  );
}

function SqliteForm({ onRegistered }: { onRegistered: () => void }) {
  const [file, setFile] = useState<File | null>(null);
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!file) return;
    setBusy(true);
    try {
      const info = await registerSqlite(file, label.trim() || undefined);
      toast.success(`registered ${info.label ?? info.connection_id}`);
      setFile(null);
      setLabel("");
      (e.currentTarget as HTMLFormElement).reset();
      onRegistered();
    } catch (e) {
      toast.error(errMsg(e, "upload failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <Field label="file">
        <FileInput
          onChange={(f) => setFile(f)}
          accept=".sqlite,.db,.sqlite3,application/x-sqlite3"
          current={file}
        />
      </Field>
      <Field label="label" hint="optional">
        <TerminalInput
          value={label}
          onChange={setLabel}
          placeholder="chinook, northwind…"
          maxLength={80}
        />
      </Field>
      <SubmitButton busy={busy} disabled={!file}>
        {busy ? "indexing…" : "upload & index"}
      </SubmitButton>
    </form>
  );
}

function PostgresForm({ onRegistered }: { onRegistered: () => void }) {
  const [conninfo, setConninfo] = useState("");
  const [label, setLabel] = useState("");
  const [busy, setBusy] = useState(false);

  async function submit(e: React.FormEvent) {
    e.preventDefault();
    if (!conninfo.trim()) return;
    setBusy(true);
    try {
      const info = await registerPostgres({
        conninfo: conninfo.trim(),
        label: label.trim() || undefined,
      });
      toast.success(`registered ${info.label ?? info.connection_id}`);
      setConninfo("");
      setLabel("");
      onRegistered();
    } catch (e) {
      toast.error(errMsg(e, "connect failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <Field
        label="conninfo"
        hint="read-only txn enforced server-side"
      >
        <TerminalTextarea
          value={conninfo}
          onChange={setConninfo}
          placeholder="postgresql://user:pass@host:5432/dbname"
          rows={3}
        />
      </Field>
      <Field label="label" hint="optional">
        <TerminalInput
          value={label}
          onChange={setLabel}
          placeholder="prod replica, analytics dwh…"
          maxLength={80}
        />
      </Field>
      <SubmitButton busy={busy} disabled={!conninfo.trim()}>
        {busy ? "indexing…" : "connect & index"}
      </SubmitButton>
    </form>
  );
}

function Field({
  label,
  hint,
  children,
}: {
  label: string;
  hint?: string;
  children: React.ReactNode;
}) {
  return (
    <label className="grid gap-1.5 text-[12px]">
      <span className="flex items-baseline justify-between text-[color:var(--muted)]">
        <span>{label}</span>
        {hint && <span className="text-[color:var(--dim)]">{hint}</span>}
      </span>
      {children}
    </label>
  );
}

function TerminalInput({
  value,
  onChange,
  placeholder,
  maxLength,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  maxLength?: number;
}) {
  return (
    <input
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      maxLength={maxLength}
      className="rounded-sm border border-[color:var(--border)] bg-[color:var(--bg-sunken)] px-2.5 py-1.5 font-mono text-[13px] text-[color:var(--ink)] placeholder:text-[color:var(--dim)] focus-visible:border-[color:var(--accent)] focus-visible:outline-none"
    />
  );
}

function TerminalTextarea({
  value,
  onChange,
  placeholder,
  rows = 3,
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  rows?: number;
}) {
  return (
    <textarea
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={placeholder}
      rows={rows}
      className="resize-none rounded-sm border border-[color:var(--border)] bg-[color:var(--bg-sunken)] px-2.5 py-1.5 font-mono text-[12px] text-[color:var(--ink)] placeholder:text-[color:var(--dim)] focus-visible:border-[color:var(--accent)] focus-visible:outline-none"
    />
  );
}

function FileInput({
  onChange,
  accept,
  current,
}: {
  onChange: (f: File | null) => void;
  accept?: string;
  current: File | null;
}) {
  return (
    <label
      className="flex cursor-pointer items-center gap-3 rounded-sm border border-dashed border-[color:var(--border)] bg-[color:var(--bg-sunken)] px-3 py-2 text-[12px] text-[color:var(--muted)] transition-colors hover:border-[color:var(--accent-dim)] hover:text-[color:var(--ink)]"
    >
      <span className="rounded-sm border border-[color:var(--border)] bg-[color:var(--bg-elev)] px-2 py-0.5 text-[11px] text-[color:var(--ink)]">
        choose file
      </span>
      <span className="min-w-0 truncate">
        {current ? current.name : "no file selected"}
      </span>
      <input
        type="file"
        accept={accept}
        className="sr-only"
        onChange={(e) => onChange(e.target.files?.[0] ?? null)}
      />
    </label>
  );
}

function SubmitButton({
  busy,
  disabled,
  children,
}: {
  busy: boolean;
  disabled?: boolean;
  children: React.ReactNode;
}) {
  return (
    <button
      type="submit"
      disabled={disabled || busy}
      className="mt-1 inline-flex items-center justify-center gap-2 rounded-sm border border-[color:var(--accent)] bg-[color:var(--accent)] px-3 py-1.5 text-[12px] font-medium text-[color:var(--accent-ink)] transition-colors hover:brightness-110 disabled:cursor-not-allowed disabled:border-[color:var(--border)] disabled:bg-transparent disabled:text-[color:var(--dim)]"
    >
      {busy ? (
        <span className="inline-block size-2 animate-pulse rounded-full bg-current" />
      ) : (
        <span aria-hidden>→</span>
      )}
      {children}
    </button>
  );
}

/* -------------------------------- utils ---------------------------------- */

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return `${fallback}: ${e.message}`;
  if (e instanceof Error) return `${fallback}: ${e.message}`;
  return fallback;
}
