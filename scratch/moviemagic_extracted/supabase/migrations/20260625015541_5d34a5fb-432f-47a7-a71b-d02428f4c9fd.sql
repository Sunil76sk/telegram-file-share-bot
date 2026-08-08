
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
