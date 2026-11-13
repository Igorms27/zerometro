# Zerômetro

Quanto falta para zerar o seu jogo? O Zerômetro lê os saves do seu PC e mostra a porcentagem da história que você já fez, com cada DLC separada.

## Baixar

**[Baixar Zerometro.exe](https://github.com/Igorms27/zerometro/releases/latest/download/Zerometro.exe)**

Não precisa instalar: é só abrir o arquivo.
Se o Windows mostrar "O Windows protegeu o computador", clique em **Mais informações** e depois em **Executar assim mesmo**. O aviso aparece porque o app não tem certificado pago.

## Jogos que ele lê

| Jogo | Lê |
|---|---|
| The Witcher 3 | História, Hearts of Stone e Blood and Wine |
| Zelda: Breath of the Wild (Savage Wind Recomp) | História e A Balada dos Campeões |
| Horizon Forbidden West | História e Burning Shores |
| The Talos Principle 2 | História, área por área |
| RV There Yet? | Mabutts Valley, Mt. Yurbuttsk e St. Büttin Bay |

Se o app não conseguir ler o save de um jogo da Steam que ele conhece, ele calcula pelas suas conquistas.

## Seu jogo não aparece?

Clique em **Gerar relatório** no fim da janela e escolha o jogo. Vai aparecer um arquivo `.zip` na sua Área de Trabalho. Mande esse arquivo para quem te passou o app. O seu jogo entra numa próxima versão.

## Atualizações

O app se atualiza sozinho. Quando sai uma versão nova, ele baixa ao abrir e pede para você fechar e abrir de novo.

## Privacidade

Os saves são lidos só no seu PC. O app só usa a internet para duas coisas, ambas no GitHub: conferir se existe versão nova e baixar a lista de jogos por conquistas (`games.json`, só dados, nunca código). Para desligar o segundo download, crie o arquivo `%APPDATA%\Zerometro\settings.json` com `{"baixar_mapa": false}`; o app passa a usar só a lista que já vem dentro dele.
