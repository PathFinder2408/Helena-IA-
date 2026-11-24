param(
  [switch]$Help,
  [int]$Top = 5
)

if ($Help) {
  Write-Output "Uso: pc_status.ps1 [-Top 5]"
  Write-Output "Reporta CPU, RAM, discos y los procesos con mayor consumo de memoria."
  exit 0
}

$cpu = (Get-Counter '\Processor(_Total)\% Processor Time' -ErrorAction SilentlyContinue).CounterSamples.CookedValue
if ($null -ne $cpu) { Write-Output ("CPU: " + [math]::Round($cpu, 1) + "%") }

$os = Get-CimInstance Win32_OperatingSystem -ErrorAction SilentlyContinue
if ($os) {
  $tot = [math]::Round($os.TotalVisibleMemorySize / 1MB, 1)
  $free = [math]::Round($os.FreePhysicalMemory / 1MB, 1)
  Write-Output ("RAM: " + ($tot - $free) + " / " + $tot + " GB usados")
}

Get-PSDrive -PSProvider FileSystem | Where-Object { $_.Used -gt 0 } | ForEach-Object {
  $freeGB = [math]::Round($_.Free / 1GB, 1)
  $totGB = [math]::Round(($_.Used + $_.Free) / 1GB, 1)
  Write-Output ("DISCO " + $_.Name + ": " + $freeGB + " GB libres de " + $totGB + " GB")
}

Write-Output ("TOP " + $Top + " PROCESOS (RAM):")
Get-Process | Sort-Object WorkingSet64 -Descending | Select-Object -First $Top | ForEach-Object {
  Write-Output ("  " + $_.ProcessName + " (" + [math]::Round($_.WorkingSet64 / 1MB, 0) + " MB)")
}
