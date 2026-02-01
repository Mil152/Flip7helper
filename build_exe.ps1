param(
  [string]$VenvPath = ".\.venv"
)

$ErrorActionPreference = "Stop"

if (!(Test-Path $VenvPath)) {
  Write-Host "Virtualenv not found at $VenvPath"
  Write-Host "Create it first:"
  Write-Host "  python -m venv .venv"
  exit 1
}

& "$VenvPath\Scripts\Activate.ps1"

python -m pip install --upgrade pip
python -m pip install pyinstaller

# Build a single-file, windowed executable (no console).
# Use a small launcher script so imports work in an EXE context.
pyinstaller --noconfirm --clean --onefile --windowed --name "Flip7Helper" "run_flip7helper.py"

Write-Host ""
Write-Host "Built:"
Write-Host "  .\dist\Flip7Helper.exe"
