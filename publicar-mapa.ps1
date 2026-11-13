# Publica o mapa de jogos por conquistas (app\games.json) para os apps dos amigos, sem exe novo.
# Os apps baixam o arquivo da etiqueta "mapa" no GitHub; este script só move a etiqueta depois de validar.
# Antes: aumente "rev" em app\games.json, faça commit e envie para o main.
# Uso: powershell -ExecutionPolicy Bypass -File publicar-mapa.ps1
$ErrorActionPreference = "Stop"
Set-Location $PSScriptRoot

$ErrorActionPreference = "Continue"
$pendente = git status --porcelain
git fetch -q origin main
$aqui = git rev-parse HEAD
$la = git rev-parse origin/main
$ErrorActionPreference = "Stop"
if ($pendente) { throw "Tem mudança não salva no git. Faça commit antes." }
if ($aqui -ne $la) { throw "A pasta não está igual ao GitHub (origin/main). Envie ou atualize antes." }

# mesma validação que o app usa: se algum jogo for descartado, não publica
$py = if (Test-Path ".venv\Scripts\python.exe") { ".venv\Scripts\python.exe" } else { "python" }
& $py -c "import json,sys; sys.path.insert(0,'app'); from readers import gamedata as g; d=json.load(open('app/games.json',encoding='utf-8-sig')); ok=g.validate(d); n=len(d.get('games',{})); print('%d de %d jogos validos, rev %s' % (len(ok), n, d.get('rev'))); sys.exit(0 if ok and len(ok)==n else 1)"
if ($LASTEXITCODE) { throw "games.json tem jogo inválido. Não publiquei." }

git tag -f mapa $aqui
git push -f origin mapa
if ($LASTEXITCODE) { throw "não consegui enviar a etiqueta mapa" }
Write-Host "Mapa publicado. Os apps pegam na próxima vez que abrirem."
