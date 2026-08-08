// Telegram Bot API wrapper via Lovable connector gateway.
// Server-only. Includes retry + structured logging (Milestone 4 hardening).
import { log, errMeta } from "@/lib/logger";

const GATEWAY = "https://connector-gateway.lovable.dev/telegram";
const MAX_ATTEMPTS = 3;
const BASE_DELAY_MS = 400;
const REQ_TIMEOUT_MS = 12_000;

const sleep = (ms: number) => new Promise((r) => setTimeout(r, ms));

function shouldRetry(status: number) {
  return status === 429 || status === 408 || status >= 500;
}

export async function tg<T = unknown>(
  method: string,
  body?: Record<string, unknown>,
): Promise<T> {
  const lovableKey = process.env.LOVABLE_API_KEY;
  const telegramKey = process.env.TELEGRAM_API_KEY;
  if (!lovableKey) throw new Error("LOVABLE_API_KEY missing");
  if (!telegramKey) throw new Error("TELEGRAM_API_KEY missing");

  let lastErr: unknown = null;
  for (let attempt = 1; attempt <= MAX_ATTEMPTS; attempt++) {
    const controller = new AbortController();
    const timer = setTimeout(() => controller.abort(), REQ_TIMEOUT_MS);
    try {
      const res = await fetch(`${GATEWAY}/${method}`, {
        method: "POST",
        headers: {
          Authorization: `Bearer ${lovableKey}`,
          "X-Connection-Api-Key": telegramKey,
          "Content-Type": "application/json",
        },
        body: JSON.stringify(body ?? {}),
        signal: controller.signal,
      });
      const data = (await res.json().catch(() => ({}))) as {
        ok?: boolean;
        result?: T;
        description?: string;
        parameters?: { retry_after?: number };
      };

      if (res.ok && data.ok) return data.result as T;

      const desc = data.description ?? `HTTP ${res.status}`;
      if (attempt < MAX_ATTEMPTS && shouldRetry(res.status)) {
        const retryAfter = data.parameters?.retry_after;
        const delay = retryAfter ? retryAfter * 1000 : BASE_DELAY_MS * 2 ** (attempt - 1);
        log.warn("tg", `retry ${method}`, { attempt, status: res.status, desc, delay });
        await sleep(delay);
        continue;
      }
      throw new Error(`Telegram ${method} failed [${res.status}]: ${desc}`);
    } catch (e) {
      lastErr = e;
      const isAbort = e instanceof Error && e.name === "AbortError";
      if (attempt < MAX_ATTEMPTS && (isAbort || (e as any)?.code === "ECONNRESET")) {
        log.warn("tg", `retry ${method} (network)`, { attempt, ...errMeta(e) });
        await sleep(BASE_DELAY_MS * 2 ** (attempt - 1));
        continue;
      }
      if (attempt >= MAX_ATTEMPTS) break;
    } finally {
      clearTimeout(timer);
    }
  }
  log.error("tg", `failed ${method}`, errMeta(lastErr));
  throw lastErr instanceof Error ? lastErr : new Error(String(lastErr));
}

export async function tgSafe<T = unknown>(
  method: string,
  body?: Record<string, unknown>,
): Promise<T | null> {
  try {
    return await tg<T>(method, body);
  } catch (e) {
    log.error("tgSafe", method, errMeta(e));
    return null;
  }
}
