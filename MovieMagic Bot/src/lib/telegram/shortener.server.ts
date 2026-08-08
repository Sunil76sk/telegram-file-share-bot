// Server-only URL shortener client. Generic GET-based API
// (teraboxlinks / shrinkearn / gplinks compatible).
// Default URL template: ${SHORTENER_API_BASE}?api=${KEY}&url=${LONG_URL}&alias=${ALIAS?}
//
// Returns { ok: true, shortUrl } on success, or { ok: false, error } on failure.
// Never throws — callers should persist the result + status.

export type ShortenResult =
  | { ok: true; shortUrl: string }
  | { ok: false; error: string };

const TIMEOUT_MS = 8000;
const MAX_ATTEMPTS = 3;

function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function fetchWithTimeout(url: string, ms: number): Promise<Response> {
  const ctrl = new AbortController();
  const id = setTimeout(() => ctrl.abort(), ms);
  try {
    return await fetch(url, { signal: ctrl.signal });
  } finally {
    clearTimeout(id);
  }
}

function extractShortUrl(payload: unknown): string | null {
  if (typeof payload === "string") {
    const s = payload.trim();
    return /^https?:\/\//i.test(s) ? s : null;
  }
  if (payload && typeof payload === "object") {
    const obj = payload as Record<string, unknown>;
    // Common response shapes across AdLinkFly-style services
    const candidates = [
      obj.shortenedUrl,
      obj.shortened_url,
      obj.short,
      obj.shortUrl,
      obj.short_url,
      obj.url,
      (obj.data as Record<string, unknown> | undefined)?.url,
    ];
    for (const c of candidates) {
      if (typeof c === "string" && /^https?:\/\//i.test(c)) return c;
    }
    if (obj.status === "error" && typeof obj.message === "string") return null;
  }
  return null;
}

export async function shortenUrl(longUrl: string, alias?: string): Promise<ShortenResult> {
  const apiKey = process.env.SHORTENER_API_KEY;
  const apiBase = process.env.SHORTENER_API_BASE;
  if (!apiKey || !apiBase) {
    return { ok: false, error: "Shortener not configured (SHORTENER_API_KEY/BASE missing)" };
  }

  const params = new URLSearchParams({ api: apiKey, url: longUrl });
  if (alias) params.set("alias", alias);
  const reqUrl = `${apiBase}?${params.toString()}`;

  let lastError = "";
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    try {
      const res = await fetchWithTimeout(reqUrl, TIMEOUT_MS);
      const contentType = res.headers.get("content-type") ?? "";
      let payload: unknown;
      if (contentType.includes("application/json")) {
        payload = await res.json().catch(() => null);
      } else {
        payload = await res.text().catch(() => "");
      }

      if (res.status === 429) {
        lastError = `rate limited (429)`;
      } else if (res.status >= 500) {
        lastError = `upstream ${res.status}`;
      } else if (!res.ok) {
        lastError = `http ${res.status}: ${typeof payload === "string" ? payload.slice(0, 200) : JSON.stringify(payload).slice(0, 200)}`;
        // 4xx (other than 429) is not retried
        console.error(`[shortener] non-retryable error: ${lastError}`);
        return { ok: false, error: lastError };
      } else {
        const shortUrl = extractShortUrl(payload);
        if (shortUrl) {
          console.log(`[shortener] success attempt=${attempt} -> ${shortUrl}`);
          return { ok: true, shortUrl };
        }
        lastError = `unparseable response: ${typeof payload === "string" ? payload.slice(0, 200) : JSON.stringify(payload).slice(0, 200)}`;
        // Unparseable on a 200 is not retried — likely a config issue
        console.error(`[shortener] ${lastError}`);
        return { ok: false, error: lastError };
      }
    } catch (e: unknown) {
      lastError = e instanceof Error ? e.message : String(e);
      console.error(`[shortener] attempt=${attempt} network error: ${lastError}`);
    }

    if (attempt < MAX_ATTEMPTS) {
      await sleep(500 * Math.pow(2, attempt - 1)); // 500ms, 1s
    }
  }
  return { ok: false, error: lastError || "unknown shortener failure" };
}
