import { createFileRoute } from "@tanstack/react-router";
import { useServerFn } from "@/lib/use-server-fn";
import { useQuery } from "@tanstack/react-query";
import { AdminShell } from "@/components/AdminShell";
import { getAnalytics, isCurrentUserAdmin } from "@/lib/admin.functions";
import { Card } from "@/components/ui/card";

import { AdminErrorBoundary } from "@/components/AdminErrorBoundary";

export const Route = createFileRoute("/_authenticated/admin/")({
  component: Dashboard,
  errorComponent: AdminErrorBoundary,
});


function Dashboard() {
  const fetchAnalytics = useServerFn(getAnalytics);
  const fetchAdmin = useServerFn(isCurrentUserAdmin);
  const admin = useQuery({ queryKey: ["isAdmin"], queryFn: () => fetchAdmin() });
  const q = useQuery({
    queryKey: ["analytics"],
    queryFn: () => fetchAnalytics(),
    enabled: !!admin.data?.isAdmin,
  });

  return (
    <AdminShell>
      <h1 className="text-3xl font-bold mb-1">Dashboard</h1>
      <p className="text-muted-foreground mb-6">Movie Delivery Bot overview</p>

      {!admin.isLoading && !admin.data?.isAdmin && (
        <Card className="p-6 mb-6 border-destructive">
          <p className="font-semibold">You're not an admin.</p>
          <p className="text-sm text-muted-foreground mt-1">
            The first signed-up account is automatically the admin. If that's not you, ask the existing admin to add your user.
          </p>
        </Card>
      )}

      {q.data && (
        <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-8">
          <Stat label="Movies" value={q.data.totals.movies} />
          <Stat label="Users" value={q.data.totals.users} />
          <Stat label="Views" value={q.data.totals.views} />
          <Stat label="Downloads" value={q.data.totals.downloads} />
        </div>
      )}

      <Card className="p-6">
        <h2 className="font-semibold mb-3">Setup checklist</h2>
        <ol className="list-decimal pl-5 space-y-2 text-sm">
          <li>Create your bot in <a className="underline" href="https://t.me/BotFather" target="_blank" rel="noreferrer">@BotFather</a> and link the Telegram connection (already done if you see this).</li>
          <li>Create 4 Telegram channels: <b>Main</b> (public), <b>Backup-Join</b> (public), <b>Storage</b> (private), <b>Backup-Storage</b> (private). Add the bot as admin in all of them.</li>
          <li>Open <a className="underline" href="/admin/settings">Settings</a> and paste the channel IDs, your bot username, and your Telegram user ID.</li>
          <li>Register the webhook (Settings page has a one-click button).</li>
          <li>DM the bot <code>/uploadmovie</code> to add your first movie.</li>
        </ol>
      </Card>
    </AdminShell>
  );
}

function Stat({ label, value }: { label: string; value: number }) {
  return (
    <Card className="p-5">
      <div className="text-xs uppercase text-muted-foreground">{label}</div>
      <div className="text-3xl font-bold mt-1">{value.toLocaleString()}</div>
    </Card>
  );
}
