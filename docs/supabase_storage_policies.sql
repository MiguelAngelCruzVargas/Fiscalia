-- Policies para bucket privado 'fiscalia' con prefijo por usuario
-- Requisitos: crear bucket 'fiscalia' (PRIVADO) en Storage
-- Nota: si tu bucket tiene otro nombre, reemplaza 'fiscalia' en las policies

-- Habilitar RLS en objetos de storage
-- En Supabase ya existen tablas 'storage.objects'

drop policy if exists "fiscalia-insert-own-folder" on storage.objects;
create policy "fiscalia-insert-own-folder"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'fiscalia'
    and split_part(name, '/', 1) = auth.uid()::text
  );

drop policy if exists "fiscalia-select-own" on storage.objects;
create policy "fiscalia-select-own"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'fiscalia'
    and split_part(name, '/', 1) = auth.uid()::text
  );

drop policy if exists "fiscalia-update-own" on storage.objects;
create policy "fiscalia-update-own"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'fiscalia'
    and split_part(name, '/', 1) = auth.uid()::text
  )
  with check (
    bucket_id = 'fiscalia'
    and split_part(name, '/', 1) = auth.uid()::text
  );

drop policy if exists "fiscalia-delete-own" on storage.objects;
create policy "fiscalia-delete-own"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'fiscalia'
    and split_part(name, '/', 1) = auth.uid()::text
  );

-- Opcional: si prefieres una función más robusta para extraer el prefijo, crea una SQL function
-- y reutiliza en las policies.
