POC SAT desde cero
===================

Objetivo: validar e.firma (.cer/.key + contraseña) y ejecutar autenticación y solicitud directa al SAT sin depender de Supabase ni de la infraestructura previa.

Pasos rápidos:
1. Coloca tus archivos:
   - poc/fiel.cer
   - poc/fiel.key
   - poc/pass.txt (primera línea contraseña)
2. Ejecuta validación básica:
   py poc\validate_fiel.py
3. Autenticar SAT 2.0:
   py poc\auth_sat.py --days 2 --kind recibidos

Dependencias necesarias (instalar en entorno limpio si deseas):
  pip install cryptography zeep lxml httpx

Notas:
- Estos scripts no guardan nada, sólo imprimen resultados.
- Si la llave es PKCS#12 (.pfx) conviértela antes (ver instrucciones en validate_fiel.py).
