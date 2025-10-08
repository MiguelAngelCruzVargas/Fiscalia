export async function getOrCreateDefaultCompany(supabase) {
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) throw new Error('Sesión no encontrada')

  const { data: existing, error: selErr } = await supabase
    .from('companies')
    .select('id, name')
    .eq('owner_id', user.id)
    .limit(1)
  if (selErr) throw selErr
  if (existing && existing.length) return existing[0].id

  // Intentar usar datos del perfil fiscal si existen
  let defaultName = 'Mi Empresa'
  let defaultRfc = 'XAXX010101000' // RFC genérico de prueba
  try {
    const { data: profile } = await supabase
      .from('profiles')
      .select('rfc, legal_name, first_name, last_name')
      .eq('user_id', user.id)
      .maybeSingle()
    const displayName = profile?.legal_name?.trim() || [profile?.first_name, profile?.last_name].filter(Boolean).join(' ').trim()
    if (displayName) defaultName = displayName
    if (profile?.rfc) defaultRfc = String(profile.rfc).toUpperCase()
  } catch {}
  const { data: inserted, error: insErr } = await supabase
    .from('companies')
    .insert({ owner_id: user.id, rfc: defaultRfc, name: defaultName })
    .select('id')
    .limit(1)
  if (insErr) throw insErr
  return inserted?.[0]?.id
}

// Crea o actualiza la empresa por defecto con los datos del perfil.
// Devuelve { id, name, rfc } de la empresa.
export async function syncCompanyFromProfile(supabase) {
  const { data: { user } } = await supabase.auth.getUser()
  if (!user) throw new Error('Sesión no encontrada')

  // Datos base del perfil
  const { data: profile, error: profErr } = await supabase
    .from('profiles')
    .select('rfc, legal_name, first_name, last_name')
    .eq('user_id', user.id)
    .maybeSingle()
  if (profErr) throw profErr

  const nameFromProfile = profile?.legal_name?.trim() || [profile?.first_name, profile?.last_name].filter(Boolean).join(' ').trim() || 'Mi Empresa'
  const rfcFromProfile = (profile?.rfc || 'XAXX010101000').toUpperCase()

  // Buscar empresa existente
  const { data: existing, error: selErr } = await supabase
    .from('companies')
    .select('id, name, rfc')
    .eq('owner_id', user.id)
    .limit(1)
  if (selErr) throw selErr

  if (existing && existing.length) {
    const company = existing[0]
    // Solo actualizar si cambió algo relevante
    if ((company.name || '').trim() !== nameFromProfile || (company.rfc || '').toUpperCase() !== rfcFromProfile) {
      const { data: upd, error: updErr } = await supabase
        .from('companies')
        .update({ name: nameFromProfile, rfc: rfcFromProfile })
        .eq('id', company.id)
        .select('id, name, rfc')
        .limit(1)
      if (updErr) throw updErr
      return upd?.[0] || { id: company.id, name: nameFromProfile, rfc: rfcFromProfile }
    }
    return company
  }

  // No existe: crear
  const { data: inserted, error: insErr } = await supabase
    .from('companies')
    .insert({ owner_id: user.id, rfc: rfcFromProfile, name: nameFromProfile })
    .select('id, name, rfc')
    .limit(1)
  if (insErr) throw insErr
  return inserted?.[0]
}
