# Roteiro de testes no celular (bot de dev)

> Criado em 03/10/2026 (S3 + S4.1); bloco G (lembretes) e H (cartões) em 05/10/2026; I (fatura) em 06/10/2026. Fazer no **@TelegranaAppDevBot**, em ordem. ✍️ = mensagem de texto; 🎙️ = mensagem de voz.
> "Responder" no Telegram do celular: deslize a mensagem para a esquerda (ou toque e segure → Responder).
> Se algo sair diferente do esperado, anote o **código do passo** (ex.: D2). O agente confere os logs (`update.processado`) e a conversa.

## A — Texto
| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| A1 | ✍️ `mercado 45,90 no pix` | ✅ Gasto registrado · 🛒 Mercado · R$ 45,90 · ⚡ Pix · hoje (sem linha 📝) |
| A2 | Responder ao recibo do A1: ✍️ `foi 54,90 no débito` | ✏️ Corrigido · R$ 54,90 · 💳 Débito |
| A3 | No recibo corrigido: 🗑️ Apagar; depois ↩️ Desfazer | "Apagado…" e depois "Lançamento de volta" + recibo |

## B — Categoria ambígua e regra aprendida
| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| B1 | ✍️ `bar 40` | Pergunta a categoria: 🎮 Lazer · 🍽️ Alimentação fora · ➕ Criar «Bar» · ✖️ Cancelar |
| B2 | Tocar 🎮 Lazer | Recibo em Lazer + "Quer que eu lembre: «bar» é sempre Lazer?" → tocar ✅ Sempre |
| B3 | ✍️ `bar 25` | Registra direto em 🎮 Lazer, sem perguntar |

## C — Áudio
| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| C1 | 🎙️ "gastei trinta reais de pão hoje" | "digitando…", depois pergunta a categoria (pão é ambíguo); ao escolher, recibo com a linha 🎙️ «…» |
| C2 | 🎙️ "paguei cento e vinte reais de luz no boleto" | 💡 Contas da casa · R$ 120,00 · 🧾 Boleto, com 🎙️ «…» |
| C3 | 🎙️ "gastei no mercado" | "💬 Quanto foi?" (o Telegram já abre a resposta) |
| C4 | Responder à pergunta do C3 com 🎙️ "quarenta e cinco" | Recibo 🛒 Mercado · R$ 45,00 |
| C5 | 🎙️ "oi, tudo bem?" | "🎙️ Ouvi: «…»" e uma saudação |

## D — Correções (o que falhou em 02/10)
| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| D1 | ✍️ `mercado 50 no pix` | Recibo 🛒 Mercado · R$ 50,00 |
| D2 | **Responder ao recibo do D1** com 🎙️ "na verdade foi na padaria, não no mercado" | ✏️ Corrigido · 🍽️ Alimentação fora (pela regra «padaria» de 02/10), R$ 50,00 mantido |
| D3 | No mesmo recibo, tocar ✏️ Corrigir; **responder à mensagem que aparecer** com 🎙️ "foi sessenta reais" | ✏️ Corrigido · R$ 60,00 |
| D4 | Sem responder a nada: 🎙️ "na verdade foi ontem" | ✏️ Corrigido no último lançamento, com a data de ontem |
| D5 | Responder a um recibo com ✍️ `na verdade foi na academia` | Pergunta a categoria (sem a atual) com ➕ Criar «Academia» e 🔎 Outra → tocar Criar → Corrigido com 🏋️ Academia |

## E — Fixos (S4.1)
| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| E1 | ✍️ `aluguel 1500 todo dia 10` | 🔁 Fixo cadastrado · 🏠 Aluguel · R$ 1.500,00 · dia 10 · lembrete na véspera, no dia e todo dia depois, às 09:00 (sem recibo de gasto) |
| E2 | ✍️ `netflix 55,90` → no recibo, tocar 🔁 Sim, todo mês | 🔁 Fixo cadastrado · Netflix · dia de hoje |
| E3 | 🎙️ "paguei a internet cento e vinte reais, todo dia cinco" | Recibo do pagamento **e** 🔁 Fixo cadastrado · Internet · R$ 120,00 (estimado) · dia 5 |
| E4 | `/fixos` → tocar Aluguel → 💰 Valor → responder `1600` | ✅ Fixo atualizado · R$ 1.600,00 |
| E5 | No Aluguel: 🔔 Lembretes → desmarcar Véspera → tocar 🌅🌙 Ambos → ✔️ Pronto | "Lembrete no dia e todo dia depois, às 09:00 e às 20:00" |
| E6 | No Netflix: 🗑️ Apagar → 🗑️ Apagar de vez | "Fixo apagado"; o lançamento do E2 continua |

## G — Lembretes (S4.2)
> O agente dispara a rotina de dev simulando o dia (`{"momento": ...}`); você só confere e toca. Os seus outros fixos (Aluguel, Internet…) também podem mandar lembrete nesses dias simulados: é o esperado.

| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| G1 | ✍️ `spotify 21,90 todo dia 20`; o agente roda a rotina como se fosse **19/10 às 09:00** | 📱 **Spotify** vence amanhã (20/10) · Valor: R$ 21,90 · ✅ Paguei · ✏️ Outro valor · ⏭️ Pular este mês |
| G2 | O agente roda **20/10 às 09:00**; tocar ✅ Paguei | Os botões somem; recibo ✅ Gasto registrado · R$ 21,90 · 📝 Spotify |
| G3 | Tocar ✅ Paguei no lembrete do G1 (véspera) | "👍 Spotify de outubro já está resolvido." (não lança de novo) |
| G4 | ✍️ `luz 200 todo dia 15`; o agente roda **16/10 às 09:00** | ⏰ **Luz** venceu em 15/10 e ainda não está marcado como pago · Valor estimado: R$ 200,00 |
| G5 | Tocar ✏️ Outro valor; mandar (respondendo ou não) 🎙️ "cento e oitenta e sete e quarenta" | Recibo 💡 Contas da casa · R$ 187,40 |
| G6 | ✍️ `condomínio 450 todo dia 18`; o agente roda **18/10 às 09:00**; tocar ⏭️ Pular este mês | "⏭️ Pronto, Condomínio de outubro ficou de fora…"; rodando **19/10**, nada chega |

## H — Cartões (S5.1)
| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| H1 | ✍️ `tênis 600 em 3x no nubank` | "📅 Cartão novo! Em que dia a fatura fecha e em que dia vence?" (2ª linha 💳 Nubank) |
| H2 | Responder (ou mandar solto) 🎙️ "fecha dia três e vence dia dez" | 💳 Compra no crédito registrada · R$ 600,00 · 💳 Nubank · 3x de R$ 200,00 · 🧾 1ª parcela na fatura que vence … |
| H3 | Se houver compras no crédito antigas: tocar ✅ Sim, mover | "Pronto: N compra(s) foram para as faturas do Nubank" |
| H4 | `/cartoes` → ➕ Novo cartão → `Inter` → `fecha 25, vence 5` | 💳 Cartão cadastrado · Inter · fecha dia 25 · vence dia 5 |
| H5 | ✍️ `farmácia 80 no crédito` → tocar 💳 Inter | Pergunta qual cartão (Nubank, Inter, ➕ Outro cartão); recibo no Inter |
| H6 | Responder ao recibo do H2 com ✍️ `foi 900` | ✏️ Corrigido · 3x de R$ 300,00 |
| H7 | Responder ao mesmo recibo com 🎙️ "na verdade foi no pix" | ✏️ Corrigido · R$ 900,00 · ⚡ Pix · sem parcelas |

## I — Fatura (S5.2)
> O agente dispara a rotina de dev simulando o dia (fechamento e vencimento).

| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| I1 | O agente roda a rotina no dia do fechamento do Nubank | 🧾 Fatura do Nubank fechou · vence dd/mm · Total · itens · ✅ Paguei R$ X · ✏️ Outro valor |
| I2 | ✍️ `paguei a fatura do nubank` | A mesma fatura com os botões (não paga sozinho) |
| I3 | ✏️ Outro valor → mandar (solto ou respondendo) 🎙️ um valor menor que o total | ✅ Pagamento parcial…; o resto vai para a fatura seguinte como «Saldo anterior» |
| I4 | `/cartoes` → Nubank → 🧾 Faturas | A fatura seguinte com o «Saldo anterior» somado |
| I5 | ✍️ `estorno de 80 no inter` | ↩️ Estorno de R$ 80,00 abatido de «farmácia» |
| I6 | `/cartoes` → Inter → 🔔 Lembretes → desmarcar Depois → ✔️ Pronto | "Lembrete na véspera e no dia, às 09:00" |

## F — Limites e ajuda
| Passo | O que fazer | O que deve acontecer |
|---|---|---|
| F1 | 🎙️ áudio com **mais de 2 minutos** | Recusa ("passa de 2 minutos") sem transcrever |
| F2 | `/ajuda` | Explica como registrar (texto ou áudio) e lista `/fixos` |
