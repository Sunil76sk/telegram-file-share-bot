import { createFileRoute, Link } from "@tanstack/react-router";

export const Route = createFileRoute("/")({
  head: () => ({
    meta: [
      { title: "Movie Delivery Bot" },
      { name: "description", content: "Telegram bot that delivers movies after channel join verification." },
      { property: "og:title", content: "Movie Delivery Bot" },
      { property: "og:description", content: "Telegram bot that delivers movies after channel join verification." },
    ],
  }),
  component: Home,
});

function Home() {
  return (
    <div className="min-h-screen bg-background text-foreground">
      <div className="max-w-3xl mx-auto px-6 py-24">
        <h1 className="text-5xl font-bold tracking-tight">🎬 Movie Delivery Bot</h1>
        <p className="mt-4 text-lg text-muted-foreground">
          A Telegram bot that converts Instagram traffic into channel members before delivering movie files.
          Force-join, shortener monetization, Telegram-native 2GB storage, admin dashboard.
        </p>
        <div className="mt-8 flex gap-3">
          <Link
            to="/admin"
            className="inline-flex items-center justify-center rounded-md bg-primary px-5 py-2.5 text-sm font-medium text-primary-foreground hover:bg-primary/90"
          >
            Open admin dashboard
          </Link>
          <Link
            to="/auth"
            className="inline-flex items-center justify-center rounded-md border border-input px-5 py-2.5 text-sm font-medium hover:bg-accent"
          >
            Sign in
          </Link>
        </div>

        <div className="mt-16 grid md:grid-cols-2 gap-4">
          {[
            ["🔐 Force-join", "Users must join main + backup channels before access."],
            ["💰 Shortener", "Per-movie deep links you wrap with teraboxlinks.com for revenue."],
            ["📦 Telegram storage", "Files live in private channels. No external cloud needed."],
            ["📊 Analytics", "Views, downloads, and unique users per movie."],
          ].map(([h, d]) => (
            <div key={h} className="rounded-lg border p-5">
              <div className="font-semibold">{h}</div>
              <div className="text-sm text-muted-foreground mt-1">{d}</div>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
