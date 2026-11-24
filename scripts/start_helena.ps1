param(
  [switch]$Help,
  [switch]$DryRun,
  [switch]$NoIDE
)

if ($Help) {
  Write-Output "Uso: start_helena.ps1 [-DryRun] [-NoIDE]"
  Write-Output "Inicia Helena en segundo plano (Ollama RTX + voz + avatar OOOOO inteligente). Respeta HELENA_OFF."
  exit 0
}

$Root = "C:\Jarvis"
$LogDir = Join-Path $Root "logs"
$LogFile = Join-Path $LogDir "startup.log"
$OffFlag = Join-Path $Root "HELENA_OFF"
$OllamaExe = Join-Path $env:LOCALAPPDATA "Programs\Ollama\ollama.exe"
$AgExe = Join-Path $env:LOCALAPPDATA "Programs\Antigravity\Antigravity.exe"
$VenvPyw = Join-Path $Root ".venv\Scripts\pythonw.exe"
$VoiceScript = Join-Path $Root "scripts\voice_bridge.py"

if (-not (Test-Path $LogDir)) { New-Item -ItemType Directory -Path $LogDir -Force | Out-Null }

function Write-Log([string]$Msg) {
  $ts = Get-Date -Format "yyyy-MM-dd HH:mm:ss"
  Add-Content -Path $LogFile -Value "[$ts] $Msg" -Encoding UTF8
}

if (Test-Path $OffFlag) {
  Write-Log "ABORT: HELENA_OFF presente. No se inicia ningún servicio."
  if ($DryRun) { Write-Output "DRYRUN: HELENA_OFF activo" }
  exit 0
}

Write-Log "START: iniciando Helena en segundo plano..."

# (1) Cerebro local Ollama (servidor puro sin ventana)
if (Test-Path $OllamaExe) {
  $olRunning = Get-Process -Name "ollama" -ErrorAction SilentlyContinue
  if ($olRunning) {
    Write-Log "SKIP: Ollama ya está en ejecución."
  } elseif ($DryRun) {
    Write-Log "DRYRUN: lanzaría Ollama serve oculto."
  } else {
    Start-Process -FilePath $OllamaExe -ArgumentList "serve" -WindowStyle Hidden
    Start-Sleep -Seconds 2
    Write-Log "OK: Ollama serve iniciado (RTX 4060)."
  }
}

# (2) Antigravity (opcional, omitible con -NoIDE)
if ((-not $NoIDE) -and (Test-Path $AgExe)) {
  $agRunning = Get-Process -Name "Antigravity" -ErrorAction SilentlyContinue
  if ($agRunning) {
    Write-Log "SKIP: Antigravity ya está en ejecución."
  } elseif ($DryRun) {
    Write-Log "DRYRUN: lanzaría Antigravity en $Root."
  } else {
    Start-Process -FilePath $AgExe -ArgumentList "`"$Root`"" -WorkingDirectory $Root
    Write-Log "OK: Antigravity lanzado en $Root."
  }
}

# (3) Puente de voz + Avatar OOOOO inteligente en segundo plano (pythonw.exe = sin ventana de consola)
if ((Test-Path $VenvPyw) -and (Test-Path $VoiceScript)) {
  $voiceRunning = Get-CimInstance Win32_Process -Filter "Name='pythonw.exe' OR Name='python.exe'" -ErrorAction SilentlyContinue |
    Where-Object { $_.CommandLine -like "*voice_bridge.py*" }
  if ($voiceRunning) {
    Write-Log "SKIP: Helena (voice_bridge.py) ya está en ejecución."
  } elseif ($DryRun) {
    Write-Log "DRYRUN: lanzaría $VenvPyw $VoiceScript en segundo plano."
  } else {
    Start-Process -FilePath $VenvPyw -ArgumentList "`"$VoiceScript`"" -WorkingDirectory $Root
    Write-Log "OK: Helena iniciada en segundo plano (escuchando 'Oye Helena' / 'Hola Helena')."
  }
} else {
  Write-Log "WARN: faltan pythonw.exe o voice_bridge.py."
}

if ($DryRun) { Write-Output "DRYRUN_OK: ver $LogFile" }
