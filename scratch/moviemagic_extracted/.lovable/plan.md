
# Movie Delivery Bot — Lovable build plan

Equivalent of your PRD, adapted to Lovable's supported stack. Same UX (Instagram → shortener → bot → force-join → movie page → file), different runtime.

## Stack mapping

| PRD | This build |
|---|---|
| Python 3.11 / Pyrogram | TypeScript on TanStack Start (Cloudflare Workers) |
| MongoDB Atlas | Postgres via Lovable Cloud |
| GitHub Actions deploy | Lovable hosting (GitHub sync available) |
| Long-poll bot | Telegram webhook → `/api/public/telegram/webhook` |
| Telegram storage channel | Same — bot stores `file_id`, never proxies bytes |
| AsyncIO / Motor | Async serverless handlers + Supabase client |

Why: Lovable runs serverless Workers, not a Python process. Telegram's HTTP Bot API + connector gateway covers every feature you listed, and using `file_id` from a storage channel keeps the 2GB limit intact because Telegram holds the bytes.

## Features

1. **Telegram bot (webhook)** with commands:
   - `/start` and `/start <movieId>` (deep-link from shortener) → force-join check → movie page or join prompt.
   - `/uploadmovie` (admin only) → conversational wizard collecting poster, file, title, language, year, genre, rating. Wizard state stored in `upload_sessions` table keyed by admin chat.
   - `/stats` (admin) → totals.
2. **Force-join** for Main + Backup channels via `getChatMember`. "✅ I've Joined" callback re-checks; only then movie buttons appear.
3. **Movie page message**: poster + formatted caption (title, ⭐ rating, 🌎 language, 📅 year, 🎭 genre, 📂 size) + "⬇️ Download" inline button. Download forwards/copies the stored message from the storage channel to the user.
4. **Anti-duplicate** via `file_unique_id` unique index.
5. **Backup channel**: every uploaded file is also copied to the backup storage channel.
6. **Shortener integration**: admin dashboard generates `https://teraboxlinks.com/...` wrapping `t.me/<bot>?start=<movieId>`. Stored per movie; copy-to-clipboard in dashboard. (Teraboxlinks API key optional — if provided, links auto-shorten via their API; otherwise we show the raw deep link to paste into their site.)
7. **Admin web dashboard** (Lovable Cloud auth, admin role):
   - Movies list (search, edit metadata, delete, view shortener link).
   - Per-movie analytics (views, downloads, unique users).
   - Global analytics dashboard.
   - Channel config (main, backup-join, storage, backup-storage channel IDs) editable from UI, stored in `bot_config`.
8. **Analytics**: `views` logged when movie page is shown, `downloads` when file is delivered, unique users derived from `downloads.user_id`.

## Database (Postgres, replaces MongoDB collections)

- `profiles` (id, telegram_user_id, username, joined_at)
- `user_roles` (admin role — separate table per platform rules; `has_role()` security-definer fn)
- `movies` (id, title, language, year, genre, rating, poster_file_id, movie_file_id, file_unique_id UNIQUE, file_size, storage_chat_id, storage_message_id, backup_message_id, created_at)
- `downloads` (id, telegram_user_id, movie_id, created_at) — unique users via `count(distinct telegram_user_id)`
- `movie_views` (id, telegram_user_id, movie_id, created_at)
- `upload_sessions` (admin_telegram_id PK, step, draft jsonb, updated_at)
- `bot_config` (singleton: main_channel_id, backup_join_channel_id, storage_chat_id, backup_storage_chat_id, admin_telegram_ids[])

All tables: RLS on, GRANTs to `authenticated` + `service_role`. Webhook uses `supabaseAdmin` (service role) since Telegram users aren't Supabase users.

## Routes / files

```text
src/routes/api/public/telegram/webhook.ts   # Telegram updates (HMAC-style secret token)
src/routes/_authenticated/admin/index.tsx   # dashboard home
src/routes/_authenticated/admin/movies.tsx  # list/edit
src/routes/_authenticated/admin/analytics.tsx
src/routes/_authenticated/admin/settings.tsx# channel IDs, shortener key
src/routes/auth.tsx                         # email/password + Google
src/routes/index.tsx                        # public landing explaining the bot
src/lib/telegram/*.ts                       # gateway client, force-join, wizard, delivery
src/lib/movies.functions.ts                 # admin server fns (list/update/delete)
```

## Integrations needed

- **Lovable Cloud** (Postgres + auth + storage for any poster previews on dashboard).
- **Telegram connector** (`standard_connectors--connect telegram`) — provides `TELEGRAM_API_KEY` for the gateway. You'll add the bot via BotFather and link it.
- **Teraboxlinks API key** (optional, requested via `add_secret` only after you confirm — needed only for automatic shortening).

## Setup you'll do once

1. Create the bot in BotFather, get the token, link via Telegram connector.
2. Create 4 Telegram channels: Main (public, users must join), Backup-Join (public, users must join), Storage (private, bot is admin), Backup-Storage (private, bot is admin).
3. Add the bot as admin in all four; paste the chat IDs into the dashboard Settings page.
4. Add your Telegram user ID in Settings → Admins to unlock `/uploadmovie`.

## Out of scope vs PRD

- No Python, Pyrogram, Motor, or MongoDB.
- No GitHub Actions workflow file — Lovable handles deploy. GitHub sync available via the Plus menu.
- 2GB upload works only through Telegram itself (admin sends file to bot), not via the web dashboard — serverless can't proxy 2GB.

## Success criteria (same as PRD)

✅ Force-join both channels enforced ✅ Movie delivered via stored `file_id` ✅ Postgres persists metadata + analytics ✅ Views/downloads/unique-users tracked ✅ Deployed on Lovable ✅ 2GB files via Telegram-native storage ✅ Shortener deep-links from Instagram convert into the bot.
