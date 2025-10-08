import sys, pathlib, hashlib

EXTS = {'.cer','.key','.pfx','.pem'}

def main():
    if len(sys.argv) < 2:
        print('Uso: python poc/list_firma_dir.py "RUTA_CARPETA"')
        return 1
    base = pathlib.Path(sys.argv[1]).expanduser().resolve()
    if not base.exists():
        print('No existe:', base)
        return 2
    print('Escaneando:', base)
    rows = []
    for p in base.rglob('*'):
        if p.is_file() and p.suffix.lower() in EXTS:
            try:
                size = p.stat().st_size
            except Exception:
                size = -1
            # Hash SHA1 de primeros bytes para ver si dos archivos son iguales sin leer todo
            try:
                head = p.open('rb').read(64)
                head_hex = head.hex().upper()[:64]
            except Exception:
                head_hex = 'ERR'
            rows.append((p, size, p.suffix.lower(), head_hex))
    if not rows:
        print('No se encontraron archivos candidatos (.cer/.key/.pfx/.pem).')
        return 0
    print('\nArchivos encontrados:')
    for p,size,ext,head in rows:
        print(f'{ext}\t{size:>8}\t{p}\n  head_hex={head}')
    print('\nSugerencias:')
    print('- Normalmente tendrás un par .cer (certificado) y .key (llave) de tamaño > 1KB.')
    print('- Si sólo ves .pfx conviértelo a .cer/.key (te diré comandos).')
    print('- Copia el par correcto a poc/fiel.cer y poc/fiel.key y la contraseña a poc/pass.txt')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
