<#!
.SYNOPSIS
  Script de prueba integral del flujo SAT (inspect -> verify -> auth -> test-flow -> sync job -> opcional CFDI render/validate)
.DESCRIPTION
  Lee variables desde un archivo .env.local o solicita input interactivo.
  Genera archivos de resultado en scripts/results/ con timestamp.
.NOTES
  Ejecutar con: pwsh -ExecutionPolicy Bypass -File .\scripts\test_sat_flow.ps1
#>

param(
  [string]$EnvFile = "..\\.env.local",
  [switch]$NonInteractive,
  [switch]$SkipJob,
  [switch]$SkipCfdiChecks
)

$ErrorActionPreference = 'Stop'

function Load-Env($path) {
  if (-not (Test-Path $path)) { return @{} }
  $h = @{}
  Get-Content $path | ForEach-Object {
    if ($_ -match '^[#\s]') { return }
    if ($_ -match '^(.*?)=(.*)$') {
      $k=$matches[1].Trim(); $v=$matches[2].Trim(); $h[$k]=$v
    }
  }
  return $h
}

$envData = Load-Env (Resolve-Path $EnvFile -ErrorAction SilentlyContinue)

function Ask($label, $default="") {
  param([string]$label,[string]$default="")
  if ($NonInteractive) { return $default }
  $p = Read-Host (if ($default) {"$label [$default]"} else {$label})
  if (-not $p -and $default) { return $default }
  return $p
}

# Variables requeridas
$Backend = if ($envData.VITE_BACKEND_URL) { $envData.VITE_BACKEND_URL } else { 'http://127.0.0.1:8000' }
$UserId  = Ask 'USER_ID (auth.users.id)' $envData.USER_ID
$CompanyId = Ask 'COMPANY_ID (companies.id)' $envData.COMPANY_ID
$Pass = if ($envData.EFIRMA_PASS) { $envData.EFIRMA_PASS } else { if ($NonInteractive) { '' } else { Read-Host -Prompt 'Contraseña e.firma' -AsSecureString |> ConvertFrom-SecureString } }
if (-not $Pass) { Write-Host 'No password provided. Aborting.'; exit 1 }
if ($Pass -is [string]) { $PlainPass = $Pass } else { $PlainPass = (New-Object System.Net.NetworkCredential('', $Pass)).Password }

$Kind = Ask 'Tipo (recibidos|emitidos)' 'recibidos'
$DaysBack = [int](Ask 'Días atrás para date_from' '5')

$stamp = (Get-Date -Format 'yyyyMMdd_HHmmss')
$resultsDir = Join-Path $PSScriptRoot 'results'
if (-not (Test-Path $resultsDir)) { New-Item -ItemType Directory -Path $resultsDir | Out-Null }
$outFile = Join-Path $resultsDir "sat_flow_$stamp.txt"

function Log($msg) { $line = "[$(Get-Date -Format 'HH:mm:ss')] $msg"; Write-Host $line; Add-Content -Path $outFile -Value $line }

Log "Inicio pruebas SAT -> Output: $outFile"
Log "Backend: $Backend"
Log "UserId: $UserId / CompanyId: $CompanyId / Kind: $Kind"

function PostJson($url, $obj) {
  $json = ($obj | ConvertTo-Json -Depth 10)
  try {
    $resp = Invoke-RestMethod -Method POST -Uri $url -Body $json -ContentType 'application/json'
    return @{ ok=$true; data=$resp }
  } catch {
    $errBody = $_.ErrorDetails.Message
    return @{ ok=$false; error=$errBody }
  }
}

# 1 Health
try { $h = Invoke-RestMethod "$Backend/health"; Log "Health ok: $($h.ok)" } catch { Log "Health error: $_" }

# 2 Inspect
$inspect = PostJson "$Backend/sat/inspect" @{ user_id=$UserId }
if ($inspect.ok) { Log "Inspect RFC=$($inspect.data.rfc) persona_moral=$($inspect.data.persona_moral) vence=$($inspect.data.valid_to)" } else { Log "Inspect ERROR: $($inspect.error)" }

# 3 Verify
$verify = PostJson "$Backend/sat/verify" @{ user_id=$UserId; passphrase=$PlainPass }
if ($verify.ok) { Log "Verify key_matches_cert=$($verify.data.key_matches_cert) csd?=$($verify.data.is_probably_csd)" } else { Log "Verify ERROR: $($verify.error)" }

# 4 Auth
$auth = PostJson "$Backend/sat/auth" @{ user_id=$UserId; passphrase=$PlainPass }
if ($auth.ok) { Log "Auth token_len=$($auth.data.token_len)" } else { Log "Auth ERROR: $($auth.error)" }

# 5 Test-flow corto
$testFlow = PostJson "$Backend/sat/test-flow" @{ user_id=$UserId; passphrase=$PlainPass; kind=$Kind }
if ($testFlow.ok) { Log "TestFlow request_id=$($testFlow.data.request_id) pkgs=$($testFlow.data.packages_count)" } else { Log "TestFlow ERROR: $($testFlow.error)" }

if (-not $SkipJob) {
  # 6 Sync job
  $df = (Get-Date).AddDays(-1 * $DaysBack).ToString('yyyy-MM-dd')
  $dt = (Get-Date).ToString('yyyy-MM-dd')
  $jobStart = PostJson "$Backend/sat/sync" @{ user_id=$UserId; company_id=$CompanyId; kind=$Kind; date_from=$df; date_to=$dt; passphrase=$PlainPass }
  if ($jobStart.ok) { Log "Job queued id=$($jobStart.data.id)" } else { Log "Job start ERROR: $($jobStart.error)" }

  if ($jobStart.ok) {
    $jid = $jobStart.data.id
    for ($i=0; $i -lt 60; $i++) {
      Start-Sleep -Seconds 3
      try {
        $j = Invoke-RestMethod "$Backend/sat/jobs/$jid"
        Log "Job poll status=$($j.status) found=$($j.total_found) downloaded=$($j.total_downloaded) auth_ms=$($j.auth_ms) verify_ms=$($j.verify_ms)" 
        if ($j.status -notin 'queued','running','verifying') { break }
      } catch { Log "Job poll error: $_" }
    }
  }

  if (-not $SkipCfdiChecks) {
    try {
      # Buscar 1 cfdi de la compañía (requiere RLS permitir al owner o usar service role con VITE_SUPABASE_ANON_KEY correcto)
      $cfdis = Invoke-RestMethod "$Backend/diag" | Out-Null
      # Usamos el backend directo (no expone list cfdi). Para un ejemplo mínimo, omitir.
    } catch { Log "CFDI list skip (no endpoint directo)." }
  }
}

Log "Fin pruebas SAT"
Write-Host "Resultado guardado en: $outFile" -ForegroundColor Cyan
