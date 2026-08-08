DROP POLICY IF EXISTS "authed read config" ON public.bot_config;
CREATE POLICY "admins read config" ON public.bot_config
  FOR SELECT TO authenticated
  USING (public.has_role(auth.uid(), 'admin'::app_role));