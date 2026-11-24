param(
  [switch]$Help,
  [string]$RepoPath = "."
)

if ($Help) {
  Write-Output "Uso: dev_check.ps1 [-RepoPath 'ruta']"
  Write-Output "Detecta tipo de proyecto (Python/Node/Docker), venv y estado git."
  exit 0
}

if (-not (Test-Path $RepoPath)) { Write-Output "ERROR: ruta no existe ($RepoPath)"; exit 1 }
$p = (Resolve-Path $RepoPath).Path
$stack = @()
if (Test-Path (Join-Path $p "package.json")) { $stack += "Node" }
if ((Test-Path (Join-Path $p "requirements.txt")) -or (Test-Path (Join-Path $p "pyproject.toml"))) { $stack += "Python" }
if (Test-Path (Join-Path $p "manage.py")) { $stack += "Django" }
if (Test-Path (Join-Path $p "Dockerfile")) { $stack += "Docker" }
$venv = (Test-Path (Join-Path $p ".venv")) -or (Test-Path (Join-Path $p "venv"))
Write-Output ("REPO: " + $p)
Write-Output ("STACK: " + ($(if ($stack.Count) { $stack -join ', ' } else { 'Genérico' })) + " | VENV: " + $venv)
if (Test-Path (Join-Path $p ".git")) {
  $st = (git -C $p status --short 2>$null | Measure-Object).Count
  Write-Output ("GIT_DIRTY: " + $st)
}
