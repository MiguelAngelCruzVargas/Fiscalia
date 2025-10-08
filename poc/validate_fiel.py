import sys, pathlib, re, hashlib
from cryptography import x509
from cryptography.hazmat.primitives.serialization import load_der_private_key, load_pem_private_key
from cryptography.hazmat.primitives import serialization

BASE = pathlib.Path(__file__).parent
CER = BASE / 'fiel.cer'
KEY = BASE / 'fiel.key'
PASSFILE = BASE / 'pass.txt'

print('== Validación e.firma básica ==')

for p in (CER, KEY, PASSFILE):
    if not p.exists():
        print(f'Falta archivo: {p}')
        sys.exit(2)

passphrase = PASSFILE.read_text(encoding='utf-8').splitlines()[0].replace('\ufeff','').strip()
print('Password length:', len(passphrase))

cer_bytes = CER.read_bytes()
key_bytes = KEY.read_bytes()
print('CER size:', len(cer_bytes), 'KEY size:', len(key_bytes))

# Intentar parsear certificado (DER o PEM)
cert = None
last_cert_err = None
for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
    try:
        cert = loader(cer_bytes)
        break
    except Exception as e:
        last_cert_err = e
if cert is None:
    print('ERROR: No se pudo parsear el .cer ->', last_cert_err)
    sys.exit(3)
print('Cert ok - Subject:', cert.subject.rfc4514_string())
print('Vigencia:', cert.not_valid_before, '->', cert.not_valid_after)
print('SHA256(cert):', hashlib.sha256(cer_bytes).hexdigest().upper())

# Detectar si el key parece ser PKCS12 o mal archivo
if b'BEGIN CERTIFICATE' in key_bytes and b'PRIVATE' not in key_bytes:
    print('ERROR: fiel.key contiene un CERTIFICADO, no la llave privada (subiste el .cer dos veces)')
    sys.exit(4)
if b'Bag Attributes' in key_bytes or b'BEGIN PKCS12' in key_bytes:
    print('POSIBLE PKCS#12 (.pfx) renombrado a .key. Convierte con:')
    print('  openssl pkcs12 -in archivo.pfx -out fiel.key -nocerts -nodes')
    print('  openssl pkcs12 -in archivo.pfx -out fiel.cer -clcerts -nokeys')
    sys.exit(5)

priv = None
last_err = None
for loader in (load_der_private_key, load_pem_private_key):
    try:
        priv = loader(key_bytes, password=passphrase.encode('utf-8') if passphrase else None)
        print('Llave privada OK usando', loader.__name__)
        break
    except Exception as e:
        last_err = e
if priv is None:
    print('ERROR: No se pudo abrir la llave privada ->', last_err)
    if 'bad decrypt' in str(last_err).lower():
        print('Hint: contraseña incorrecta o llave no corresponde a este certificado')
    sys.exit(6)

# Verificar que key y cert corresponden
try:
    pub1 = cert.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    pub2 = priv.public_key().public_bytes(serialization.Encoding.DER, serialization.PublicFormat.SubjectPublicKeyInfo)
    if pub1 == pub2:
        print('Match: la llave privada corresponde al certificado.')
    else:
        print('ERROR: llave privada NO corresponde al certificado (pares diferentes).')
except Exception as e:
    print('No se pudo comparar llaves:', e)

# RFC heurístico
import re
rfc_pat = re.compile(r'[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}', re.I)
subj = cert.subject.rfc4514_string().upper()
match = rfc_pat.search(subj)
print('RFC detectado en Subject:' , match.group(0) if match else 'N/A')
print('Fin validación.')
