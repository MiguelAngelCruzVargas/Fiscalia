import os
import uuid
import tempfile
from datetime import datetime
from typing import Optional, List, Dict, Any
import time
import base64
import zipfile
from io import BytesIO

try:
    from zeep import Client as ZeepClient
    from zeep import Settings as ZeepSettings
    from zeep.wsse.signature import Signature
    from zeep.exceptions import Fault as ZeepFault
    try:
        from zeep.plugins import HistoryPlugin  # type: ignore
    except Exception:  # pragma: no cover
        HistoryPlugin = None  # type: ignore
    try:
        # Timestamp WS-Security token (algunos servicios WCF del SAT lo requieren)
        from zeep.wsse import Timestamp  # type: ignore
    except Exception:  # pragma: no cover
        Timestamp = None  # type: ignore
    try:
        # TransportError gives HTTP status/response info
        from zeep.exceptions import TransportError as ZeepTransportError
    except Exception:  # pragma: no cover
        ZeepTransportError = None  # type: ignore
except Exception:  # pragma: no cover
    ZeepClient = None
    Signature = None
    # Garantizar que los bloques "except ZeepFault" no fallen si zeep no está instalado
    ZeepFault = Exception  # type: ignore
    ZeepTransportError = None  # type: ignore
    ZeepSettings = None  # type: ignore
try:
    import xmlsec  # type: ignore
    XMLSEC_AVAILABLE = True
except Exception:  # pragma: no cover
    XMLSEC_AVAILABLE = False
from cryptography import x509
from cryptography.hazmat.primitives.serialization import (
    load_der_private_key,
    load_pem_private_key,
    Encoding,
    PrivateFormat,
    NoEncryption,
)
WSDL_AUTENTICACION = "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx/Autenticacion/Autenticacion.svc?wsdl"
WSDL_SOLICITUD = "https://cfdidescargamasivasolicitud.clouda.sat.gob.mx/SolicitaDescargaService.svc?wsdl"
# Los servicios de verificación y descarga suelen estar en WSDL distintos al de solicitud
# Ajusta las URLs si el SAT publica nuevas rutas; estas son las comunes en 2.0
WSDL_VERIFICACION = "https://cfdidescargamasivaconsultas.clouda.sat.gob.mx/VerificaSolicitudDescargaService.svc?wsdl"
WSDL_DESCARGA = "https://cfdidescargamasivadescarga.clouda.sat.gob.mx/DescargarService.svc?wsdl"


class Sat20Client:
    """
    Cliente para el servicio de Descarga Masiva de CFDI 2.0 del SAT.
    Implementa el flujo completo de autenticación, solicitud, verificación y descarga.
    """

    def __init__(self) -> None:
        self.auth_wsdl = WSDL_AUTENTICACION
        self.request_wsdl = WSDL_SOLICITUD
        self.verify_wsdl = WSDL_VERIFICACION
        self.download_wsdl = WSDL_DESCARGA
        # Campos de diagnóstico (no críticos):
        self._last_request_meta: Dict[str, Any] = {}
        self._last_verify_trace: List[Dict[str, Any]] = []
        # Instancias SAT-CFDI (modo FULL): request_id -> sat_instance
        self._satcfdi_requests: Dict[str, Any] = {}
        self._satcfdi_last_instance: Optional[Any] = None

    def authenticate(self, cer_bytes: bytes, key_bytes: bytes, passphrase: Optional[str]) -> str:
        """Autenticación contra SAT 2.0 para obtener un token de acceso."""
        if ZeepClient is None or Signature is None:
            raise RuntimeError('Dependencias SOAP no disponibles (zeep). Instala con `pip install zeep`.')
        if not XMLSEC_AVAILABLE:
            raise RuntimeError(
                'xmlsec no está instalado. Necesitas tanto la librería Python (`pip install xmlsec`) como las libs nativas.'
                '\nWindows opciones:'
                '\n  1) Usar WSL (recomendado):'
                '\n     wsl --install (si no tienes) -> dentro de Ubuntu:'
                '\n       sudo apt update && sudo apt install -y libxml2-dev libxmlsec1-dev libxmlsec1-openssl pkg-config && pip install xmlsec'
                '\n  2) Nativo Windows (más complejo):'
                '\n     a) Instala vcpkg o choco: choco install -y pkgconfiglite openssl'
                '\n     b) Descarga/compila xmlsec1 + libxml2 y expón INCLUDE/LIB (rutas)'
                '\n     c) pip install xmlsec (usará pkg-config)'
                '\nSi necesitas una alternativa rápida, levanta el backend dentro de Docker/WSL. Sin xmlsec no se puede firmar el SOAP.'
            )

        debug = os.environ.get('SAT_DEBUG', '0').lower() in ('1','true','yes')
        if debug:
            try:
                import platform
                print(f"[SAT_AUTH][DEBUG] python={platform.python_version()} xmlsec_available={XMLSEC_AVAILABLE} passphrase_len={len(passphrase) if passphrase else 0}")
            except Exception:
                pass

        # Normalizar certificado a formato PEM/DER
        try:
            try:
                cert = x509.load_der_x509_certificate(cer_bytes)
            except Exception:
                cert = x509.load_pem_x509_certificate(cer_bytes)
            cert_pem = cert.public_bytes(Encoding.PEM)
            cert_der = cert.public_bytes(Encoding.DER)
        except Exception as e:
            raise RuntimeError(f'Certificado .cer inválido: {e}')

        # Cargar clave privada y exportarla a PEM sin cifrado para xmlsec
        try:
            priv = None
            key_load_errors = []
            # Detección de placeholder común para evitar confusión
            if passphrase and 'TU_CONTRASENA' in passphrase.upper():
                raise RuntimeError('Estás usando el placeholder "TU_CONTRASENA_EFIRMA". Sustituye por tu contraseña real de la e.firma.')
            for loader in (load_der_private_key, load_pem_private_key):
                try:
                    priv = loader(key_bytes, password=(passphrase.encode('utf-8') if passphrase else None))
                    break
                except Exception as e:
                    key_load_errors.append(f"{loader.__name__}: {e.__class__.__name__}: {e}")
            if priv is None:
                detail = '; '.join(key_load_errors) or 'sin detalles'
                raise RuntimeError(f'Contraseña inválida o formato de .key no soportado (detalles intentos: {detail})')
            key_pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
        except Exception as e:
            raise RuntimeError(f'Llave privada .key inválida: {e}')

        with tempfile.TemporaryDirectory() as td:
            cert_path = os.path.join(td, 'cert.pem')
            key_path = os.path.join(td, 'key.pem')
            with open(cert_path, 'wb') as f:
                f.write(cert_pem)
            with open(key_path, 'wb') as f:
                f.write(key_pem)

            # Clave privada en DER (para librerías externas como SAT-CFDI)
            try:
                key_der = priv.private_bytes(Encoding.DER, PrivateFormat.PKCS8, NoEncryption())
            except Exception:
                key_der = None  # type: ignore

            # Opción 1: usar la librería SAT-CFDI si está habilitada y disponible
            if os.environ.get('SAT_USE_SATCFDI', '0').lower() in ('1','true','yes'):
                try:
                    token_lib = self._satcfdi_authenticate(cert_der, key_der, passphrase)
                    if token_lib:
                        return token_lib
                except Exception as e:
                    if debug:
                        print(f"[SAT_AUTH][SATCFDI][WARN] {e}")

            # Fallback manual opcional: construir y firmar SOAP sin Zeep/WSSE
            if os.environ.get('SAT_MANUAL_AUTH', '0').lower() in ('1','true','yes'):
                return self._manual_authenticate(cert_der, key_pem)

            # Subclase para omitir verificación de firma en la respuesta SOAP (algunos WSDL devuelven
            # headers que provocan SignatureVerificationFailed aunque la Autentica sea correcta).
            class SignatureNoVerify(Signature):  # type: ignore
                def verify(self, envelope):  # type: ignore[override]
                    return envelope

            # Intentamos distintas combinaciones de algoritmos de firma/digest.
            # El SAT históricamente acepta RSA-SHA1, pero algunos entornos/rotaciones de certificados
            # funcionan mejor con SHA256. Probamos ambas.
            from xmlsec import Transform  # type: ignore
            alg_options_all = [
                {'label': 'rsa-sha1', 'sig': Transform.RSA_SHA1, 'dig': Transform.SHA1},
                {'label': 'rsa-sha256', 'sig': Transform.RSA_SHA256, 'dig': Transform.SHA256},
            ]
            force_alg = os.environ.get('SAT_FORCE_ALG', '').lower().strip()
            if force_alg:
                alg_options = [a for a in alg_options_all if a['label'] == force_alg]
                if not alg_options:
                    raise RuntimeError(f'SAT_FORCE_ALG={force_alg} no reconocido (usa rsa-sha1 o rsa-sha256)')
            else:
                alg_options = alg_options_all
            if debug:
                print(f"[SAT_AUTH][DEBUG] algs_a_probar={[a['label'] for a in alg_options]} force_alg={force_alg or 'none'}")

            last_err: Optional[Exception] = None
            # Combinaciones de WS-Security: con/sin Timestamp y orden del header
            ts_combos = [
                {'with_ts': True, 'ts_first': True, 'label': 'ts+sig'},
                {'with_ts': True, 'ts_first': False, 'label': 'sig+ts'},
                {'with_ts': False, 'ts_first': False, 'label': 'sig-only'},
            ]

            # debug ya definido arriba

            def explain_fault(msg: str) -> str:
                """Traduce mensajes típicos de WS-Security a causas probables para el usuario."""
                low = msg.lower()
                hints = []
                if 'verifying security' in low or 'security for the message' in low:
                    hints.append('El SAT no pudo validar la firma WS-Security.')
                    hints.append('Causas: usar CSD en vez de FIEL, reloj del sistema desfasado (>5m), .key o passphrase incorrecta, certificado expirado, orden Timestamp incorrecto o alg no aceptado.')
                if 'expired' in low or 'vigencia' in low:
                    hints.append('El certificado podría estar vencido o fuera de ventana de tiempo.')
                if 'password' in low:
                    hints.append('Contraseña de la .key incorrecta.')
                if not hints:
                    return msg
                return msg + ' · ' + ' '.join(hints)
            for alg in alg_options:
                try:
                    plugins = []  # asegurar definida para bloques except
                    wsse_token = SignatureNoVerify(
                        key_path,
                        cert_path,
                        signature_method=alg['sig'],
                        digest_method=alg['dig']
                    )

                    # Plugin para inyectar BinarySecurityToken + SecurityTokenReference (algunos endpoints SAT lo requieren)
                    # Activable con SAT_WSSE_BST=1 (por defecto lo activamos para aumentar compatibilidad)
                    inject_bst = os.environ.get('SAT_WSSE_BST', '1').lower() not in ('0','false','no')
                    bst_id = f"BST-{uuid.uuid4()}"
                    bst_plugin = None
                    if inject_bst:
                        try:
                            from lxml import etree  # type: ignore
                            from zeep import Plugin  # type: ignore

                            cert_der = cert.public_bytes(Encoding.DER)  # type: ignore
                            cert_b64 = base64.b64encode(cert_der).decode('ascii')

                            class BSTInjectionPlugin(Plugin):  # type: ignore
                                def egress(self, envelope, http_headers, operation, binding_options):  # type: ignore[override]
                                    # Namespaces estándar WS-Security
                                    NSMAP = {
                                        'wsse': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd',
                                        'wsu': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd',
                                        'ds': 'http://www.w3.org/2000/09/xmldsig#'
                                    }
                                    header = envelope.find('{http://schemas.xmlsoap.org/soap/envelope/}Header')
                                    if header is None:
                                        header = etree.SubElement(envelope, '{http://schemas.xmlsoap.org/soap/envelope/}Header')
                                    sec = header.find('.//{http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd}Security')
                                    if sec is None:
                                        sec = etree.SubElement(header, '{%s}Security' % NSMAP['wsse'], nsmap=NSMAP)
                                    # Evitar duplicar
                                    existing_bst = sec.find('.//{http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd}BinarySecurityToken')
                                    if existing_bst is None:
                                        bst_el = etree.SubElement(sec, '{%s}BinarySecurityToken' % NSMAP['wsse'], attrib={
                                            '{%s}Id' % NSMAP['wsu']: bst_id,
                                            'EncodingType': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary',
                                            'ValueType': 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3'
                                        })
                                        bst_el.text = cert_b64
                                    # Insertar SecurityTokenReference dentro de KeyInfo si existe la Firma (posterior a firma real no podemos, así que si no está, lo añadimos para ayuda diagnóstica)
                                    # Nota: xmlsec ya habrá firmado usando KeyInfo/X509Data. Algunos validadores SAT aceptan ambas.
                                    return envelope

                            bst_plugin = BSTInjectionPlugin()
                        except Exception as e:
                            if debug:
                                print(f"[SAT_AUTH][BST] No se pudo preparar plugin BST: {e}")
                    for ts in ts_combos:
                        try:  # intento específico (alg + ts combo)
                            if ts['with_ts'] and 'Timestamp' in globals() and Timestamp:
                                ts_obj = Timestamp(ttl=600)
                                wsse = [ts_obj, wsse_token] if ts['ts_first'] else [wsse_token, ts_obj]
                            else:
                                wsse = wsse_token
                            # Settings y transport para compatibilidad WCF
                            settings = None
                            try:
                                if ZeepSettings:
                                    settings = ZeepSettings()  # usar valores por defecto
                            except Exception:
                                settings = None
                            try:
                                from requests import Session
                                from zeep.transports import Transport
                                session = Session()
                                session.headers.update({'Connection': 'close'})
                                transport = Transport(session=session)
                            except Exception:
                                transport = None  # type: ignore
                            plugins = []  # ensure bound
                            try:
                                if HistoryPlugin:
                                    plugins = [HistoryPlugin()]
                            except Exception:
                                plugins = []
                            if bst_plugin:
                                try:
                                    plugins.append(bst_plugin)  # type: ignore[arg-type]
                                except Exception:
                                    pass
                            client = ZeepClient(wsdl=self.auth_wsdl, wsse=wsse, settings=settings, transport=transport, plugins=plugins)
                            if debug:
                                print(f"[SAT_AUTH] Intento alg={alg['label']} wsse={ts['label']}")
                            if debug:
                                print(f"[SAT_AUTH][STEP] Invocando Autentica alg={alg['label']} wsse={ts['label']}")
                            try:
                                result = client.service.Autentica()  # llamada SOAP
                            except AssertionError as ae:
                                # Guardar envelope si existe para diagnóstico
                                if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes') and plugins and HistoryPlugin:
                                    try:
                                        sent = plugins[0].last_sent  # type: ignore
                                        if sent and getattr(sent, 'envelope', None) is not None:
                                            from lxml import etree as _et  # type: ignore
                                            env_txt = _et.tostring(sent.envelope, encoding='unicode', pretty_print=True)
                                            with open('sat_auth_envelope.xml', 'w', encoding='utf-8') as fh:
                                                fh.write(env_txt)
                                    except Exception:
                                        pass
                                raise RuntimeError('AssertionError interno al firmar/enviar la solicitud SOAP (posible problema con xmlsec en Windows). Reinstala xmlsec + dependencias, confirma OpenSSL. Detalle: ' + repr(ae))
                            token = str(result) if result is not None else ''
                            # Guardar envelope enviado si se solicitó
                            if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes') and plugins and HistoryPlugin:
                                try:
                                    sent = plugins[0].last_sent  # type: ignore
                                    if sent and getattr(sent, 'envelope', None) is not None:
                                        from lxml import etree as _et  # type: ignore
                                        env_txt = _et.tostring(sent.envelope, encoding='unicode', pretty_print=True)
                                        with open('sat_auth_envelope.xml', 'w', encoding='utf-8') as fh:
                                            fh.write(env_txt)
                                except Exception as _e:
                                    if debug:
                                        print(f"[SAT_AUTH][WARN] No se pudo guardar envelope: {_e}")
                            if not token:
                                raise RuntimeError('SAT no devolvió token. Revisa la validez de la e.firma (FIEL, no CSD), la contraseña y la hora del sistema.')
                            return token
                        except ZeepFault as e:  # type: ignore
                            msg = getattr(e, 'message', str(e))
                            fault_detail = ''
                            try:
                                # Algunos Faults traen .detail con hijos
                                detail_obj = getattr(e, 'detail', None)
                                if detail_obj is not None:
                                    from lxml import etree  # type: ignore
                                    fault_detail = etree.tostring(detail_obj, encoding='unicode')[:400]
                            except Exception:
                                pass
                            if isinstance(msg, str) and 'verifying security' in msg.lower():
                                # Incluir pequeño snippet del request para diagnóstico
                                snippet = ''
                                try:
                                    _plugins = locals().get('plugins', [])
                                    if _plugins and HistoryPlugin:
                                        sent = _plugins[0].last_sent  # type: ignore
                                        if sent and getattr(sent, 'envelope', None) is not None:
                                            from lxml import etree  # type: ignore
                                            snippet = etree.tostring(sent.envelope, encoding='unicode')[:400]
                                        # Guardar respuesta completa si se solicitó
                                        if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes'):
                                            try:
                                                from lxml import etree as _et  # type: ignore
                                                recv = _plugins[0].last_received  # type: ignore
                                                if recv and getattr(recv, 'envelope', None) is not None:
                                                    env_txt = _et.tostring(recv.envelope, encoding='unicode', pretty_print=True)
                                                    with open('sat_auth_fault_response.xml', 'w', encoding='utf-8') as fh:
                                                        fh.write(env_txt)
                                            except Exception:
                                                pass
                                except Exception:
                                    pass
                                extra = f' [wsse={ts["label"]}]'
                                msg_explained = explain_fault(str(msg))
                                if fault_detail:
                                    msg_explained += f" · detail={fault_detail}"  # agrega XML del Fault
                                last_err = RuntimeError(f'Fault del SAT en Autentica (alg={alg["label"]}{extra}): {msg_explained}{(" · SOAP_SENT=" + snippet) if snippet and debug else ""}')
                                if debug:
                                    print(f"[SAT_AUTH][WARN] {last_err}")
                                    # Guardar envelope y fault si se solicitó
                                    if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes') and plugins and HistoryPlugin:
                                        try:
                                            sent = plugins[0].last_sent  # type: ignore
                                            if sent and getattr(sent, 'envelope', None) is not None:
                                                from lxml import etree as _et  # type: ignore
                                                env_txt = _et.tostring(sent.envelope, encoding='unicode', pretty_print=True)
                                                with open('sat_auth_envelope.xml', 'w', encoding='utf-8') as fh:
                                                    fh.write(env_txt)
                                        except Exception:
                                            pass
                                continue
                            raise RuntimeError(f'Fault del SAT en Autentica (alg={alg["label"]}, wsse={ts["label"]}): {msg}')
                        except Exception as e:
                            if ZeepTransportError and isinstance(e, ZeepTransportError):  # type: ignore
                                status = getattr(e, 'status_code', 'N/A')
                                content = getattr(e, 'content', b'')
                                snippet = ''
                                try:
                                    snippet = (content.decode('utf-8', errors='ignore') or '')[:300]
                                except Exception:
                                    pass
                                raise RuntimeError(f'Error de transporte al autenticar (HTTP {status}). Resumen: {snippet}')
                            # Capturar stack trace para diagnóstico profundo si fue un cierre inesperado
                            import traceback
                            trace_txt = ''.join(traceback.format_exception(type(e), e, e.__traceback__))
                            if debug:
                                print(f"[SAT_AUTH][EXC] alg={alg['label']} wsse={ts['label']} tipo={e.__class__.__name__}: {e}")
                            if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes'):
                                try:
                                    with open('sat_auth_error_trace.txt', 'a', encoding='utf-8') as fh:
                                        fh.write(f"\n--- ERROR {datetime.utcnow().isoformat()} alg={alg['label']} wsse={ts['label']} ---\n")
                                        fh.write(trace_txt)
                                except Exception:
                                    pass
                            last_err = e
                            if debug:
                                print(f"[SAT_AUTH][ERROR] alg={alg['label']} wsse={ts['label']} -> {e}")
                            continue
                except ZeepFault as e:  # type: ignore
                    msg = getattr(e, 'message', str(e))
                    last_err = RuntimeError(f'Fault del SAT en Autentica (alg={alg["label"]}): {msg}')
                    continue
                except Exception as e:
                    if ZeepTransportError and isinstance(e, ZeepTransportError):  # type: ignore
                        status = getattr(e, 'status_code', 'N/A')
                        content = getattr(e, 'content', b'')
                        snippet = ''
                        try:
                            snippet = (content.decode('utf-8', errors='ignore') or '')[:300]
                        except Exception:
                            pass
                        raise RuntimeError(f'Error de transporte al autenticar (HTTP {status}). Resumen: {snippet}')
                    last_err = e
                    if debug:
                        print(f"[SAT_AUTH][ERROR] alg={alg['label']} init -> {e}")
                    continue

            # Si llegamos aquí, ninguno de los algoritmos pasó
            if last_err:
                extra = ' · Sugerencias: verifica reloj del sistema, usa FIEL (no CSD), certificado vigente, que .cer/.key coincidan con la contraseña, SAT_FORCE_ALG=rsa-sha1 y prueba SAT_DEBUG=1. Considera ejecutar en WSL/Linux si usas Windows.'
                # Mejorar claridad del último error mostrando tipo de excepción interna
                last_str = str(last_err) or repr(last_err)
                # Intentar fallback manual automáticamente si no se pidió explícitamente
                try:
                    if os.environ.get('SAT_MANUAL_AUTH', '0').lower() not in ('1','true','yes'):
                        if debug:
                            print('[SAT_AUTH][FALLBACK] Intentando modo manual (sin Zeep/wsse).')
                        token_fb = self._manual_authenticate(cert_der, key_pem)
                        return token_fb
                except Exception as fe:
                    if debug:
                        print(f'[SAT_AUTH][FALLBACK][ERROR] {fe}')
                    last_str += f' | Fallback manual falló: {fe}'
                raise RuntimeError(f'Error en la llamada de autenticación al SAT (último intento): {last_str}{extra}')
            raise RuntimeError('No fue posible autenticarse con el SAT por causa desconocida.')

    def _manual_authenticate(self, cert_der: bytes, key_pem: bytes) -> str:
        """Autenticación manual: construye y firma un SOAP 1.1 con XMLDSig y lo envía via requests.

        Útil en Windows cuando Zeep+xmlsec presentan errores. Requiere xmlsec y requests.
        """
        import requests  # type: ignore
        from lxml import etree  # type: ignore
        import xmlsec  # type: ignore

        debug = os.environ.get('SAT_DEBUG', '0').lower() in ('1','true','yes')
        alg = os.environ.get('SAT_FORCE_ALG', 'rsa-sha1').lower().strip() or 'rsa-sha1'
        dig_env = os.environ.get('SAT_FORCE_DIGEST', '').lower().strip()

        # Selección de métodos de firma/digest (vía getattr para evitar warnings de tipos)
        Transform = getattr(xmlsec, 'Transform')
        template = getattr(xmlsec, 'template')
        Key = getattr(xmlsec, 'Key')
        KeyFormat = getattr(xmlsec, 'KeyFormat')
        tree_mod = getattr(xmlsec, 'tree')
        SignatureContext = getattr(xmlsec, 'SignatureContext')

        excl_c14n = getattr(Transform, 'EXCL_C14N')

        NS_SOAP = 'http://schemas.xmlsoap.org/soap/envelope/'
        NS_WSSE = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-secext-1.0.xsd'
        NS_WSU = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-wssecurity-utility-1.0.xsd'
        AUT_NS = 'http://DescargaMasivaTerceros.gob.mx'
        BST_VALUETYPE = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-x509-token-profile-1.0#X509v3'
        BST_ENCODING = 'http://docs.oasis-open.org/wss/2004/01/oasis-200401-wss-soap-message-security-1.0#Base64Binary'

        bst_id = f"BST-{uuid.uuid4()}"
        body_id = f"id-{uuid.uuid4()}"
        cert_b64 = base64.b64encode(cert_der).decode('ascii')

        # Preparar combos de algoritmo/firma para intentar (preferimos env primero)
        combos: List[Dict[str, str]] = []
        pref_dig = dig_env if dig_env in ('sha1','sha256') else ''
        if alg in ('rsa-sha1','rsa-sha256'):
            combos.append({'sig': alg, 'dig': pref_dig or ('sha1' if alg=='rsa-sha1' else 'sha256')})
        # Añadir otras combinaciones típicas aceptadas por servicios WCF/SAT
        combos.extend([
            {'sig': 'rsa-sha1', 'dig': 'sha1'},
            {'sig': 'rsa-sha256', 'dig': 'sha1'},
            {'sig': 'rsa-sha256', 'dig': 'sha256'},
        ])
        # Eliminar duplicados manteniendo orden
        seen = set()
        uniq: List[Dict[str,str]] = []
        for c in combos:
            key_c = (c['sig'], c['dig'])
            if key_c in seen:
                continue
            seen.add(key_c)
            uniq.append(c)

        # Variaciones WS-Security: Timestamp (ninguno/presente/signed) y modo de KeyInfo
        modes = [
            {'ts': 'signed-only', 'label': 'ts-signed-only'},  # Sólo Timestamp firmado (no Body) — coincide con plantilla SAT-CFDI
            {'ts': 'both', 'label': 'ts-signed'},              # Timestamp presente y firmado junto al Body
            {'ts': 'present', 'label': 'ts-only'},             # Timestamp presente pero NO firmado
            {'ts': 'none', 'label': 'no-ts'},                  # Sin Timestamp
        ]
        # KeyInfo puede referenciar BST (Reference) o incluir X509Data directa
        ki_modes = ['reference', 'x509data']
        # Incluir BST o no (algunos servicios aceptan sólo X509Data)
        include_bst_opts = [True, False]
        # Canonicalización: exclusiva (común en WS-Security) e inclusiva (para compatibilidad)
        c14n_opts = [
            {'name': 'excl', 'tx': getattr(Transform, 'EXCL_C14N')},
            {'name': 'incl', 'tx': getattr(Transform, 'C14N', getattr(Transform, 'EXCL_C14N'))},
        ]

        last_err: Optional[Exception] = None
        for c in uniq:
            try:
                sig_method = getattr(Transform, 'RSA_SHA1') if c['sig'] == 'rsa-sha1' else getattr(Transform, 'RSA_SHA256')
                dig_method = getattr(Transform, 'SHA1') if c['dig'] == 'sha1' else getattr(Transform, 'SHA256')
                for m in modes:
                    for ki_mode in ki_modes:
                        for include_bst in include_bst_opts:
                            for c14n in c14n_opts:
                                if debug:
                                    print(f"[SAT_MANUAL_AUTH] firma={c['sig']} digest={c['dig']} mode={m['label']} ki={ki_mode} bst={include_bst} c14n={c14n['name']}")

                                # Envelope base
                                NS_WSA = 'http://www.w3.org/2005/08/addressing'
                                env = etree.Element(
                                    etree.QName(NS_SOAP, 'Envelope'),
                                    nsmap={'soap': NS_SOAP, 'wsse': NS_WSSE, 'wsu': NS_WSU, 'wsa': NS_WSA}
                                )
                                header = etree.SubElement(env, etree.QName(NS_SOAP, 'Header'))
                                # WS-Addressing: Action y To (muchos servicios WCF lo requieren)
                                wsa_action = etree.SubElement(header, etree.QName(NS_WSA, 'Action'))
                                wsa_action.text = 'http://DescargaMasivaTerceros.gob.mx/IAutenticacion/Autentica'
                                wsa_to = etree.SubElement(header, etree.QName(NS_WSA, 'To'))
                                wsa_to.text = self.auth_wsdl.split('?')[0]
                                security = etree.SubElement(header, etree.QName(NS_WSSE, 'Security'))
                                security.set(etree.QName(NS_SOAP, 'mustUnderstand'), '1')

                                # Timestamp opcional
                                ts_id = None
                                if m['ts'] in ('both','present','signed-only'):
                                    ts_id = f"TS-{uuid.uuid4()}"
                                    ts = etree.SubElement(security, etree.QName(NS_WSU, 'Timestamp'), attrib={etree.QName(NS_WSU, 'Id'): ts_id})
                                    from datetime import datetime, timedelta, timezone
                                    now = datetime.now(timezone.utc)
                                    created = etree.SubElement(ts, etree.QName(NS_WSU, 'Created'))
                                    created.text = now.replace(microsecond=0).isoformat().replace('+00:00', 'Z')
                                    expires = etree.SubElement(ts, etree.QName(NS_WSU, 'Expires'))
                                    expires.text = (now + timedelta(minutes=10)).replace(microsecond=0).isoformat().replace('+00:00', 'Z')

                                # BST opcional
                                if include_bst:
                                    bst = etree.SubElement(
                                        security,
                                        etree.QName(NS_WSSE, 'BinarySecurityToken'),
                                        attrib={etree.QName(NS_WSU, 'Id'): bst_id, 'EncodingType': BST_ENCODING, 'ValueType': BST_VALUETYPE}
                                    )
                                    bst.text = cert_b64

                                # Body y operación
                                body = etree.SubElement(env, etree.QName(NS_SOAP, 'Body'), attrib={etree.QName(NS_WSU, 'Id'): body_id})
                                etree.SubElement(body, etree.QName(AUT_NS, 'Autentica'))

                                # Firma con c14n seleccionada
                                sign_node = template.create(env, c14n['tx'], sig_method)
                                security.append(sign_node)
                                # Selección de referencias a firmar según modo
                                if m['ts'] == 'signed-only' and ts_id:
                                    # Sólo firmar el Timestamp (no el Body)
                                    ref_ts = template.add_reference(sign_node, dig_method, uri=f'#{ts_id}')
                                    template.add_transform(ref_ts, c14n['tx'])
                                else:
                                    # Siempre firmar el Body salvo en 'signed-only'
                                    ref = template.add_reference(sign_node, dig_method, uri=f'#{body_id}')
                                    template.add_transform(ref, c14n['tx'])
                                    if m['ts'] == 'both' and ts_id:
                                        ref_ts = template.add_reference(sign_node, dig_method, uri=f'#{ts_id}')
                                        template.add_transform(ref_ts, c14n['tx'])

                                # KeyInfo y referencia de certificado
                                ki = template.ensure_key_info(sign_node)
                                if ki_mode == 'reference' and include_bst:
                                    str_el = etree.SubElement(ki, etree.QName(NS_WSSE, 'SecurityTokenReference'))
                                    etree.SubElement(
                                        str_el,
                                        etree.QName(NS_WSSE, 'Reference'),
                                        attrib={'URI': f'#{bst_id}', 'ValueType': BST_VALUETYPE}
                                    )
                                else:
                                    # Sólo X509Data
                                    x509_data = etree.SubElement(ki, '{http://www.w3.org/2000/09/xmldsig#}X509Data')
                                    x509_cert = etree.SubElement(x509_data, '{http://www.w3.org/2000/09/xmldsig#}X509Certificate')
                                    x509_cert.text = cert_b64

                                tree_mod.add_ids(env, ['Id'])
                                try:
                                    key = Key.from_memory(key_pem, KeyFormat.PEM, None)
                                except Exception as e:
                                    raise RuntimeError(f'Error cargando llave en modo manual: {e}')
                                ctx = SignatureContext()
                                ctx.key = key
                                try:
                                    ctx.sign(sign_node)
                                except Exception as e:
                                    raise RuntimeError(f'Error firmando XML manualmente: {e}')

                                xml_data = etree.tostring(env, encoding='utf-8', xml_declaration=True)
                                if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes'):
                                    try:
                                        with open('sat_auth_envelope.xml', 'wb') as fh:
                                            fh.write(xml_data)
                                    except Exception:
                                        pass

                                # Probar con y sin comillas en SOAPAction
                                for quoted in (True, False):
                                    headers = {
                                        'Content-Type': 'text/xml; charset=utf-8',
                                        'SOAPAction': '"http://DescargaMasivaTerceros.gob.mx/IAutenticacion/Autentica"' if quoted else 'http://DescargaMasivaTerceros.gob.mx/IAutenticacion/Autentica'
                                    }
                                    url = self.auth_wsdl.split('?')[0]
                                    try:
                                        resp = requests.post(url, data=xml_data, headers=headers, timeout=30)
                                    except Exception as e:
                                        raise RuntimeError(f'Error de transporte en modo manual: {e}')

                                    if resp.status_code >= 400:
                                        if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes'):
                                            try:
                                                with open('sat_auth_fault_response.xml', 'wb') as fh:
                                                    fh.write(resp.content)
                                            except Exception:
                                                pass
                                        last_err = RuntimeError(f'HTTP {resp.status_code}: {(resp.text or "")[:300]}')
                                        continue

                                    try:
                                        doc = etree.fromstring(resp.content)
                                    except Exception as e:
                                        last_err = RuntimeError(f'Respuesta SOAP inválida (no XML) en modo manual: {e}')
                                        continue

                                    token: Optional[str] = None
                                    for el in doc.xpath('//*[local-name()="AutenticaResult"]'):
                                        txt = ''.join(el.itertext()).strip()
                                        if txt:
                                            token = txt
                                            break
                                    if not token:
                                        for el in doc.xpath('//*[not(*)]'):
                                            val = (el.text or '').strip()
                                            if len(val) > 20 and ' ' not in val:
                                                token = val
                                                break
                                    if token:
                                        return token

                                    if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes'):
                                        try:
                                            with open('sat_auth_fault_response.xml', 'wb') as fh:
                                                fh.write(resp.content)
                                        except Exception:
                                            pass
                                    txt = (resp.text or '')[:200]
                                    last_err = RuntimeError(f'SAT no devolvió token con firma={c["sig"]} digest={c["dig"]} mode={m["label"]} ki={ki_mode} bst={include_bst} c14n={c14n["name"]}. Resumen: {txt}')

            except Exception as e:
                last_err = e
                continue
        # Si ninguna combinación funcionó
        raise last_err or RuntimeError('SAT no devolvió token en modo manual tras varios intentos.')

    def _satcfdi_authenticate(self, cert_der: bytes, key_der: Optional[bytes], passphrase: Optional[str]) -> str:
        """Autenticación usando SAT-CFDI (preferencia: paquete PyPI; fallback: vendor en external/python-satcfdi).

        Requiere dependencias: satcfdi, pyOpenSSL, cryptography, lxml, requests, beautifulsoup4, packaging.
        """
        if cert_der is None or key_der is None:
            raise RuntimeError('SATCFDI: bytes DER de certificado/llave no disponibles')
        # Intentar importar desde PyPI primero
        imported = False
        try:
            from satcfdi.pacs.sat import _CFDIAutenticacion  # type: ignore
            from satcfdi.models import Signer  # type: ignore
            from lxml import etree  # type: ignore
            import requests  # type: ignore
            imported = True
        except Exception:
            # Fallback: vendor local en external/python-satcfdi
            here = os.path.dirname(__file__)
            repo_root = os.path.normpath(os.path.join(here, '..', '..', '..'))
            ext_path = os.path.join(repo_root, 'external', 'python-satcfdi')
            import sys  # local import
            if os.path.isdir(ext_path) and ext_path not in sys.path:
                sys.path.insert(0, ext_path)
            try:
                from satcfdi.pacs.sat import _CFDIAutenticacion  # type: ignore
                from satcfdi.models import Signer  # type: ignore
                from lxml import etree  # type: ignore
                import requests  # type: ignore
                imported = True
            except Exception as e:
                raise RuntimeError(f'No se pudo importar SAT-CFDI (PyPI ni vendor): {e}')

        signer = Signer.load(certificate=cert_der, key=key_der, password=(passphrase or '').encode('utf-8') if passphrase else None)
        req = _CFDIAutenticacion(signer=signer, arguments={'seconds': 600})
        payload = req.get_payload()
        headers = {
            'Content-type': 'text/xml;charset="utf-8"',
            'Accept': 'text/xml',
            'Cache-Control': 'no-cache',
            'SOAPAction': req.soap_action,
        }
        resp = requests.post(req.soap_url, data=payload, headers=headers, timeout=30)
        if resp.status_code >= 400:
            raise RuntimeError(f'SATCFDI HTTP {resp.status_code}: {(resp.text or "")[:300]}')
        doc = etree.fromstring(resp.content)
        parsed = req.process_response(doc)
        token = (parsed or {}).get('AutenticaResult')
        if not token:
            raise RuntimeError('SATCFDI no devolvió token')
        # Guardar artefactos si está habilitado
        if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes'):
            try:
                with open('sat_auth_envelope.xml', 'wb') as fh:
                    fh.write(payload)
                with open('sat_auth_fault_response.xml', 'wb') as fh:
                    fh.write(resp.content)
            except Exception:
                pass
        return str(token)

    def _client_with_token(self, wsdl: str, token: str):
        """Crea un cliente Zeep con el token de autorización en los headers."""
        if ZeepClient is None:
            raise RuntimeError('zeep no disponible')
        try:
            from requests import Session
            from zeep.transports import Transport
        except Exception:
            raise RuntimeError('requests no instalado; es requerido por zeep')
        
        session = Session()
        session.headers.update({'Authorization': f'WRAP access_token="{token}"'})
        transport = Transport(session=session)
        return ZeepClient(wsdl=wsdl, transport=transport)

    def request_download(
        self,
        token: str,
        rfc: str,
        date_from: str,
        date_to: str,
        kind: str,
        solicitante_rfc: Optional[str] = None,
        tipo_solicitud_override: Optional[str] = None,
        estado_comprobante_override: Optional[str] = None,
        tipo_comprobante_override: Optional[str] = None,
        cer_bytes: Optional[bytes] = None,
        key_bytes: Optional[bytes] = None,
        key_passphrase: Optional[str] = None,
    ) -> str:
        """Crea una solicitud de descarga y retorna un request_id.

        Usa el tipo complejo correcto del WSDL (nsX:SolicitudDescargaMasivaTercero[Recibidos|Emitidos])
        para evitar errores de deserialización en servicios WCF.
        """
        # Si se habilita modo FULL SAT-CFDI, delegar solicitud a la librería
        if os.environ.get('SAT_USE_SATCFDI_FULL','0').lower() in ('1','true','yes') and cer_bytes and key_bytes:
            try:
                from . import satcfdi_adapter
                import hashlib
                cert_sha = hashlib.sha256(cer_bytes).hexdigest()[:16]
                # Preparar instancia SAT (con caching interno de tokens)
                from satcfdi.pacs.sat import SAT, Signer  # type: ignore
            except Exception:
                # Intentar vendor local
                try:
                    import sys
                    repo_root = os.path.normpath(os.path.join(os.path.dirname(__file__), '..', '..', '..'))
                    ext_path = os.path.join(repo_root, 'external', 'python-satcfdi')
                    if os.path.isdir(ext_path) and ext_path not in sys.path:
                        sys.path.insert(0, ext_path)
                    from satcfdi.pacs.sat import SAT, Signer  # type: ignore
                    from . import satcfdi_adapter
                except Exception as e:  # pragma: no cover
                    raise RuntimeError(f'SATCFDI FULL no disponible: {e}')
            # Construir signer (DER preferido). Convertir a DER si viene PEM
            from cryptography import x509 as _x509
            from cryptography.hazmat.primitives.serialization import Encoding as _SatcfdiEncoding
            try:
                try:
                    cert_obj = _x509.load_der_x509_certificate(cer_bytes)
                except Exception:
                    cert_obj = _x509.load_pem_x509_certificate(cer_bytes)
                cert_der_local = cert_obj.public_bytes(_SatcfdiEncoding.DER)
                # key_bytes ya debería estar en DER (si no, intentar DER loader)
                key_der_local = key_bytes
            except Exception:
                cert_der_local = cer_bytes
                key_der_local = key_bytes
            # Crea instancia SAT con signer
            signer = Signer.load(certificate=cert_der_local, key=key_der_local, password=(key_passphrase or '').encode('utf-8') if key_passphrase else None)
            sat_instance = SAT(signer=signer)
            tipo_solicitud = (tipo_solicitud_override or os.environ.get('SAT_TIPO_SOLICITUD', 'CFDI')).strip() or 'CFDI'
            estado_comp = (estado_comprobante_override or os.environ.get('SAT_ESTADO_COMPROBANTE', '')).strip()
            # tipo_comprobante se gestiona como override posterior; SAT-CFDI no lo soporta directamente en solicitud base
            # Ejecutar solicitud
            try:
                # SAT-CFDI espera rfc_emisor o rfc_receptor según kind
                result = satcfdi_adapter.solicitar(
                    signer_rfc=signer.rfc,
                    kind=kind,
                    rfc_objetivo=rfc,
                    date_from=date_from,
                    date_to=date_to,
                    token_provider=sat_instance,
                    tipo_solicitud=tipo_solicitud,
                    estado_comp=estado_comp or None,
                    tipo_comp=tipo_comprobante_override or None,
                )
            except Exception as e:
                raise RuntimeError(f'SATCFDI solicitud falló: {e}')
            req_id = result.get('IdSolicitud') or result.get('IdSolicitudCFDI')
            cod = result.get('CodEstatus') or result.get('CodigoEstatus') or ''
            msg = result.get('Mensaje') or ''
            self._last_request_meta = {
                'codestatus': cod,
                'mensaje': msg,
                'kind': kind,
                'rfc_objetivo': rfc,
                'fecha_inicial': date_from,
                'fecha_final': date_to,
                'tipo_solicitud': tipo_solicitud,
                'estado_comprobante': estado_comp or None,
                'tipo_comprobante': tipo_comprobante_override or None,
                'via': 'satcfdi'
            }
            if not req_id:
                raise RuntimeError(f'SATCFDI no devolvió IdSolicitud (CodEstatus={cod} Msg={msg})')
            if cod and cod not in ('5000','Solicitud Aceptada','OK','5004','5005'):
                raise RuntimeError(f"SATCFDI reportó estado {cod}: {msg or 'sin mensaje'}")
            # Guardar instancia para verificación/descarga posteriores
            self._satcfdi_requests[str(req_id)] = sat_instance
            self._satcfdi_last_instance = sat_instance
            return str(req_id)

        # Construir payload base como dict y calcular overrides (modo interno original)
        k = (kind or '').lower()
        op_name = 'SolicitaDescargaEmitidos' if k.startswith('emit') else 'SolicitaDescargaRecibidos'
        tipo_solicitud = (tipo_solicitud_override or os.environ.get('SAT_TIPO_SOLICITUD', 'CFDI')).strip() or 'CFDI'
        estado_comp = (estado_comprobante_override or os.environ.get('SAT_ESTADO_COMPROBANTE', '')).strip()
        tipo_comp = (tipo_comprobante_override or os.environ.get('SAT_TIPO_COMPROBANTE', '')).strip().upper()

        # Si se indica modo manual (o hay material de firma), usar SOAP 1.1 manual para evitar 415
        if os.environ.get('SAT_SOLICITUD_MANUAL', '1').lower() in ('1','true','yes'):
            return self._manual_request_download(
                token=token,
                rfc=rfc,
                date_from=date_from,
                date_to=date_to,
                kind=kind,
                solicitante_rfc=solicitante_rfc,
                tipo_solicitud=tipo_solicitud,
                estado_comp=estado_comp,
                tipo_comp=tipo_comp,
                cer_bytes=cer_bytes,
                key_bytes=key_bytes,
                key_passphrase=key_passphrase,
            )

        # Cliente Zeep con plugin para firmar la solicitud (XMLDSig dentro del cuerpo)
        if ZeepClient is None:
            raise RuntimeError('zeep no disponible')
        try:
            from requests import Session
            from zeep.transports import Transport
            from zeep import Plugin  # type: ignore
            from lxml import etree  # type: ignore
            import xmlsec as _xmlsec  # type: ignore
        except Exception as e:
            raise RuntimeError(f'Dependencias para firma de solicitud no disponibles: {e}')

        # Preparar llave privada en PEM para xmlsec
        key_pem: Optional[bytes] = None
        cert_b64: Optional[str] = None
        if key_bytes is not None and cer_bytes is not None:
            try:
                # Cargar certificado (DER o PEM) y exportar DER->base64
                try:
                    cert = x509.load_der_x509_certificate(cer_bytes)
                except Exception:
                    cert = x509.load_pem_x509_certificate(cer_bytes)
                cert_der = cert.public_bytes(Encoding.DER)
                import base64 as _b64
                cert_b64 = _b64.b64encode(cert_der).decode('ascii')
            except Exception as e:
                raise RuntimeError(f'Certificado inválido para firmar solicitud: {e}')
            try:
                priv = None
                for loader in (load_der_private_key, load_pem_private_key):
                    try:
                        priv = loader(key_bytes, password=(key_passphrase.encode('utf-8') if key_passphrase else None))
                        break
                    except Exception:
                        continue
                if priv is None:
                    raise RuntimeError('No se pudo cargar la .key con la contraseña proporcionada')
                key_pem = priv.private_bytes(Encoding.PEM, PrivateFormat.PKCS8, NoEncryption())
            except Exception as e:
                raise RuntimeError(f'Llave privada inválida para firmar solicitud: {e}')

        # Plugin que inserta ds:Signature dentro del elemento de solicitud
        class SignSolicitudPlugin(Plugin):  # type: ignore
            def egress(self, envelope, http_headers, operation, binding_options):  # type: ignore[override]
                if key_pem is None or cert_b64 is None:
                    return envelope
                NS_SOAP = 'http://schemas.xmlsoap.org/soap/envelope/'
                body = envelope.find('{%s}Body' % NS_SOAP)
                if body is None:
                    return envelope
                # Buscar wrapper de operación y nodo 'solicitud' (SAT 2.0)
                wrapper = None
                solicitud_node = None
                try:
                    # Wrapper esperado
                    w = body.xpath('.//*[local-name()="SolicitaDescargaEmitidos" or local-name()="SolicitaDescargaRecibidos"]')  # type: ignore[attr-defined]
                    if w:
                        wrapper = w[0]
                        # Hijo 'solicitud'
                        s = wrapper.xpath('.//*[local-name()="solicitud"]')  # type: ignore[attr-defined]
                        if s:
                            solicitud_node = s[0]
                except Exception:
                    wrapper = None
                if wrapper is None:
                    return envelope

                # Asegurar un Id para firmar (en el wrapper)
                uid = 'SOL-%s' % uuid.uuid4().hex
                wrapper.set('Id', uid)

                # Crear ds:Signature (enveloped) y firmar el elemento target
                ds = _xmlsec  # alias
                try:
                    Transform = getattr(ds, 'Transform')
                    template = getattr(ds, 'template')
                    tree_mod = getattr(ds, 'tree')
                    SignatureContext = getattr(ds, 'SignatureContext')
                    Key = getattr(ds, 'Key')
                    KeyFormat = getattr(ds, 'KeyFormat')
                    # Selección de algoritmos (SATCFDI usa sha1 en solicitud)
                    import os as _os_local
                    alg = (_os_local.environ.get('SAT_FORCE_ALG') or 'rsa-sha1').lower()
                    dig = (_os_local.environ.get('SAT_FORCE_DIGEST') or 'sha1').lower()
                    sig_method = Transform.RSA_SHA1 if alg == 'rsa-sha1' else Transform.RSA_SHA256
                    dig_method = Transform.SHA1 if dig == 'sha1' else Transform.SHA256

                    # Registrar atributo Id como tipo ID para resoluciones de URI en wrapper
                    try:
                        tree_mod.add_ids(wrapper, ['Id'])
                    except Exception:
                        pass

                    sign = template.create(wrapper, Transform.EXCL_C14N, sig_method)
                    # Referencia al propio elemento (enveloped + c14n)
                    ref = template.add_reference(sign, dig_method, uri=f'#{uid}')
                    template.add_transform(ref, Transform.ENVELOPED)
                    template.add_transform(ref, Transform.EXCL_C14N)
                    # KeyInfo con X509Data
                    ki = template.ensure_key_info(sign)
                    x509data = etree.SubElement(ki, '{http://www.w3.org/2000/09/xmldsig#}X509Data')
                    x509cert = etree.SubElement(x509data, '{http://www.w3.org/2000/09/xmldsig#}X509Certificate')
                    x509cert.text = cert_b64
                    # Adjuntar Signature como hijo de 'solicitud' si existe, si no al wrapper
                    if solicitud_node is not None:
                        solicitud_node.append(sign)
                    else:
                        wrapper.append(sign)
                    # Firmar
                    ctx = SignatureContext()
                    key = Key.from_memory(key_pem, KeyFormat.PEM, None)
                    ctx.key = key
                    ctx.sign(sign)
                except Exception:
                    # Si falla, dejamos el envelope sin modificar
                    return envelope
                return envelope

        session = Session()
        session.headers.update({'Authorization': f'WRAP access_token="{token}"'})
        transport = Transport(session=session)
        plugins = []
        try:
            if key_pem is not None and cert_b64 is not None:
                plugins.append(SignSolicitudPlugin())  # type: ignore[arg-type]
        except Exception:
            pass
        client = ZeepClient(wsdl=self.request_wsdl, transport=transport, plugins=plugins)
        # op_name y overrides ya calculados arriba

        base = {
            'FechaInicial': f'{date_from}T00:00:00',
            'FechaFinal': f'{date_to}T23:59:59',
            'RfcSolicitante': solicitante_rfc or rfc,
            'TipoSolicitud': tipo_solicitud,
        }
        # Incluir sólo si son válidos
        if estado_comp in ('0', '1'):
            # Omitimos el atributo cuando es '0' (vigentes) para evitar rechazo 301 en algunos entornos
            if estado_comp == '1':
                base['EstadoComprobante'] = estado_comp
        if tipo_comp in ('I','E','P','N'):
            base['TipoComprobante'] = tipo_comp
        if op_name == 'SolicitaDescargaEmitidos':
            base['RfcEmisor'] = rfc
            type_local = 'SolicitudDescargaMasivaTerceroEmitidos'
        else:
            base['RfcReceptor'] = rfc
            type_local = 'SolicitudDescargaMasivaTerceroRecibidos'

        # Intentar construir el objeto de tipo complejo correcto (nsX:Type)
        payload_obj = None
        for ns in ('ns0', 'ns1', 'ns2', 'ns3', 'tns'):
            t = None
            try:
                t = client.get_type(f'{ns}:{type_local}')
            except Exception:
                t = None
            if t:
                try:
                    payload_obj = t(**base)
                    break
                except Exception:
                    payload_obj = None
                    continue
        # Fallback: usar dict si no encontramos el tipo
        payload_final = payload_obj or base

        try:
            svc = getattr(client.service, op_name)
        except Exception:
            raise RuntimeError(f"Operación '{op_name}' no disponible en el WSDL del SAT.")

        # Llamar con argumento nombrado; si falla, posicional
        try:
            resp = svc(solicitud=payload_final)
        except Exception:
            resp = svc(payload_final)

        # Extraer campos relevantes de la respuesta
        cod = str(getattr(resp, 'CodEstatus', '') or getattr(resp, 'CodigoEstatus', '') or '')
        msg = str(getattr(resp, 'Mensaje', '') or getattr(resp, 'Observaciones', '') or '')
        req_id = getattr(resp, 'IdSolicitud', None)
        # Guardar metadatos de diagnóstico para que el caller los lea (sin romper API)
        self._last_request_meta = {
            'codestatus': cod,
            'mensaje': msg,
            'kind': kind,
            'rfc_objetivo': rfc,
            'fecha_inicial': date_from,
            'fecha_final': date_to,
            'tipo_solicitud': tipo_solicitud,
            'estado_comprobante': estado_comp or None,
            'tipo_comprobante': tipo_comp or None,
        }
        if not req_id:
            # Si no hay IdSolicitud, reportar código y mensaje devueltos por el SAT
            raise RuntimeError(f"Solicitud rechazada por el SAT (CodEstatus={cod or 'N/A'}): {msg or 'sin mensaje'}")
        if cod and cod not in ('5000', 'Solicitud Aceptada', 'OK'):
            # Aunque haya IdSolicitud, algunos códigos indican advertencias o rechazos
            # Conservamos el Id para diagnósticos pero elevamos el contexto si es evidente
            if cod not in ('5004',):
                # 5004 es 'No se encontró la información' y puede resolverse en verificación
                raise RuntimeError(f"SAT reportó estado {cod}: {msg or 'sin mensaje'}")
        return str(req_id)

    def _manual_request_download(
        self,
        token: str,
        rfc: str,
        date_from: str,
        date_to: str,
        kind: str,
        solicitante_rfc: Optional[str],
        tipo_solicitud: str,
        estado_comp: str,
        tipo_comp: str,
        cer_bytes: Optional[bytes],
        key_bytes: Optional[bytes],
        key_passphrase: Optional[str],
    ) -> str:
        import requests  # type: ignore
        from lxml import etree  # type: ignore
        import base64 as _b64
        from cryptography.hazmat.primitives import hashes  # type: ignore
        from cryptography.hazmat.primitives.serialization import (
            load_der_private_key,
            load_pem_private_key,
            Encoding,
        )  # type: ignore
        from cryptography import x509  # type: ignore
        from cryptography.hazmat.primitives.asymmetric import padding as asy_padding  # type: ignore
        from cryptography.hazmat.primitives.asymmetric.rsa import RSAPrivateKey  # type: ignore
        from typing import cast

        # Construir Envelope SOAP 1.1
        NS_SOAP = 'http://schemas.xmlsoap.org/soap/envelope/'
        NS_DES = 'http://DescargaMasivaTerceros.sat.gob.mx'
        NS_DS = 'http://www.w3.org/2000/09/xmldsig#'
        env = etree.Element(etree.QName(NS_SOAP, 'Envelope'), nsmap={'s': NS_SOAP, 'des': NS_DES})
        etree.SubElement(env, etree.QName(NS_SOAP, 'Header'))
        body = etree.SubElement(env, etree.QName(NS_SOAP, 'Body'))
        op = 'SolicitaDescargaEmitidos' if (kind or '').lower().startswith('emit') else 'SolicitaDescargaRecibidos'
        wrapper = etree.SubElement(body, etree.QName(NS_DES, op))
        wrapper.set('Id', '_0')
        solicitud = etree.SubElement(wrapper, etree.QName(NS_DES, 'solicitud'))
        # Atributos de la solicitud
        solicitud.set('FechaInicial', f'{date_from}T00:00:00')
        solicitud.set('FechaFinal', f'{date_to}T23:59:59')
        solicitud.set('RfcSolicitante', (solicitante_rfc or rfc))
        solicitud.set('TipoSolicitud', tipo_solicitud)
        if op == 'SolicitaDescargaEmitidos':
            solicitud.set('RfcEmisor', rfc)
        else:
            solicitud.set('RfcReceptor', rfc)
        if estado_comp in ('0','1'):
            # Algunos entornos SAT rechazan explícitamente solicitudes con EstadoComprobante="0".
            # Omitimos el atributo cuando es '0' para dejar por defecto 'vigentes'.
            if estado_comp == '1':
                solicitud.set('EstadoComprobante', estado_comp)
        if tipo_comp in ('I','E','P','N'):
            solicitud.set('TipoComprobante', tipo_comp)

        # Firma XMLDSig (enveloped) igual que python-satcfdi
        if cer_bytes is not None and key_bytes is not None:
            # digest sobre el wrapper (no el documento completo), c14n INCLUSIVA
            digest_src = etree.tostring(wrapper, method='c14n', exclusive=False, with_comments=False)
            import hashlib as _hl
            digest = _b64.b64encode(_hl.sha1(digest_src).digest()).decode('ascii')

            si = etree.Element(etree.QName(NS_DS, 'SignedInfo'))
            etree.SubElement(si, etree.QName(NS_DS, 'CanonicalizationMethod'), Algorithm='http://www.w3.org/TR/2001/REC-xml-c14n-20010315')
            etree.SubElement(si, etree.QName(NS_DS, 'SignatureMethod'), Algorithm='http://www.w3.org/2000/09/xmldsig#rsa-sha1')
            # URI vacía (firma "enveloped" del elemento contenedor), como satcfdi
            ref = etree.SubElement(si, etree.QName(NS_DS, 'Reference'), URI='')
            trans = etree.SubElement(ref, etree.QName(NS_DS, 'Transforms'))
            etree.SubElement(trans, etree.QName(NS_DS, 'Transform'), Algorithm='http://www.w3.org/2000/09/xmldsig#enveloped-signature')
            etree.SubElement(ref, etree.QName(NS_DS, 'DigestMethod'), Algorithm='http://www.w3.org/2000/09/xmldsig#sha1')
            etree.SubElement(ref, etree.QName(NS_DS, 'DigestValue')).text = digest

            si_c14n = etree.tostring(si, method='c14n', exclusive=False)
            # Cargar llave y firmar si_c14n con SHA1 PKCS1v15
            priv = None
            for loader in (load_der_private_key, load_pem_private_key):
                try:
                    priv = loader(key_bytes, password=(key_passphrase.encode('utf-8') if key_passphrase else None))
                    break
                except Exception:
                    continue
            if priv is None:
                raise RuntimeError('No se pudo cargar la .key para firmar la solicitud (manual)')
            if not isinstance(priv, RSAPrivateKey):
                raise RuntimeError('La llave privada no es RSA. El SAT requiere RSA para firmar la solicitud.')
            priv_rsa: RSAPrivateKey = cast(RSAPrivateKey, priv)
            sig_bytes = priv_rsa.sign(si_c14n, asy_padding.PKCS1v15(), hashes.SHA1())
            sig_b64 = _b64.b64encode(sig_bytes).decode('ascii')

            ds_sig = etree.Element(etree.QName(NS_DS, 'Signature'))
            ds_sig.append(si)
            etree.SubElement(ds_sig, etree.QName(NS_DS, 'SignatureValue')).text = sig_b64
            ki = etree.SubElement(ds_sig, etree.QName(NS_DS, 'KeyInfo'))
            x509_el = etree.SubElement(ki, etree.QName(NS_DS, 'X509Data'))
            # Certificado base64
            try:
                cert = None
                try:
                    cert = x509_load = x509.load_der_x509_certificate(cer_bytes)
                except Exception:
                    cert = x509.load_pem_x509_certificate(cer_bytes)
                cert_der = cert.public_bytes(Encoding.DER)
                etree.SubElement(x509_el, etree.QName(NS_DS, 'X509Certificate')).text = _b64.b64encode(cert_der).decode('ascii')
            except Exception:
                pass
            # Insertar firma como hijo de 'solicitud'
            solicitud.append(ds_sig)

        # Enviar
        data = etree.tostring(env, encoding='utf-8', xml_declaration=True)
        if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes'):
            try:
                with open('sat_request_envelope.xml', 'wb') as fh:
                    fh.write(data)
            except Exception:
                pass
        url = self.request_wsdl.split('?')[0]
        soap_action = f'http://DescargaMasivaTerceros.sat.gob.mx/ISolicitaDescargaService/{op}'
        last_err = None
        resp = None
        for quoted in (False, True):  # probar primero sin comillas, como satcfdi
            headers = {
                'Content-type': 'text/xml;charset="utf-8"',
                'Accept': 'text/xml',
                'SOAPAction': f'"{soap_action}"' if quoted else soap_action,
                'Authorization': f'WRAP access_token="{token}"',
            }
            try:
                resp = requests.post(url, data=data, headers=headers, timeout=30)
            except Exception as e:
                last_err = e
                continue
            if resp.status_code < 400:
                if os.environ.get('SAT_SAVE_SOAP', '0').lower() in ('1','true','yes'):
                    try:
                        with open('sat_request_response.xml', 'wb') as fh:
                            fh.write(resp.content)
                    except Exception:
                        pass
                break
            last_err = RuntimeError(f'Solicitud HTTP {resp.status_code}: {(resp.text or "")[:300]}')
        if resp is None:
            raise RuntimeError(f'Error enviando solicitud: {last_err}')
        if resp.status_code >= 400:
            raise last_err if isinstance(last_err, BaseException) else RuntimeError(str(last_err))
        try:
            doc = etree.fromstring(resp.content)
        except Exception as e:
            raise RuntimeError(f'Respuesta inválida del SAT (no XML) en solicitud: {e}')

        # Extraer resultado
        res = doc.find(f'{{*}}Body/{{*}}{op}Response/{{*}}{op}Result')
        if res is None:
            # intentar cualquier '*Result'
            for el in doc.xpath('//*[contains(local-name(),"Result")]'):
                res = el
                break
        if res is None:
            raise RuntimeError('El SAT no devolvió nodo de resultado en la solicitud')
        cod = res.attrib.get('CodEstatus') or res.attrib.get('CodigoEstatus') or ''
        msg = res.attrib.get('Mensaje') or res.attrib.get('Observaciones') or ''
        req_id = res.attrib.get('IdSolicitud')
        # Registrar metadatos incluso si la solicitud es rechazada para diagnóstico externo
        self._last_request_meta = {
            'codestatus': cod,
            'mensaje': msg,
            'kind': kind,
            'rfc_objetivo': rfc,
            'fecha_inicial': date_from,
            'fecha_final': date_to,
            'tipo_solicitud': tipo_solicitud,
            'estado_comprobante_enviado': (estado_comp if estado_comp == '1' else None),
            'tipo_comprobante': (tipo_comp or None),
            'manual': True,
        }
        if not req_id:
            raise RuntimeError(f"Solicitud rechazada por el SAT (CodEstatus={cod or 'N/A'}): {msg or 'sin mensaje'}")
        if cod and cod not in ('5000','Solicitud Aceptada','OK','5005','5004'):
            raise RuntimeError(f"SAT reportó estado {cod}: {msg or 'sin mensaje'}")
        return str(req_id)

    def wait_and_list_packages(self, token: str, request_id: str) -> List[str]:
        """Realiza polling al SAT hasta que la solicitud esté lista y devuelve los IDs de paquetes."""
        if os.environ.get('SAT_USE_SATCFDI_FULL','0').lower() in ('1','true','yes'):
            sat_instance = self._satcfdi_requests.get(request_id) or self._satcfdi_last_instance
            if sat_instance is not None:
                try:
                    from . import satcfdi_adapter
                    res = satcfdi_adapter.verificar(sat_instance, request_id)
                    cod = res.get('codigo')
                    if cod == '5004':
                        return []
                    if cod in ('5003','5011'):
                        raise RuntimeError(f'Verificación SATCFDI código {cod}')
                    return [str(p) for p in res.get('paquetes', [])]
                except Exception as e:
                    # Fallback a flujo original si falla
                    print(f"[SATCFDI_FULL][WARN] Verificación fallback: {e}")
        # El endpoint de verificación suele ser distinto al de solicitud
        trace_enabled = os.environ.get('SAT_TRACE_VERIFY', '0').lower() in ('1','true','yes')
        if trace_enabled:
            # Reset trazas anteriores
            self._last_verify_trace = []
        try:
            client = self._client_with_token(self.verify_wsdl, token)
        except Exception:
            # Fallback al WSDL de solicitud si no está disponible el de verificación
            client = self._client_with_token(self.request_wsdl, token)
        # Aumentamos el rango para dar más tiempo, hasta 5 minutos
        for i in range(150):
            for op in ('VerificaSolicitudDescarga', 'VerificarSolicitudDescarga', 'ConsultarSolicitudDescarga'):
                try:
                    svc = getattr(client.service, op)
                    try:
                        resp = svc(solicitud={'IdSolicitud': request_id})
                    except Exception:
                        resp = svc({'IdSolicitud': request_id})
                    estado = getattr(resp, 'EstadoSolicitud', '0')
                    cod = str(getattr(resp, 'CodigoEstadoSolicitud', ''))
                    msg = str(getattr(resp, 'Mensaje', '')) or str(getattr(resp, 'Observaciones', ''))
                    if trace_enabled and len(self._last_verify_trace) < 20:
                        # Guardar primeros 20 estados para diagnóstico
                        self._last_verify_trace.append({
                            'intento': i + 1,
                            'operacion': op,
                            'estado': estado,
                            'codigo': cod,
                            'mensaje': msg,
                        })
                    
                    if str(estado) in ('3', 'Terminada'): # 3 es "Terminada"
                        paquetes_raw = getattr(resp, 'IdsPaquetes', []) or []
                        # Normalizar a lista de strings
                        if isinstance(paquetes_raw, (list, tuple)):
                            paquetes = [str(p) for p in paquetes_raw if str(p).strip()]
                        elif isinstance(paquetes_raw, str):
                            paquetes = [p.strip() for p in paquetes_raw.split(',') if p.strip()]
                        else:
                            try:
                                # Algunos esquemas devuelven un objeto con atributo 'string' o similar
                                posibles = getattr(paquetes_raw, 'string', None) or getattr(paquetes_raw, 'IdPaquete', None) or []
                                if isinstance(posibles, str):
                                    paquetes = [p.strip() for p in posibles.split(',') if p.strip()]
                                else:
                                    paquetes = [str(p) for p in posibles] if posibles else []
                            except Exception:
                                paquetes = []
                        if trace_enabled and self._last_verify_trace:
                            # Marcar finalización
                            self._last_verify_trace.append({'fin': True, 'paquetes': len(paquetes)})
                        return paquetes
                    # Manejo temprano de códigos específicos del PDF
                    if cod == '5004':
                        # No se encontró la información: no hay paquetes
                        if trace_enabled:
                            self._last_verify_trace.append({'terminada_sin_info': True, 'codigo': cod})
                        return []
                    if cod == '5003':
                        raise RuntimeError('La solicitud sobrepasa el tope máximo de resultados del SAT (5003). Reduce el rango de fechas o segmenta la consulta.')
                    if cod == '5011':
                        raise RuntimeError('Se alcanzó el límite de descargas por día (5011). Intenta de nuevo más tarde.')
                    if cod in {'300','301','302','303','304','305'}:
                        raise RuntimeError(f'Error de verificación SAT código {cod}: {msg or "verifica usuario, sello, certificado o XML"}')
                    elif str(estado) in ('4', 'Error', '5', 'Rechazada', '6', 'Vencida'):
                         cod_estado = getattr(resp, 'CodigoEstadoSolicitud', 'N/A')
                         raise RuntimeError(f"La solicitud {request_id} falló con estado {estado} y código {cod_estado}.")

                except Exception as e:
                    # Ignorar errores de operación no encontrada y reintentar
                    emsg = str(e)
                    if ('No such operation' in emsg) or ('Service has no operation' in emsg):
                        pass
                    else:
                        raise e # Re-lanzar otros errores de zeep
            
            print(f"Esperando paquetes... intento {i+1}")
            time.sleep(2) # Espera 2 segundos entre cada verificación
            
        raise RuntimeError(f'Timeout esperando paquetes del SAT para la solicitud {request_id}.')

    def download_package_xmls(self, token: str, package_id: str) -> List[Dict[str, Any]]:
        """Descarga un paquete ZIP, lo descomprime y extrae la información de los XMLs."""
        if os.environ.get('SAT_USE_SATCFDI_FULL','0').lower() in ('1','true','yes'):
            sat_instance = self._satcfdi_last_instance
            if sat_instance is not None:
                try:
                    from . import satcfdi_adapter
                    pkg = satcfdi_adapter.descargar_paquete(sat_instance, package_id)
                    items = satcfdi_adapter.parse_zip_cfdis(pkg['b64'])
                    return items
                except Exception as e:
                    print(f"[SATCFDI_FULL][WARN] Descarga fallback: {e}")
        # El endpoint de descarga suele ser distinto al de solicitud/verificación
        try:
            client = self._client_with_token(self.download_wsdl, token)
        except Exception:
            client = self._client_with_token(self.request_wsdl, token)
        data_b64 = None
        for op in ('Descargar', 'DescargaMasiva'):
            try:
                svc = getattr(client.service, op)
                try:
                    resp = svc(peticionDescarga={'IdPaquete': package_id})
                except Exception:
                    resp = svc({'IdPaquete': package_id})
                data_b64 = getattr(resp, 'Paquete', None)
                if data_b64:
                    break
            except Exception:
                continue
        if not data_b64:
            raise RuntimeError(f'El SAT no devolvió contenido para el paquete {package_id}')
        
        try:
            raw = base64.b64decode(data_b64)
            zf = zipfile.ZipFile(BytesIO(raw))
        except Exception as e:
            raise RuntimeError(f'El paquete {package_id} es inválido o corrupto: {e}')

        items = []
        for name in zf.namelist():
            if not name.lower().endswith('.xml'):
                continue
            try:
                xml_bytes = zf.read(name)
                text = xml_bytes.decode('utf-8', errors='ignore')
                import re

                def rex(pat):
                    m = re.search(pat, text, re.I)
                    return m.group(1) if m else ''

                uid = rex(r'UUID="([^"]+)"') or str(uuid.uuid4()).upper()
                fecha = (rex(r'Fecha="([0-9T:\-]+)"') or '')[:10]
                subtotal = float(rex(r'SubTotal="([0-9\.]+)"') or 0)
                total = float(rex(r'Total="([0-9\.]+)"') or 0)
                tipo = (rex(r'TipoDeComprobante="([IEP])"') or 'I')
                emisor_rfc = (rex(r'Emisor[^>]*Rfc="([A-Z0-9&]+)"') or '').upper()
                receptor_rfc = (rex(r'Receptor[^>]*Rfc="([A-Z0-9&]+)"') or '').upper()
                iva = 0.0
                for m in re.finditer(r'Traslado[^>]*Impuesto="002"[^>]*Importe="([0-9\.]+)"', text, re.I):
                    try:
                        iva += float(m.group(1) or 0)
                    except Exception:
                        pass
                
                items.append({
                    'uuid': uid, 'fecha': fecha, 'subtotal': subtotal, 'iva': round(iva, 2) if iva else None,
                    'total': total, 'tipo': tipo, 'emisor_rfc': emisor_rfc, 'receptor_rfc': receptor_rfc,
                    'content': text,
                })
            except Exception:
                continue
        return items
