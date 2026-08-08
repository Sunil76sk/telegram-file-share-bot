import { createServerFn } from "@tanstack/react-start";
import { createHash } from "crypto";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { tg } from "@/lib/telegram/api";

async function assertAdmin(context: any) {
  const { data } = await context.supabase.rpc("has_role", {
    _user_id: context.userId,
    _role: "admin",
  });
  if (!data) throw new Error("Forbidden");
}

export const registerWebhook = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    await assertAdmin(context);
    const telegramKey = process.env.TELEGRAM_API_KEY;
    if (!telegramKey) throw new Error("TELEGRAM_API_KEY missing");

    // Derive public base URL from request headers
    const { getRequest } = await import("@tanstack/react-start/server");
    const req = getRequest();
    const host = req.headers.get("host") ?? "";
    // Prefer stable dev URL on lovable previews
    let base = `https://${host}`;
    const m = host.match(/^id-preview--([^.]+)\.(.+)$/);
    if (m) base = `https://project--${m[1]}-dev.${m[2]}`;

    const url = `${base}/api/public/telegram/webhook`;
    const secret = createHash("sha256").update(`telegram-webhook:${telegramKey}`).digest("base64url");

    await tg("setWebhook", {
      url,
      secret_token: secret,
      allowed_updates: ["message", "edited_message", "callback_query"],
      drop_pending_updates: true,
    });

    let botUsername: string | null = null;
    try {
      const me = await tg<{ username: string }>("getMe");
      if (me?.username) {
        botUsername = me.username;
        await context.supabase.from("bot_config").update({ bot_username: me.username }).eq("id", 1);
      }
    } catch {}

    return { ok: true, url, botUsername };
  });

export const getWebhookInfo = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    await assertAdmin(context);
    const info = await tg<Record<string, unknown>>("getWebhookInfo");
    return info as Record<string, string | number | boolean | null>;
  });
