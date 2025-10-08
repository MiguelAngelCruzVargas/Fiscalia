"""Script de prueba integral del flujo SAT usando requests.

Uso:
  py scripts/test_sat_flow.py --backend http://127.0.0.1:8000 \
      --user-id <UUID> --company-id <UUID_COMPANY> --passfile contrasema.txt \
      --kind recibidos --days 5

Genera archivo de resultados en scripts/results/sat_flow_<timestamp>.log
"""
from __future__ import annotations
import argparse, json, time, sys, os
from pathlib import Path
import datetime as dt
import requests

DEF_BACKEND = "http://127.0.0.1:8000"

class FlowLogger:
    def __init__(self, path: Path):
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
    def log(self, msg: str):
        line = f"[{dt.datetime.utcnow().strftime('%H:%M:%S')}] {msg}"
        print(line)
        with self.path.open('a', encoding='utf-8') as fh:
            fh.write(line + '\n')

def post_json(url: str, payload: dict, timeout=60):
    try:
        r = requests.post(url, json=payload, timeout=timeout)
        try:
            data = r.json()
        except Exception:
            data = {'raw': r.text}
        if not r.ok:
            # Normalizar mensaje
            detail = data.get('detail') if isinstance(data, dict) else None
            if isinstance(detail, dict) and 'message' in detail:
                msg = f"{detail.get('message')} ({detail.get('code','')})".strip()
            else:
                msg = detail if isinstance(detail, str) else f"HTTP {r.status_code}"
            return False, msg, data
        return True, None, data
    except requests.RequestException as e:
        return False, str(e), {}

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--backend', default=DEF_BACKEND)
    ap.add_argument('--user-id', default=os.getenv('SAT_TEST_USER_ID'), help='UUID usuario (o SAT_TEST_USER_ID env)')
    ap.add_argument('--company-id', default=os.getenv('SAT_TEST_COMPANY_ID'), help='UUID compañía (o SAT_TEST_COMPANY_ID env)')
    default_pass = os.getenv('SAT_TEST_PASSFILE') or ('contrasema.txt' if Path('contrasema.txt').exists() else None)
    ap.add_argument('--passfile', default=default_pass, help='Archivo con la contraseña (o SAT_TEST_PASSFILE env, default contrasema.txt si existe)')
    ap.add_argument('--kind', default='recibidos', choices=['recibidos','emitidos'])
    ap.add_argument('--days', type=int, default=5)
    ap.add_argument('--skip-job', action='store_true')
    ap.add_argument('--skip-cfdi', action='store_true')
    ap.add_argument('--cfdi-limit', type=int, default=5)
    args = ap.parse_args()

    # Validaciones de argumentos (más amigables que el usage por defecto)
    missing = []
    if not args.user_id:
        missing.append('user-id (o SAT_TEST_USER_ID)')
    if not args.company_id:
        missing.append('company-id (o SAT_TEST_COMPANY_ID)')
    if not args.passfile:
        missing.append('passfile (o SAT_TEST_PASSFILE / contrasema.txt)')
    if missing:
        print('\nFaltan parámetros requeridos: ' + ', '.join(missing), file=sys.stderr)
        print('Ejemplo:\n  py scripts/test_sat_flow.py --backend http://127.0.0.1:8000 \\\n    --user-id <UUID_USER> --company-id <UUID_COMPANY> --passfile contrasema.txt --kind recibidos', file=sys.stderr)
        print('\nO usando variables de entorno en PowerShell:')
        print('  $env:SAT_TEST_USER_ID="..."; $env:SAT_TEST_COMPANY_ID="..."; $env:SAT_TEST_PASSFILE="contrasema.txt"', file=sys.stderr)
        print('  py scripts/test_sat_flow.py --kind recibidos', file=sys.stderr)
        return 2

    pass_path = Path(args.passfile)
    if not pass_path.exists():
        print('Passfile no encontrado:', pass_path, file=sys.stderr)
        return 3
    passphrase = pass_path.read_text(encoding='utf-8').splitlines()[0].strip()

    stamp = dt.datetime.utcnow().strftime('%Y%m%d_%H%M%S')
    out = Path('scripts/results') / f'sat_flow_{stamp}.log'
    logger = FlowLogger(out)
    logger.log(f'Inicio pruebas SAT -> archivo {out}')
    logger.log(f'Backend={args.backend} user={args.user_id} company={args.company_id} kind={args.kind}')

    def step(name, url, payload):
        ok, err, data = post_json(url, payload)
        if ok:
            logger.log(f'{name} OK {json.dumps(data)[:300]}')
            return data
        else:
            logger.log(f'{name} ERROR: {err}')
            return None

    # 1 Inspect
    inspect = step('INSPECT', f'{args.backend}/sat/inspect', {'user_id': args.user_id})
    # 2 Verify
    verify = step('VERIFY', f'{args.backend}/sat/verify', {'user_id': args.user_id, 'passphrase': passphrase})
    # 3 Auth
    auth = step('AUTH', f'{args.backend}/sat/auth', {'user_id': args.user_id, 'passphrase': passphrase})
    # 4 Test-flow
    testflow = step('TEST_FLOW', f'{args.backend}/sat/test-flow', {'user_id': args.user_id, 'passphrase': passphrase, 'kind': args.kind})

    # 5 Job full
    if not args.skip_job:
        df = (dt.datetime.utcnow() - dt.timedelta(days=args.days)).strftime('%Y-%m-%d')
        dt_to = dt.datetime.utcnow().strftime('%Y-%m-%d')
        job = step('JOB_START', f'{args.backend}/sat/sync', {
            'user_id': args.user_id,
            'company_id': args.company_id,
            'kind': args.kind,
            'date_from': df,
            'date_to': dt_to,
            'passphrase': passphrase,
        })
        if job and 'id' in job:
            jid = job['id']
            for i in range(60):
                time.sleep(3)
                try:
                    r = requests.get(f'{args.backend}/sat/jobs/{jid}', timeout=30)
                    data = r.json() if r.headers.get('content-type','').startswith('application/json') else {'raw': r.text}
                    logger.log(f'JOB_POLL {i} status={data.get("status")} found={data.get("total_found")} downloaded={data.get("total_downloaded")}')
                    if data.get('status') not in ('queued','running','verifying'):
                        break
                except Exception as e:
                    logger.log(f'JOB_POLL ERROR {e}')
    if not args.skip_cfdi:
        # Intentar listar cfdi de la compañía
        list_url = f'{args.backend}/sat/cfdi/list'
        try:
            r = requests.get(list_url, params={'company_id': args.company_id, 'limit': args.cfdi_limit}, timeout=30)
            if r.ok:
                ldata = r.json()
                items = ldata.get('items', []) if isinstance(ldata, dict) else []
                logger.log(f'CFDI_LIST count={len(items)}')
                if items:
                    first = items[0]
                    uuid = first.get('uuid')
                    if uuid:
                        # validate
                        vurl = f'{args.backend}/sat/cfdi/{uuid}/validate'
                        vr = requests.get(vurl, timeout=30)
                        if vr.ok:
                            logger.log(f'CFDI_VALIDATE {uuid} {vr.json()}')
                        else:
                            logger.log(f'CFDI_VALIDATE ERROR HTTP {vr.status_code}')
                        # render html
                        hr = requests.get(f'{args.backend}/sat/cfdi/{uuid}/render', params={'format':'html'}, timeout=30)
                        if hr.ok:
                            html_path = Path('scripts/results')/f'cfdi_{uuid}.html'
                            html_path.write_text(hr.text, encoding='utf-8')
                            logger.log(f'CFDI_RENDER_HTML saved={html_path}')
                        # render pdf
                        pr = requests.get(f'{args.backend}/sat/cfdi/{uuid}/render', params={'format':'pdf'}, timeout=60)
                        if pr.ok:
                            pdf_path = Path('scripts/results')/f'cfdi_{uuid}.pdf'
                            pdf_path.write_bytes(pr.content)
                            logger.log(f'CFDI_RENDER_PDF saved={pdf_path}')
                        else:
                            logger.log('CFDI_RENDER_PDF error (tal vez satcfdi sin pdf_bytes)')
            else:
                logger.log(f'CFDI_LIST ERROR HTTP {r.status_code}')
        except Exception as e:
            logger.log(f'CFDI_LIST EXCEPTION {e}')

    logger.log('Fin pruebas SAT')
    print(f'Archivo de resultados: {out}')

if __name__ == '__main__':
    raise SystemExit(main())
