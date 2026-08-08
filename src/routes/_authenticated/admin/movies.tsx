import { createFileRoute } from "@tanstack/react-router";
import { useServerFn } from "@/lib/use-server-fn";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { AdminShell } from "@/components/AdminShell";
import {
  listMovies,
  deleteMovie,
  updateMovie,
  getConfig,
  regenerateShortUrl,
  listEpisodes,
  deleteEpisode,
} from "@/lib/admin.functions";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Badge } from "@/components/ui/badge";
import { toast } from "sonner";

import { AdminErrorBoundary } from "@/components/AdminErrorBoundary";

export const Route = createFileRoute("/_authenticated/admin/movies")({
  component: MoviesPage,
  errorComponent: AdminErrorBoundary,
});


type MovieRow = {
  id: string;
  title: string;
  language: string | null;
  year: number | null;
  genre: string | null;
  rating: number | null;
  file_size: number | null;
  poster_file_id: string | null;
  content_type: string | null;
  deep_link: string | null;
  short_url: string | null;
  shortener_status: string | null;
  shortener_last_error: string | null;
  shortener_url: string | null;
  episode_count?: number;
  created_at: string;
};

function MoviesPage() {
  const fetchMovies = useServerFn(listMovies);
  const fetchConfig = useServerFn(getConfig);
  const del = useServerFn(deleteMovie);
  const upd = useServerFn(updateMovie);
  const regen = useServerFn(regenerateShortUrl);
  const qc = useQueryClient();
  const [search, setSearch] = useState("");
  const [busyId, setBusyId] = useState<string | null>(null);
  const [expanded, setExpanded] = useState<string | null>(null);

  const movies = useQuery({ queryKey: ["movies"], queryFn: () => fetchMovies() });
  const cfg = useQuery({ queryKey: ["cfg"], queryFn: () => fetchConfig() });

  const filtered = ((movies.data ?? []) as MovieRow[]).filter((m) =>
    m.title.toLowerCase().includes(search.toLowerCase()),
  );

  const botUser = cfg.data?.bot_username ?? "your_bot";

  return (
    <AdminShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Library</h1>
        <Input
          placeholder="Search…"
          value={search}
          onChange={(e) => setSearch(e.target.value)}
          className="max-w-xs"
        />
      </div>

      {!movies.data?.length && (
        <Card className="p-8 text-center text-muted-foreground">
          Nothing yet. DM your bot <code>/uploadmovie</code> or <code>/uploadseries</code>.
        </Card>
      )}

      <div className="grid gap-3">
        {filtered.map((m) => {
          const deepLink = m.deep_link ?? `https://t.me/${botUser}?start=${m.id}`;
          const shortUrl = m.short_url;
          const status = (m.shortener_status ?? "pending") as
            | "pending" | "success" | "failed" | "disabled";
          const statusVariant =
            status === "success" ? "default" : status === "failed" ? "destructive" : "secondary";
          const isSeries = m.content_type === "series";
          return (
            <Card key={m.id} className="p-4 flex flex-col gap-3">
              <div className="flex items-center gap-4">
                <div className="flex-1 min-w-0">
                  <div className="flex items-center gap-2 flex-wrap">
                    <Badge variant={isSeries ? "secondary" : "outline"}>
                      {isSeries ? "📺 Series" : "🎬 Movie"}
                    </Badge>
                    <div className="font-semibold truncate">{m.title}</div>
                    <Badge variant={statusVariant} className="capitalize">{status}</Badge>
                    {isSeries && (
                      <Badge variant="outline">{m.episode_count ?? 0} ep</Badge>
                    )}
                  </div>
                  <div className="text-xs text-muted-foreground mt-0.5">
                    ⭐ {m.rating ?? "—"} · 🌎 {m.language ?? "—"} · 📅 {m.year ?? "—"} · 🎭{" "}
                    {m.genre ?? "—"}
                    {m.file_size ? ` · 📂 ${(m.file_size / 1e9).toFixed(2)} GB` : ""}
                  </div>
                </div>
                {isSeries && (
                  <Button
                    size="sm"
                    variant="outline"
                    onClick={() => setExpanded(expanded === m.id ? null : m.id)}
                  >
                    {expanded === m.id ? "Hide episodes" : "Episodes"}
                  </Button>
                )}
                <Button
                  size="sm"
                  variant="ghost"
                  onClick={async () => {
                    const t = prompt("New title?", m.title);
                    if (!t) return;
                    await upd({ data: { id: m.id, title: t } });
                    qc.invalidateQueries({ queryKey: ["movies"] });
                  }}
                >
                  Edit
                </Button>
                <Button
                  size="sm"
                  variant="destructive"
                  onClick={async () => {
                    if (!confirm(`Delete "${m.title}"?${isSeries ? " All episodes will be removed." : ""}`)) return;
                    await del({ data: { id: m.id } });
                    toast.success("Deleted");
                    qc.invalidateQueries({ queryKey: ["movies"] });
                  }}
                >
                  Delete
                </Button>
              </div>

              <div className="grid gap-2 text-xs">
                <LinkRow
                  label="Deep link"
                  url={deepLink}
                  onCopy={() => {
                    navigator.clipboard.writeText(deepLink);
                    toast.success("Deep link copied");
                  }}
                />
                {shortUrl ? (
                  <LinkRow
                    label="Short URL"
                    url={shortUrl}
                    onCopy={() => {
                      navigator.clipboard.writeText(shortUrl);
                      toast.success("Short URL copied");
                    }}
                  />
                ) : (
                  <div className="flex items-center gap-2 text-muted-foreground">
                    <span className="w-20 shrink-0">Short URL:</span>
                    <span className="italic">
                      {status === "failed" ? "Generation failed" : "Generating…"}
                    </span>
                  </div>
                )}
                {status === "failed" && m.shortener_last_error && (
                  <div className="text-destructive text-[11px]">
                    Last error: {m.shortener_last_error}
                  </div>
                )}
                <div className="flex">
                  <Button
                    size="sm"
                    variant="outline"
                    disabled={busyId === m.id}
                    onClick={async () => {
                      setBusyId(m.id);
                      try {
                        const r = await regen({ data: { id: m.id } });
                        if (r.ok) toast.success("Short URL regenerated");
                        else toast.error(`Failed: ${r.error}`);
                        qc.invalidateQueries({ queryKey: ["movies"] });
                      } catch (e) {
                        toast.error(e instanceof Error ? e.message : "Failed");
                      } finally {
                        setBusyId(null);
                      }
                    }}
                  >
                    {busyId === m.id ? "Working…" : shortUrl ? "Regenerate short URL" : "Generate short URL"}
                  </Button>
                </div>
              </div>

              {isSeries && expanded === m.id && <EpisodeList movieId={m.id} />}
            </Card>
          );
        })}
      </div>
    </AdminShell>
  );
}

function EpisodeList({ movieId }: { movieId: string }) {
  const fetchEps = useServerFn(listEpisodes);
  const delEp = useServerFn(deleteEpisode);
  const qc = useQueryClient();
  const { data, isLoading } = useQuery({
    queryKey: ["episodes", movieId],
    queryFn: () => fetchEps({ data: { movieId } }),
  });
  if (isLoading) return <div className="text-xs text-muted-foreground">Loading episodes…</div>;
  if (!data?.length) return <div className="text-xs text-muted-foreground">No episodes yet. Send more via /uploadseries.</div>;

  // Group by season
  const bySeason = new Map<number, typeof data>();
  for (const ep of data) {
    const arr = bySeason.get(ep.season_number) ?? [];
    arr.push(ep);
    bySeason.set(ep.season_number, arr);
  }
  const seasons = Array.from(bySeason.keys()).sort((a, b) => a - b);

  return (
    <div className="border-t pt-3 grid gap-3">
      {seasons.map((s) => (
        <div key={s}>
          <div className="font-semibold text-sm mb-1">Season {s}</div>
          <div className="grid gap-1">
            {bySeason.get(s)!.map((ep) => (
              <div key={ep.id} className="flex items-center gap-2 text-xs">
                <Badge variant="outline" className="font-mono">S{ep.season_number}E{ep.episode_number}</Badge>
                <span className="truncate flex-1">{ep.title ?? "(no title)"}</span>
                <span className="text-muted-foreground">
                  {ep.file_size ? `${(ep.file_size / 1e9).toFixed(2)} GB` : "—"}
                </span>
                <Button
                  size="sm"
                  variant="ghost"
                  className="h-6 px-2 text-destructive"
                  onClick={async () => {
                    if (!confirm(`Delete S${ep.season_number}E${ep.episode_number}?`)) return;
                    await delEp({ data: { id: ep.id } });
                    toast.success("Episode deleted");
                    qc.invalidateQueries({ queryKey: ["episodes", movieId] });
                    qc.invalidateQueries({ queryKey: ["movies"] });
                  }}
                >
                  Delete
                </Button>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}

function LinkRow({ label, url, onCopy }: { label: string; url: string; onCopy: () => void }) {
  return (
    <div className="flex items-center gap-2">
      <span className="w-20 shrink-0 text-muted-foreground">{label}:</span>
      <a
        href={url}
        target="_blank"
        rel="noreferrer"
        className="font-mono truncate text-primary hover:underline flex-1 min-w-0"
      >
        {url}
      </a>
      <Button size="sm" variant="outline" className="h-7 px-2 text-xs" onClick={onCopy}>
        Copy
      </Button>
    </div>
  );
}
