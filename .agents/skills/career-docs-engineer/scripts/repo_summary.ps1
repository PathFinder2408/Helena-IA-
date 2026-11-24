param(
  [switch]$Help,
  [string]$RepoPath = "."
)

if ($Help) {
  Write-Output "Uso: repo_summary.ps1 [-RepoPath 'ruta']"
  Write-Output "Resume extensiones, estructura principal y actividad git para documentacion/portafolio."
  exit 0
}

if (-not (Test-Path $RepoPath)) { Write-Output "ERROR: ruta no existe ($RepoPath)"; exit 1 }
$p = (Resolve-Path $RepoPath).Path
$exclude = '\\(\.git|node_modules|\.venv|venv|dist|build|__pycache__)\\'

Write-Output ("PROYECTO: " + (Split-Path $p -Leaf) + " (" + $p + ")")
$top = Get-ChildItem -Path $p -Depth 0 -ErrorAction SilentlyContinue | Select-Object -ExpandProperty Name
Write-Output ("RAIZ: " + ($top -join ', '))

$exts = Get-ChildItem -Path $p -Recurse -File -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch $exclude -and $_.Extension } |
  Group-Object Extension | Sort-Object Count -Descending | Select-Object -First 8 |
  ForEach-Object { "$($_.Name):$($_.Count)" }
Write-Output ("EXTENSIONES: " + ($exts -join ', '))

if (Test-Path (Join-Path $p ".git")) {
  $cnt = (git -C $p rev-list --count HEAD 2>$null)
  if ($cnt) {
    Write-Output ("COMMITS_TOTAL: " + $cnt)
    git -C $p log -n 5 --oneline 2>$null | ForEach-Object { Write-Output ("  " + $_) }
  } else {
    Write-Output "COMMITS_TOTAL: 0"
  }
}
exit 0
