from fastapi import APIRouter, HTTPException, Query
from pydantic import BaseModel
from typing import List, Optional, Dict
from ..supabase_client import get_supabase
import os

router = APIRouter()


class MonthlyRow(BaseModel):
    periodo: str  # YYYY-MM
    ingresos: float
    egresos: float
    iva_cobrado: float
    iva_acreditable: float
    iva_a_pagar: float
    isr_base: float
    isr: float


def _get_company_and_regime(sb, company_id: str) -> Dict[str, Optional[str]]:
    comp = sb.table('companies').select('rfc, owner_id').eq('id', company_id).maybe_single().execute()
    if not getattr(comp, 'data', None):
        raise RuntimeError('Compañía no encontrada')
    company_rfc = (comp.data.get('rfc') or '').upper()
    owner_id = comp.data.get('owner_id')
    regime = None
    if owner_id:
        prof = sb.table('profiles').select('regime').eq('user_id', owner_id).maybe_single().execute()
        regime = (getattr(prof, 'data', {}) or {}).get('regime')
    return { 'rfc': company_rfc, 'regime': regime }


@router.get('/monthly', response_model=List[MonthlyRow])
def monthly_summary(company_id: str = Query(..., description="UUID de la compañía"), persist: bool = False):
    try:
        sb = get_supabase()
        meta = _get_company_and_regime(sb, company_id)
        company_rfc = meta['rfc']
        regime = (meta['regime'] or '').lower()

        # Tasas configurables
        isr_rate_resico = float(os.environ.get('ISR_RATE_RESICO', '0.0125'))
        isr_rate_default = float(os.environ.get('ISR_RATE_DEFAULT', '0.30'))
        isr_rate = isr_rate_resico if ('resico' in regime) else isr_rate_default

        res = sb.table('cfdi').select('fecha,total,impuestos,emisor_rfc,receptor_rfc').eq('company_id', company_id).execute()
        rows = getattr(res, 'data', []) or []
        agg: Dict[str, Dict[str, float]] = {}

        for r in rows:
            fecha = (r.get('fecha') or '')
            ym = str(fecha)[:7]
            if len(ym) != 7:
                continue
            bucket = agg.setdefault(ym, { 'ingresos': 0.0, 'egresos': 0.0, 'iva_cobrado': 0.0, 'iva_acreditable': 0.0 })
            total = float(r.get('total') or 0)
            iva = r.get('impuestos')
            if iva is None:
                iva = round(total * 0.16, 2)  # aproximación si no hay desglose
            else:
                iva = float(iva or 0)

            emisor = (r.get('emisor_rfc') or '').upper()
            receptor = (r.get('receptor_rfc') or '').upper()
            if emisor == company_rfc:
                bucket['ingresos'] += total
                bucket['iva_cobrado'] += iva
            if receptor == company_rfc:
                bucket['egresos'] += total
                bucket['iva_acreditable'] += iva

        out: List[MonthlyRow] = []
        for ym in sorted(agg.keys()):
            v = agg[ym]
            isr_base = max(v['ingresos'] - v['egresos'], 0.0)
            isr = round(isr_base * isr_rate, 2)
            iva_a_pagar = round(v['iva_cobrado'] - v['iva_acreditable'], 2)
            row = MonthlyRow(
                periodo=ym,
                ingresos=round(v['ingresos'], 2),
                egresos=round(v['egresos'], 2),
                iva_cobrado=round(v['iva_cobrado'], 2),
                iva_acreditable=round(v['iva_acreditable'], 2),
                iva_a_pagar=iva_a_pagar,
                isr_base=round(isr_base, 2),
                isr=isr,
            )
            out.append(row)

        if persist:
            # Guardar en taxes_monthly (upsert-like: update si existe)
            for row in out:
                rec = {
                    'company_id': company_id,
                    'periodo': f"{row.periodo}-01",
                    'isr_base': row.isr_base,
                    'isr': row.isr,
                    'iva_cobrado': row.iva_cobrado,
                    'iva_acreditable': row.iva_acreditable,
                    'iva_a_pagar': row.iva_a_pagar,
                }
                try:
                    sb.table('taxes_monthly').insert(rec).execute()
                except Exception:
                    sb.table('taxes_monthly').update(rec).eq('company_id', company_id).eq('periodo', rec['periodo']).execute()

        return out
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
