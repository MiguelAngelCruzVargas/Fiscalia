const ENTITY_MAP = {
  AS: 'AGUASCALIENTES',
  BC: 'BAJA CALIFORNIA',
  BS: 'BAJA CALIFORNIA SUR',
  CC: 'CAMPECHE',
  CL: 'COAHUILA',
  CM: 'COLIMA',
  CS: 'CHIAPAS',
  CH: 'CHIHUAHUA',
  DF: 'CIUDAD DE MÉXICO',
  DG: 'DURANGO',
  GT: 'GUANAJUATO',
  GR: 'GUERRERO',
  HG: 'HIDALGO',
  JC: 'JALISCO',
  MC: 'MÉXICO',
  MN: 'MICHOACÁN',
  MS: 'MORELOS',
  NT: 'NAYARIT',
  NL: 'NUEVO LEÓN',
  OC: 'OAXACA',
  PL: 'PUEBLA',
  QT: 'QUERÉTARO',
  QR: 'QUINTANA ROO',
  SP: 'SAN LUIS POTOSÍ',
  SL: 'SINALOA',
  SR: 'SONORA',
  TC: 'TABASCO',
  TS: 'TAMAULIPAS',
  TL: 'TLAXCALA',
  VZ: 'VERACRUZ',
  YN: 'YUCATÁN',
  ZS: 'ZACATECAS',
  NE: 'NACIDO EN EL EXTRANJERO'
}

export function parseCurp(curp) {
  if (!curp) return null
  const s = String(curp).toUpperCase().trim()
  const m = s.match(/^[A-Z]{4}(\d{2})(\d{2})(\d{2})([HM])([A-Z]{2})[A-Z]{3}[A-Z0-9]{2}$/)
  if (!m) return null
  const [, yy, mm, dd, sex, ent] = m
  const now = new Date()
  const currentYY = now.getFullYear() % 100
  const year = (parseInt(yy, 10) <= currentYY ? 2000 : 1900) + parseInt(yy, 10)
  const month = parseInt(mm, 10)
  const day = parseInt(dd, 10)
  const birth_date = `${year}-${String(month).padStart(2, '0')}-${String(day).padStart(2, '0')}`
  const gender = sex === 'H' ? 'Hombre' : 'Mujer'
  const birth_state = ENTITY_MAP[ent] || ent
  const rfc_base = s.slice(0, 4) + yy + mm + dd // Primeros 10 del RFC de persona física
  return { birth_date, gender, birth_state, entity_code: ent, rfc_base }
}

export function rfcBaseFromCurp(curp) {
  const s = String(curp || '').toUpperCase().trim()
  const m = s.match(/^[A-Z]{4}(\d{2})(\d{2})(\d{2})[HM][A-Z]{2}/)
  if (!m) return null
  const [, yy, mm, dd] = m
  return s.slice(0, 4) + yy + mm + dd
}
