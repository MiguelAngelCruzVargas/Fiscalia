@echo off
SETLOCAL ENABLEDELAYEDEXPANSION

REM =============================================================
REM  Fiscal-IA Starter (Simplificado)
REM =============================================================
REM  Uso:
REM    start.bat             -> backend + frontend
REM    start.bat no-backend  -> sólo frontend
REM    start.bat no-frontend -> sólo backend
REM =============================================================

SET RUN_BACKEND=1
SET RUN_FRONTEND=1
FOR %%A IN (%*) DO (
  IF /I "%%~A"=="no-backend" SET RUN_BACKEND=0
  IF /I "%%~A"=="no-frontend" SET RUN_FRONTEND=0
)

SET SCRIPT_DIR=%~dp0
PUSHD "%SCRIPT_DIR%.." >NUL
SET WORKSPACE_DIR=%CD%
POPD >NUL

SET BACKEND_DIR=%WORKSPACE_DIR%\backend
SET WEB_DIR=%WORKSPACE_DIR%\web
SET VENV_DIR=%BACKEND_DIR%\.venv
SET VENV_PY=%VENV_DIR%\Scripts\python.exe
SET PY_CMD=py

ECHO ==================================================
ECHO   Fiscal-IA Start
ECHO   Workspace : %WORKSPACE_DIR%
ECHO   Fecha/Hora: %DATE% %TIME%
ECHO   Backend   : %RUN_BACKEND%  Frontend: %RUN_FRONTEND%
ECHO ==================================================

where %PY_CMD% >NUL 2>&1 || (ECHO [ERROR] No se encontró 'py' en PATH.& EXIT /B 1)
where npm >NUL 2>&1 || (
  IF "%RUN_FRONTEND%"=="1" (
    ECHO [WARN] npm no disponible. Se desactiva frontend.
    SET RUN_FRONTEND=0
  )
)

IF "%RUN_BACKEND%"=="1" (
  ECHO.
  ECHO [BACKEND] Preparando entorno...
  IF NOT EXIST "%VENV_PY%" (
    ECHO [BACKEND] Creando venv...
    %PY_CMD% -m venv "%VENV_DIR%" || (ECHO [ERROR] Falló creación de venv & EXIT /B 2)
  ) ELSE (
    ECHO [BACKEND] venv existente.
  )
  "%VENV_PY%" -c "import fastapi" >NUL 2>&1
  IF ERRORLEVEL 1 (
    ECHO [BACKEND] Instalando dependencias...
    "%VENV_PY%" -m pip install --upgrade pip >NUL
    "%VENV_PY%" -m pip install -r "%BACKEND_DIR%\requirements.txt" || ECHO [WARN] Problema instalando requirements.
  ) ELSE (
    ECHO [BACKEND] Dependencias ok.
  )
  ECHO [BACKEND] Lanzando Uvicorn (8000)...
  START "Fiscal-IA Backend" cmd /K "CD /D %BACKEND_DIR% && "%VENV_PY%" -m uvicorn app.main:app --host 127.0.0.1 --port 8000 --reload"
) ELSE (
  ECHO [BACKEND] Omitido (no-backend).
)

IF "%RUN_FRONTEND%"=="1" (
  ECHO.
  ECHO [FRONTEND] Preparando entorno...
  IF NOT EXIST "%WEB_DIR%\package.json" (
    ECHO [ERROR] Falta web\package.json. No se inicia frontend.
  ) ELSE (
    IF NOT EXIST "%WEB_DIR%\node_modules" (
      ECHO [FRONTEND] Instalando dependencias (npm ci)...
      PUSHD "%WEB_DIR%" >NUL
      CALL npm ci || ECHO [WARN] npm ci terminó con errores.
      POPD >NUL
    ) ELSE (
      ECHO [FRONTEND] node_modules ok.
    )
    ECHO [FRONTEND] Lanzando Vite (5174)...
    START "Fiscal-IA Frontend" cmd /K "CD /D %WEB_DIR% && npm run dev -- --port 5174 --strictPort"
  )
) ELSE (
  ECHO [FRONTEND] Omitido (no-frontend).
)

ECHO.
ECHO [INFO] Servicios lanzados (si no hubo errores). Ventanas separadas activas.
ECHO.
EXIT /B 0
