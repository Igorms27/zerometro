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

# O exe tem que sair exatamente do código que está no GitHub: sem mudança pendente e igual ao origin/main
$ErrorActionPreference = "Continue"
$pendente = git status --porcelain
git fetch -q origin main
$aqui = git rev-parse HEAD
$la = git rev-parse origin/main
$ErrorActionPreference = "Stop"
if ($pendente) { throw "Tem mudança não salva no git. Faça commit (e envie) antes de publicar." }
if ($aqui -ne $la) { throw "A pasta não está igual ao GitHub (origin/main). Envie ou atualize antes de publicar." }

& powershell -ExecutionPolicy Bypass -File build.ps1
if ($LASTEXITCODE) { throw "build falhou" }

$exe = "dist\Zerometro.exe"

# Autoteste: o exe novo precisa abrir e carregar tudo; um exe que nem abre não tem como voltar sozinho
$t = Start-Process -FilePath $exe -ArgumentList "--autoteste" -Wait -PassThru
if ($t.ExitCode -ne 0) { throw "O exe gerado falhou no autoteste (código $($t.ExitCode)). Não publiquei." }
$sha = (Get-FileHash $exe -Algorithm SHA256).Hash.ToLower()
$json = @{ version = $ver; sha256 = $sha } | ConvertTo-Json -Compress
[IO.File]::WriteAllText("$PSScriptRoot\dist\version.json", $json)

# As notas vão por arquivo UTF-8 (sem BOM): passar como argumento perde aspas e acentos.
$arqNotas = "$PSScriptRoot\dist\notas.md"
if ($ArquivoNotas) { $notas = [IO.File]::ReadAllText((Resolve-Path $ArquivoNotas).Path, [Text.Encoding]::UTF8) }
[IO.File]::WriteAllText($arqNotas, $notas, (New-Object Text.UTF8Encoding($false)))

& $gh release create "v$ver" $exe "dist\version.json" --repo $repo --title "Zerômetro $ver" --notes-file $arqNotas --latest --target $aqui
if ($LASTEXITCODE) { throw "publicação falhou" }
Write-Host "Publicado: Zerômetro $ver. Os amigos recebem na próxima vez que abrirem o app."
