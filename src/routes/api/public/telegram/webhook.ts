import { createFileRoute } from "@tanstack/react-router";
import { tg, tgSafe } from "@/lib/telegram/api";
import { log, errMeta } from "@/lib/logger";

function expectedSecret(key: string) {
  if (typeof window !== "undefined") return "";
  const { createHash } = require("crypto");
  return createHash("sha256").update(`telegram-webhook:${key}`).digest("base64url");
}

function safeEqual(a: string, b: string) {
  if (typeof window !== "undefined") return false;
  const { timingSafeEqual } = require("crypto");
  const A = Buffer.from(a);
  const B = Buffer.from(b);
  return A.length === B.length && timingSafeEqual(A, B);
}

type BotConfig = {
  main_channel_id: number | null;
  main_channel_username: string | null;
  backup_join_channel_id: number | null;
  backup_join_channel_username: string | null;
  storage_chat_id: number | null;
  backup_storage_chat_id: number | null;
  admin_telegram_ids: number[];
  bot_username: string | null;
};

const UPLOAD_STEPS = [
  "awaiting_file",
  "awaiting_series_episode", // legacy — still handled for in-flight sessions
] as const;
type UploadStep = (typeof UPLOAD_STEPS)[number];


const EPISODES_PER_PAGE = 20;

// Extract any Telegram media object from a message. Supports all common types.
function extractMedia(
  msg: any,
): { file_id: string; file_unique_id: string; file_size?: number; file_name?: string } | null {
  if (msg.video) return msg.video;
  if (msg.document) return msg.document;
  if (msg.audio) return msg.audio;
  if (msg.animation) return msg.animation;
  if (msg.voice) return msg.voice;
  if (msg.video_note) return msg.video_note;
  if (Array.isArray(msg.photo) && msg.photo.length) return msg.photo[msg.photo.length - 1];
  return null;
}

export const Route = createFileRoute("/api/public/telegram/webhook")({
  server: {
    handlers: {
      POST: async ({ request }) => {
        const telegramKey = process.env.TELEGRAM_API_KEY;
        if (!telegramKey) return new Response("misconfigured", { status: 500 });

        const headerSecret = request.headers.get("X-Telegram-Bot-Api-Secret-Token") ?? "";
        if (!safeEqual(headerSecret, expectedSecret(telegramKey))) {
          return new Response("Unauthorized", { status: 401 });
        }

        const update = (await request.json()) as any;
        try {
          await handleUpdate(update);
        } catch (e) {
          log.error("webhook", "handleUpdate failed", {
            ...errMeta(e),
            update_id: update?.update_id,
          });
        }
        return Response.json({ ok: true });

      },
    },
  },
});

export async function handleUpdate(update: any) {
  try {
    const { supabaseAdmin } = await import("@/integrations/supabase/client.server");

    const cfgRes = await supabaseAdmin.from("bot_config").select("*").eq("id", 1).maybeSingle();
    const cfg = (cfgRes.data ?? {}) as Partial<BotConfig>;

    if (!cfg.storage_chat_id) {
      cfg.storage_chat_id = -1003931975466;
      cfg.main_channel_id = cfg.main_channel_id ?? -1002471479640;
      cfg.backup_join_channel_id = cfg.backup_join_channel_id ?? -1001565776206;
      cfg.backup_join_channel_username = cfg.backup_join_channel_username ?? "kannadanewmovie_sk";
      cfg.backup_storage_chat_id = cfg.backup_storage_chat_id ?? -1003650568162;
      cfg.bot_username = cfg.bot_username ?? "myfileshareskbot";
      await supabaseAdmin.from("bot_config").upsert({
        id: 1,
        storage_chat_id: cfg.storage_chat_id,
        main_channel_id: cfg.main_channel_id,
        backup_join_channel_id: cfg.backup_join_channel_id,
        backup_join_channel_username: cfg.backup_join_channel_username,
        backup_storage_chat_id: cfg.backup_storage_chat_id,
        bot_username: cfg.bot_username,
      }, { onConflict: "id" });
    }

  const msg = update.message ?? update.edited_message;
  const cb = update.callback_query;

  if (cb) return handleCallback(cb, cfg, supabaseAdmin);
  if (!msg) return;

  const chatId = msg.chat?.id;
  const fromId = msg.from?.id as number | undefined;
  if (!chatId || !fromId) return;

  try {
    await supabaseAdmin.from("profiles").upsert(
      {
        telegram_user_id: fromId,
        username: msg.from?.username ?? null,
        first_name: msg.from?.first_name ?? null,
        last_seen_at: new Date().toISOString(),
      },
      { onConflict: "telegram_user_id" },
    );
  } catch (e) {
    console.warn("⚠️ Could not upsert profile:", e);
  }

  const rawText: string = msg.text ?? msg.caption ?? "";
  const text = rawText.replace(/^(\/[A-Za-z0-9_]+)@\w+/, "$1");
  const envAdmins = (process.env.ADMIN_IDS ?? "").split(",").map((s) => Number(s.trim())).filter((n) => !isNaN(n) && n > 0);
  const cfgAdmins = (cfg.admin_telegram_ids ?? []).map(Number);
  const isAdmin = envAdmins.includes(Number(fromId)) || cfgAdmins.includes(Number(fromId));

  if (envAdmins.includes(Number(fromId)) && !cfgAdmins.includes(Number(fromId))) {
    const updatedAdmins = Array.from(new Set([...cfgAdmins, Number(fromId)]));
    await supabaseAdmin.from("bot_config").update({ admin_telegram_ids: updatedAdmins }).eq("id", 1);
  }

  // Unified batch upload: /upload, /uploadmovie, /uploadseries all behave the same.
  const uploadMatch = text.match(/^\/(upload|uploadmovie|uploadseries)(?:\s+(.+))?$/);
  if (uploadMatch || text === "/cancel" || text === "/done") {
    // Note: /done is handled below inside the session block, not here.
  }
  if (uploadMatch) {
    await supabaseAdmin.from("upload_sessions").delete().eq("telegram_user_id", fromId);
    if (!isAdmin) {
      return tg("sendMessage", { chat_id: chatId, text: `❌ Admins only. Your Telegram ID is ${fromId}.` });
    }
    if (!cfg.storage_chat_id) {
      return tg("sendMessage", {
        chat_id: chatId,
        text: "⚠️ Storage channel not configured. Set it in the admin dashboard first.",
      });
    }
    const title = (uploadMatch[2] ?? "").trim();
    if (!title) {
      return tg("sendMessage", {
        chat_id: chatId,
        text: "Usage: `/upload <Title>`\n\nExample: `/upload Breaking Bad S01`\n\nThen send one or more files (video, document, audio, photo — any type). Send /done when finished.",
        parse_mode: "Markdown",
      });
    }
    const ins = await supabaseAdmin
      .from("movies")
      .insert({
        title,
        content_type: "series", // reused as batch container
        created_by_telegram_id: fromId,
        shortener_status: "pending",
      })
      .select("id")
      .single();
    if (ins.error) {
      return tg("sendMessage", { chat_id: chatId, text: `❌ Save failed: ${ins.error.message}` });
    }
    await supabaseAdmin.from("upload_sessions").upsert({
      telegram_user_id: fromId,
      step: "awaiting_series_episode" satisfies UploadStep,
      draft: { kind: "batch", series_id: ins.data.id, title },
    });
    return tg("sendMessage", {
      chat_id: chatId,
      text: `📦 Batch *${title}* started.\n\nSend any files (video, document, audio, photo, animation, voice) in order. Send /done when finished, or /cancel to abort.`,
      parse_mode: "Markdown",
    });
  }

  if (text === "/cancel") {
    await supabaseAdmin.from("upload_sessions").delete().eq("telegram_user_id", fromId);
    return tg("sendMessage", { chat_id: chatId, text: "✅ Cancelled." });
  }


  if (isAdmin) {
    const sessRes = await supabaseAdmin
      .from("upload_sessions")
      .select("*")
      .eq("telegram_user_id", fromId)
      .maybeSingle();
    const sess = sessRes.data;
    if (sess) {
      if (text === "/done") {
        return finalizeSeries(chatId, fromId, sess, cfg, supabaseAdmin);
      }
      const handled = await advanceUpload(msg, sess, cfg, supabaseAdmin);
      if (handled) return;
    }
  }

  if (text.startsWith("/start")) {
    console.log(`🚀 Replying to /start from user ${fromId}...`);
    const parts = text.split(" ");
    const payload = parts[1]?.trim();
    if (payload) {
      // Deep link payload format: <movieId>  or  <movieId>_<source>
      const [movieId, source] = payload.split("_", 2);
      return showMovie(chatId, fromId, movieId!, cfg, supabaseAdmin, source ?? null);
    }
    const res = await tg("sendMessage", {
      chat_id: chatId,
      text:
        "👋 Welcome to the Movie Bot!\n\nUse a movie link from our Instagram to get started, or contact an admin.",
    });
    console.log("✅ Sent /start reply cleanly:", res);
    return res;
  }

  if (text === "/stats" && isAdmin) {
    const [{ count: movies }, { count: users }, { count: downloads }, { count: episodes }] = await Promise.all([
      supabaseAdmin.from("movies").select("*", { count: "exact", head: true }),
      supabaseAdmin.from("profiles").select("*", { count: "exact", head: true }),
      supabaseAdmin.from("downloads").select("*", { count: "exact", head: true }),
      supabaseAdmin.from("series_episodes").select("*", { count: "exact", head: true }),
    ]);
    return tg("sendMessage", {
      chat_id: chatId,
      text: `📊 Stats\n\n🎬 Movies/Series: ${movies ?? 0}\n📺 Episodes: ${episodes ?? 0}\n👥 Users: ${users ?? 0}\n⬇️ Downloads: ${downloads ?? 0}`,
    });
  }

  if (text === "/myid") {
    console.log(`🚀 Replying to /myid from user ${fromId}...`);
    return tg("sendMessage", { chat_id: chatId, text: `Your Telegram ID: \`${fromId}\``, parse_mode: "Markdown" });
  }
  } catch (err) {
    console.error("❌ Error inside handleUpdate:", err);
  }
}

async function advanceUpload(
  msg: any,
  sess: any,
  cfg: Partial<BotConfig>,
  supabaseAdmin: any,
): Promise<boolean> {
  const chatId = msg.chat.id;
  const fromId = msg.from.id;
  const draft = sess.draft ?? {};
  const step = sess.step as UploadStep;
  const text: string = (msg.text ?? "").trim();

  if (text === "/cancel" || text === "/done") return false;

  const save = async (next: UploadStep | null, patch: Record<string, unknown>) => {
    Object.assign(draft, patch);
    if (next) {
      await supabaseAdmin
        .from("upload_sessions")
        .update({ step: next, draft })
        .eq("telegram_user_id", fromId);
    } else {
      await supabaseAdmin
        .from("upload_sessions")
        .update({ draft })
        .eq("telegram_user_id", fromId);
    }
  };

  // Unified batch upload: accept any Telegram media type, add to series_episodes.
  const seriesId = draft.series_id as string | undefined;
  if (!seriesId) {
    await supabaseAdmin.from("upload_sessions").delete().eq("telegram_user_id", fromId);
    await tg("sendMessage", { chat_id: chatId, text: "❌ Session invalid. Start again with /upload <Title>." });
    return true;
  }

  const media = extractMedia(msg);
  if (!media) {
    await tg("sendMessage", {
      chat_id: chatId,
      text: "Send a file (video, document, audio, photo, animation, voice) or /done to finish.",
    });
    return true;
  }

  // Dedup within this batch by file_unique_id
  const dup = await supabaseAdmin
    .from("series_episodes")
    .select("id,episode_number")
    .eq("movie_id", seriesId)
    .eq("file_unique_id", media.file_unique_id)
    .maybeSingle();
  if (dup.data) {
    await tg("sendMessage", {
      chat_id: chatId,
      text: `⚠️ Already added as #${dup.data.episode_number}.`,
    });
    return true;
  }

  const season = 1;
  const { data: lastEp } = await supabaseAdmin
    .from("series_episodes")
    .select("episode_number")
    .eq("movie_id", seriesId)
    .eq("season_number", season)
    .order("episode_number", { ascending: false })
    .limit(1)
    .maybeSingle();
  const episode = (lastEp?.episode_number ?? 0) + 1;
  const epTitle = (msg.caption ?? "").trim() || (media as any).file_name || null;

  const storageChat = cfg.storage_chat_id!;
  const stored = await tgSafe<{ message_id: number }>("copyMessage", {
    chat_id: storageChat,
    from_chat_id: chatId,
    message_id: msg.message_id,
  });
  if (!stored) {
    await tg("sendMessage", {
      chat_id: chatId,
      text: `❌ Cannot copy file to Storage Channel (${storageChat}).\n\n👉 Please make sure *@myfileshareskbot* is added as an **Administrator** (with Post Messages permission) inside your Telegram Storage Channel!`,
      parse_mode: "Markdown",
    });
    return true;
  }
  const insEp = await supabaseAdmin.from("series_episodes").insert({
    movie_id: seriesId,
    season_number: season,
    episode_number: episode,
    title: epTitle,
    file_id: media.file_id,
    file_unique_id: media.file_unique_id,
    file_size: media.file_size ?? null,
    storage_chat_id: storageChat,
    storage_message_id: stored.message_id,
  });
  if (insEp.error) {
    await tg("sendMessage", { chat_id: chatId, text: `❌ Save failed: ${insEp.error.message}` });
    return true;
  }
  const { count } = await supabaseAdmin
    .from("series_episodes")
    .select("*", { count: "exact", head: true })
    .eq("movie_id", seriesId);
  await tg("sendMessage", {
    chat_id: chatId,
    text: `✅ File #${episode} saved${epTitle ? ` — ${epTitle}` : ""}. (${count ?? "?"} total)\n\nSend another or /done.`,
  });
  return true;
}

function parseEpisodeCaption(caption: string): { season: number; episode: number; title: string | null } | null {
  if (!caption) return null;
  const m = caption.match(/^\s*S(\d{1,3})\s*[Ee](\d{1,4})\b[\s\-_:.]*(.*)$/i);
  if (!m) return null;
  const season = parseInt(m[1]!, 10);
  const episode = parseInt(m[2]!, 10);
  if (!season || season > 100 || !episode || episode > 1000) return null;
  const title = (m[3] ?? "").trim() || null;
  return { season, episode, title };
}

async function finalizeSeries(
  chatId: number,
  fromId: number,
  sess: any,
  cfg: Partial<BotConfig>,
  supabaseAdmin: any,
) {
  const seriesId = sess.draft?.series_id as string | undefined;
  await supabaseAdmin.from("upload_sessions").delete().eq("telegram_user_id", fromId);
  if (!seriesId) {
    return tg("sendMessage", { chat_id: chatId, text: "⚠️ No series in progress." });
  }
  const { count } = await supabaseAdmin
    .from("series_episodes")
    .select("*", { count: "exact", head: true })
    .eq("movie_id", seriesId);
  const { data: series } = await supabaseAdmin
    .from("movies")
    .select("title,rating")
    .eq("id", seriesId)
    .single();
  await finalizeWithShortener(chatId, seriesId, series?.title ?? "Series", series?.rating ?? 0, cfg, supabaseAdmin, "series", count ?? 0);
}

async function finalizeWithShortener(
  chatId: number,
  movieId: string,
  title: string,
  rating: number,
  cfg: Partial<BotConfig>,
  supabaseAdmin: any,
  kind: "movie" | "series",
  episodeCount = 0,
) {
  const botUser = cfg.bot_username ?? "your_bot";
  const deepLink = `https://t.me/${botUser}?start=${movieId}`;
  await supabaseAdmin
    .from("movies")
    .update({ deep_link: deepLink, shortener_status: "pending" })
    .eq("id", movieId);

  const header = kind === "series"
    ? `🎉 Series saved!\n\n📺 ${title}\n📦 ${episodeCount} episode(s)\n⭐ ${rating}/10`
    : `🎉 Movie added!\n\n🎬 ${title}\n⭐ ${rating}/10`;
  await tg("sendMessage", {
    chat_id: chatId,
    text: `${header}\n\n🔗 Deep link:\n${deepLink}\n\nGenerate a short URL now, or skip.`,
    disable_web_page_preview: true,
    reply_markup: {
      inline_keyboard: [[
        { text: "🔗 Generate short URL", callback_data: `gen:${movieId}` },
        { text: "⏭ Skip", callback_data: `skip:${movieId}` },
      ]],
    },
  });
}

async function generateShortNow(
  chatId: number,
  messageId: number | undefined,
  movieId: string,
  supabaseAdmin: any,
) {
  const { data: row } = await supabaseAdmin
    .from("movies")
    .select("deep_link")
    .eq("id", movieId)
    .single();
  const deepLink = row?.deep_link;
  if (!deepLink) {
    return tg("sendMessage", { chat_id: chatId, text: "⚠️ No deep link found for this item." });
  }
  await tg("sendMessage", { chat_id: chatId, text: "⏳ Generating short URL…" });
  let text: string;
  try {
    const { shortenUrl } = await import("@/lib/telegram/shortener.server");
    const result = await shortenUrl(deepLink);
    if (result.ok) {
      await supabaseAdmin
        .from("movies")
        .update({ short_url: result.shortUrl, shortener_status: "success", shortener_last_error: null })
        .eq("id", movieId);
      text = `🔗 Short URL:\n${result.shortUrl}`;
    } else {
      await supabaseAdmin
        .from("movies")
        .update({ shortener_status: "failed", shortener_last_error: result.error.slice(0, 500) })
        .eq("id", movieId);
      text = `⚠️ Shortener failed: ${result.error.slice(0, 200)}`;
    }
  } catch (e) {
    console.error("[shortener] inline error:", e);
    text = "⚠️ Shortener error. Try again from admin dashboard.";
  }
  await tg("sendMessage", { chat_id: chatId, text, disable_web_page_preview: true });
  if (messageId) {
    await tgSafe("editMessageReplyMarkup", { chat_id: chatId, message_id: messageId, reply_markup: { inline_keyboard: [] } });
  }
}


async function handleCallback(cb: any, cfg: Partial<BotConfig>, supabaseAdmin: any) {
  const data: string = cb.data ?? "";
  const chatId = cb.message?.chat?.id;
  const userId = cb.from?.id;
  if (!chatId || !userId) return;

  if (data.startsWith("check:")) {
    const movieId = data.slice("check:".length);
    await tgSafe("answerCallbackQuery", { callback_query_id: cb.id, text: "Checking..." });
    return showMovie(chatId, userId, movieId, cfg, supabaseAdmin);
  }
  if (data.startsWith("gen:")) {
    const movieId = data.slice("gen:".length);
    await tgSafe("answerCallbackQuery", { callback_query_id: cb.id, text: "Generating…" });
    return generateShortNow(chatId, cb.message?.message_id, movieId, supabaseAdmin);
  }
  if (data.startsWith("skip:")) {
    const movieId = data.slice("skip:".length);
    await tgSafe("answerCallbackQuery", { callback_query_id: cb.id, text: "Skipped" });
    await supabaseAdmin
      .from("movies")
      .update({ shortener_status: "disabled" })
      .eq("id", movieId);
    if (cb.message?.message_id) {
      await tgSafe("editMessageReplyMarkup", {
        chat_id: chatId,
        message_id: cb.message.message_id,
        reply_markup: { inline_keyboard: [] },
      });
    }
    return tg("sendMessage", { chat_id: chatId, text: "⏭ Skipped short URL. You can generate it later from the admin dashboard." });
  }
  if (data.startsWith("dl:")) {
    const movieId = data.slice("dl:".length);
    await tgSafe("answerCallbackQuery", { callback_query_id: cb.id });
    return deliverMovie(chatId, userId, movieId, cfg, supabaseAdmin);
  }
  if (data.startsWith("season:")) {
    // season:<movieId>:<n>  OR  season:<movieId> (list seasons)
    const rest = data.slice("season:".length);
    const parts = rest.split(":");
    const movieId = parts[0]!;
    await tgSafe("answerCallbackQuery", { callback_query_id: cb.id });
    if (parts.length === 1) return showSeasonPicker(chatId, movieId, supabaseAdmin);
    const season = parseInt(parts[1]!, 10);
    return showEpisodeList(chatId, movieId, season, 0, supabaseAdmin);
  }
  if (data.startsWith("epi:")) {
    // epi:<movieId>:<season>:<page>
    const parts = data.slice("epi:".length).split(":");
    const movieId = parts[0]!;
    const season = parseInt(parts[1]!, 10);
    const page = parseInt(parts[2] ?? "0", 10);
    await tgSafe("answerCallbackQuery", { callback_query_id: cb.id });
    return showEpisodeList(chatId, movieId, season, page, supabaseAdmin);
  }
  if (data.startsWith("epdl:")) {
    const epId = data.slice("epdl:".length);
    await tgSafe("answerCallbackQuery", { callback_query_id: cb.id });
    return deliverEpisode(chatId, userId, epId, cfg, supabaseAdmin);
  }
}

async function isJoined(channelId: number, userId: number): Promise<boolean> {
  const res = await tgSafe<{ status: string }>("getChatMember", {
    chat_id: channelId,
    user_id: userId,
  });
  if (!res) return false;
  return ["member", "administrator", "creator", "restricted"].includes(res.status);
}

async function channelJoinUrl(
  channelId: number,
  username: string | null | undefined,
): Promise<string> {
  if (username) return `https://t.me/${username.replace(/^@/, "")}`;
  const link = await tgSafe<string>("exportChatInviteLink", { chat_id: channelId });
  if (typeof link === "string" && link.length > 0) return link;
  const created = await tgSafe<{ invite_link: string }>("createChatInviteLink", {
    chat_id: channelId,
  });
  return created?.invite_link ?? "https://t.me/";
}

async function enforceForceJoin(
  chatId: number,
  userId: number,
  movieId: string,
  cfg: Partial<BotConfig>,
): Promise<boolean> {
  // Returns true if user is joined; otherwise sends a force-join prompt and returns false.
  const joinButtons: { label: string; url: string }[] = [];
  const needJoin: { label: string; url: string }[] = [];
  if (cfg.main_channel_id) {
    const ok = await isJoined(cfg.main_channel_id, userId);
    const b = { label: "📢 Join Main Channel", url: await channelJoinUrl(cfg.main_channel_id, cfg.main_channel_username) };
    joinButtons.push(b);
    if (!ok) needJoin.push(b);
  }
  if (cfg.backup_join_channel_id) {
    const ok = await isJoined(cfg.backup_join_channel_id, userId);
    const b = { label: "📢 Join Backup Channel", url: await channelJoinUrl(cfg.backup_join_channel_id, cfg.backup_join_channel_username) };
    joinButtons.push(b);
    if (!ok) needJoin.push(b);
  }
  if (!needJoin.length) return true;
  const keyboard = [
    ...joinButtons.map((c) => [{ text: c.label, url: c.url }]),
    [{ text: "✅ I've Joined", callback_data: `check:${movieId}` }],
  ];
  await tg("sendMessage", {
    chat_id: chatId,
    text: "🔐 Please join the required channel(s), then tap **I've Joined**.",
    parse_mode: "Markdown",
    reply_markup: { inline_keyboard: keyboard },
  });
  return false;
}

async function showMovie(
  chatId: number,
  userId: number,
  movieId: string,
  cfg: Partial<BotConfig>,
  supabaseAdmin: any,
  source: string | null = null,
) {
  const m = await supabaseAdmin.from("movies").select("*").eq("id", movieId).maybeSingle();
  if (!m.data) return tg("sendMessage", { chat_id: chatId, text: "❌ Not found." });

  if (!(await enforceForceJoin(chatId, userId, movieId, cfg))) return;

  await supabaseAdmin.from("movie_views").insert({ movie_id: movieId, telegram_user_id: userId, source });
  const movie = m.data;

  // Gather all files in this batch (episodes) plus legacy single-movie file.
  const { data: eps } = await supabaseAdmin
    .from("series_episodes")
    .select("id,episode_number,storage_chat_id,storage_message_id,file_id")
    .eq("movie_id", movieId)
    .order("season_number", { ascending: true })
    .order("episode_number", { ascending: true });

  const deliveredIds: number[] = [];

  if (eps && eps.length) {
    for (const ep of eps as Array<{ storage_chat_id: number; storage_message_id: number; file_id: string }>) {
      const sent = await tgSafe<{ message_id: number }>("copyMessage", {
        chat_id: chatId,
        from_chat_id: ep.storage_chat_id,
        message_id: ep.storage_message_id,
      });
      if (sent?.message_id) deliveredIds.push(sent.message_id);
      else {
        const fb = await tgSafe<{ message_id: number }>("sendDocument", {
          chat_id: chatId, document: ep.file_id,
        });
        if (fb?.message_id) deliveredIds.push(fb.message_id);
      }
    }
  } else if (movie.storage_chat_id && movie.storage_message_id) {
    const sent = await tgSafe<{ message_id: number }>("copyMessage", {
      chat_id: chatId,
      from_chat_id: movie.storage_chat_id,
      message_id: movie.storage_message_id,
    });
    if (sent?.message_id) deliveredIds.push(sent.message_id);
    else if (movie.movie_file_id) {
      const fb = await tgSafe<{ message_id: number }>("sendDocument", {
        chat_id: chatId, document: movie.movie_file_id,
      });
      if (fb?.message_id) deliveredIds.push(fb.message_id);
    }
  } else {
    return tg("sendMessage", { chat_id: chatId, text: "⚠️ No files available yet." });
  }

  await supabaseAdmin.from("downloads").insert({ movie_id: movieId, telegram_user_id: userId });
  await scheduleDeliveryDelete(chatId, deliveredIds, supabaseAdmin);
}

async function schedulePosterDelete(chatId: number, messageId: number | undefined, supabaseAdmin: any) {
  if (!messageId) return;
  const deleteAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();
  const { error } = await supabaseAdmin
    .from("scheduled_deletions")
    .insert({ chat_id: chatId, message_id: messageId, delete_at: deleteAt });
  if (error) console.error("[poster] scheduled_deletions insert error:", error.message);
}

async function showSeasonPicker(chatId: number, movieId: string, supabaseAdmin: any) {
  const { data, error } = await supabaseAdmin
    .from("series_episodes")
    .select("season_number")
    .eq("movie_id", movieId);
  if (error || !data?.length) {
    return tg("sendMessage", { chat_id: chatId, text: "No episodes yet." });
  }
  const seasons = Array.from(new Set((data as { season_number: number }[]).map((r) => r.season_number))).sort((a, b) => a - b);
  // Up to 5 per row
  const rows: { text: string; callback_data: string }[][] = [];
  for (let i = 0; i < seasons.length; i += 5) {
    rows.push(seasons.slice(i, i + 5).map((s) => ({ text: `S${s}`, callback_data: `season:${movieId}:${s}` })));
  }
  await tg("sendMessage", {
    chat_id: chatId,
    text: "📂 Choose a season:",
    reply_markup: { inline_keyboard: rows },
  });
}

async function showEpisodeList(
  chatId: number,
  movieId: string,
  season: number,
  page: number,
  supabaseAdmin: any,
) {
  const from = page * EPISODES_PER_PAGE;
  const to = from + EPISODES_PER_PAGE - 1;
  const { data, count, error } = await supabaseAdmin
    .from("series_episodes")
    .select("id,episode_number,title", { count: "exact" })
    .eq("movie_id", movieId)
    .eq("season_number", season)
    .order("episode_number", { ascending: true })
    .range(from, to);
  if (error || !data?.length) {
    return tg("sendMessage", { chat_id: chatId, text: `No episodes in S${season}.` });
  }
  const rows = (data as { id: string; episode_number: number; title: string | null }[]).map((e) => [
    {
      text: `S${season}E${e.episode_number}${e.title ? ` · ${truncate(e.title, 30)}` : ""}`,
      callback_data: `epdl:${e.id}`,
    },
  ]);
  const total = count ?? data.length;
  const nav: { text: string; callback_data: string }[] = [];
  if (page > 0) nav.push({ text: "◀ Prev", callback_data: `epi:${movieId}:${season}:${page - 1}` });
  if (to + 1 < total) nav.push({ text: "Next ▶", callback_data: `epi:${movieId}:${season}:${page + 1}` });
  if (nav.length) rows.push(nav);
  rows.push([{ text: "↩️ Seasons", callback_data: `season:${movieId}` }]);
  await tg("sendMessage", {
    chat_id: chatId,
    text: `📺 Season ${season} · Page ${page + 1}/${Math.max(1, Math.ceil(total / EPISODES_PER_PAGE))}`,
    reply_markup: { inline_keyboard: rows },
  });
}

function truncate(s: string, n: number) {
  return s.length > n ? s.slice(0, n - 1) + "…" : s;
}

async function deliverMovie(
  chatId: number,
  userId: number,
  movieId: string,
  cfg: Partial<BotConfig>,
  supabaseAdmin: any,
) {
  const m = await supabaseAdmin.from("movies").select("*").eq("id", movieId).maybeSingle();
  if (!m.data) return tg("sendMessage", { chat_id: chatId, text: "❌ Not found." });
  if (!(await enforceForceJoin(chatId, userId, movieId, cfg))) return;

  const sent = await tgSafe<{ message_id: number }>("copyMessage", {
    chat_id: chatId,
    from_chat_id: m.data.storage_chat_id,
    message_id: m.data.storage_message_id,
  });
  let fileMsgId: number | null = sent?.message_id ?? null;
  if (!sent && m.data.movie_file_id) {
    const fb = await tgSafe<{ message_id: number }>("sendDocument", {
      chat_id: chatId, document: m.data.movie_file_id,
    });
    fileMsgId = fb?.message_id ?? null;
  }
  await supabaseAdmin.from("downloads").insert({ movie_id: movieId, telegram_user_id: userId });
  await scheduleDeliveryDelete(chatId, fileMsgId, supabaseAdmin);
}

async function deliverEpisode(
  chatId: number,
  userId: number,
  episodeId: string,
  cfg: Partial<BotConfig>,
  supabaseAdmin: any,
) {
  const ep = await supabaseAdmin
    .from("series_episodes")
    .select("id,movie_id,season_number,episode_number,title,file_id,storage_chat_id,storage_message_id")
    .eq("id", episodeId)
    .maybeSingle();
  if (!ep.data) return tg("sendMessage", { chat_id: chatId, text: "❌ Episode not found." });

  if (!(await enforceForceJoin(chatId, userId, ep.data.movie_id, cfg))) return;

  const sent = await tgSafe<{ message_id: number }>("copyMessage", {
    chat_id: chatId,
    from_chat_id: ep.data.storage_chat_id,
    message_id: ep.data.storage_message_id,
  });
  let fileMsgId: number | null = sent?.message_id ?? null;
  if (!sent) {
    const fb = await tgSafe<{ message_id: number }>("sendDocument", {
      chat_id: chatId, document: ep.data.file_id,
    });
    fileMsgId = fb?.message_id ?? null;
  }
  await supabaseAdmin.from("downloads").insert({ movie_id: ep.data.movie_id, telegram_user_id: userId });
  await scheduleDeliveryDelete(chatId, fileMsgId, supabaseAdmin);
}

async function scheduleDeliveryDelete(
  chatId: number,
  fileMsgIds: number | number[] | null,
  supabaseAdmin: any,
) {
  const warn = await tgSafe<{ message_id: number }>("sendMessage", {
    chat_id: chatId,
    text: "⚠️ This file will be auto-deleted in 5 minutes due to copyright.\n\n📥 Forward it to your Saved Messages now to keep a copy.",
  });
  const deleteAt = new Date(Date.now() + 5 * 60 * 1000).toISOString();
  const rows: { chat_id: number; message_id: number; delete_at: string }[] = [];
  const ids = Array.isArray(fileMsgIds) ? fileMsgIds : fileMsgIds ? [fileMsgIds] : [];
  for (const id of ids) rows.push({ chat_id: chatId, message_id: id, delete_at: deleteAt });
  if (warn?.message_id) rows.push({ chat_id: chatId, message_id: warn.message_id, delete_at: deleteAt });
  if (rows.length) {
    const { error } = await supabaseAdmin.from("scheduled_deletions").insert(rows);
    if (error) console.error("[delivery] scheduled_deletions insert error:", error.message);
  }
}

function escapeMd(s: string) {
  return s.replace(/([_*`\[\]])/g, "\\$1");
}
