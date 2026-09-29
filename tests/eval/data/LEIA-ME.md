# tests/eval/data — conjunto real de avaliação da IA

**O conteúdo desta pasta NUNCA vai para o Git.** O repositório é público (D015) e
estas mensagens e áudios são dados financeiros reais da família (D016). O
`.gitignore` ignora tudo aqui, exceto este arquivo.

Formato esperado (detalhes em `docs/manual/S0.7-marca-e-dados.md`):

```
tests/eval/data/
├── mensagens.txt      # uma mensagem por linha, do jeito que vocês escreveriam
├── audios.txt         # "nome-do-arquivo | o que foi dito", uma linha por áudio
└── audios/            # os áudios (.ogg, .oga, .opus, .m4a, .mp3, .wav)
```

Como o CI vai acessar esses dados sem publicá-los será decidido na S2 (proposta
em D016: um repositório privado separado só para o conjunto de avaliação).
