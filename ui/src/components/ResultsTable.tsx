import { useState } from "react";
import { Check, Copy } from "lucide-react";

import { Button } from "@/components/ui/button";
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from "@/components/ui/table";
import type { FinalEvent } from "@/lib/events";

type Props = {
  final: FinalEvent;
};

export function ResultsTable({ final }: Props) {
  return (
    <div className="space-y-4">
      {final.final_sql && <SqlBlock sql={final.final_sql} />}
      {!final.success && final.answer_text && (
        <div className="rounded-xl border border-destructive/50 bg-destructive/5 px-4 py-3 text-sm">
          <div className="mb-1 font-medium text-destructive">
            Agent could not answer
          </div>
          <p className="text-muted-foreground">{final.answer_text}</p>
        </div>
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

function SqlBlock({ sql }: { sql: string }) {
  const [copied, setCopied] = useState(false);

  async function copy() {
    try {
      await navigator.clipboard.writeText(sql);
      setCopied(true);
      setTimeout(() => setCopied(false), 1200);
    } catch {
      /* clipboard may be unavailable — ignore */
    }
  }

  return (
    <div className="rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <span className="text-sm font-medium">Generated SQL</span>
        <Button size="sm" variant="ghost" onClick={copy}>
          {copied ? (
            <Check className="mr-1.5 size-3.5" />
          ) : (
            <Copy className="mr-1.5 size-3.5" />
          )}
          {copied ? "Copied" : "Copy"}
        </Button>
      </div>
      <pre className="overflow-x-auto px-4 py-4 font-mono text-sm leading-relaxed">
        {sql}
      </pre>
    </div>
  );
}

function RowsTable({
  columns,
  rows,
  rowCount,
}: {
  columns: string[];
  rows: unknown[][];
  rowCount: number;
}) {
  if (rows.length === 0) {
    return (
      <div className="rounded-xl border bg-card px-4 py-8 text-center text-sm text-muted-foreground">
        Query returned no rows.
      </div>
    );
  }

  return (
    <div className="rounded-xl border bg-card">
      <div className="flex items-center justify-between border-b px-4 py-2.5">
        <span className="text-sm font-medium">Results</span>
        <span className="text-xs text-muted-foreground">
          {rowCount} row{rowCount === 1 ? "" : "s"}
        </span>
      </div>
      <div className="overflow-x-auto">
        <Table>
          <TableHeader>
            <TableRow>
              {columns.map((c) => (
                <TableHead key={c} className="whitespace-nowrap">
                  {c}
                </TableHead>
              ))}
            </TableRow>
          </TableHeader>
          <TableBody>
            {rows.map((row, i) => (
              <TableRow key={i}>
                {row.map((cell, j) => (
                  <TableCell
                    key={j}
                    className="whitespace-nowrap font-mono text-xs"
                  >
                    {formatCell(cell)}
                  </TableCell>
                ))}
              </TableRow>
            ))}
          </TableBody>
        </Table>
      </div>
    </div>
  );
}

function formatCell(v: unknown): string {
  if (v === null || v === undefined) return "∅";
  if (typeof v === "object") return JSON.stringify(v);
  return String(v);
}
