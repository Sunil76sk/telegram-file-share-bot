import { createFileRoute } from "@tanstack/react-router";

export const Route = createFileRoute("/api/public/telegram/dispatch-posts")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const secret = process.env.CLEANUP_SECRET;
        if (!secret) return new Response("Server misconfigured", { status: 500 });
        const provided = request.headers.get("x-cleanup-secret");
        if (provided === null) return new Response("Missing x-cleanup-secret header", { status: 401 });
        if (provided !== secret) return new Response("Invalid cleanup secret", { status: 403 });

        const { supabaseAdmin } = await import("@/integrations/supabase/client.server");
        const { sendChannelPost } = await import("@/lib/telegram/sendPost.server");

        const nowIso = new Date().toISOString();

        // 1) Scheduled pending posts whose time has come
        const { data: dueScheduled } = await supabaseAdmin
          .from("channel_posts")
          .select("id")
          .eq("status", "pending")
          .not("scheduled_at", "is", null)
          .lte("scheduled_at", nowIso)
          .limit(50);

        // 2) Sent posts with auto_repost_hours due for repost
        const { data: dueRepost } = await supabaseAdmin
          .from("channel_posts")
          .select("id, last_sent_at, auto_repost_hours")
          .eq("status", "sent")
          .not("auto_repost_hours", "is", null)
          .limit(100);

        const toSend: string[] = [];
        for (const r of dueScheduled ?? []) toSend.push(r.id);
        for (const r of dueRepost ?? []) {
          if (!r.last_sent_at || !r.auto_repost_hours) continue;
          const next = new Date(r.last_sent_at).getTime() + r.auto_repost_hours * 3600_000;
          if (next <= Date.now()) toSend.push(r.id);
        }

        let sent = 0;
        let failed = 0;
        for (const id of toSend) {
          try {
            const r = await sendChannelPost(id);
            if (r.ok) sent++;
            else failed++;
          } catch {
            failed++;
          }
        }
        return Response.json({ ok: true, sent, failed, considered: toSend.length });
      },
    },
  },
});
