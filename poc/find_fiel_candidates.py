import os, pathlib, fnmatch

ROOT = pathlib.Path(__file__).resolve().parent.parent
EXCLUDE_DIRS = {'external', '.venv', 'node_modules', '.git', '__pycache__'}
cer_files = []
key_files = []
for base, dirs, files in os.walk(ROOT):
    # prune
    segs = set(pathlib.Path(base).parts)
    if any(d in EXCLUDE_DIRS for d in segs):
        continue
    for f in files:
        lf = f.lower()
        if lf.endswith('.cer') and len(lf) < 80:
            cer_files.append(os.path.join(base, f))
        elif lf.endswith('.key') and len(lf) < 80:
            key_files.append(os.path.join(base, f))

print('== Posibles certificados (.cer) ==')
for p in cer_files:
    print(p)
print('\n== Posibles llaves (.key) ==')
for p in key_files:
    print(p)

print('\nPara usar en la POC:')
print('  Copia el par correcto a poc/fiel.cer y poc/fiel.key y crea poc/pass.txt con la contraseña en la primera línea.')
