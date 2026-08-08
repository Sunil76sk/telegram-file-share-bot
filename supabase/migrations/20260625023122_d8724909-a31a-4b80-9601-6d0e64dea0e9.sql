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