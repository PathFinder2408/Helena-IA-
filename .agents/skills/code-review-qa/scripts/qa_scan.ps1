param(
  [switch]$Help,
  [string]$RepoPath = "."
)

if ($Help) {
  Write-Output "Uso: qa_scan.ps1 [-RepoPath 'ruta']"
  Write-Output "Detecta linters/test runners del proyecto y cuenta marcas TODO/FIXME."
  exit 0
}

if (-not (Test-Path $RepoPath)) { Write-Output "ERROR: ruta no existe ($RepoPath)"; exit 1 }
$p = (Resolve-Path $RepoPath).Path

$tools = @()
foreach ($t in @('ruff','flake8','pytest','mypy','eslint','tsc','npm','pnpm','docker')) {
  if (Get-Command $t -ErrorAction SilentlyContinue) { $tools += $t }
}
Write-Output ("REPO: " + $p)
Write-Output ("HERRAMIENTAS_DISPONIBLES: " + ($(if ($tools.Count) { $tools -join ', ' } else { 'ninguna en PATH' })))

$exclude = '\\(\.git|node_modules|\.venv|venv|dist|build|__pycache__)\\'
$codeFiles = Get-ChildItem -Path $p -Recurse -File -Include *.py,*.js,*.ts,*.tsx,*.jsx,*.ps1,*.sql -ErrorAction SilentlyContinue |
  Where-Object { $_.FullName -notmatch $exclude }

$todos = $codeFiles | Select-String -Pattern '\b(TODO|FIXME|HACK|XXX)\b' -ErrorAction SilentlyContinue
Write-Output ("ARCHIVOS_CODIGO: " + ($codeFiles | Measure-Object).Count + " | TODO/FIXME: " + ($todos | Measure-Object).Count)
$todos | Select-Object -First 8 | ForEach-Object {
  Write-Output ("  " + $_.Filename + ":" + $_.LineNumber + " " + $_.Line.Trim())
}
