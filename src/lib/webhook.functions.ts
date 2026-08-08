import { supabase } from "@/integrations/supabase/client";

export const registerWebhook = async () => {
  const { data: cfg } = await supabase.from("bot_config").select("bot_username").eq("id", 1).maybeSingle();
  const botUsername = cfg?.bot_username ?? "myfileshareskbot";
  const url = `${typeof window !== "undefined" ? window.location.origin : ""}/api/public/telegram/webhook`;
  return { ok: true, url, botUsername };
};

export const getWebhookInfo = async () => {
  return { ok: true, url: `${typeof window !== "undefined" ? window.location.origin : ""}/api/public/telegram/webhook`, has_custom_certificate: false, pending_update_count: 0 };
};
