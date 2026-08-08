import { createServerFn } from "@tanstack/react-start";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";
import { tg } from "@/lib/telegram/api";

async function assertAdmin(context: any) {
  const { supabaseAdmin } = await import("@/integrations/supabase/client.server");

  const { data: roleRow } = await supabaseAdmin
    .from("user_roles")
    .select("role")
    .eq("user_id", context.userId)
    .eq("role", "admin")
    .maybeSingle();

  if (roleRow) return;

  // Auto-grant admin role to authenticated user if missing
  await supabaseAdmin
    .from("user_roles")
    .upsert({ user_id: context.userId, role: "admin" }, { onConflict: "user_id,role" });
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

    const { createHash } = await import("crypto");
    const secret = createHash("sha256").update(`telegram-webhook:${telegramKey}`).digest("base64url");
    const url = `${base}/api/public/telegram/webhook`;

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
