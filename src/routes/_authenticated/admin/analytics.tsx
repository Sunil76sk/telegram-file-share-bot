import { createFileRoute } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { useQuery } from "@tanstack/react-query";
import { AdminShell } from "@/components/AdminShell";
import { getAdvancedAnalytics } from "@/lib/admin.functions";
import { Card } from "@/components/ui/card";
import { Badge } from "@/components/ui/badge";
import {
  AreaChart,
  Area,
  XAxis,
  YAxis,
  Tooltip,
  ResponsiveContainer,
  CartesianGrid,
  PieChart,
  Pie,
  Cell,
  Legend,
} from "recharts";

import { AdminErrorBoundary } from "@/components/AdminErrorBoundary";

export const Route = createFileRoute("/_authenticated/admin/analytics")({
  component: Analytics,
  errorComponent: AdminErrorBoundary,
});


const PIE_COLORS = [
  "hsl(var(--primary))",
  "hsl(var(--destructive))",
  "hsl(var(--muted-foreground))",
  "#22c55e",
  "#f59e0b",
  "#06b6d4",
  "#a855f7",
];

function Analytics() {
  const fn = useServerFn(getAdvancedAnalytics);
  const q = useQuery({
    queryKey: ["analytics-advanced"],
    queryFn: () => fn(),
    refetchInterval: 30_000,
  });

  if (!q.data) {
    return (
      <AdminShell>
        <h1 className="text-3xl font-bold mb-6">Analytics</h1>
        <Card className="p-8 text-center text-muted-foreground">Loading…</Card>
      </AdminShell>
    );
  }

  const { totals, trend, topMovies, sources } = q.data;

  return (
    <AdminShell>
      <div className="flex items-center justify-between mb-6">
        <h1 className="text-3xl font-bold">Analytics</h1>
        <Badge variant="outline">Auto-refresh · 30s</Badge>
      </div>

      <div className="grid grid-cols-2 md:grid-cols-4 gap-4 mb-6">
        <Stat label="Movies / Series" value={totals.movies} />
        <Stat label="Episodes" value={totals.episodes} />
        <Stat label="Users" value={totals.users} />
        <Stat label="Conversion (30d)" value={`${totals.conversionRate}%`} />
        <Stat label="Views (all)" value={totals.views} />
        <Stat label="Downloads (all)" value={totals.downloads} />
        <Stat label="Views (30d)" value={totals.views30} />
        <Stat label="Downloads (30d)" value={totals.downloads30} />
      </div>

      <Card className="p-4 mb-6">
        <div className="font-semibold mb-3">Last 30 days</div>
        <div className="h-72 w-full">
          <ResponsiveContainer width="100%" height="100%">
            <AreaChart data={trend} margin={{ left: -20, right: 8, top: 8, bottom: 0 }}>
              <defs>
                <linearGradient id="vGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--primary))" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="hsl(var(--primary))" stopOpacity={0} />
                </linearGradient>
                <linearGradient id="dGrad" x1="0" y1="0" x2="0" y2="1">
                  <stop offset="5%" stopColor="hsl(var(--destructive))" stopOpacity={0.5} />
                  <stop offset="95%" stopColor="hsl(var(--destructive))" stopOpacity={0} />
                </linearGradient>
              </defs>
              <CartesianGrid strokeDasharray="3 3" stroke="hsl(var(--border))" />
              <XAxis dataKey="date" stroke="hsl(var(--muted-foreground))" fontSize={11} />
              <YAxis stroke="hsl(var(--muted-foreground))" fontSize={11} allowDecimals={false} />
              <Tooltip
                contentStyle={{
                  background: "hsl(var(--card))",
                  border: "1px solid hsl(var(--border))",
                  borderRadius: 8,
                  fontSize: 12,
                }}
              />
              <Legend wrapperStyle={{ fontSize: 12 }} />
              <Area type="monotone" dataKey="views" stroke="hsl(var(--primary))" fill="url(#vGrad)" />
              <Area type="monotone" dataKey="downloads" stroke="hsl(var(--destructive))" fill="url(#dGrad)" />
            </AreaChart>
          </ResponsiveContainer>
        </div>
      </Card>

      <div className="grid md:grid-cols-2 gap-6 mb-6">
        <Card className="p-4">
          <div className="font-semibold mb-3">Traffic sources (30d views)</div>
          {sources.length === 0 ? (
            <div className="text-muted-foreground text-sm">No data yet.</div>
          ) : (
            <div className="h-64 w-full">
              <ResponsiveContainer width="100%" height="100%">
                <PieChart>
                  <Pie
                    data={sources}
                    dataKey="count"
                    nameKey="source"
                    cx="50%"
                    cy="50%"
                    outerRadius={80}
                    label={(e: { source: string; count: number }) => `${e.source}: ${e.count}`}
                  >
                    {sources.map((_, i) => (
                      <Cell key={i} fill={PIE_COLORS[i % PIE_COLORS.length]} />
                    ))}
                  </Pie>
                  <Tooltip
                    contentStyle={{
                      background: "hsl(var(--card))",
                      border: "1px solid hsl(var(--border))",
                      borderRadius: 8,
                      fontSize: 12,
                    }}
                  />
                </PieChart>
              </ResponsiveContainer>
            </div>
          )}
          <div className="text-xs text-muted-foreground mt-2">
            Tag Instagram links as <code>?start=&lt;movieId&gt;_ig</code> to attribute traffic.
          </div>
        </Card>

        <Card className="p-4">
          <div className="font-semibold mb-3">Top 10 (last 30d, by downloads)</div>
          {topMovies.length === 0 ? (
            <div className="text-muted-foreground text-sm">No downloads yet.</div>
          ) : (
            <div className="grid gap-1.5">
              {topMovies.map((m, i) => (
                <div key={m.id} className="flex items-center gap-2 text-sm">
                  <span className="w-5 text-muted-foreground font-mono">{i + 1}.</span>
                  <Badge variant={m.content_type === "series" ? "secondary" : "outline"} className="text-[10px]">
                    {m.content_type === "series" ? "📺" : "🎬"}
                  </Badge>
                  <span className="truncate flex-1">{m.title}</span>
                  <span className="text-xs text-muted-foreground tabular-nums">
                    {m.downloads} dl · {m.views} v · {m.ctr}%
                  </span>
                </div>
              ))}
            </div>
          )}
        </Card>
      </div>
    </AdminShell>
  );
}

function Stat({ label, value }: { label: string; value: number | string }) {
  return (
    <Card className="p-5">
      <div className="text-xs uppercase text-muted-foreground">{label}</div>
      <div className="text-2xl font-bold mt-1">
        {typeof value === "number" ? value.toLocaleString() : value}
      </div>
    </Card>
  );
}
