# Publica uma versão nova no GitHub. Os apps dos amigos baixam sozinhos na próxima vez que abrirem.
# Antes: suba APP_VERSION em app\main.py (ex.: 0.3.0 -> 0.3.1).
# Uso: powershell -ExecutionPolicy Bypass -File publicar.ps1 "o que mudou"
#  ou: powershell -ExecutionPolicy Bypass -File publicar.ps1 -ArquivoNotas notas.md   (texto em UTF-8, aspas e acentos preservados)
# Este arquivo deve ficar salvo em UTF-8 com BOM, senão o PowerShell 5 lê os acentos errado.
param([string]$notas = "Versão nova do Zerômetro", [string]$ArquivoNotas = "")
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$gh = (Get-Command gh -ErrorAction SilentlyContinue).Source
if (-not $gh) { $gh = "$env:ProgramFiles\GitHub CLI\gh.exe" }

$main = Get-Content app\main.py -Raw -Encoding UTF8
$ver  = [regex]::Match($main, 'APP_VERSION = "([^"]+)"').Groups[1].Value
$repo = [regex]::Match($main, 'UPDATE_REPO = "([^"]+)"').Groups[1].Value
if (-not $ver -or -not $repo) { throw "APP_VERSION ou UPDATE_REPO vazio em app\main.py" }

$ErrorActionPreference = "Continue"  # "release not found" vem no stderr e é o esperado
& $gh release view "v$ver" --repo $repo *> $null
$existe = ($LASTEXITCODE -eq 0)
$ErrorActionPreference = "Stop"
if ($existe) { throw "A versão $ver já foi publicada. Suba APP_VERSION em app\main.py." }

& powershell -ExecutionPolicy Bypass -File build.ps1
if ($LASTEXITCODE) { throw "build falhou" }

$exe = "dist\Zerometro.exe"
$sha = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
$json = @{ version = $ver; sha256 = $sha } | ConvertTo-Json -Compress
[IO.File]::WriteAllText("$PSScriptRoot\dist\version.json", $json)

# As notas vão por arquivo UTF-8 (sem BOM): passar como argumento perde aspas e acentos.
$arqNotas = "$PSScriptRoot\dist\notas.md"
if ($ArquivoNotas) { $notas = [IO.File]::ReadAllText((Resolve-Path $ArquivoNotas).Path, [Text.Encoding]::UTF8) }
[IO.File]::WriteAllText($arqNotas, $notas, (New-Object Text.UTF8Encoding($false)))

& $gh release create "v$ver" $exe "dist\version.json" --repo $repo --title "Zerômetro $ver" --notes-file $arqNotas --latest
if ($LASTEXITCODE) { throw "publicação falhou" }
Write-Host "Publicado: Zerômetro $ver. Os amigos recebem na próxima vez que abrirem o app."
