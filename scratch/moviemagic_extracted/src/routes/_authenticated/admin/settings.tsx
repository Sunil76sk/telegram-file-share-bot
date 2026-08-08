import { createFileRoute } from "@tanstack/react-router";
import { useServerFn } from "@tanstack/react-start";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { AdminShell } from "@/components/AdminShell";
import { getConfig, updateConfig } from "@/lib/admin.functions";
import { registerWebhook, getWebhookInfo } from "@/lib/webhook.functions";
import { Card } from "@/components/ui/card";
import { Button } from "@/components/ui/button";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { toast } from "sonner";

import { AdminErrorBoundary } from "@/components/AdminErrorBoundary";

export const Route = createFileRoute("/_authenticated/admin/settings")({
  component: Settings,
  errorComponent: AdminErrorBoundary,
});


function Settings() {
  const fetchCfg = useServerFn(getConfig);
  const saveCfg = useServerFn(updateConfig);
  const register = useServerFn(registerWebhook);
  const whInfo = useServerFn(getWebhookInfo);
  const qc = useQueryClient();
  const cfg = useQuery({ queryKey: ["cfg"], queryFn: () => fetchCfg() });
  const [form, setForm] = useState<any>({});

  useEffect(() => {
    if (cfg.data) {
      setForm({
        ...cfg.data,
        admin_telegram_ids: (cfg.data.admin_telegram_ids ?? []).join(", "),
      });
    }
  }, [cfg.data]);

  if (!cfg.data) return <AdminShell><p>Loading…</p></AdminShell>;

  async function save() {
    const payload: any = { ...form };
    payload.admin_telegram_ids = String(form.admin_telegram_ids || "")
      .split(",")
      .map((s: string) => s.trim())
      .filter(Boolean)
      .map(Number)
      .filter((n: number) => !isNaN(n));
    for (const k of ["main_channel_id", "backup_join_channel_id", "storage_chat_id", "backup_storage_chat_id"]) {
      if (payload[k] === "" || payload[k] == null) payload[k] = null;
      else payload[k] = Number(payload[k]);
    }
    try {
      await saveCfg({ data: payload });
      toast.success("Saved");
      qc.invalidateQueries({ queryKey: ["cfg"] });
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  async function doRegister() {
    try {
      const r: any = await register({});
      toast.success(`Webhook registered: ${r.url}`);
      qc.invalidateQueries({ queryKey: ["cfg"] });
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  async function showInfo() {
    try {
      const r: any = await whInfo();
      alert(JSON.stringify(r, null, 2));
    } catch (e: any) {
      toast.error(e.message);
    }
  }

  const F = (key: string, label: string, type: string = "text", hint?: string) => (
    <div>
      <Label>{label}</Label>
      <Input
        type={type}
        value={form[key] ?? ""}
        onChange={(e) => setForm({ ...form, [key]: e.target.value })}
      />
      {hint && <p className="text-xs text-muted-foreground mt-1">{hint}</p>}
    </div>
  );

  return (
    <AdminShell>
      <h1 className="text-3xl font-bold mb-6">Settings</h1>

      <Card className="p-6 mb-6">
        <h2 className="font-semibold mb-4">Telegram webhook</h2>
        <p className="text-sm text-muted-foreground mb-3">
          Registers this app as the bot's webhook so Telegram delivers updates here.
        </p>
        <div className="flex gap-2">
          <Button onClick={doRegister}>Register webhook</Button>
          <Button variant="outline" onClick={showInfo}>View status</Button>
        </div>
        {cfg.data.bot_username && (
          <p className="text-xs text-muted-foreground mt-3">Bot: @{cfg.data.bot_username}</p>
        )}
      </Card>

      <Card className="p-6 mb-6 grid gap-4">
        <h2 className="font-semibold">Channels</h2>
        {F("main_channel_id", "Main channel ID", "number", "e.g. -1001234567890")}
        {F("main_channel_username", "Main channel username", "text", "without @, used for the Join button")}
        {F("backup_join_channel_id", "Backup-join channel ID", "number")}
        {F("backup_join_channel_username", "Backup-join channel username")}
        {F("storage_chat_id", "Storage channel ID", "number", "Private channel where movie files are stored")}
        {F("backup_storage_chat_id", "Backup-storage channel ID", "number")}
      </Card>

      <Card className="p-6 mb-6 grid gap-4">
        <h2 className="font-semibold">Admins & bot</h2>
        {F("bot_username", "Bot username", "text", "without @")}
        {F("admin_telegram_ids", "Admin Telegram IDs", "text", "Comma-separated user IDs. Use /myid in the bot to get yours.")}
      </Card>

      <Card className="p-6 mb-6 grid gap-4">
        <h2 className="font-semibold">Shortener</h2>
        <p className="text-sm text-muted-foreground">
          Manual flow with teraboxlinks.com: copy the per-movie deep link from the Movies page and paste it into the teraboxlinks dashboard to mint a monetized URL for Instagram.
        </p>
      </Card>

      <Button onClick={save} size="lg">Save changes</Button>
    </AdminShell>
  );
}
