param(
  [switch]$Help,
  [string]$City = "",
  [string]$TodoPath = ""
)

if ($Help) {
  Write-Output "Uso: briefing.ps1 [-City 'Santiago,CL'] [-TodoPath 'memory\TODO.md']"
  Write-Output "Muestra hora local, clima (wttr.in), pendientes y estado git de repos."
  exit 0
}

$Root = (Resolve-Path (Join-Path $PSScriptRoot "..\..\..\..")).Path
$EnvFile = Join-Path $Root ".env"
if (Test-Path $EnvFile) {
  Get-Content $EnvFile | ForEach-Object {
    if ($_ -match '^\s*([A-Za-z0-9_]+)\s*=\s*(.*)$' -and -not $_.Trim().StartsWith('#')) {
      $k = $Matches[1]; $v = $Matches[2].Trim()
      if ($k -eq "CITY" -and [string]::IsNullOrWhiteSpace($City) -and $v) { $City = $v }
      if ($k -eq "HELENA_PROJECTS_DIR" -and $v) { $script:ProjDir = $v }
    }
  }
}

if ([string]::IsNullOrWhiteSpace($City)) { $City = "Santiago,CL" }
if ([string]::IsNullOrWhiteSpace($TodoPath)) { $TodoPath = Join-Path $Root "memory\TODO.md" }

Write-Output ("HORA: " + (Get-Date -Format "yyyy-MM-dd HH:mm (ddd)"))

try {
  $w = Invoke-RestMethod -Uri ("https://wttr.in/" + [uri]::EscapeDataString($City) + "?format=%l:+%C+%t+(%w)") -TimeoutSec 4 -ErrorAction Stop
  Write-Output ("CLIMA: " + $w.Trim())
} catch {
  Write-Output "CLIMA: sin conexión (offline)"
}

if (Test-Path $TodoPath) {
  $todos = Select-String -Path $TodoPath -Pattern '^\s*-\s*\[\s*\]' | Select-Object -First 5
  Write-Output ("PENDIENTES (" + $todos.Count + "):")
  foreach ($t in $todos) { Write-Output ("  " + $t.Line.Trim()) }
}

$repos = @($Root)
if ($script:ProjDir -and (Test-Path $script:ProjDir)) {
  Get-ChildItem $script:ProjDir -Directory -ErrorAction SilentlyContinue | Select-Object -First 5 | ForEach-Object { $repos += $_.FullName }
}
foreach ($r in $repos) {
  if (Test-Path (Join-Path $r ".git")) {
    $branch = (git -C $r rev-parse --abbrev-ref HEAD 2>$null)
    if (-not $branch) { $branch = "sin-commits" }
    $dirty = (git -C $r status --porcelain 2>$null | Measure-Object).Count
    Write-Output ("GIT [" + (Split-Path $r -Leaf) + "]: rama=" + $branch + " cambios=" + $dirty)
  }
}
