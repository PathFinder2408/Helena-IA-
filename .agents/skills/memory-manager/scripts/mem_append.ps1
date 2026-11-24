param(
  [switch]$Help,
  [ValidateSet("inbox", "context")]
  [string]$Target = "inbox",
  [string]$Text = ""
)

if ($Help) {
  Write-Output "Uso: mem_append.ps1 -Target inbox|context -Text 'nota a guardar'"
  Write-Output "Agrega una entrada con fecha sin duplicar ni borrar contenido previo."
  exit 0
}

if ([string]::IsNullOrWhiteSpace($Text)) { Write-Output "ERROR: -Text requerido"; exit 1 }
$file = if ($Target -eq "context") { "C:\Jarvis\memory\context.md" } else { "C:\Jarvis\memory\inbox.md" }
if (-not (Test-Path $file)) { Write-Output "ERROR: archivo no existe ($file)"; exit 1 }

$existing = Get-Content $file -Raw -ErrorAction SilentlyContinue
if ($existing -and $existing.Contains($Text.Trim())) {
  Write-Output "SKIP: entrada ya existe en $Target"
  exit 0
}

$date = Get-Date -Format "yyyy-MM-dd"
Add-Content -Path $file -Value ("- **" + $date + ":** " + $Text.Trim()) -Encoding UTF8
Write-Output ("OK: agregado a " + $file)
