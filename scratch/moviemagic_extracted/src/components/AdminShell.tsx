import { Link, useRouter } from "@tanstack/react-router";
import { ReactNode } from "react";
import { supabase } from "@/integrations/supabase/client";
import { Button } from "@/components/ui/button";

export function AdminShell({ children }: { children: ReactNode }) {
  const router = useRouter();
  async function signOut() {
    await supabase.auth.signOut();
    router.navigate({ to: "/auth" });
  }
  return (
    <div className="min-h-screen bg-background">
      <header className="border-b">
        <div className="max-w-6xl mx-auto px-6 h-14 flex items-center justify-between">
          <div className="flex items-center gap-6">
            <Link to="/admin" className="font-bold">🎬 Movie Bot</Link>
            <nav className="flex items-center gap-4 text-sm">
              <Link to="/admin" activeProps={{ className: "font-semibold" }}>Dashboard</Link>
              <Link to="/admin/movies" activeProps={{ className: "font-semibold" }}>Movies</Link>
              <Link to="/admin/posts" activeProps={{ className: "font-semibold" }}>Posts</Link>
              <Link to="/admin/analytics" activeProps={{ className: "font-semibold" }}>Analytics</Link>
              <Link to="/admin/settings" activeProps={{ className: "font-semibold" }}>Settings</Link>
            </nav>
          </div>
          <Button size="sm" variant="ghost" onClick={signOut}>Sign out</Button>
        </div>
      </header>
      <main className="max-w-6xl mx-auto px-6 py-8">{children}</main>
    </div>
  );
}
