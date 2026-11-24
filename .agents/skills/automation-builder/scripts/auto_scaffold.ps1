param(
  [switch]$Help,
  [string]$Name = "",
  [ValidateSet("ps1", "py", "gh-action")]
  [string]$Kind = "py",
  [string]$OutDir = "C:\Jarvis\scripts\automations"
)

if ($Help) {
  Write-Output "Uso: auto_scaffold.ps1 -Name 'mi_tarea' -Kind ps1|py|gh-action [-OutDir 'C:\Jarvis\scripts\automations']"
  Write-Output "Crea una plantilla de automatizacion idempotente con --dry-run y logging."
  exit 0
}

if ([string]::IsNullOrWhiteSpace($Name)) { Write-Output "ERROR: -Name requerido"; exit 1 }
$safe = ($Name -replace '[^a-zA-Z0-9_\-]', '_').ToLower()
if (-not (Test-Path $OutDir)) { New-Item -ItemType Directory -Path $OutDir -Force | Out-Null }

if ($Kind -eq "ps1") {
  $target = Join-Path $OutDir "$safe.ps1"
  $body = @"
param([switch]`$Help, [switch]`$DryRun)
if (`$Help) { Write-Output "Uso: $safe.ps1 [-DryRun]"; exit 0 }
`$Log = "C:\Jarvis\logs\$safe.log"
function Log([string]`$m) { Add-Content `$Log "[[`$(Get-Date -Format 'yyyy-MM-dd HH:mm:ss')]] `$m" -Encoding UTF8 }
Log "START (DryRun=`$DryRun)"
if (`$DryRun) { Write-Output "DRYRUN OK: $safe"; exit 0 }
# TODO: logica idempotente aqui
Log "DONE"
"@
} elseif ($Kind -eq "py") {
  $target = Join-Path $OutDir "$safe.py"
  $body = @"
#!/usr/bin/env python3
import argparse, logging
from pathlib import Path

LOG = Path(r"C:\Jarvis\logs\$safe.log")
logging.basicConfig(filename=LOG, level=logging.INFO, format="[%(asctime)s] %(levelname)s %(message)s")

def main() -> int:
    p = argparse.ArgumentParser(description="Automatizacion $safe")
    p.add_argument("--dry-run", action="store_true", help="Simula sin aplicar cambios")
    args = p.parse_args()
    logging.info("START dry_run=%s", args.dry_run)
    if args.dry_run:
        print("DRYRUN OK: $safe")
        return 0
    # TODO: logica idempotente aqui
    logging.info("DONE")
    return 0

if __name__ == "__main__":
    raise SystemExit(main())
"@
} else {
  $target = Join-Path $OutDir "$safe.yml"
  $body = @"
name: $safe
on:
  workflow_dispatch:
  push:
    branches: [ main ]
jobs:
  ci:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - name: Run checks
        run: echo "Configurar lint/tests aqui"
"@
}

if (Test-Path $target) {
  Write-Output "SKIP: ya existe $target (no sobrescrito)."
  exit 0
}
Set-Content -Path $target -Value $body -Encoding UTF8
Write-Output ("OK: creado " + $target)
