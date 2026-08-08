import { supabase } from "@/integrations/supabase/client";

function getClientData(opts?: any) {
  return opts?.data !== undefined ? opts.data : opts;
}

export const listPosts = async () => {
  const { data, error } = await supabase
    .from("channel_posts")
    .select("*")
    .order("created_at", { ascending: false })
    .limit(200);
  if (error) throw new Error(error.message);
  return data ?? [];
};

export const createPost = async (opts?: any) => {
  const data = getClientData(opts);
  const { data: userRes } = await supabase.auth.getUser();
  const { error, data: row } = await supabase
    .from("channel_posts")
    .insert({
      caption: data.caption,
      photo_url: data.photo_url ?? null,
      image_link_url: data.image_link_url ?? null,
      buttons: data.buttons ?? [],
      scheduled_at: data.scheduled_at ?? null,
      auto_repost_hours: data.auto_repost_hours ?? null,
      status: "pending",
      created_by: userRes?.user?.id ?? null,
    })
    .select("*")
    .single();
  if (error) throw new Error(error.message);
  return row;
};

export const updatePost = async (opts?: any) => {
  const data = getClientData(opts);
  const { id, ...patch } = data;
  const { error } = await supabase
    .from("channel_posts")
    .update(patch)
    .eq("id", id);
  if (error) throw new Error(error.message);
  return { ok: true };
};

export const cancelPost = async (opts?: any) => {
  const data = getClientData(opts);
  const { error } = await supabase
    .from("channel_posts")
    .update({ status: "cancelled" })
    .eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
};

export const deletePost = async (opts?: any) => {
  const data = getClientData(opts);
  const { error } = await supabase
    .from("channel_posts")
    .delete()
    .eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
};

export const sendPostNow = async (opts?: any) => {
  const data = getClientData(opts);
  const { error } = await supabase
    .from("channel_posts")
    .update({ status: "sent" })
    .eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
};

export const retryPost = sendPostNow;
