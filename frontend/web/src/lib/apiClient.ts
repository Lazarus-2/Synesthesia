/**
 * Centralized API client (Plan 2 F4).
 *
 * Every fetch to the Synesthesia backend goes through here so we get:
 *   - One base URL (set via NEXT_PUBLIC_API_URL; defaults to localhost:8001)
 *   - One canonical request shape (sets Accept, surfaces APIError envelopes)
 *   - One SSE consumer (Plan 2 D6 event-tagged protocol)
 *   - Easy single-site insertion of auth headers once D4's frontend bits land
 *
 * Anything that called `fetch("http://localhost:8001/...")` directly should
 * migrate to `api.get/post/postForm/sse`.
 */

const FALLBACK_BASE = "http://localhost:8001";

/** Resolved base URL. Reads NEXT_PUBLIC_API_URL at module load. */
export const API_BASE_URL: string = (
  process.env.NEXT_PUBLIC_API_URL || FALLBACK_BASE
).replace(/\/+$/, "");

/** Versioned API root — every endpoint other than /health lives under here.
 *  The backend currently double-mounts at root and /api/v1 for backward
 *  compatibility; once the frontend fully migrates, the backend will drop
 *  the unversioned aliases (see backend/main.py). */
export const API_V1 = `${API_BASE_URL}/api/v1`;

/** Returns `{ Authorization: "Bearer <jwt>" }` if a token is in localStorage,
 *  else `{}`. Read directly from storage so apiClient stays free of a
 *  store import cycle (useAuthStore imports apiClient). Mirrors the
 *  TOKEN_KEY in useAuthStore. */
export function authHeader(): Record<string, string> {
  if (typeof window === "undefined") return {};
  const raw = window.localStorage.getItem("synesthesia.auth.token");
  if (!raw) return {};
  try {
    const token = JSON.parse(raw) as string;
    return token ? { Authorization: `Bearer ${token}` } : {};
  } catch {
    return {};
  }
}

/** Shape of the backend's APIError envelope (mirrors backend/main.py). */
export interface ApiErrorPayload {
  status: "error";
  code: string;
  message: string;
  details?: Record<string, unknown> | null;
}

/** Thrown when a request returns a non-2xx response. */
export class ApiError extends Error {
  status: number;
  code: string;
  details?: Record<string, unknown> | null;

  constructor(status: number, payload: ApiErrorPayload | string) {
    if (typeof payload === "string") {
      super(payload);
      this.code = `HTTP_${status}`;
    } else {
      super(payload.message);
      this.code = payload.code;
      this.details = payload.details ?? undefined;
    }
    this.status = status;
    this.name = "ApiError";
  }
}

async function parseErrorBody(res: Response): Promise<ApiErrorPayload | string> {
  try {
    const body = await res.json();
    if (body && typeof body === "object" && body.code && body.message) {
      return body as ApiErrorPayload;
    }
    return JSON.stringify(body).slice(0, 200);
  } catch {
    return res.statusText || `HTTP ${res.status}`;
  }
}

interface RequestOpts {
  /** Force the legacy root mount (`/health` is the only legitimate caller). */
  unversioned?: boolean;
  signal?: AbortSignal;
  headers?: Record<string, string>;
}

function resolveUrl(path: string, opts?: RequestOpts): string {
  if (path.startsWith("http://") || path.startsWith("https://")) return path;
  const cleaned = path.startsWith("/") ? path : `/${path}`;
  return opts?.unversioned ? `${API_BASE_URL}${cleaned}` : `${API_V1}${cleaned}`;
}

/** GET JSON. */
export async function apiGet<T = unknown>(
  path: string, opts?: RequestOpts,
): Promise<T> {
  const res = await fetch(resolveUrl(path, opts), {
    method: "GET",
    headers: { Accept: "application/json", ...authHeader(), ...(opts?.headers || {}) },
    signal: opts?.signal,
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorBody(res));
  return res.json() as Promise<T>;
}

/** POST JSON body. */
export async function apiPostJson<T = unknown>(
  path: string, body: unknown, opts?: RequestOpts,
): Promise<T> {
  const res = await fetch(resolveUrl(path, opts), {
    method: "POST",
    headers: {
      Accept: "application/json",
      "Content-Type": "application/json",
      ...authHeader(),
      ...(opts?.headers || {}),
    },
    body: JSON.stringify(body),
    signal: opts?.signal,
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorBody(res));
  return res.json() as Promise<T>;
}

/** POST FormData (no Content-Type — browser sets the boundary). */
export async function apiPostForm<T = unknown>(
  path: string, form: FormData, opts?: RequestOpts,
): Promise<T> {
  const res = await fetch(resolveUrl(path, opts), {
    method: "POST",
    headers: { Accept: "application/json", ...authHeader(), ...(opts?.headers || {}) },
    body: form,
    signal: opts?.signal,
  });
  if (!res.ok) throw new ApiError(res.status, await parseErrorBody(res));
  return res.json() as Promise<T>;
}

// ---------------------------------------------------------------------------
// SSE consumer (Plan 2 D6 protocol)
// ---------------------------------------------------------------------------

/** One frame from a tagged SSE stream. */
export interface SseEvent<T = unknown> {
  event: string;
  data: T;
}

interface SseHandlers<TChunk = unknown, TDone = unknown> {
  onChunk?: (data: TChunk) => void;
  onDone?: (data: TDone) => void;
  onError?: (data: { code?: string; message: string; details?: unknown }) => void;
  /** Phase-2 AURA: the "Discussing: …" authoritative facts frame. */
  onContext?: (data: unknown) => void;
  /** Phase-2 AURA: tool start/end status pills ({name, phase}). */
  onTool?: (data: unknown) => void;
  /** Catch-all for unknown event names — used during the D6 transition so
   *  legacy `data: ...` frames without an `event:` tag still surface. */
  onUnknown?: (event: SseEvent) => void;
}

/**
 * Consume a tagged SSE stream from an async iterable of decoded text chunks.
 *
 * Backend emits frames like:
 *   event: chunk
 *   data: {"text": "..."}
 *
 *   event: done
 *   data: {"job_id": "..."}
 *
 *   event: error
 *   data: {"code": "...", "message": "..."}
 *
 * Legacy frames (`data: [DONE]`, bare `data: {"chunk": "..."}`) are still
 * recognized so the consumer works against both old + new backends during
 * the transition.
 */
export function consumeSse<TChunk = unknown, TDone = unknown>(
  source: ReadableStream<Uint8Array>,
  handlers: SseHandlers<TChunk, TDone>,
): Promise<void> {
  const reader = source.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  return (async () => {
    try {
      while (true) {
        const { value, done } = await reader.read();
        if (done) break;
        buffer += decoder.decode(value, { stream: true });

        // SSE frames are delimited by a blank line.
        let frameEnd: number;
        while ((frameEnd = buffer.indexOf("\n\n")) !== -1) {
          const frame = buffer.slice(0, frameEnd);
          buffer = buffer.slice(frameEnd + 2);
          handleFrame(frame, handlers);
        }
      }
    } finally {
      reader.releaseLock();
    }
  })();
}

function handleFrame<TChunk, TDone>(
  frame: string, handlers: SseHandlers<TChunk, TDone>,
): void {
  let eventName: string | null = null;
  let dataRaw = "";
  for (const line of frame.split("\n")) {
    if (line.startsWith("event:")) eventName = line.slice(6).trim();
    else if (line.startsWith("data:")) dataRaw += line.slice(5).trim();
  }
  if (!dataRaw && eventName === null) return;

  // Legacy completion sentinel.
  if (dataRaw === "[DONE]") {
    handlers.onDone?.(undefined as unknown as TDone);
    return;
  }

  let data: unknown = dataRaw;
  try {
    data = JSON.parse(dataRaw);
  } catch {
    /* keep dataRaw as string */
  }

  switch (eventName) {
    case "chunk":
      handlers.onChunk?.(data as TChunk);
      return;
    case "done":
      handlers.onDone?.(data as TDone);
      return;
    case "error":
      handlers.onError?.(data as { message: string; code?: string });
      return;
    case "context":
      handlers.onContext?.(data);
      return;
    case "tool":
      handlers.onTool?.(data);
      return;
    default:
      // Untagged frame (legacy): infer from payload shape.
      if (data && typeof data === "object") {
        const o = data as Record<string, unknown>;
        if (o.status === "done") {
          handlers.onDone?.(data as TDone);
          return;
        }
        if (o.status === "error") {
          handlers.onError?.({
            code: typeof o.code === "string" ? o.code : undefined,
            message: typeof o.message === "string" ? o.message : "Unknown error",
            details: o.details,
          });
          return;
        }
        if ("chunk" in o) {
          handlers.onChunk?.(o.chunk as TChunk);
          return;
        }
      }
      handlers.onUnknown?.({ event: eventName ?? "message", data });
  }
}

/** Convenience wrapper for `EventSource` against the JobStore SSE stream.
 *
 *  EventSource auto-reconnects on transport failures, which is what we want
 *  for the long-lived progress stream. Consumers register typed handlers and
 *  get back the EventSource instance for manual `.close()`. */
export function openProgressStream(
  jobId: string,
  handlers: SseHandlers,
  opts?: { unversioned?: boolean },
): EventSource {
  const path = `/jobs/${encodeURIComponent(jobId)}/progress`;
  const url = opts?.unversioned ? `${API_BASE_URL}${path}` : `${API_V1}${path}`;
  const es = new EventSource(url);

  // Named events (Plan 2 D6).
  es.addEventListener("chunk", (e) => handlers.onChunk?.(safeParse((e as MessageEvent).data)));
  es.addEventListener("done", (e) => handlers.onDone?.(safeParse((e as MessageEvent).data)));
  // The "error" listener fires for BOTH server-sent ``event: error`` frames
  // AND for native transport errors (server restart, connection blip).
  // Native transport errors arrive with no ``data`` payload and the
  // EventSource auto-reconnects (readyState === CONNECTING). Only surface
  // the error to the consumer when it's a real server-sent error frame.
  es.addEventListener("error", (e) => {
    const me = e as MessageEvent;
    if (!me.data) {
      // Transport blip — EventSource is already auto-reconnecting. Ignore
      // unless the connection is permanently closed (readyState === 2).
      if (es.readyState !== EventSource.CLOSED) return;
      handlers.onError?.({ message: "SSE connection closed" });
      return;
    }
    const data = safeParse(me.data);
    handlers.onError?.(
      data && typeof data === "object"
        ? data as { code?: string; message: string }
        : { message: "SSE connection error" },
    );
  });

  // Default/untagged frames (legacy backend).
  es.onmessage = (e) => {
    const data = safeParse(e.data);
    if (data && typeof data === "object") {
      const o = data as Record<string, unknown>;
      if (o.status === "done") handlers.onDone?.(data);
      else if (o.status === "error") handlers.onError?.({
        message: typeof o.message === "string" ? o.message : "Unknown error",
        code: typeof o.code === "string" ? o.code : undefined,
      });
      else handlers.onChunk?.(data);
    } else {
      handlers.onUnknown?.({ event: "message", data });
    }
  };

  return es;
}

function safeParse(raw: string): unknown {
  try { return JSON.parse(raw); } catch { return raw; }
}
