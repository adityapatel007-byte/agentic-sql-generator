import { API_BASE } from "./config";
import type { StreamEvent } from "./events";

// POST-friendly SSE reader. The browser's built-in EventSource is GET-only,
// so we do it by hand: fetch + ReadableStream + split on the SSE frame delimiter.
//
// Wire format from sse-starlette:
//   event: <name>\n
//   data:  <json>\n
//   \n                      <- frame terminator
//
// Multi-line data uses multiple `data:` lines joined with \n on the client.
// We ignore the `event:` field because the payload already carries `type`.

export type AskStreamOptions = {
  connectionId: string;
  question: string;
  signal?: AbortSignal;
};

export async function* askStream({
  connectionId,
  question,
  signal,
}: AskStreamOptions): AsyncGenerator<StreamEvent, void, void> {
  const res = await fetch(
    `${API_BASE}/ask/${encodeURIComponent(connectionId)}`,
    {
      method: "POST",
      headers: {
        "content-type": "application/json",
        accept: "text/event-stream",
      },
      body: JSON.stringify({ question }),
      signal,
    },
  );

  if (!res.ok || !res.body) {
    const detail = await res.text().catch(() => res.statusText);
    throw new Error(`SSE request failed (${res.status}): ${detail || "no body"}`);
  }

  const reader = res.body.pipeThrough(new TextDecoderStream()).getReader();
  let buffer = "";

  try {
    while (true) {
      const { value, done } = await reader.read();
      if (done) break;
      buffer += value;

      // Frames are separated by a blank line. Handle both LF-only and CRLF servers.
      let hit = findFrameEnd(buffer);
      while (hit) {
        const frame = buffer.slice(0, hit.at);
        buffer = buffer.slice(hit.at + hit.len);
        const evt = parseFrame(frame);
        if (evt) yield evt;
        hit = findFrameEnd(buffer);
      }
    }
  } finally {
    reader.releaseLock();
  }
}

type FrameEnd = { at: number; len: number };

function findFrameEnd(s: string): FrameEnd | null {
  const crlf = s.indexOf("\r\n\r\n");
  const lf = s.indexOf("\n\n");
  if (crlf === -1 && lf === -1) return null;
  if (crlf !== -1 && (lf === -1 || crlf < lf)) return { at: crlf, len: 4 };
  return { at: lf, len: 2 };
}

function parseFrame(frame: string): StreamEvent | null {
  const dataLines: string[] = [];
  for (const raw of frame.split(/\r?\n/)) {
    if (!raw || raw.startsWith(":")) continue;
    const colon = raw.indexOf(":");
    if (colon === -1) continue;
    const field = raw.slice(0, colon);
    // Per SSE spec, a single space after the colon is optional and stripped.
    const value = raw.slice(colon + 1).replace(/^ /, "");
    if (field === "data") dataLines.push(value);
  }
  if (dataLines.length === 0) return null;
  try {
    return JSON.parse(dataLines.join("\n")) as StreamEvent;
  } catch {
    return null;
  }
}
