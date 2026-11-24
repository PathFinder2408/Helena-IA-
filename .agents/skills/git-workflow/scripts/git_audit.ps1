param(
  [switch]$Help,
  [string]$RepoPath = "."
)

if ($Help) {
  Write-Output "Uso: git_audit.ps1 [-RepoPath 'ruta']"
  Write-Output "Reporta rama, estado, ultimos commits y escaneo basico de secretos en el diff."
  exit 0
}

if (-not (Test-Path (Join-Path $RepoPath ".git"))) {
  Write-Output "ERROR: $RepoPath no es un repositorio git."
  exit 1
}

$branch = (git -C $RepoPath rev-parse --abbrev-ref HEAD 2>$null)
if (-not $branch) { $branch = "sin-commits" }
$status = git -C $RepoPath status --short 2>$null
$stagedDiff = git -C $RepoPath diff --cached 2>$null
$unstagedDiff = git -C $RepoPath diff 2>$null
$allDiff = ($stagedDiff -join "`n") + "`n" + ($unstagedDiff -join "`n")

Write-Output ("RAMA: " + $branch)
Write-Output ("CAMBIOS (" + ($status | Measure-Object).Count + "):")
$status | Select-Object -First 15 | ForEach-Object { Write-Output ("  " + $_) }

$secretPattern = '(AIza[0-9A-Za-z\-_]{20,}|ghp_[0-9A-Za-z]{20,}|sk-[0-9A-Za-z]{20,}|AKIA[0-9A-Z]{16}|BEGIN (RSA|OPENSSH|EC) PRIVATE KEY)'
if ($allDiff -match $secretPattern) {
  Write-Output "ALERTA_SECRETOS: POSIBLE CLAVE/TOKEN DETECTADO EN EL DIFF. NO HACER COMMIT."
} else {
  Write-Output "ALERTA_SECRETOS: Ninguno detectado en diff."
}

$commits = git -C $RepoPath log -n 5 --oneline 2>$null
if ($commits) {
  Write-Output "ULTIMOS_COMMITS:"
  $commits | ForEach-Object { Write-Output ("  " + $_) }
}
