# Zerômetro (app de PC)

Lê os saves dos jogos e mostra quanto falta para zerar a história principal e as DLCs.

## Estrutura

- `app/main.py`: servidor só local (127.0.0.1) + janela do Edge em modo app. Fecha quando a janela fecha.
- `app/readers/`: um arquivo por jogo. Primeiro o save (`witcher3.py`, `botw.py`); se não der,
  as conquistas da Steam (`by_achievements.py`, com o leitor genérico em `steam.py`).
- `app/report.py`: botão "Gerar relatório" (saves + conquistas num .zip na Área de Trabalho).
- `app/web/index.html`: a tela (a mesma do artefato do Zerômetro, com um adaptador para o app).
- `build.ps1`: gera `dist/Zerometro.exe`.

## Adicionar um jogo novo

1. Receba o `Zerometro-relatorio-<jogo>-<data>.zip`.
2. Se o save der para ler: crie `app/readers/<jogo>.py` com `ID`, `NAME`, `PLATFORM`, `LABELS` e
   `latest(cache)`, e coloque em `SAVE_READERS` (`app/readers/__init__.py`).
3. Se não der: adicione o jogo em `app/games.json` (mapa de conquistas, usando `steam/conquistas.json` do relatório). Esse arquivo é baixado pelo app da `main` ao abrir, então um ajuste de partes/horas chega sem exe novo (a validação está em `readers/gamedata.py`). Só dado: formato de save novo ainda exige leitor em Python e release.
4. Aumente `APP_VERSION` em `main.py`, rode `build.ps1` e mande o `.exe` novo.

Dados do usuário: `%APPDATA%\Zerometro` (biblioteca, configurações, log).
