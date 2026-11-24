param(
  [switch]$Help,
  [string]$Url = "",
  [switch]$Ports
)

if ($Help) {
  Write-Output "Uso: api_probe.ps1 [-Url 'http://localhost:8000/health'] [-Ports]"
  Write-Output "Prueba un endpoint GET (status + latencia + preview) y/o lista puertos locales en escucha."
  exit 0
}

if ($Ports -or [string]::IsNullOrWhiteSpace($Url)) {
  $devPorts = @(3000,3001,4200,5000,5173,5432,6379,8000,8080,8888,27017)
  $listeners = Get-NetTCPConnection -State Listen -ErrorAction SilentlyContinue |
    Where-Object { $devPorts -contains $_.LocalPort } |
    Select-Object -Unique LocalPort, OwningProcess
  if ($listeners) {
    Write-Output "PUERTOS_DEV_ACTIVOS:"
    foreach ($l in $listeners) {
      $pname = (Get-Process -Id $l.OwningProcess -ErrorAction SilentlyContinue).ProcessName
      Write-Output ("  :" + $l.LocalPort + " -> " + $pname + " (PID " + $l.OwningProcess + ")")
    }
  } else {
    Write-Output "PUERTOS_DEV_ACTIVOS: ninguno en puertos comunes (3000,5173,5432,6379,8000,8080...)"
  }
}

if (-not [string]::IsNullOrWhiteSpace($Url)) {
  $sw = [System.Diagnostics.Stopwatch]::StartNew()
  try {
    $resp = Invoke-WebRequest -Uri $Url -Method Get -TimeoutSec 8 -UseBasicParsing -ErrorAction Stop
    $sw.Stop()
    $preview = ($resp.Content -replace '\s+', ' ')
    if ($preview.Length -gt 220) { $preview = $preview.Substring(0, 220) + "..." }
    Write-Output ("HTTP: " + $resp.StatusCode + " | LATENCIA: " + $sw.ElapsedMilliseconds + " ms")
    Write-Output ("BODY: " + $preview)
  } catch {
    $sw.Stop()
    Write-Output ("HTTP_ERROR (" + $sw.ElapsedMilliseconds + " ms): " + $_.Exception.Message)
    exit 1
  }
}
