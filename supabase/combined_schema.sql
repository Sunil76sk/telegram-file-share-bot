
-- Roles
CREATE TYPE public.app_role AS ENUM ('admin', 'user');

CREATE TABLE public.user_roles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  user_id UUID NOT NULL REFERENCES auth.users(id) ON DELETE CASCADE,
  role app_role NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (user_id, role)
);
GRANT SELECT ON public.user_roles TO authenticated;
GRANT ALL ON public.user_roles TO service_role;
ALTER TABLE public.user_roles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "users read own roles" ON public.user_roles FOR SELECT TO authenticated USING (auth.uid() = user_id);

CREATE OR REPLACE FUNCTION public.has_role(_user_id UUID, _role app_role)
RETURNS BOOLEAN LANGUAGE SQL STABLE SECURITY DEFINER SET search_path = public AS $$
  SELECT EXISTS (SELECT 1 FROM public.user_roles WHERE user_id = _user_id AND role = _role)
$$;

-- Profiles (Telegram users)
CREATE TABLE public.profiles (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  telegram_user_id BIGINT NOT NULL UNIQUE,
  username TEXT,
  first_name TEXT,
  joined_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  last_seen_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.profiles TO authenticated;
GRANT ALL ON public.profiles TO service_role;
ALTER TABLE public.profiles ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read profiles" ON public.profiles FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- Movies
CREATE TABLE public.movies (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  title TEXT NOT NULL,
  language TEXT,
  year INT,
  genre TEXT,
  rating NUMERIC(3,1),
  poster_file_id TEXT,
  movie_file_id TEXT NOT NULL,
  file_unique_id TEXT NOT NULL UNIQUE,
  file_size BIGINT,
  storage_chat_id BIGINT NOT NULL,
  storage_message_id BIGINT NOT NULL,
  backup_message_id BIGINT,
  shortener_url TEXT,
  created_by_telegram_id BIGINT,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.movies TO authenticated;
GRANT INSERT, UPDATE, DELETE ON public.movies TO authenticated;
GRANT ALL ON public.movies TO service_role;
ALTER TABLE public.movies ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authed read movies" ON public.movies FOR SELECT TO authenticated USING (true);
CREATE POLICY "admins write movies" ON public.movies FOR INSERT TO authenticated WITH CHECK (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "admins update movies" ON public.movies FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE POLICY "admins delete movies" ON public.movies FOR DELETE TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- Analytics events
CREATE TABLE public.movie_views (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
  telegram_user_id BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.movie_views TO authenticated;
GRANT ALL ON public.movie_views TO service_role;
ALTER TABLE public.movie_views ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read views" ON public.movie_views FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE INDEX idx_movie_views_movie ON public.movie_views(movie_id);

CREATE TABLE public.downloads (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
  telegram_user_id BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT SELECT ON public.downloads TO authenticated;
GRANT ALL ON public.downloads TO service_role;
ALTER TABLE public.downloads ENABLE ROW LEVEL SECURITY;
CREATE POLICY "admins read downloads" ON public.downloads FOR SELECT TO authenticated USING (public.has_role(auth.uid(), 'admin'));
CREATE INDEX idx_downloads_movie ON public.downloads(movie_id);
CREATE INDEX idx_downloads_user ON public.downloads(telegram_user_id);

-- Upload wizard state
CREATE TABLE public.upload_sessions (
  telegram_user_id BIGINT PRIMARY KEY,
  step TEXT NOT NULL,
  draft JSONB NOT NULL DEFAULT '{}'::jsonb,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
GRANT ALL ON public.upload_sessions TO service_role;
ALTER TABLE public.upload_sessions ENABLE ROW LEVEL SECURITY;

-- Bot config (singleton)
CREATE TABLE public.bot_config (
  id INT PRIMARY KEY DEFAULT 1 CHECK (id = 1),
  main_channel_id BIGINT,
  main_channel_username TEXT,
  backup_join_channel_id BIGINT,
  backup_join_channel_username TEXT,
  storage_chat_id BIGINT,
  backup_storage_chat_id BIGINT,
  admin_telegram_ids BIGINT[] NOT NULL DEFAULT '{}',
  shortener_api_key TEXT,
  bot_username TEXT,
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);
INSERT INTO public.bot_config (id) VALUES (1) ON CONFLICT DO NOTHING;
GRANT SELECT ON public.bot_config TO authenticated;
GRANT ALL ON public.bot_config TO service_role;
ALTER TABLE public.bot_config ENABLE ROW LEVEL SECURITY;
CREATE POLICY "authed read config" ON public.bot_config FOR SELECT TO authenticated USING (true);
CREATE POLICY "admins update config" ON public.bot_config FOR UPDATE TO authenticated USING (public.has_role(auth.uid(), 'admin'));

-- updated_at trigger
CREATE OR REPLACE FUNCTION public.tg_set_updated_at() RETURNS TRIGGER LANGUAGE plpgsql AS $$
BEGIN NEW.updated_at = now(); RETURN NEW; END $$;
CREATE TRIGGER trg_movies_updated BEFORE UPDATE ON public.movies FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();
CREATE TRIGGER trg_bot_config_updated BEFORE UPDATE ON public.bot_config FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();
CREATE TRIGGER trg_upload_sessions_updated BEFORE UPDATE ON public.upload_sessions FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

-- Auto-grant admin role to the first signed-up user (bootstrap)
CREATE OR REPLACE FUNCTION public.bootstrap_first_admin() RETURNS TRIGGER LANGUAGE plpgsql SECURITY DEFINER SET search_path = public AS $$
BEGIN
  IF NOT EXISTS (SELECT 1 FROM public.user_roles WHERE role = 'admin') THEN
    INSERT INTO public.user_roles (user_id, role) VALUES (NEW.id, 'admin');
  END IF;
  RETURN NEW;
END $$;
CREATE TRIGGER trg_bootstrap_first_admin AFTER INSERT ON auth.users FOR EACH ROW EXECUTE FUNCTION public.bootstrap_first_admin();

ALTER FUNCTION public.tg_set_updated_at() SET search_path = public;

REVOKE EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO service_role;

REVOKE EXECUTE ON FUNCTION public.bootstrap_first_admin() FROM PUBLIC, anon, authenticated;

CREATE POLICY "service only" ON public.upload_sessions FOR SELECT TO authenticated USING (false);

GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated;

create table if not exists public.scheduled_deletions (
  id bigserial primary key,
  chat_id bigint not null,
  message_id bigint not null,
  delete_at timestamptz not null,
  created_at timestamptz not null default now()
);
grant all on public.scheduled_deletions to service_role;
grant usage, select on sequence public.scheduled_deletions_id_seq to service_role;
alter table public.scheduled_deletions enable row level security;
create index if not exists idx_scheduled_deletions_due on public.scheduled_deletions (delete_at);
GRANT ALL ON public.scheduled_deletions TO service_role;
GRANT SELECT, INSERT, UPDATE, DELETE ON public.scheduled_deletions TO authenticated;

ALTER TABLE public.movies
  ADD COLUMN IF NOT EXISTS deep_link text,
  ADD COLUMN IF NOT EXISTS short_url text,
  ADD COLUMN IF NOT EXISTS shortener_status text NOT NULL DEFAULT 'pending',
  ADD COLUMN IF NOT EXISTS shortener_last_error text;

ALTER TABLE public.movies
  DROP CONSTRAINT IF EXISTS movies_shortener_status_check;
ALTER TABLE public.movies
  ADD CONSTRAINT movies_shortener_status_check
  CHECK (shortener_status IN ('pending','success','failed','disabled'));

ALTER TABLE public.movies
  ADD COLUMN IF NOT EXISTS content_type TEXT NOT NULL DEFAULT 'movie'
  CHECK (content_type IN ('movie','series'));

-- Movies created via /uploadseries don't carry a primary file; relax NOT NULL on those fields.
ALTER TABLE public.movies ALTER COLUMN movie_file_id DROP NOT NULL;
ALTER TABLE public.movies ALTER COLUMN file_unique_id DROP NOT NULL;
ALTER TABLE public.movies ALTER COLUMN storage_chat_id DROP NOT NULL;
ALTER TABLE public.movies ALTER COLUMN storage_message_id DROP NOT NULL;

CREATE TABLE IF NOT EXISTS public.series_episodes (
  id UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  movie_id UUID NOT NULL REFERENCES public.movies(id) ON DELETE CASCADE,
  season_number INT NOT NULL CHECK (season_number >= 1 AND season_number <= 100),
  episode_number INT NOT NULL CHECK (episode_number >= 1 AND episode_number <= 1000),
  title TEXT,
  file_unique_id TEXT NOT NULL,
  file_id TEXT NOT NULL,
  file_size BIGINT,
  storage_chat_id BIGINT NOT NULL,
  storage_message_id BIGINT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (movie_id, season_number, episode_number),
  UNIQUE (movie_id, file_unique_id)
);

CREATE INDEX IF NOT EXISTS series_episodes_movie_idx
  ON public.series_episodes (movie_id, season_number, episode_number);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.series_episodes TO authenticated;
GRANT ALL ON public.series_episodes TO service_role;

ALTER TABLE public.series_episodes ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins can read episodes"
  ON public.series_episodes FOR SELECT
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'));

CREATE POLICY "Admins can modify episodes"
  ON public.series_episodes FOR ALL
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

ALTER TABLE public.movie_views ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE public.downloads ADD COLUMN IF NOT EXISTS source TEXT;
CREATE INDEX IF NOT EXISTS movie_views_created_at_idx ON public.movie_views (created_at DESC);
CREATE INDEX IF NOT EXISTS downloads_created_at_idx ON public.downloads (created_at DESC);
CREATE INDEX IF NOT EXISTS movie_views_source_idx ON public.movie_views (source);
CREATE INDEX IF NOT EXISTS downloads_source_idx ON public.downloads (source);
DROP POLICY IF EXISTS "authed read config" ON public.bot_config;
CREATE POLICY "admins read config" ON public.bot_config
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::app_role));
-- 1. Movies: admins only for SELECT (webhook uses service_role and bypasses RLS)
DROP POLICY IF EXISTS "authed read movies" ON public.movies;
CREATE POLICY "admins read movies" ON public.movies
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::app_role));

-- 2. Series episodes: same lockdown
DROP POLICY IF EXISTS "authed read episodes" ON public.series_episodes;
CREATE POLICY "admins read episodes" ON public.series_episodes
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::app_role));

-- 3. has_role: restrict EXECUTE to authenticated only
REVOKE ALL ON FUNCTION public.has_role(uuid, public.app_role) FROM PUBLIC, anon;
GRANT EXECUTE ON FUNCTION public.has_role(uuid, public.app_role) TO authenticated, service_role;

-- 4. Trigger helpers: never callable via the API (triggers still work — they run as table owner)
REVOKE ALL ON FUNCTION public.bootstrap_first_admin() FROM PUBLIC, anon, authenticated;
REVOKE ALL ON FUNCTION public.tg_set_updated_at() FROM PUBLIC, anon, authenticated;
GRANT EXECUTE ON FUNCTION public.bootstrap_first_admin() TO service_role;
GRANT EXECUTE ON FUNCTION public.tg_set_updated_at() TO service_role;

CREATE TABLE public.channel_posts (
  id UUID NOT NULL DEFAULT gen_random_uuid() PRIMARY KEY,
  caption TEXT NOT NULL,
  photo_url TEXT,
  buttons JSONB NOT NULL DEFAULT '[]'::jsonb,
  scheduled_at TIMESTAMPTZ,
  status TEXT NOT NULL DEFAULT 'pending' CHECK (status IN ('pending','sent','failed','cancelled')),
  telegram_message_id BIGINT,
  auto_repost_hours INTEGER,
  last_sent_at TIMESTAMPTZ,
  error TEXT,
  created_by UUID REFERENCES auth.users(id) ON DELETE SET NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT now(),
  updated_at TIMESTAMPTZ NOT NULL DEFAULT now()
);

GRANT SELECT, INSERT, UPDATE, DELETE ON public.channel_posts TO authenticated;
GRANT ALL ON public.channel_posts TO service_role;

ALTER TABLE public.channel_posts ENABLE ROW LEVEL SECURITY;

CREATE POLICY "Admins manage channel_posts"
  ON public.channel_posts FOR ALL
  TO authenticated
  USING (public.has_role(auth.uid(), 'admin'))
  WITH CHECK (public.has_role(auth.uid(), 'admin'));

CREATE TRIGGER trg_channel_posts_updated_at
  BEFORE UPDATE ON public.channel_posts
  FOR EACH ROW EXECUTE FUNCTION public.tg_set_updated_at();

CREATE INDEX idx_channel_posts_status_scheduled ON public.channel_posts(status, scheduled_at);
CREATE INDEX idx_channel_posts_created_at ON public.channel_posts(created_at DESC);
ALTER TABLE public.channel_posts
  ADD COLUMN IF NOT EXISTS image_link_url text;
