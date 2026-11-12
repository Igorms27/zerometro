# Gera dist\Zerometro.exe (um arquivo só, sem janela de console).
# Uso: clique com o botão direito > Executar com o PowerShell, ou: powershell -ExecutionPolicy Bypass -File build.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot
$py = "python"
& $py -m pip install --user --quiet pyinstaller
# se o app estiver aberto, o exe não pode ser apagado, mas pode ser renomeado
$exe = "$PSScriptRoot\dist\Zerometro.exe"
Remove-Item "$exe.old" -ErrorAction SilentlyContinue
if (Test-Path $exe) { try { Remove-Item $exe -ErrorAction Stop } catch { Rename-Item $exe "Zerometro.exe.old" } }
& $py -m PyInstaller --noconfirm --clean --onefile --noconsole --name Zerometro `
    --icon "$PSScriptRoot\app\icon\app.ico" `
    --distpath dist --workpath build --specpath build `
    --add-data "$PSScriptRoot\app\web;web" `
    app\main.py
if ($LASTEXITCODE) { throw "PyInstaller falhou" }
Write-Host "Pronto: $PSScriptRoot\dist\Zerometro.exe"
