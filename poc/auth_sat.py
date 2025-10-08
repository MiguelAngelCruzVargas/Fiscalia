import pathlib, sys, argparse, datetime as dt
from cryptography import x509
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.serialization import load_der_private_key, load_pem_private_key
import httpx, base64, hashlib

WSDL_AUT = 'https://pruebassiaw.siat.sat.gob.mx/ProveedorAutenticacion/ProveedorAutenticacion.svc?wsdl'
# Nota: En producción cambiar a endpoint productivo (esto es ejemplo; ajusta según documentación oficial).

BASE = pathlib.Path(__file__).parent
CER = BASE / 'fiel.cer'
KEY = BASE / 'fiel.key'
PASSFILE = BASE / 'pass.txt'

SOAP_TEMPLATE = """<s:Envelope xmlns:s="http://schemas.xmlsoap.org/soap/envelope/">\n  <s:Body>\n    <Autentica xmlns="http://DescargaMasivaTerceros.sat.gob.mx">\n      <peticionAutenticacion>\n        <FirmaElectronica>\n          <PKCS7>{pkcs7}</PKCS7>\n        </FirmaElectronica>\n      </peticionAutenticacion>\n    </Autentica>\n  </s:Body>\n</s:Envelope>"""

# Simplificado: generación de un PKCS7 detached manual implicaría usar OpenSSL o librerías de firma CMS.
# Aquí haremos sólo carga y hash del certificado como stand-in (NO válido para producción);
# objetivo: aislar problema de la llave, no completar auth real.

def load_cert_key(passphrase: str):
    cer_bytes = CER.read_bytes()
    key_bytes = KEY.read_bytes()
    cert = None
    for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
        try:
            cert = loader(cer_bytes)
            break
        except Exception:
            pass
    if cert is None:
        raise RuntimeError('No se pudo parsear fiel.cer')
    priv = None
    last_err = None
    for loader in (load_der_private_key, load_pem_private_key):
        try:
            priv = loader(key_bytes, password=passphrase.encode('utf-8'))
            break
        except Exception as e:
            last_err = e
    if priv is None:
        raise RuntimeError(f'Llave privada inválida: {last_err}')
    return cert, priv

def fake_pkcs7(cert):
    # Placeholder: base64 de SHA256 del DER
    der = cert.public_bytes(serialization.Encoding.DER)
    h = hashlib.sha256(der).digest()
    return base64.b64encode(h).decode()

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument('--kind', default='recibidos')
    args = ap.parse_args()

    if not CER.exists() or not KEY.exists() or not PASSFILE.exists():
        print('Coloca fiel.cer, fiel.key y pass.txt en poc/')
        return 2
    passphrase = PASSFILE.read_text(encoding='utf-8').splitlines()[0].strip()
    cert, priv = load_cert_key(passphrase)
    pkcs7_placeholder = fake_pkcs7(cert)
    envelope = SOAP_TEMPLATE.format(pkcs7=pkcs7_placeholder)
    print('Envelope (placeholder) listo, longitud:', len(envelope))
    print('Este script NO realiza autenticación real; confirma que la llave y cert cargan sin error.')
    return 0

if __name__ == '__main__':
    raise SystemExit(main())
