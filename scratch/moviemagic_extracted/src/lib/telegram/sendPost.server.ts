// Server-only helper: send a channel_posts row to the configured main channel.
// Layout matches competitor: caption ABOVE, large square-ish image BELOW,
// image is clickable (opens image_link_url or the image itself).
import { tg } from "@/lib/telegram/api";
import { supabaseAdmin } from "@/integrations/supabase/client.server";

type Button = { text: string; url: string };

export async function sendChannelPost(id: string) {
  const { data: post, error } = await supabaseAdmin
    .from("channel_posts")
    .select("*")
    .eq("id", id)
    .single();
  if (error || !post) throw new Error(error?.message ?? "Post not found");

  const { data: cfg } = await supabaseAdmin
    .from("bot_config")
    .select("main_channel_id")
    .eq("id", 1)
    .single();
  const chatId = cfg?.main_channel_id;
  if (!chatId) {
    await supabaseAdmin
      .from("channel_posts")
      .update({ status: "failed", error: "main_channel_id not configured" })
      .eq("id", id);
    throw new Error("main_channel_id not configured");
  }

  const p = post as typeof post & { image_link_url?: string | null };
  const buttons = (p.buttons ?? []) as Button[];
  const inline_keyboard = buttons.length
    ? buttons.map((b) => [{ text: b.text, url: b.url }])
    : undefined;

  try {
    let result: { message_id: number };

    if (p.photo_url) {
      // Use sendMessage + link preview so the caption sits ABOVE the image.
      // The image is clickable and opens image_link_url (fallback: the image itself).
      const clickUrl = (p.image_link_url && p.image_link_url.trim()) || p.photo_url;
      // Embed an invisible anchor (no newline) so Telegram has a URL to preview
      // without adding any visible gap to the user's caption.
      const text = `${p.caption}<a href="${escapeHtml(p.photo_url)}">\u200b</a>`;
      result = await tg<{ message_id: number }>("sendMessage", {
        chat_id: chatId,
        text,
        parse_mode: "HTML",
        link_preview_options: {
          is_disabled: false,
          url: clickUrl,
          prefer_large_media: true,
          show_above_text: false,
        },
        ...(inline_keyboard ? { reply_markup: { inline_keyboard } } : {}),
      });
    } else {
      result = await tg<{ message_id: number }>("sendMessage", {
        chat_id: chatId,
        text: p.caption,
        parse_mode: "HTML",
        link_preview_options: { is_disabled: true },
        ...(inline_keyboard ? { reply_markup: { inline_keyboard } } : {}),
      });
    }

    await supabaseAdmin
      .from("channel_posts")
      .update({
        status: "sent",
        telegram_message_id: result.message_id,
        last_sent_at: new Date().toISOString(),
        error: null,
      })
      .eq("id", id);
    return { ok: true as const, message_id: result.message_id };
  } catch (e) {
    const msg = e instanceof Error ? e.message : String(e);
    await supabaseAdmin
      .from("channel_posts")
      .update({ status: "failed", error: msg.slice(0, 500) })
      .eq("id", id);
    return { ok: false as const, error: msg };
  }
}

function escapeHtml(s: string) {
  return s.replace(/&/g, "&amp;").replace(/</g, "&lt;").replace(/>/g, "&gt;").replace(/"/g, "&quot;");
}
