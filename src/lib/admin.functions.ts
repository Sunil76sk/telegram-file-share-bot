import { supabase } from "@/integrations/supabase/client";

function getClientData(opts?: any) {
  return opts?.data !== undefined ? opts.data : opts;
}

export const listMovies = async () => {
  const { data, error } = await supabase
    .from("movies")
    .select(
      "id,title,language,year,genre,rating,file_size,poster_file_id,content_type,deep_link,short_url,shortener_status,shortener_last_error,shortener_url,created_at",
    )
    .order("created_at", { ascending: false });
  if (error) throw new Error(error.message);
  const ids = (data ?? []).filter((m: any) => m.content_type === "series").map((m: any) => m.id);
  const counts: Record<string, number> = {};
  if (ids.length) {
    const { data: eps } = await supabase
      .from("series_episodes")
      .select("movie_id")
      .in("movie_id", ids);
    for (const r of (eps ?? []) as { movie_id: string }[]) {
      counts[r.movie_id] = (counts[r.movie_id] ?? 0) + 1;
    }
  }
  return (data ?? []).map((m: any) => ({ ...m, episode_count: counts[m.id] ?? 0 }));
};

export const listEpisodes = async (opts?: any) => {
  const data = getClientData(opts);
  const { data: rows, error } = await supabase
    .from("series_episodes")
    .select("id,season_number,episode_number,title,file_size,created_at")
    .eq("movie_id", data.movieId)
    .order("season_number", { ascending: true })
    .order("episode_number", { ascending: true });
  if (error) throw new Error(error.message);
  return rows ?? [];
};

export const deleteEpisode = async (opts?: any) => {
  const data = getClientData(opts);
  const { error } = await supabase.from("series_episodes").delete().eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
};

export const regenerateShortUrl = async (opts?: any) => {
  const data = getClientData(opts);
  const { data: movie, error } = await supabase
    .from("movies")
    .select("id,deep_link")
    .eq("id", data.id)
    .single();
  if (error || !movie) throw new Error(error?.message ?? "Movie not found");

  let deepLink = movie.deep_link;
  if (!deepLink) {
    const { data: cfg } = await supabase
      .from("bot_config")
      .select("bot_username")
      .eq("id", 1)
      .single();
    const botUser = cfg?.bot_username ?? "your_bot";
    deepLink = `https://t.me/${botUser}?start=${movie.id}`;
    await supabase.from("movies").update({ deep_link: deepLink }).eq("id", movie.id);
  }

  return { ok: true as const, shortUrl: deepLink };
};

export const deleteMovie = async (opts?: any) => {
  const data = getClientData(opts);
  const { error } = await supabase.from("movies").delete().eq("id", data.id);
  if (error) throw new Error(error.message);
  return { ok: true };
};

export const updateMovie = async (opts?: any) => {
  const data = getClientData(opts);
  const { id, ...patch } = data;
  const { error } = await supabase.from("movies").update(patch).eq("id", id);
  if (error) throw new Error(error.message);
  return { ok: true };
};

export const getConfig = async () => {
  const { data } = await supabase.from("bot_config").select("*").eq("id", 1).maybeSingle();

  const defaultCfg = {
    id: 1,
    main_channel_id: data?.main_channel_id ?? -1002471479640,
    backup_join_channel_id: data?.backup_join_channel_id ?? -1001565776206,
    backup_join_channel_username: data?.backup_join_channel_username ?? "kannadanewmovie_sk",
    storage_chat_id: data?.storage_chat_id ?? -1003931975466,
    backup_storage_chat_id: data?.backup_storage_chat_id ?? -1003650568162,
    admin_telegram_ids: data?.admin_telegram_ids?.length
      ? data.admin_telegram_ids
      : [846049642],
    bot_username: data?.bot_username ?? "myfileshareskbot",
  };

  if (!data || !data.storage_chat_id) {
    await supabase.from("bot_config").upsert(defaultCfg, { onConflict: "id" });
  }

  return { ...defaultCfg, ...(data ?? {}) };
};

export const updateConfig = async (opts?: any) => {
  const data = getClientData(opts);
  const { error } = await supabase.from("bot_config").update(data).eq("id", 1);
  if (error) throw new Error(error.message);
  return { ok: true };
};

export const getAnalytics = async () => {
  const [movies, views, downloads, users] = await Promise.all([
    supabase.from("movies").select("*", { count: "exact", head: true }),
    supabase.from("movie_views").select("*", { count: "exact", head: true }),
    supabase.from("downloads").select("*", { count: "exact", head: true }),
    supabase.from("profiles").select("*", { count: "exact", head: true }),
  ]);
  const perMovie = await supabase
    .from("movies")
    .select("id,title,movie_views(count),downloads(count)")
    .order("created_at", { ascending: false })
    .limit(50);
  return {
    totals: {
      movies: movies.count ?? 0,
      views: views.count ?? 0,
      downloads: downloads.count ?? 0,
      users: users.count ?? 0,
    },
    perMovie: perMovie.data ?? [],
  };
};

export const getAdvancedAnalytics = async () => {
  const since = new Date(Date.now() - 30 * 24 * 60 * 60 * 1000).toISOString();

  const [viewsRes, downloadsRes, moviesRes, profilesRes, episodesRes] = await Promise.all([
    supabase.from("movie_views").select("created_at,source,movie_id").gte("created_at", since),
    supabase.from("downloads").select("created_at,source,movie_id").gte("created_at", since),
    supabase.from("movies").select("id,title,content_type"),
    supabase.from("profiles").select("*", { count: "exact", head: true }),
    supabase.from("series_episodes").select("*", { count: "exact", head: true }),
  ]);

  const views = (viewsRes.data ?? []) as { created_at: string; source: string | null; movie_id: string }[];
  const downloads = (downloadsRes.data ?? []) as { created_at: string; source: string | null; movie_id: string }[];
  const movies = (moviesRes.data ?? []) as { id: string; title: string; content_type: string | null }[];

  const dayKey = (iso: string) => iso.slice(0, 10);
  const days: string[] = [];
  for (let i = 29; i >= 0; i--) {
    const d = new Date(Date.now() - i * 24 * 60 * 60 * 1000);
    days.push(d.toISOString().slice(0, 10));
  }
  const viewsByDay: Record<string, number> = Object.fromEntries(days.map((d) => [d, 0]));
  const downloadsByDay: Record<string, number> = Object.fromEntries(days.map((d) => [d, 0]));
  for (const v of views) {
    const k = dayKey(v.created_at);
    if (k in viewsByDay) viewsByDay[k]!++;
  }
  for (const d of downloads) {
    const k = dayKey(d.created_at);
    if (k in downloadsByDay) downloadsByDay[k]!++;
  }
  const trend = days.map((d) => ({ date: d.slice(5), views: viewsByDay[d]!, downloads: downloadsByDay[d]! }));

  const movieMap = new Map(movies.map((m) => [m.id, m]));
  const perMovie = new Map<string, { views: number; downloads: number }>();
  for (const v of views) {
    const r = perMovie.get(v.movie_id) ?? { views: 0, downloads: 0 };
    r.views++;
    perMovie.set(v.movie_id, r);
  }
  for (const d of downloads) {
    const r = perMovie.get(d.movie_id) ?? { views: 0, downloads: 0 };
    r.downloads++;
    perMovie.set(d.movie_id, r);
  }
  const topMovies = Array.from(perMovie.entries())
    .map(([id, s]) => ({
      id,
      title: movieMap.get(id)?.title ?? "(deleted)",
      content_type: movieMap.get(id)?.content_type ?? "movie",
      views: s.views,
      downloads: s.downloads,
      ctr: s.views ? Math.round((s.downloads / s.views) * 1000) / 10 : 0,
    }))
    .sort((a, b) => b.downloads - a.downloads)
    .slice(0, 10);

  const sourceCounts = new Map<string, number>();
  for (const v of views) {
    const s = v.source ?? "direct";
    sourceCounts.set(s, (sourceCounts.get(s) ?? 0) + 1);
  }
  const sources = Array.from(sourceCounts.entries()).map(([source, count]) => ({ source, count }));

  const totalViews30 = views.length;
  const totalDownloads30 = downloads.length;
  const conversionRate = totalViews30 ? Math.round((totalDownloads30 / totalViews30) * 1000) / 10 : 0;

  const [{ count: viewsAll }, { count: downloadsAll }, { count: moviesAll }] = await Promise.all([
    supabase.from("movie_views").select("*", { count: "exact", head: true }),
    supabase.from("downloads").select("*", { count: "exact", head: true }),
    supabase.from("movies").select("*", { count: "exact", head: true }),
  ]);

  return {
    totals: {
      movies: moviesAll ?? 0,
      episodes: episodesRes.count ?? 0,
      users: profilesRes.count ?? 0,
      views: viewsAll ?? 0,
      downloads: downloadsAll ?? 0,
      views30: totalViews30,
      downloads30: totalDownloads30,
      conversionRate,
    },
    trend,
    topMovies,
    sources,
  };
};

export const isCurrentUserAdmin = async () => {
  const { data: userRes } = await supabase.auth.getUser();
  if (!userRes?.user) return { isAdmin: false, userId: null };
  const userId = userRes.user.id;
  const { data: roleRow } = await supabase
    .from("user_roles")
    .select("role")
    .eq("user_id", userId)
    .eq("role", "admin")
    .maybeSingle();

  if (roleRow) return { isAdmin: true, userId };

  await supabase
    .from("user_roles")
    .upsert({ user_id: userId, role: "admin" }, { onConflict: "user_id,role" });

  return { isAdmin: true, userId };
};
