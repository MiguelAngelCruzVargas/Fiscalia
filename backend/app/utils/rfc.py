import re
from datetime import datetime
from typing import Optional, Dict

# Patrones SAT (simplificados) para RFC:
# Persona moral: 3 letras/&/Ñ + 6 dígitos fecha + 3 homoclave
# Persona física: 4 letras (incluye Ñ & ampersand) + 6 dígitos fecha + 3 homoclave
_MORAL_RE = re.compile(r'^[A-Z&Ñ]{3}\d{6}[A-Z0-9]{3}$', re.IGNORECASE)
_FISICA_RE = re.compile(r'^[A-Z&Ñ]{4}\d{6}[A-Z0-9]{3}$', re.IGNORECASE)
_GENERAL_RE = re.compile(r'^[A-Z&Ñ]{3,4}\d{6}[A-Z0-9]{3}$', re.IGNORECASE)

def _valid_date_fragment(rfc: str) -> bool:
    """Valida la parte de fecha (YYMMDD) considerando ventana 1930- (año actual + 1)."""
    try:
        if len(rfc) not in (12,13):
            return False
        # posiciones de fecha dependen de longitud del prefijo (3 o 4)
        start = 3 if len(rfc)==12 else 4
        frag = rfc[start:start+6]
        yy = int(frag[0:2])
        mm = int(frag[2:4])
        dd = int(frag[4:6])
        # Interpretación de siglo: si yy > año actual % 100 => 1900 + yy, else 2000 + yy (heurística SAT común)
        current_two = int(datetime.utcnow().strftime('%y'))
        year = 1900 + yy if yy > current_two else 2000 + yy
        if year < 1930 or year > datetime.utcnow().year + 1:
            return False
        datetime(year, mm, dd)
        return True
    except Exception:
        return False

def classify_rfc(rfc: str) -> Dict[str, Optional[object]]:
    rfc = (rfc or '').strip().upper()
    if not rfc:
        return { 'valid': False, 'normalized': None, 'persona_moral': None, 'error': 'vacío' }
    if not _GENERAL_RE.match(rfc):
        return { 'valid': False, 'normalized': rfc, 'persona_moral': None, 'error': 'patrón inválido' }
    if not _valid_date_fragment(rfc):
        return { 'valid': False, 'normalized': rfc, 'persona_moral': None, 'error': 'fecha inválida' }
    is_moral = bool(_MORAL_RE.match(rfc)) and len(rfc)==12
    is_fisica = bool(_FISICA_RE.match(rfc)) and len(rfc)==13
    if not (is_moral or is_fisica):
        # Si cae aquí es porque patrón general coincide pero no entró en específicos (raro)
        return { 'valid': False, 'normalized': rfc, 'persona_moral': None, 'error': 'no coincide con reglas de física/moral' }
    return { 'valid': True, 'normalized': rfc, 'persona_moral': True if is_moral else False, 'error': None }

__all__ = ['classify_rfc']
