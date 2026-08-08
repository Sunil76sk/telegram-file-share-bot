// Lightweight structured logger. Server-safe (works in Workers).
type Level = "info" | "warn" | "error";

function emit(level: Level, scope: string, msg: string, meta?: Record<string, unknown>) {
  const payload = {
    t: new Date().toISOString(),
    level,
    scope,
    msg,
    ...(meta ?? {}),
  };
  const line = JSON.stringify(payload);
  if (level === "error") console.error(line);
  else if (level === "warn") console.warn(line);
  else console.log(line);
}

export const log = {
  info: (scope: string, msg: string, meta?: Record<string, unknown>) => emit("info", scope, msg, meta),
  warn: (scope: string, msg: string, meta?: Record<string, unknown>) => emit("warn", scope, msg, meta),
  error: (scope: string, msg: string, meta?: Record<string, unknown>) => emit("error", scope, msg, meta),
};

export function errMeta(e: unknown): Record<string, unknown> {
  if (e instanceof Error) return { error: e.message, stack: e.stack?.split("\n").slice(0, 4).join(" | ") };
  return { error: String(e) };
}
