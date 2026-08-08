
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
