# Gera dist\Zerometro.exe (um arquivo só, sem janela de console).
# Uso: clique com o botão direito > Executar com o PowerShell, ou: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
# venv local (.venv, ignorado pelo git) com as versões fixadas em requirements.txt: o build sai igual em qualquer dia
$venv = "$PSScriptRoot\.venv"
if (-not (Test-Path "$venv\Scripts\python.exe")) {
    & python -m venv $venv
    if ($LASTEXITCODE) { throw "não consegui criar o venv" }
}
$py = "$venv\Scripts\python.exe"
& $py -m pip install --quiet --disable-pip-version-check -r "$PSScriptRoot\requirements.txt"
if ($LASTEXITCODE) { throw "pip install falhou" }
# se o app estiver aberto, o exe não pode ser apagado, mas pode ser renomeado
$exe = "$PSScriptRoot\dist\Zerometro.exe"
Remove-Item "$exe.old" -ErrorAction SilentlyContinue
if (Test-Path $exe) { try { Remove-Item $exe -ErrorAction Stop } catch { Rename-Item $exe "Zerometro.exe.old" } }
& $py -m PyInstaller --noconfirm --clean --onefile --noconsole --name Zerometro `
    --icon "$PSScriptRoot\app\icon\app.ico" `
    --distpath dist --workpath build --specpath build `
    --add-data "$PSScriptRoot\app\web;web" `
    --add-data "$PSScriptRoot\app\games.json;." `
    app\main.py
if ($LASTEXITCODE) { throw "PyInstaller falhou" }
Write-Host "Pronto: $PSScriptRoot\dist\Zerometro.exe"
