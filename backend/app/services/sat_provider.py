from enum import Enum
from typing import Optional, Tuple, List, Dict, Any
import uuid
import os
from datetime import datetime
from ..supabase_client import get_supabase
from .sat_sat20 import Sat20Client
from cryptography.hazmat.primitives.serialization import load_der_private_key, load_pem_private_key
from cryptography import x509
from cryptography.x509.oid import NameOID, ExtensionOID
import time
import re
import socket
import hashlib

try:  # zeep/xmlsec availability checks (for SAT SOAP mode diagnostics)
    import zeep  # type: ignore
    _ZEEP_OK = True
except Exception:  # pragma: no cover
    _ZEEP_OK = False
try:
    import xmlsec  # type: ignore
    _XMLSEC_OK = True
except Exception:  # pragma: no cover
    _XMLSEC_OK = False
try:
    import httpx  # type: ignore
    _HTTPX_OK = True
except Exception:  # pragma: no cover
    _HTTPX_OK = False

class SatKind(str, Enum):
    recibidos = 'recibidos'
    emitidos = 'emitidos'

class SatProvider:
    def __init__(self):
        # Bucket de firmas: por defecto antes era 'firmas'. Tu proyecto usa 'fiscalia'.
        # Si no se define FIRMAS_BUCKET en entorno, intentamos detectar 'fiscalia' si existe variable alternativa.
        self.firmas_bucket = os.environ.get('FIRMAS_BUCKET') or os.environ.get('FISCALIA_BUCKET') or 'firmas'
        self.cfdi_bucket = os.environ.get('CFDI_BUCKET', 'cfdi-xml')
        self.mode = os.environ.get('SAT_MODE', 'mock').lower()
        self.demo = os.environ.get('DEMO_MODE', 'false').lower() in ('1', 'true', 'yes')
        # Inicialización perezosa/segura del cliente de Supabase para que /sat/self-check
        # funcione aunque falten variables de entorno.
        try:
            self.sb = get_supabase()
            self.init_error = None
        except Exception as e:
            self.sb = None  # type: ignore[assignment]
            self.init_error = str(e)

    def _sb(self):
        """Devuelve un cliente de Supabase listo o lanza un error claro si falta config."""
        if self.sb is None:
            try:
                self.sb = get_supabase()
            except Exception as e:
                raise RuntimeError(f"Supabase no configurado: {e}")
        return self.sb

    def self_check(self) -> Dict[str, Any]:
        """Verifica prerequisitos del núcleo: entorno, conexión a Supabase,
        tablas mínimas y buckets de Storage. Devuelve un dict con detalles.

        No modifica nada; solo intenta listar/seleccionar y reporta errores claros.
        """
        out: Dict[str, Any] = {
            'sat_mode': self.mode,
            'demo_mode': self.demo,
            'env': {
                'SUPABASE_URL': bool(os.environ.get('SUPABASE_URL')),
                'SUPABASE_SERVICE_ROLE': bool(os.environ.get('SUPABASE_SERVICE_ROLE')),
                'FIRMAS_BUCKET': self.firmas_bucket,
                'CFDI_BUCKET': self.cfdi_bucket,
            },
            'supabase_ok': False,
            'tables': {},
            'buckets': {},
            'soap_prereqs': {}
        }
        # Conexión a Supabase
        try:
            sb = self.sb or get_supabase()
            out['supabase_ok'] = True
        except Exception as e:
            out['supabase_error'] = str(e)
            return out

        # Tablas requeridas
        tables = ['profiles', 'companies', 'sat_jobs', 'cfdi', 'taxes_monthly']
        for t in tables:
            try:
                # seleccionar 1 fila (puede estar vacía, lo importante es que exista)
                sb.table(t).select('*').limit(1).execute()
                out['tables'][t] = {'exists': True}
            except Exception as e:
                out['tables'][t] = {'exists': False, 'error': str(e)}

        # Buckets requeridos
        for b in [self.firmas_bucket, self.cfdi_bucket]:
            try:
                # intentar listar raíz
                sb.storage.from_(b).list("")
                out['buckets'][b] = {'exists': True}
            except Exception as e:
                out['buckets'][b] = {'exists': False, 'error': str(e)}
        if self.firmas_bucket == 'firmas' and out['buckets'].get('firmas', {}).get('exists') is False:
            # Hint para el caso donde realmente se llama 'fiscalia'
            out['buckets_hint'] = 'Define FIRMAS_BUCKET=fiscalia en .env si tu bucket real de e.firma es fiscalia.'

        # Prerrequisitos SOAP sólo si el modo configurado es soap (o siempre, pero marcamos)
        soap = {
            'zeep_installed': _ZEEP_OK,
            'xmlsec_installed': _XMLSEC_OK,
            'httpx_installed': _HTTPX_OK,
            'wsdl_autenticacion_reachable': None,
            'wsdl_solicitud_reachable': None,
            'system_has_openssl': False,
            'clock_utc': datetime.utcnow().isoformat() + 'Z',
        }
        # Señal rápida de que el sistema probablemente tiene openssl (usado por xmlsec)
        try:
            import subprocess, shlex
            # Windows: 'where openssl', Unix: 'which openssl'. Probamos ambos guardando errores.
            cmd = 'where openssl' if os.name == 'nt' else 'which openssl'
            p = subprocess.run(shlex.split(cmd), capture_output=True, text=True, timeout=3)
            if p.returncode == 0 and p.stdout.strip():
                soap['system_has_openssl'] = True
        except Exception:
            pass

        if _HTTPX_OK:
            # Intentos HEAD/GET cortos para evaluar accesibilidad (sin bloquear si la red está caída)
            from .sat_sat20 import WSDL_AUTENTICACION, WSDL_SOLICITUD  # local import to avoid cycles
            for field, url in [
                ('wsdl_autenticacion_reachable', WSDL_AUTENTICACION),
                ('wsdl_solicitud_reachable', WSDL_SOLICITUD),
            ]:
                try:
                    # DNS + socket check rápido antes de la petición para aislar problema de resolución
                    host = url.split('//',1)[1].split('/',1)[0]
                    try:
                        socket.gethostbyname(host)
                    except Exception as dns_e:
                        soap[field] = f'dns_error:{dns_e}'
                        continue
                    with httpx.Client(timeout=5.0, verify=True) as client:  # type: ignore
                        try:
                            r = client.head(url)
                            if r.status_code >= 400:
                                # fallback a GET por si HEAD no permitido
                                r = client.get(url)
                            soap[field] = f'OK({r.status_code})'
                        except Exception as req_e:
                            soap[field] = f'error:{req_e.__class__.__name__}'
                except Exception as e:
                    soap[field] = f'error:{e}'
        out['soap_prereqs'] = soap
        return out

    # --- Helpers internos adicionales ---
    def _compute_will_expire_soon(self, cert) -> bool:
        """Devuelve True si el certificado expira en <=60 días.

        Evita errores de resta aware vs naive normalizando a naive UTC.
        """
        try:
            from datetime import timezone
            not_after = getattr(cert, 'not_valid_after_utc', None) or getattr(cert, 'not_valid_after', None)
            if not_after is None:
                return False
            # Convertir aware->naive UTC
            if getattr(not_after, 'tzinfo', None) is not None and not_after.tzinfo is not None:
                not_after_naive = not_after.astimezone(timezone.utc).replace(tzinfo=None)
            else:
                not_after_naive = not_after
            now_naive = datetime.utcnow()
            delta = not_after_naive - now_naive
            return delta.days <= 60
        except Exception:
            return False

    def load_firma(self, user_id: str) -> tuple[bytes, bytes]:
        """Carga los bytes del .cer y .key desde Storage usando firma_ref del perfil.

        Devuelve (cer_bytes, key_bytes). No expone rutas; pensado para consumo interno (/sat/auth).
        """
        prof = self._get_profile(user_id, require_rfc=False)
        firma_ref: str = prof['firma_ref']
        files = self._list_firma_files(firma_ref)
        cer_path, key_path = self._get_cer_key_paths(files)
        cer_bytes = self._download_bytes(cer_path)
        key_bytes = self._download_bytes(key_path)
        return cer_bytes, key_bytes

    def inspect_firma(self, user_id: str) -> Dict[str, Any]:
        """Lee el .cer del usuario y devuelve sugerencias para autocompletar perfil.

        Campos sugeridos: rfc, full_name o legal_name, persona_moral, valid_from/to, serial_hex, issuer.
        Regla importante: si el perfil ya tiene RFC, se respeta y se usa para decidir física/moral.
        """
        # Para inspección de certificado NO requerimos .key; basta el .cer
        prof = self._get_profile(user_id, require_rfc=False)
        firma_ref: str = prof['firma_ref']
        rfc_profile = str((prof.get('rfc') or '')).upper().strip()
        files = self._list_firma_files(firma_ref)
        cer_path = next((p for p in files if p.lower().endswith('.cer')), None)
        if not cer_path:
            raise RuntimeError(f"No se encontró archivo .cer en Storage. Bucket='{self.firmas_bucket}', firma_ref='{firma_ref}'. Sube tu cert.cer desde la sección 'Subir e.firma'.")
        cer = self._download_bytes(cer_path)
        # Parsear certificado
        cert = None
        for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
            try:
                cert = loader(cer)
                break
            except Exception:
                pass
        if cert is None:
            raise RuntimeError('No se pudo leer el certificado .cer')

        subj = cert.subject
        issuer = cert.issuer
        # Fuerza a str para evitar confusiones del type checker entre bytes/str
        cn = str(next((a.value for a in subj if a.oid == NameOID.COMMON_NAME), ''))
        sn = str(next((a.value for a in subj if a.oid == NameOID.SERIAL_NUMBER), ''))
        org = str(next((a.value for a in subj if a.oid == NameOID.ORGANIZATION_NAME), ''))

        # Extensiones útiles para diagnosticar FIEL vs CSD
        eku_list = []
        policies = []
        try:
            eku_ext = cert.extensions.get_extension_for_oid(ExtensionOID.EXTENDED_KEY_USAGE)  # type: ignore[attr-defined]
            eku_val = getattr(eku_ext, 'value', None)
            if eku_val is not None:
                for oid in getattr(eku_val, 'usages', []):
                    try:
                        eku_list.append(str(oid.dotted_string))
                    except Exception:
                        eku_list.append(str(oid))
        except Exception:
            pass
        try:
            cps_ext = cert.extensions.get_extension_for_oid(ExtensionOID.CERTIFICATE_POLICIES)  # type: ignore[attr-defined]
            cps_val = getattr(cps_ext, 'value', None)
            if cps_val is not None:
                for pol in cps_val:
                    try:
                        policies.append(str(pol.policy_identifier.dotted_string))
                    except Exception:
                        try:
                            policies.append(str(pol.policy_identifier))
                        except Exception:
                            pass
        except Exception:
            pass

        # Extraer RFC por regex desde CN o serialNumber
        rfc_pat = re.compile(r'[A-ZÑ&]{3,4}\d{6}[A-Z0-9]{3}', re.I)
        rfc_cert = ''
        for source in (cn or '', sn or '', org or ''):
            m = rfc_pat.search(str(source).upper())
            if m:
                rfc_cert = m.group(0)
                break

        # Decidir persona_moral priorizando el RFC del perfil si existe (más confiable)
        def infer_pm(rfc: str) -> Optional[bool]:
            if len(rfc) == 12:
                return True
            if len(rfc) == 13:
                return False
            return None

        persona_moral_origin = None
        persona_moral = None
        # Primero, si el perfil ya tiene RFC válido, lo usamos
        if infer_pm(rfc_profile) is not None:
            persona_moral = infer_pm(rfc_profile)
            persona_moral_origin = 'profile_rfc_length'
        else:
            # Intentar clasificar el RFC encontrado en el certificado
            from ..utils.rfc import classify_rfc  # import local para evitar ciclos al iniciar
            if rfc_cert:
                cls = classify_rfc(rfc_cert)
                if cls.get('valid'):
                    persona_moral = cls.get('persona_moral')  # type: ignore[assignment]
                    persona_moral_origin = 'cert_classification'
                else:
                    persona_moral = infer_pm(rfc_cert)
                    persona_moral_origin = 'cert_length_heuristic'
            else:
                persona_moral = None
                persona_moral_origin = 'unknown'

        # RFC sugerido: prioriza el del perfil si es válido, si no el del cert si parece válido
        rfc = rfc_profile if infer_pm(rfc_profile) is not None else (rfc_cert or None)

        # Heurística de nombres: si persona moral, usar CN u O como razón social; si física, CN como full_name
        legal_name = None
        full_name = None
        if rfc and persona_moral:
            # Intenta quitar el RFC del CN si viene embebido
            base = str(cn or org or '')
            legal_name = base.replace(rfc or '', '').replace(':', ' ').strip() or (org or None)
        else:
            base_cn = str(cn or '')
            full_name = base_cn.replace(rfc or '', '').replace(':', ' ').strip() or None

        # Heurística simple: si CN/OU/ORG menciona 'SELLO' o similar, probablemente es CSD.
        text_all = f"{cn} {org}".upper()
        is_probably_csd = ('SELLO' in text_all) or ('CSD' in text_all)

        # Clasificación adicional del RFC sugerido (puede diferir del RFC extraído del cert)
        rfc_analysis = None
        try:
            if rfc:
                from ..utils.rfc import classify_rfc
                rfc_analysis = classify_rfc(rfc)
        except Exception:
            rfc_analysis = None

        out = {
            'rfc': rfc or None,
            'rfc_cert': rfc_cert or None,
            'rfc_profile': rfc_profile or None,
            'persona_moral': persona_moral,
            'persona_moral_origin': persona_moral_origin,
            'full_name': full_name,
            'legal_name': legal_name,
            'subject_common_name': cn or None,
            'subject_serial_number': sn or None,
            'issuer': ', '.join([f"{a.oid._name}={a.value}" for a in issuer]) if issuer else None,
            'valid_from': getattr(cert, 'not_valid_before_utc', cert.not_valid_before).isoformat(),
            'valid_to': getattr(cert, 'not_valid_after_utc', cert.not_valid_after).isoformat(),
            'serial_hex': format(cert.serial_number, 'x').upper(),
            # Cálculo robusto evitando resta entre aware vs naive datetimes
            'will_expire_soon': self._compute_will_expire_soon(cert),
            'ext_key_usages': eku_list,
            'certificate_policies': policies,
            'is_probably_csd': is_probably_csd,
            'rfc_analysis': rfc_analysis,
        }
        return out

    def debug_profile(self, user_id: str) -> Dict[str, Any]:
        """Devuelve información cruda del perfil y listado de archivos bajo firma_ref.

        No intenta interpretar el certificado. Útil para depurar errores 400 de /sat/inspect
        (por ejemplo: perfil sin fila, sin firma_ref, archivos mal nombrados, falta .cer/.key).
        """
        sb = self._sb()
        # Evitar maybe_single para esquivar bug 204 Missing response
        prof_resp = sb.table('profiles').select('*').eq('user_id', user_id).limit(1).execute()
        data_list = getattr(prof_resp, 'data', None)
        if not data_list:
            return {'exists': False, 'error': 'Perfil no encontrado', 'user_id': user_id}
        prof = data_list[0]
        firma_ref = prof.get('firma_ref') if isinstance(prof, dict) else None
        files = []
        list_error = None
        if firma_ref:
            try:
                files = self._list_firma_files(str(firma_ref))
            except Exception as e:
                list_error = str(e)
        return {
            'exists': True,
            'user_id': user_id,
            'profile': prof,
            'firma_ref': firma_ref,
            'files': files,
            'missing_cer': not any(f.lower().endswith('.cer') for f in files),
            'missing_key': not any(f.lower().endswith('.key') for f in files),
            'list_error': list_error,
            'bucket': self.firmas_bucket,
        }

    def debug_firma(self, user_id: str) -> Dict[str, Any]:
        """Verifica que se pueden leer los bytes del .cer y .key y devuelve metadatos mínimos.

        NO requiere passphrase (sólo se descarga el .key cifrado). Útil antes de pedir la contraseña.
        No expone el contenido de los archivos, sólo tamaños, hash del .cer y metadatos básicos.
        """
        prof = self._get_profile(user_id, require_rfc=False)
        firma_ref: str = prof['firma_ref']
        files = self._list_firma_files(firma_ref)
        cer_path, key_path = self._get_cer_key_paths(files)
        cer_bytes = self._download_bytes(cer_path)
        key_bytes = self._download_bytes(key_path)

        # Intentar parsear el certificado para confirmar que es válido y extraer CN y vigencia
        cert = None
        for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
            try:
                cert = loader(cer_bytes)
                break
            except Exception:
                pass
        if cert is None:
            return {
                'ok': False,
                'error': 'No se pudo parsear el .cer',
                'cer_path': cer_path,
                'key_path': key_path,
                'cer_size': len(cer_bytes),
                'key_size': len(key_bytes),
            }

        subj = cert.subject
        subj_cn = next((a.value for a in subj if a.oid == NameOID.COMMON_NAME), None)
        subj_sn = next((a.value for a in subj if a.oid == NameOID.SERIAL_NUMBER), None)
        subj_org = next((a.value for a in subj if a.oid == NameOID.ORGANIZATION_NAME), None)
        text_all = f"{str(subj_cn or '')} {str(subj_org or '')}".upper()
        is_probably_csd = ('SELLO' in text_all) or ('CSD' in text_all)

        sha256 = hashlib.sha256(cer_bytes).hexdigest().upper()

        return {
            'ok': True,
            'cer_path': cer_path,
            'key_path': key_path,
            'cer_size': len(cer_bytes),
            'key_size': len(key_bytes),
            'cer_sha256': sha256,
            'subject_common_name': subj_cn,
            'subject_serial_number': subj_sn,
            'valid_from': getattr(cert, 'not_valid_before_utc', cert.not_valid_before).isoformat(),
            'valid_to': getattr(cert, 'not_valid_after_utc', cert.not_valid_after).isoformat(),
            'serial_hex': format(cert.serial_number, 'x').upper(),
            'is_probably_csd': is_probably_csd,
            'rfc_in_profile': prof.get('rfc'),
        }

    def _get_profile(self, user_id: str, require_rfc: bool = True) -> dict:
        try:
            resp = self._sb().table('profiles').select('user_id,rfc,firma_ref').eq('user_id', user_id).limit(1).execute()
        except Exception as e:
            msg = str(e)
            if 'Missing response' in msg or "'code': '204'" in msg:
                raise RuntimeError('Perfil no encontrado para el usuario (profiles.user_id)')
            raise RuntimeError(f'Error consultando perfil en Supabase: {e}')
        data_list = getattr(resp, 'data', None)
        if not data_list:
            raise RuntimeError('Perfil no encontrado para el usuario (profiles.user_id)')
        if not isinstance(data_list, list) or not data_list or not isinstance(data_list[0], dict):
            raise RuntimeError('Respuesta de perfil inesperada')
        data = data_list[0]
        if require_rfc and not data.get('rfc'):
            raise RuntimeError('Perfil sin RFC; completa tu RFC en el Perfil')
        if not data.get('firma_ref'):
            raise RuntimeError('Perfil sin referencia de e.firma (firma_ref)')
        return data

    def _list_firma_files(self, prefix: str) -> List[str]:
        prefix = prefix.strip('/')
        files = self._sb().storage.from_(self.firmas_bucket).list(path=prefix or '')
        names: List[str] = [f['name'] for f in files]
        return [f"{prefix}/{n}" if prefix else n for n in names]

    def _get_cer_key_paths(self, files: List[str]) -> Tuple[str, str]:
        cer = next((p for p in files if p.lower().endswith('.cer')), None)
        key = next((p for p in files if p.lower().endswith('.key')), None)
        if not cer or not key:
            raise RuntimeError('No se encontraron archivos .cer y .key en el bucket de firmas bajo firma_ref')
        return cer, key

    def _download_bytes(self, path: str) -> bytes:
        data = self._sb().storage.from_(self.firmas_bucket).download(path)
        return bytes(data)

    def _get_company_rfc(self, company_id: str) -> str:
        # Realizamos la consulta y extraemos el atributo "data" de forma segura para
        # que Pylance (y type checkers) no marquen acceso potencial a None.
        resp = self._sb().table('companies').select('rfc').eq('id', company_id).maybe_single().execute()
        data = getattr(resp, 'data', None)
        if not data or not isinstance(data, dict):
            raise RuntimeError('Compañía no encontrada')
        rfc = data.get('rfc')
        if not rfc:
            raise RuntimeError('La compañía no tiene RFC definido')
        return str(rfc).upper()

    def _update_job(self, job_id: str, fields: Dict[str, Any]):
        try:
            resp = self._sb().table('sat_jobs').update(fields).eq('id', job_id).execute()
            _ = getattr(resp, 'data', None)  # acceso seguro; ignoramos resultado
        except Exception as e:
            raise RuntimeError(f"Error actualizando job: {e}")

    def enqueue_sync(self, user_id: str, company_id: str, kind: SatKind, date_from: Optional[str], date_to: Optional[str], tipo_solicitud: Optional[str] = None) -> str:
        df = date_from or datetime.utcnow().strftime('%Y-%m-01')
        dt = date_to or datetime.utcnow().strftime('%Y-%m-%d')

        if not self.demo:
            self._get_profile(user_id) # Valida que exista perfil y firma_ref

        job_id = str(uuid.uuid4())
        payload = {
            'id': job_id,
            'user_id': user_id,
            'company_id': company_id,
            'kind': kind.value,
            'date_from': df,
            'date_to': dt,
            'status': 'queued',
            'tipo_solicitud_final': (tipo_solicitud.upper() if tipo_solicitud else None),
        }
        try:
            self._sb().table('sat_jobs').insert(payload).execute()
        except Exception as e:
            raise RuntimeError(f"Error creando job: {e}")
        return job_id

    def process_job(
        self,
        job_id: str,
        user_id: str,
        company_id: str,
        kind: SatKind,
        date_from: Optional[str],
        date_to: Optional[str],
        passphrase: Optional[str] = None,
        tipo_solicitud: Optional[str] = None,
    ) -> None:
        try:
            self._update_job(job_id, {'status': 'running', 'updated_at': datetime.utcnow().isoformat()})

            df = date_from or datetime.utcnow().strftime('%Y-%m-01')
            dt = date_to or datetime.utcnow().strftime('%Y-%m-%d')
            
            company_rfc = self._get_company_rfc(company_id)
            generated_xmls = []

            disable_mock = os.environ.get('SAT_DISABLE_MOCK','0').lower() in ('1','true','yes')
            # Métricas
            t0 = time.time()
            auth_ms = request_ms = verify_ms = download_ms = 0
            packages_count: Optional[int] = None
            if self.mode == 'soap':
                if self.demo and disable_mock:
                    raise RuntimeError('El modo demo (mock) está deshabilitado por SAT_DISABLE_MOCK=1. Ejecuta con credenciales reales.')
                # Siempre forzamos flujo real si disable_mock o demo desactivado
                if not passphrase:
                    raise RuntimeError('Se requiere contraseña de e.firma para modo SOAP')
                # Preparar firma real
                prof = self._get_profile(user_id)
                firma_ref: str = prof['firma_ref']
                files = self._list_firma_files(firma_ref)
                cer_path, key_path = self._get_cer_key_paths(files)
                cer_bytes = self._download_bytes(cer_path)
                key_bytes = self._download_bytes(key_path)

                # Determinar RFC del certificado para usarlo como RfcSolicitante
                cert_rfc: Optional[str] = None
                try:
                    insp = self.inspect_firma(user_id)
                    cert_rfc = (str(insp.get('rfc_cert') or insp.get('rfc') or insp.get('rfc_profile') or '')).upper() or None
                except Exception:
                    cert_rfc = None
                if not cert_rfc:
                    self._update_job(job_id, {'note': 'No se pudo determinar RFC del certificado; se usará company_rfc como solicitante (puede fallar).'})
                    cert_rfc = company_rfc
                else:
                    if cert_rfc != company_rfc:
                        self._update_job(job_id, {'note': f'RFC certificado ({cert_rfc}) difiere del RFC de la compañía ({company_rfc}). Requiere autorización de terceros o usar FIEL del mismo RFC.'})

                # 1. Autenticar y obtener token
                sat_client = Sat20Client()
                ta = time.time()
                token = sat_client.authenticate(cer_bytes, key_bytes, passphrase)
                auth_ms = int((time.time() - ta) * 1000)
                self._update_job(job_id, {'note': 'Autenticación exitosa.'})

                # 2. Solicitar descarga (con fallback CFDI->Metadata en CodEstatus=301 cancelados)
                tipo_solicitud_final = 'CFDI'
                fallback_used = False
                try:
                    tr = time.time()
                    request_id = sat_client.request_download(
                        token=token,
                        rfc=company_rfc,
                        date_from=df,
                        date_to=dt,
                        kind=kind.value,
                        solicitante_rfc=cert_rfc,
                        cer_bytes=cer_bytes,
                        key_bytes=key_bytes,
                        key_passphrase=passphrase,
                    )
                    request_ms = int((time.time() - tr) * 1000)
                except Exception as e:
                    em = str(e)
                    meta_first = getattr(sat_client, '_last_request_meta', None) or {}
                    if 'CodEstatus=301' in em and 'cancelad' in em.lower():
                        try:
                            tr2 = time.time()
                            request_id = sat_client.request_download(
                                token=token,
                                rfc=company_rfc,
                                date_from=df,
                                date_to=dt,
                                kind=kind.value,
                                solicitante_rfc=cert_rfc,
                                tipo_solicitud_override='Metadata',
                                cer_bytes=cer_bytes,
                                key_bytes=key_bytes,
                                key_passphrase=passphrase,
                            )
                            request_ms = int((time.time() - tr2) * 1000)
                            tipo_solicitud_final = 'Metadata'
                            fallback_used = True
                            self._update_job(job_id, {
                                'note': 'Fallback CFDI->Metadata aplicado (CodEstatus=301 cancelados).',
                                'request_error': em,
                                'request_meta_first': meta_first,
                                'updated_at': datetime.utcnow().isoformat(),
                            })
                        except Exception as e2:
                            meta_second = getattr(sat_client, '_last_request_meta', None) or {}
                            self._update_job(job_id, {
                                'status': 'error',
                                'error': f'CFDI request fallo y fallback Metadata tambien fallo: {e2}',
                                'request_error': em,
                                'request_meta': meta_first,
                                'fallback_error': str(e2),
                                'fallback_meta': meta_second,
                                'updated_at': datetime.utcnow().isoformat(),
                            })
                            raise
                    else:
                        if 'CodEstatus=' in em or 'SAT reportó estado' in em:
                            self._update_job(job_id, {'status': 'error', 'error': em, 'request_meta': meta_first, 'updated_at': datetime.utcnow().isoformat()})
                            raise
                        if 'No se encontró la información' in em or '5004' in em:
                            self._update_job(job_id, {'status': 'success', 'note': 'SAT: No se encontró información para el rango/criterios (5004).', 'total_found': 0, 'total_downloaded': 0, 'request_meta': meta_first, 'updated_at': datetime.utcnow().isoformat()})
                            return
                        self._update_job(job_id, {'status': 'error', 'error': em, 'request_meta': meta_first, 'updated_at': datetime.utcnow().isoformat()})
                        raise

                meta_success = getattr(sat_client, '_last_request_meta', None) or {}
                self._update_job(job_id, {
                    'sat_request_id': request_id,
                    'status': 'verifying',
                    'note': 'Solicitud enviada al SAT.' + (' (fallback Metadata)' if fallback_used else ''),
                    'tipo_solicitud_final': tipo_solicitud_final,
                    'fallback_from_cfdi': fallback_used,
                    'request_meta': meta_success,
                    'updated_at': datetime.utcnow().isoformat(),
                })

                # 3. Verificar estatus y obtener paquetes
                try:
                    tv = time.time()
                    packages = sat_client.wait_and_list_packages(token, request_id)
                    verify_ms = int((time.time() - tv) * 1000)
                    packages_count = len(packages)
                except Exception as e:
                    self._update_job(job_id, {'status': 'error', 'error': f'Error en verificación: {e}', 'updated_at': datetime.utcnow().isoformat()})
                    raise
                self._update_job(job_id, {'note': f'Se encontraron {packages_count} paquetes.'})

                # 4. Descargar XMLs de cada paquete
                for pkg_id in packages:
                    try:
                        tp = time.time()
                        xml_contents = sat_client.download_package_xmls(token, pkg_id)
                        generated_xmls.extend(xml_contents)
                        download_ms += int((time.time() - tp) * 1000)
                        self._update_job(job_id, {'note': f'Paquete {pkg_id} descargado.'})
                    except Exception as e:
                        self._update_job(job_id, {'note': f'Error con paquete {pkg_id}: {e}'})
            else:
                # MODO MOCK (solo permitido si no se ha deshabilitado explícitamente)
                if disable_mock:
                    raise RuntimeError('SAT_DISABLE_MOCK=1 impide usar SAT_MODE=mock. Cambia a SAT_MODE=soap con credenciales reales.')
                generated_xmls = self._mock_sat_download(kind=kind, company_rfc=company_rfc)

            # --- Procesamiento y guardado de XMLs ---
            total_found = len(generated_xmls)
            total_downloaded = 0
            for xml_data in generated_xmls:
                try:
                    uid = xml_data['uuid']
                    xml_bytes = xml_data['content'].encode('utf-8')
                    storage_key = f"{user_id}/{company_id}/{uid}.xml"
                    
                    # Subir a Storage
                    self._sb().storage.from_(self.cfdi_bucket).upload(storage_key, xml_bytes)
                    
                    # Guardar registro en la base de datos
                    record = {
                        'company_id': company_id,
                        'uuid': uid, 'tipo': xml_data['tipo'], 'emisor_rfc': xml_data['emisor_rfc'],
                        'receptor_rfc': xml_data['receptor_rfc'], 'fecha': xml_data['fecha'],
                        'subtotal': xml_data['subtotal'], 'impuestos': xml_data['iva'],
                        'total': xml_data['total'], 'xml_ref': storage_key, 'status': 'imported',
                    }
                    self._sb().table('cfdi').upsert(record).execute()
                    total_downloaded += 1
                except Exception as e:
                    print(f"Error procesando XML {xml_data.get('uuid', 'N/A')}: {e}")
                    pass

            metrics_payload = {
                'status': 'success',
                'total_found': total_found,
                'total_downloaded': total_downloaded,
                'updated_at': datetime.utcnow().isoformat(),
                'auth_ms': auth_ms or None,
                'request_ms': request_ms or None,
                'verify_ms': verify_ms or None,
                'download_ms': download_ms or None,
                'sat_meta': {
                    'rfc_company': company_rfc,
                    'kind': kind.value,
                    'date_from': df,
                    'date_to': dt,
                    'packages': packages_count,
                }
            }
            try:
                self._update_job(job_id, metrics_payload)
            except Exception:
                # Si columnas no existen, concatenamos en note
                note = f"metrics auth={auth_ms}ms request={request_ms}ms verify={verify_ms}ms download={download_ms}ms"
                try:
                    self._update_job(job_id, {'status': 'success', 'total_found': total_found, 'total_downloaded': total_downloaded, 'note': note, 'updated_at': datetime.utcnow().isoformat()})
                except Exception:
                    self._update_job(job_id, {'status': 'success', 'total_found': total_found, 'total_downloaded': total_downloaded, 'updated_at': datetime.utcnow().isoformat()})

        except Exception as e:
            self._update_job(job_id, {'status': 'error', 'error': str(e), 'updated_at': datetime.utcnow().isoformat()})
            raise e

    # ... (el resto de tus métodos como _get_job, verify_firma, etc. permanecen igual) ...
    # ... (incluyendo tu excelente función _mock_sat_download para pruebas) ...
    
    # --- El resto de tus métodos auxiliares van aquí ---
    def get_job(self, job_id: str) -> Optional[Dict[str, Any]]:
        resp = self._sb().table('sat_jobs').select('*').eq('id', job_id).maybe_single().execute()
        data = getattr(resp, 'data', None)
        return data if isinstance(data, dict) else None

    def verify_firma(self, user_id: str, passphrase: Optional[str]) -> Dict[str, Any]:
        prof = self._get_profile(user_id, require_rfc=False)
        firma_ref: str = prof['firma_ref']
        files = self._list_firma_files(firma_ref)
        cer_path, key_path = self._get_cer_key_paths(files)
        cer_bytes = self._download_bytes(cer_path)
        key_bytes = self._download_bytes(key_path)
        # Normalizar passphrase: quitar BOM / espacios finales accidentales
        if passphrase is not None:
            passphrase = passphrase.replace('\ufeff','').strip('\r\n')

        priv = None
        last_err = None
        tried = []
        for loader in (load_der_private_key, load_pem_private_key):
            try:
                priv = loader(key_bytes, password=(passphrase.encode('utf-8') if passphrase else None))
                tried.append(loader.__name__ + ':OK')
                break
            except Exception as e:
                tried.append(loader.__name__ + ':' + e.__class__.__name__)
                last_err = e
        if priv is None:
            # Heurísticas de diagnóstico
            key_preview = key_bytes[:32]
            hex_preview = key_preview.hex().upper()
            text_preview = key_bytes[:64].decode('latin-1', errors='ignore')
            hints = []
            if b'BEGIN PKCS12' in key_bytes or b'Bag Attributes' in key_bytes:
                hints.append('Parece un contenedor PKCS#12 (.pfx) renombrado .key; convierte con: openssl pkcs12 -in archivo.pfx -out key.pem -nocerts -nodes')
            if b'BEGIN CERTIFICATE' in key_bytes and b'PRIVATE' not in key_bytes:
                hints.append('El archivo .key contiene un CERTIFICADO, no la llave privada (subiste el .cer dos veces).')
            if passphrase and 'bad decrypt' in str(last_err).lower():
                hints.append('La contraseña es incorrecta o el archivo no coincide con el .cer (FIEL de otro RFC).')
            if passphrase and passphrase.strip() == '' and len(passphrase) == 0:
                hints.append('La contraseña está vacía; asegúrate de que contrasema.txt tenga la pass en la primera línea sin espacios.')
            if not passphrase:
                hints.append('No proporcionaste passphrase; la FIEL normalmente está cifrada, confirma si tu .key realmente no tiene contraseña.')
            if len(key_bytes) < 100:
                hints.append('El archivo .key es demasiado pequeño, parece truncado o incorrecto.')
            raise RuntimeError(
                'Llave privada .key inválida: '\
                + f'{last_err}; intentos={tried}; preview_hex={hex_preview} '\
                + (f"hints={hints}" if hints else '')
            )

        cert = None
        for loader in (x509.load_der_x509_certificate, x509.load_pem_x509_certificate):
            try:
                cert = loader(cer_bytes)
                break
            except Exception:
                pass
        if cert is None:
            raise RuntimeError('No se pudo leer el certificado .cer')

        subj = cert.subject
        issuer = cert.issuer
        subj_cn = next((a.value for a in subj if a.oid == NameOID.COMMON_NAME), None)
        subj_sn = next((a.value for a in subj if a.oid == NameOID.SERIAL_NUMBER), None)
        subj_org = next((a.value for a in subj if a.oid == NameOID.ORGANIZATION_NAME), None)

        # Verificar que la llave privada corresponda al .cer (misma llave pública)
        key_matches_cert = False
        try:
            from cryptography.hazmat.primitives import serialization as _ser
            pub_from_cert = cert.public_key()
            pub_from_key = priv.public_key()
            cert_pub_bytes = pub_from_cert.public_bytes(_ser.Encoding.DER, _ser.PublicFormat.SubjectPublicKeyInfo)
            key_pub_bytes = pub_from_key.public_bytes(_ser.Encoding.DER, _ser.PublicFormat.SubjectPublicKeyInfo)
            key_matches_cert = (cert_pub_bytes == key_pub_bytes)
        except Exception:
            key_matches_cert = False

        # Heurística simple para detectar CSD (no válido para autenticación SAT):
        text_all = f"{str(subj_cn or '')} {str(subj_org or '')}".upper()
        is_probably_csd = ('SELLO' in text_all) or ('CSD' in text_all)

        return {
            'cer_path': cer_path, 'key_path': key_path,
            'subject_common_name': subj_cn, 'subject_serial_number': subj_sn,
            'issuer': ', '.join([f"{a.oid._name}={a.value}" for a in issuer]),
            'valid_from': getattr(cert, 'not_valid_before_utc', cert.not_valid_before).isoformat(),
            'valid_to': getattr(cert, 'not_valid_after_utc', cert.not_valid_after).isoformat(),
            'serial_hex': format(cert.serial_number, 'x').upper(),
            'key_matches_cert': key_matches_cert,
            'is_probably_csd': is_probably_csd,
        }

    def _mock_sat_download(self, kind: SatKind, company_rfc: str) -> List[Dict[str, Any]]:
        now = datetime.utcnow()
        ymdd = now.strftime('%Y-%m-%d')
        items: List[Dict[str, Any]] = []
        n = 2 
        for i in range(n):
            uid = str(uuid.uuid4()).upper()
            subtotal = 100.0 + i * 10
            iva = round(subtotal * 0.16, 2)
            total = round(subtotal + iva, 2)
            if kind == SatKind.emitidos:
                emisor, receptor, tipo = company_rfc, 'XAXX010101000', 'I'
            else:
                emisor, receptor, tipo = 'XAXX010101000', company_rfc, 'E'
            
            xml_content = f"""
<?xml version="1.0" encoding="UTF-8"?>
<cfdi:Comprobante Version="4.0" Fecha="{ymdd}T12:00:00" SubTotal="{subtotal}" Total="{total}" TipoDeComprobante="{tipo}" xmlns:cfdi="http://www.sat.gob.mx/cfd/4">
  <cfdi:Emisor Rfc="{emisor}" Nombre="EMISOR PRUEBA" RegimenFiscal="601"/>
  <cfdi:Receptor Rfc="{receptor}" Nombre="RECEPTOR PRUEBA" UsoCFDI="G03"/>
  <cfdi:Impuestos TotalImpuestosTrasladados="{iva}"><cfdi:Traslados><cfdi:Traslado Base="{subtotal}" Impuesto="002" TipoFactor="Tasa" TasaOCuota="0.160000" Importe="{iva}"/></cfdi:Traslados></cfdi:Impuestos>
  <cfdi:Complemento><tfd:TimbreFiscalDigital xmlns:tfd="http://www.sat.gob.mx/TimbreFiscalDigital" UUID="{uid}" Version="1.1"/></cfdi:Complemento>
</cfdi:Comprobante>
""".strip()

            items.append({
                'uuid': uid, 'fecha': ymdd, 'subtotal': subtotal, 'iva': iva, 'total': total,
                'tipo': tipo, 'emisor_rfc': emisor, 'receptor_rfc': receptor, 'content': xml_content,
            })
        return items
