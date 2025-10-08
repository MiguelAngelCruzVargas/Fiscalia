# Este archivo es el "worker" o la "cocina".
# Es un proceso que se ejecuta de forma continua en tu servidor,
# buscando y procesando trabajos pendientes.

import time
import os
from app.supabase_client import get_supabase
from app.services.sat_provider import SatProvider, SatKind

def main():
    """
    Ciclo principal del worker. Busca trabajos en estado 'queued'
    y los procesa uno por uno.
    """
    print("Iniciando worker de Fiscal-IA...")
    sb = get_supabase()
    provider = SatProvider()

    while True:
        try:
            # 1. Buscar un trabajo pendiente en la base de datos
            response = sb.table('sat_jobs').select('*').eq('status', 'queued').limit(1).maybe_single().execute()
            
            job = response.data
            if not job:
                # No hay trabajos pendientes, esperamos un poco
                print("No hay trabajos pendientes. Esperando...")
                time.sleep(10) # Espera 10 segundos antes de volver a consultar
                continue

            print(f"Procesando job ID: {job['id']}")
            
            # Extraer la contraseña de la e.firma (debe pasarse de forma segura,
            # aquí asumimos que se pasa como variable de entorno para el worker)
            # En un sistema real, podrías usar un servicio como Vault o KMS.
            passphrase = os.environ.get("DEFAULT_EFIRMA_PASSPHRAS_E")

            # 2. Procesar el job encontrado
            # Esta es la llamada larga y pesada que se conecta al SAT
            provider.process_job(
                job_id=job['id'],
                user_id=job['user_id'],
                company_id=job['company_id'],
                kind=SatKind(job['kind']),
                date_from=job['date_from'],
                date_to=job['date_to'],
                passphrase=passphrase, # ¡Importante!
            )

            print(f"Job ID: {job['id']} completado.")

        except Exception as e:
            print(f"Error en el ciclo del worker: {e}")
            # Si hay un error grave (ej. DB desconectada), esperamos más tiempo
            time.sleep(30)

if __name__ == "__main__":
    main()

