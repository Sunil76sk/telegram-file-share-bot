import "dotenv/config";
import { handleUpdate } from "../src/routes/api/public/telegram/webhook";
import { tg } from "../src/lib/telegram/api";

async function runBot() {
  const token = process.env.TELEGRAM_API_KEY;
  if (!token) {
    console.error("❌ TELEGRAM_API_KEY is not set in .env!");
    process.exit(1);
  }

  console.log("🤖 Starting MovieMagic Telegram Bot (Long-Polling Mode)...");
  
  try {
    const me = await tg<{ username: string; first_name: string }>("getMe");
    console.log(`🤖 Connected to Telegram Bot: @${me.username} (${me.first_name})`);
    // Delete any active webhook to switch to long polling
    await tg("deleteWebhook", { drop_pending_updates: false });
    console.log(`✅ Webhook cleared for @${me.username}. Ready for updates!`);
  } catch (e) {
    console.warn("⚠️ Could not verify bot identity or clear webhook:", e);
  }

  let offset = 0;

  while (true) {
    try {
      const updates = (await tg("getUpdates", {
        offset,
        timeout: 30,
        allowed_updates: ["message", "callback_query", "edited_message"],
      })) as any[];

      if (Array.isArray(updates) && updates.length > 0) {
        for (const update of updates) {
          offset = update.update_id + 1;
          try {
            const sender = update.message?.from?.first_name || update.message?.from?.username || update.callback_query?.from?.first_name || "User";
            const text = update.message?.text || update.callback_query?.data || "(media/other)";
            console.log(`📩 [${sender}] sent: ${text}`);
            await handleUpdate(update);
            console.log(`✅ Handled update #${update.update_id}`);
          } catch (err) {
            console.error(`❌ Error processing update #${update.update_id}:`, err);
          }
        }
      }
    } catch (err: any) {
      if (String(err?.message || "").includes("409") || String(err?.message || "").includes("setWebhook")) {
        console.warn("⚠️ Webhook conflict detected. Re-clearing webhook to resume local long-polling...");
        try { await tg("deleteWebhook", { drop_pending_updates: false }); } catch {}
      } else {
        console.error("⚠️ Network / API error during polling, retrying in 5s...", err);
      }
      await new Promise((resolve) => setTimeout(resolve, 5000));
    }
  }
}

runBot().catch((err) => {
  console.error("Fatal bot error:", err);
  process.exit(1);
});
