import { createServerFn } from "@tanstack/react-start";
import { z } from "zod";
import { requireSupabaseAuth } from "@/integrations/supabase/auth-middleware";

async function assertAdmin(context: any) {
  const { data, error } = await context.supabase.rpc("has_role", {
    _user_id: context.userId,
    _role: "admin",
  });
  if (error || !data) throw new Error("Forbidden");
}

const ButtonSchema = z.object({
  text: z.string().trim().min(1).max(64),
  url: z.string().url().max(2048),
});

const PostInputSchema = z.object({
  caption: z.string().trim().min(1).max(4096),
  photo_url: z.string().url().max(2048).nullable().optional(),
  image_link_url: z.string().url().max(2048).nullable().optional(),
  buttons: z.array(ButtonSchema).max(16).default([]),
  scheduled_at: z.string().datetime().nullable().optional(),
  auto_repost_hours: z.number().int().min(1).max(720).nullable().optional(),
});

export const listPosts = createServerFn({ method: "GET" })
  .middleware([requireSupabaseAuth])
  .handler(async ({ context }) => {
    await assertAdmin(context);
    const { data, error } = await context.supabase
      .from("channel_posts")
      .select("*")
      .order("created_at", { ascending: false })
      .limit(200);
    if (error) throw new Error(error.message);
    return data ?? [];
  });

export const createPost = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => PostInputSchema.parse(d))
  .handler(async ({ data, context }) => {
    await assertAdmin(context);
    const { error, data: row } = await context.supabase
      .from("channel_posts")
      .insert({
        caption: data.caption,
        photo_url: data.photo_url ?? null,
        image_link_url: data.image_link_url ?? null,
        buttons: data.buttons,
        scheduled_at: data.scheduled_at ?? null,
        auto_repost_hours: data.auto_repost_hours ?? null,
        status: "pending",
        created_by: context.userId,
      })
      .select("*")
      .single();
    if (error) throw new Error(error.message);
    return row;
  });

export const updatePost = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) =>
    PostInputSchema.partial().extend({ id: z.string().uuid() }).parse(d),
  )
  .handler(async ({ data, context }) => {
    await assertAdmin(context);
    const { id, ...patch } = data;
    const { error } = await context.supabase
      .from("channel_posts")
      .update(patch)
      .eq("id", id);
    if (error) throw new Error(error.message);
    return { ok: true };
  });

export const cancelPost = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ id: z.string().uuid() }).parse(d))
  .handler(async ({ data, context }) => {
    await assertAdmin(context);
    const { error } = await context.supabase
      .from("channel_posts")
      .update({ status: "cancelled" })
      .eq("id", data.id);
    if (error) throw new Error(error.message);
    return { ok: true };
  });

export const deletePost = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ id: z.string().uuid() }).parse(d))
  .handler(async ({ data, context }) => {
    await assertAdmin(context);
    const { error } = await context.supabase
      .from("channel_posts")
      .delete()
      .eq("id", data.id);
    if (error) throw new Error(error.message);
    return { ok: true };
  });

export const sendPostNow = createServerFn({ method: "POST" })
  .middleware([requireSupabaseAuth])
  .inputValidator((d) => z.object({ id: z.string().uuid() }).parse(d))
  .handler(async ({ data, context }) => {
    await assertAdmin(context);
    const { sendChannelPost } = await import("@/lib/telegram/sendPost.server");
    return await sendChannelPost(data.id);
  });

export const retryPost = sendPostNow;
