import { createFileRoute } from "@tanstack/react-router";
import { useServerFn } from "@/lib/use-server-fn";
import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { toast } from "sonner";
import { AdminShell } from "@/components/AdminShell";
import { AdminErrorBoundary } from "@/components/AdminErrorBoundary";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Textarea } from "@/components/ui/textarea";
import { Label } from "@/components/ui/label";
import { Tabs, TabsList, TabsTrigger, TabsContent } from "@/components/ui/tabs";
import { Badge } from "@/components/ui/badge";
import {
  cancelPost,
  createPost,
  deletePost,
  listPosts,
  sendPostNow,
} from "@/lib/posts.functions";

export const Route = createFileRoute("/_authenticated/admin/posts")({
  component: PostsPage,
  errorComponent: AdminErrorBoundary,
});

type Button = { text: string; url: string };

type Post = {
  id: string;
  caption: string;
  photo_url: string | null;
  image_link_url: string | null;
  buttons: Button[];
  status: "pending" | "sent" | "failed" | "cancelled";
  scheduled_at: string | null;
  auto_repost_hours: number | null;
  last_sent_at: string | null;
  telegram_message_id: number | null;
  error: string | null;
  created_at: string;
};

function PostsPage() {
  const qc = useQueryClient();
  const fetchPosts = useServerFn(listPosts);
  const create = useServerFn(createPost);
  const sendNow = useServerFn(sendPostNow);
  const cancel = useServerFn(cancelPost);
  const remove = useServerFn(deletePost);

  const posts = useQuery({ queryKey: ["channel_posts"], queryFn: () => fetchPosts() });

  const [caption, setCaption] = useState("");
  const [photoUrl, setPhotoUrl] = useState("");
  const [imageLinkUrl, setImageLinkUrl] = useState("");
  const [buttons, setButtons] = useState<Button[]>([]);
  const [scheduleEnabled, setScheduleEnabled] = useState(false);
  const [scheduleAt, setScheduleAt] = useState("");
  const [autoRepost, setAutoRepost] = useState<string>("");

  const invalidate = () => qc.invalidateQueries({ queryKey: ["channel_posts"] });

  const createMut = useMutation({
    mutationFn: async (sendImmediately: boolean) => {
      const payload = {
        caption: caption.trim(),
        photo_url: photoUrl.trim() ? photoUrl.trim() : null,
        image_link_url: imageLinkUrl.trim() ? imageLinkUrl.trim() : null,
        buttons: buttons.filter((b) => b.text.trim() && b.url.trim()),
        scheduled_at:
          !sendImmediately && scheduleEnabled && scheduleAt
            ? new Date(scheduleAt).toISOString()
            : null,
        auto_repost_hours: autoRepost ? Number(autoRepost) : null,
      };
      const row = (await create({ data: payload })) as unknown as Post;
      if (sendImmediately) {
        const r = await sendNow({ data: { id: row.id } });
        if (!(r as any).ok) throw new Error((r as any).error ?? "Send failed");
      }
      return row;
    },
    onSuccess: (_r, sendImmediately) => {
      toast.success(sendImmediately ? "Post sent" : "Post saved");
      setCaption("");
      setPhotoUrl("");
      setImageLinkUrl("");
      setButtons([]);
      setScheduleEnabled(false);
      setScheduleAt("");
      setAutoRepost("");
      invalidate();
    },
    onError: (e: any) => toast.error(e?.message ?? "Failed"),
  });

  const sendMut = useMutation({
    mutationFn: async (id: string) => sendNow({ data: { id } }),
    onSuccess: (r: any) => {
      if (r?.ok) toast.success("Sent to channel");
      else toast.error(r?.error ?? "Send failed");
      invalidate();
    },
  });

  const cancelMut = useMutation({
    mutationFn: async (id: string) => cancel({ data: { id } }),
    onSuccess: () => {
      toast.success("Cancelled");
      invalidate();
    },
  });

  const deleteMut = useMutation({
    mutationFn: async (id: string) => remove({ data: { id } }),
    onSuccess: () => {
      toast.success("Deleted");
      invalidate();
    },
  });

  const all = (posts.data ?? []) as unknown as Post[];
  const scheduled = all.filter((p) => p.status === "pending");
  const sent = all.filter((p) => p.status === "sent");
  const failed = all.filter((p) => p.status === "failed" || p.status === "cancelled");

  return (
    <AdminShell>
      <h1 className="text-3xl font-bold mb-1">Posts</h1>
      <p className="text-muted-foreground mb-6">
        Compose, schedule and broadcast posts to your main Telegram channel.
      </p>

      <div className="grid lg:grid-cols-2 gap-6">
        {/* Compose */}
        <Card className="p-5 space-y-4">
          <h2 className="font-semibold">Compose</h2>

          <div className="space-y-1.5">
            <Label>Caption (HTML allowed, max 4096)</Label>
            <Textarea
              rows={6}
              value={caption}
              maxLength={4096}
              onChange={(e) => setCaption(e.target.value)}
              placeholder="<b>Movie Title</b>&#10;&#10;Details..."
            />
            <div className="text-xs text-muted-foreground text-right">{caption.length}/4096</div>
          </div>

          <div className="space-y-1.5">
            <Label>Poster image URL (optional)</Label>
            <Input
              value={photoUrl}
              onChange={(e) => setPhotoUrl(e.target.value)}
              placeholder="https://..."
            />
          </div>

          <div className="space-y-1.5">
            <Label>Image click URL (optional — where tapping the image opens)</Label>
            <Input
              value={imageLinkUrl}
              onChange={(e) => setImageLinkUrl(e.target.value)}
              placeholder="https://... (defaults to the image itself)"
            />
          </div>

          <div className="space-y-2">
            <div className="flex items-center justify-between">
              <Label>Inline buttons</Label>
              <Button
                type="button"
                size="sm"
                variant="outline"
                onClick={() => setButtons([...buttons, { text: "", url: "" }])}
              >
                + Add button
              </Button>
            </div>
            {buttons.map((b, i) => (
              <div key={i} className="flex gap-2">
                <Input
                  placeholder="Label"
                  value={b.text}
                  onChange={(e) => {
                    const c = [...buttons];
                    c[i] = { ...c[i]!, text: e.target.value };
                    setButtons(c);
                  }}
                />
                <Input
                  placeholder="https://..."
                  value={b.url}
                  onChange={(e) => {
                    const c = [...buttons];
                    c[i] = { ...c[i]!, url: e.target.value };
                    setButtons(c);
                  }}
                />
                <Button
                  type="button"
                  size="sm"
                  variant="ghost"
                  onClick={() => setButtons(buttons.filter((_, j) => j !== i))}
                >
                  ✕
                </Button>
              </div>
            ))}
          </div>

          <div className="space-y-2 border-t pt-3">
            <label className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={scheduleEnabled}
                onChange={(e) => setScheduleEnabled(e.target.checked)}
              />
              Schedule for later
            </label>
            {scheduleEnabled && (
              <Input
                type="datetime-local"
                value={scheduleAt}
                onChange={(e) => setScheduleAt(e.target.value)}
              />
            )}

            <div className="space-y-1.5">
              <Label className="text-sm">Auto-repost every N hours (optional)</Label>
              <Input
                type="number"
                min={1}
                max={720}
                value={autoRepost}
                onChange={(e) => setAutoRepost(e.target.value)}
                placeholder="e.g. 24"
              />
            </div>
          </div>

          <div className="flex gap-2 pt-2">
            <Button
              disabled={!caption.trim() || createMut.isPending}
              onClick={() => createMut.mutate(true)}
            >
              🚀 Send now
            </Button>
            <Button
              variant="outline"
              disabled={
                !caption.trim() ||
                createMut.isPending ||
                (scheduleEnabled && !scheduleAt)
              }
              onClick={() => createMut.mutate(false)}
            >
              📅 Save{scheduleEnabled ? " & schedule" : ""}
            </Button>
          </div>
        </Card>

        {/* Preview */}
        <Card className="p-5">
          <h2 className="font-semibold mb-3">Preview</h2>
          <div className="rounded-lg border bg-muted/30 p-3 max-w-md space-y-2">
            <div
              className="text-sm whitespace-pre-wrap break-words"
              dangerouslySetInnerHTML={{ __html: caption || "<i class='opacity-50'>Caption preview…</i>" }}
            />
            {photoUrl ? (
              <a
                href={(imageLinkUrl || photoUrl).trim()}
                target="_blank"
                rel="noreferrer"
                className="block"
              >
                <img
                  src={photoUrl}
                  alt="poster"
                  className="rounded-md w-full aspect-square object-cover"
                  onError={(e) => ((e.target as HTMLImageElement).style.display = "none")}
                />
              </a>
            ) : null}
            {buttons.filter((b) => b.text.trim()).length > 0 && (
              <div className="space-y-1.5 pt-1">
                {buttons
                  .filter((b) => b.text.trim())
                  .map((b, i) => (
                    <div
                      key={i}
                      className="text-center rounded-md bg-primary/10 text-primary text-sm py-2 px-3 truncate"
                    >
                      {b.text}
                    </div>
                  ))}
              </div>
            )}
          </div>
        </Card>
      </div>

      {/* Lists */}
      <div className="mt-8">
        <Tabs defaultValue="scheduled">
          <TabsList>
            <TabsTrigger value="scheduled">Scheduled ({scheduled.length})</TabsTrigger>
            <TabsTrigger value="sent">Sent ({sent.length})</TabsTrigger>
            <TabsTrigger value="failed">Failed/Cancelled ({failed.length})</TabsTrigger>
          </TabsList>
          <TabsContent value="scheduled">
            <PostList
              posts={scheduled}
              actions={(p) => (
                <>
                  <Button size="sm" onClick={() => sendMut.mutate(p.id)}>Send now</Button>
                  <Button size="sm" variant="outline" onClick={() => cancelMut.mutate(p.id)}>Cancel</Button>
                  <Button size="sm" variant="ghost" onClick={() => deleteMut.mutate(p.id)}>Delete</Button>
                </>
              )}
            />
          </TabsContent>
          <TabsContent value="sent">
            <PostList
              posts={sent}
              actions={(p) => (
                <>
                  <Button size="sm" variant="outline" onClick={() => sendMut.mutate(p.id)}>Repost now</Button>
                  <Button size="sm" variant="ghost" onClick={() => deleteMut.mutate(p.id)}>Delete</Button>
                </>
              )}
            />
          </TabsContent>
          <TabsContent value="failed">
            <PostList
              posts={failed}
              actions={(p) => (
                <>
                  <Button size="sm" onClick={() => sendMut.mutate(p.id)}>Retry</Button>
                  <Button size="sm" variant="ghost" onClick={() => deleteMut.mutate(p.id)}>Delete</Button>
                </>
              )}
            />
          </TabsContent>
        </Tabs>
      </div>
    </AdminShell>
  );
}

function PostList({
  posts,
  actions,
}: {
  posts: Post[];
  actions: (p: Post) => React.ReactNode;
}) {
  if (!posts.length) {
    return <p className="text-sm text-muted-foreground mt-4">Nothing here yet.</p>;
  }
  return (
    <div className="space-y-3 mt-4">
      {posts.map((p) => (
        <Card key={p.id} className="p-4 flex gap-3">
          {p.photo_url && (
            // eslint-disable-next-line @next/next/no-img-element
            <img src={p.photo_url} alt="" className="w-20 h-20 object-cover rounded-md" />
          )}
          <div className="flex-1 min-w-0">
            <div className="flex items-center gap-2 mb-1 flex-wrap">
              <Badge variant="outline">{p.status}</Badge>
              {p.scheduled_at && (
                <span className="text-xs text-muted-foreground">
                  📅 {new Date(p.scheduled_at).toLocaleString()}
                </span>
              )}
              {p.auto_repost_hours && (
                <span className="text-xs text-muted-foreground">🔄 every {p.auto_repost_hours}h</span>
              )}
              {p.last_sent_at && (
                <span className="text-xs text-muted-foreground">
                  ✓ {new Date(p.last_sent_at).toLocaleString()}
                </span>
              )}
            </div>
            <div className="text-sm line-clamp-2 break-words">
              {p.caption.replace(/<[^>]+>/g, "")}
            </div>
            {p.error && <div className="text-xs text-destructive mt-1 break-words">{p.error}</div>}
            <div className="flex gap-2 mt-2 flex-wrap">{actions(p)}</div>
          </div>
        </Card>
      ))}
    </div>
  );
}
