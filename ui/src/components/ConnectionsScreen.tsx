import { useEffect, useState } from "react";
import { Database, FileText, Loader2, Plug, Trash2, Upload } from "lucide-react";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { Textarea } from "@/components/ui/textarea";
import { Badge } from "@/components/ui/badge";

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

export function ConnectionsScreen({ onSelect }: Props) {
  const [connections, setConnections] = useState<ConnectionInfo[]>([]);
  const [loading, setLoading] = useState(true);

  async function refresh() {
    try {
      const res = await listConnections();
      setConnections(res.connections);
    } catch (e) {
      toast.error(errMsg(e, "Failed to load connections"));
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
      toast.success("Connection removed");
    } catch (e) {
      toast.error(errMsg(e, "Failed to delete"));
    }
  }

  return (
    <div className="mx-auto grid w-full max-w-5xl gap-8 px-6 py-10 lg:grid-cols-[1.1fr_0.9fr]">
      <section>
        <h2 className="mb-1 text-xl font-semibold tracking-tight">
          Connect a database
        </h2>
        <p className="mb-6 text-sm text-muted-foreground">
          Upload a SQLite file or paste a Postgres connection string. The
          schema is indexed automatically so you can ask questions right away.
        </p>

        <Card>
          <CardContent className="pt-6">
            <Tabs defaultValue="sqlite">
              <TabsList className="grid w-full grid-cols-2">
                <TabsTrigger value="sqlite">
                  <FileText className="mr-2 size-4" /> SQLite
                </TabsTrigger>
                <TabsTrigger value="postgres">
                  <Database className="mr-2 size-4" /> Postgres
                </TabsTrigger>
              </TabsList>

              <TabsContent value="sqlite" className="mt-6">
                <SqliteForm onRegistered={refresh} />
              </TabsContent>
              <TabsContent value="postgres" className="mt-6">
                <PostgresForm onRegistered={refresh} />
              </TabsContent>
            </Tabs>
          </CardContent>
        </Card>
      </section>

      <section>
        <h2 className="mb-1 text-xl font-semibold tracking-tight">
          Your connections
        </h2>
        <p className="mb-6 text-sm text-muted-foreground">
          Pick one to start asking questions.
        </p>

        {loading ? (
          <Card>
            <CardContent className="flex items-center gap-3 py-10 text-sm text-muted-foreground">
              <Loader2 className="size-4 animate-spin" /> Loading…
            </CardContent>
          </Card>
        ) : connections.length === 0 ? (
          <Card>
            <CardContent className="py-10 text-center text-sm text-muted-foreground">
              No connections yet. Register one on the left.
            </CardContent>
          </Card>
        ) : (
          <div className="grid gap-3">
            {connections.map((c) => (
              <ConnectionRow
                key={c.connection_id}
                conn={c}
                onSelect={() => onSelect(c)}
                onDelete={() => handleDelete(c.connection_id)}
              />
            ))}
          </div>
        )}
      </section>
    </div>
  );
}

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
    <Card className="group transition hover:border-foreground/20">
      <CardContent className="flex items-center justify-between gap-4 py-4">
        <div className="min-w-0">
          <div className="flex items-center gap-2">
            <Badge variant="secondary" className="uppercase tracking-wide">
              {conn.kind}
            </Badge>
            <span className="truncate font-medium">
              {conn.label ?? "(unnamed)"}
            </span>
          </div>
          <p className="mt-1 truncate font-mono text-xs text-muted-foreground">
            {conn.connection_id}
          </p>
        </div>
        <div className="flex gap-2">
          <Button size="sm" onClick={onSelect}>
            <Plug className="mr-1.5 size-3.5" />
            Use
          </Button>
          <Button
            size="icon"
            variant="ghost"
            aria-label="Delete connection"
            onClick={onDelete}
          >
            <Trash2 className="size-4" />
          </Button>
        </div>
      </CardContent>
    </Card>
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
      toast.success(`Registered ${info.label ?? info.connection_id}`);
      setFile(null);
      setLabel("");
      (e.currentTarget as HTMLFormElement).reset();
      onRegistered();
    } catch (e) {
      toast.error(errMsg(e, "Upload failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <div className="grid gap-2">
        <Label htmlFor="sqlite-file">SQLite file</Label>
        <Input
          id="sqlite-file"
          type="file"
          accept=".sqlite,.db,.sqlite3,application/x-sqlite3"
          onChange={(e) => setFile(e.target.files?.[0] ?? null)}
          required
        />
      </div>
      <div className="grid gap-2">
        <Label htmlFor="sqlite-label">Label (optional)</Label>
        <Input
          id="sqlite-label"
          placeholder="chinook, northwind, my project…"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          maxLength={80}
        />
      </div>
      <Button type="submit" disabled={!file || busy}>
        {busy ? (
          <Loader2 className="mr-2 size-4 animate-spin" />
        ) : (
          <Upload className="mr-2 size-4" />
        )}
        Upload &amp; index
      </Button>
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
      toast.success(`Registered ${info.label ?? info.connection_id}`);
      setConninfo("");
      setLabel("");
      onRegistered();
    } catch (e) {
      toast.error(errMsg(e, "Connect failed"));
    } finally {
      setBusy(false);
    }
  }

  return (
    <form onSubmit={submit} className="grid gap-4">
      <div className="grid gap-2">
        <Label htmlFor="pg-conn">Connection string</Label>
        <Textarea
          id="pg-conn"
          className="font-mono text-xs"
          rows={3}
          placeholder="postgresql://user:pass@host:5432/dbname"
          value={conninfo}
          onChange={(e) => setConninfo(e.target.value)}
          required
        />
        <p className="text-xs text-muted-foreground">
          Read-only transactions are enforced server-side.
        </p>
      </div>
      <div className="grid gap-2">
        <Label htmlFor="pg-label">Label (optional)</Label>
        <Input
          id="pg-label"
          placeholder="production replica, analytics warehouse…"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
          maxLength={80}
        />
      </div>
      <Button type="submit" disabled={!conninfo.trim() || busy}>
        {busy ? (
          <Loader2 className="mr-2 size-4 animate-spin" />
        ) : (
          <Plug className="mr-2 size-4" />
        )}
        Connect &amp; index
      </Button>
    </form>
  );
}

function errMsg(e: unknown, fallback: string): string {
  if (e instanceof ApiError) return `${fallback}: ${e.message}`;
  if (e instanceof Error) return `${fallback}: ${e.message}`;
  return fallback;
}
