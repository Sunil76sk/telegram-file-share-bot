import { createFileRoute } from "@tanstack/react-router";
import { tgSafe } from "@/lib/telegram/api";

export const Route = createFileRoute("/api/public/telegram/cleanup")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const secret = process.env.CLEANUP_SECRET;
        if (!secret) {
          return new Response("Server misconfigured", { status: 500 });
        }
        const provided = request.headers.get("x-cleanup-secret");
        if (provided === null) {
          return new Response("Missing x-cleanup-secret header", { status: 401 });
        }
        if (provided !== secret) {
          return new Response("Invalid cleanup secret", { status: 403 });
        }
        const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
        const { data, error } = await supabaseAdmin
          .from("scheduled_deletions")
          .select("id, chat_id, message_id")
          .lte("delete_at", new Date().toISOString())
          .limit(200);
        if (error) return Response.json({ ok: false, error: error.message }, { status: 500 });

        let deleted = 0;
        let failed = 0;
        for (const row of data ?? []) {
          const del = await tgSafe("deleteMessage", {
            chat_id: row.chat_id,
            message_id: row.message_id,
          });
          if (!del) {
            console.error(`[cleanup] failed to delete message ${row.message_id} in chat ${row.chat_id}`);
            failed++;
          }
          await supabaseAdmin.from("scheduled_deletions").delete().eq("id", row.id);
          deleted++;
        }
        return Response.json({ ok: true, deleted, failed });
      },
    },
  },
});
