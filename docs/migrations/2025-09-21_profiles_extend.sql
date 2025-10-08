-- Extiende tabla profiles con datos personales requeridos por la app
-- Ejecuta esto en Supabase SQL editor sobre tu base de datos del proyecto

do $$ begin
	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'first_name'
	) then alter table public.profiles add column first_name text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'last_name'
	) then alter table public.profiles add column last_name text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'curp'
	) then alter table public.profiles add column curp text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'street'
	) then alter table public.profiles add column street text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'ext_number'
	) then alter table public.profiles add column ext_number text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'int_number'
	) then alter table public.profiles add column int_number text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'neighborhood'
	) then alter table public.profiles add column neighborhood text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'city'
	) then alter table public.profiles add column city text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'state'
	) then alter table public.profiles add column state text; end if;

	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'postal_code'
	) then alter table public.profiles add column postal_code text; end if;

		if not exists (
			select 1 from information_schema.columns
			where table_schema = 'public' and table_name = 'profiles' and column_name = 'birth_date'
		) then alter table public.profiles add column birth_date date; end if;

		if not exists (
			select 1 from information_schema.columns
			where table_schema = 'public' and table_name = 'profiles' and column_name = 'gender'
		) then alter table public.profiles add column gender text; end if;

		if not exists (
			select 1 from information_schema.columns
			where table_schema = 'public' and table_name = 'profiles' and column_name = 'birth_state'
		) then alter table public.profiles add column birth_state text; end if;
end $$;

-- Índices útiles
create index if not exists idx_profiles_user_id on public.profiles(user_id);
create index if not exists idx_profiles_rfc on public.profiles(rfc);
create index if not exists idx_profiles_curp on public.profiles(curp);

-- Tipo de persona (física=false, moral=true). Se detecta automáticamente de RFC/.cer, pero se guarda para UX.
do $$ begin
	if not exists (
		select 1 from information_schema.columns
		where table_schema = 'public' and table_name = 'profiles' and column_name = 'persona_moral'
	) then alter table public.profiles add column persona_moral boolean; end if;
end $$;
