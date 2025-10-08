-- Policies para bucket privado 'cfdi-xml' con prefijo por usuario
-- Crea un bucket PRIVADO llamado 'cfdi-xml' y aplica estas policies en Supabase SQL editor

drop policy if exists "cfdi-xml-insert-own-folder" on storage.objects;
create policy "cfdi-xml-insert-own-folder"
  on storage.objects for insert to authenticated
  with check (
    bucket_id = 'cfdi-xml'
    and split_part(name, '/', 1) = auth.uid()::text
  );

drop policy if exists "cfdi-xml-select-own" on storage.objects;
create policy "cfdi-xml-select-own"
  on storage.objects for select to authenticated
  using (
    bucket_id = 'cfdi-xml'
    and split_part(name, '/', 1) = auth.uid()::text
  );

drop policy if exists "cfdi-xml-update-own" on storage.objects;
create policy "cfdi-xml-update-own"
  on storage.objects for update to authenticated
  using (
    bucket_id = 'cfdi-xml'
    and split_part(name, '/', 1) = auth.uid()::text
  )
  with check (
    bucket_id = 'cfdi-xml'
    and split_part(name, '/', 1) = auth.uid()::text
  );

drop policy if exists "cfdi-xml-delete-own" on storage.objects;
create policy "cfdi-xml-delete-own"
  on storage.objects for delete to authenticated
  using (
    bucket_id = 'cfdi-xml'
    and split_part(name, '/', 1) = auth.uid()::text
  );

-- Sube los XML bajo: {auth.uid()}/{company_id}/{uuid}.xml