import { useState } from "react";

import type { FinalEvent } from "@/lib/events";

type Props = {
  final: FinalEvent;
};

export function ResultsTable({ final }: Props) {
  return (
    <div className="space-y-4">
      {final.final_sql && <SqlBlock sql={final.final_sql} />}
      {!final.success && final.answer_text && (
        <ErrorBlock message={final.answer_text} />
      )}
      {final.final_rows && final.final_columns && (
        <RowsTable
          columns={final.final_columns}
          rows={final.final_rows}
          rowCount={final.row_count ?? final.final_rows.length}
        />
      )}
    </div>
  );
}

/* ---------------------------------- sql ---------------------------------- */

function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1500);
    } catch {
      /* ignore */
    }
  }

  return (
    <section aria-labelledby="sql-heading" className="rounded-md border border-[color:var(--border)] bg-[color:var(--bg-elev)]">
      <header className="flex items-center justify-between border-b border-[color:var(--border)] px-4 py-2 text-[11px]">
        <div className="flex items-center gap-2 text-[color:var(--muted)]">
          <span className="text-[color:var(--accent)]">▍</span>
          <h3 id="sql-heading" className="text-[color:var(--ink)]">
            generated sql
          </h3>
        </div>
        <button
          type="button"
          onClick={copy}
          className="rounded-sm border border-[color:var(--border)] px-2 py-0.5 text-[color:var(--muted)] transition-colors hover:border-[color:var(--accent)] hover:text-[color:var(--accent)]"
        >
          {copied ? "copied ✓" : "copy"}
        </button>
      </header>
      <div className="flex overflow-x-auto">
        <div
          aria-hidden
          className="shrink-0 select-none border-r border-[color:var(--border)] bg-[color:var(--bg-sunken)] px-3 py-3 font-mono text-[12px] leading-relaxed text-[color:var(--accent)]"
        >
          {sql.split("\n").map((_, i) => (
            <div key={i}>{i === 0 ? "→" : " "}</div>
          ))}
        </div>
        <pre className="flex-1 whitespace-pre px-4 py-3 font-mono text-[12px] leading-relaxed text-[color:var(--ink)]">
          {sql.trim()}
        </pre>
      </div>
    </section>
  );
}

/* -------------------------------- error ---------------------------------- */

function ErrorBlock({ message }: { message: string }) {
  return (
    <div className="rounded-md border border-[color:var(--err)]/50 bg-[color:var(--err)]/5 px-4 py-3 text-[12px]">
      <div className="mb-1 flex items-center gap-2 text-[color:var(--err)]">
        <span aria-hidden>×</span>
        <span className="uppercase tracking-wider">agent stopped</span>
      </div>
      <p className="whitespace-pre-wrap leading-relaxed text-[color:var(--muted)]">
        {message}
      </p>
    </div>
  );
}

/* --------------------------------- rows ---------------------------------- */

function RowsTable({
  columns,
  rows,
  rowCount,
}: {
  columns: string[];
  rows: unknown[][];
  rowCount: number;
}) {
  return (
    <section aria-labelledby="results-heading" className="rounded-md border border-[color:var(--border)] bg-[color:var(--bg-elev)]">
      <header className="flex items-center justify-between border-b border-[color:var(--border)] px-4 py-2 text-[11px]">
        <div className="flex items-center gap-2">
          <span className="text-[color:var(--accent)]">▍</span>
          <h3 id="results-heading" className="text-[color:var(--ink)]">
            results
          </h3>
        </div>
        <span className="text-[color:var(--dim)]">
          {rowCount} row{rowCount === 1 ? "" : "s"}
          {" · "}
          {columns.length} col{columns.length === 1 ? "" : "s"}
        </span>
      </header>
      {rows.length === 0 ? (
        <div className="px-4 py-6 text-center text-[12px] text-[color:var(--dim)]">
          query returned no rows
        </div>
      ) : (
        <div className="overflow-x-auto">
          <table className="w-full min-w-full border-collapse font-mono text-[12px]">
            <thead>
              <tr className="border-b border-[color:var(--border)] text-left text-[11px] uppercase tracking-wider text-[color:var(--muted)]">
                {columns.map((c) => (
                  <th
                    key={c}
                    scope="col"
                    className="whitespace-nowrap px-3 py-2 font-normal"
                  >
                    {c}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {rows.map((row, i) => (
                <tr
                  key={i}
                  className="border-b border-[color:var(--border)] last:border-0 transition-colors hover:bg-[color:var(--hover)]"
                >
                  {row.map((cell, j) => (
                    <td
                      key={j}
                      className="whitespace-nowrap px-3 py-1.5 tabular-nums"
                    >
                      <FormattedCell value={cell} />
                    </td>
                  ))}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </section>
  );
}

function FormattedCell({ value }: { value: unknown }) {
  if (value === null || value === undefined)
    return <span className="text-[color:var(--dim)]">∅</span>;
  if (typeof value === "number")
    return <span className="text-[color:var(--ink)]">{value}</span>;
  if (typeof value === "boolean")
    return (
      <span className="text-[color:var(--accent)]">{value ? "t" : "f"}</span>
    );
  if (typeof value === "object")
    return (
      <span className="text-[color:var(--muted)]">{JSON.stringify(value)}</span>
    );
  return <span className="text-[color:var(--ink)]">{String(value)}</span>;
}
