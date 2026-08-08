
ALTER TABLE public.movie_views ADD COLUMN IF NOT EXISTS source TEXT;
ALTER TABLE public.downloads ADD COLUMN IF NOT EXISTS source TEXT;
CREATE INDEX IF NOT EXISTS movie_views_created_at_idx ON public.movie_views (created_at DESC);
CREATE INDEX IF NOT EXISTS downloads_created_at_idx ON public.downloads (created_at DESC);
CREATE INDEX IF NOT EXISTS movie_views_source_idx ON public.movie_views (source);
CREATE INDEX IF NOT EXISTS downloads_source_idx ON public.downloads (source);
