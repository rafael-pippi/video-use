---
name: video-editor-shorts
description: >
  Editor de vídeos curtos 9:16 (1080x1920) para Reels/TikTok/Shorts no formato
  meia-tela: você falando embaixo (50%) + b-rolls de vídeo MUDOS em cima (50%),
  trocando em sincronia com a narração. Feito para gravações roteirizadas
  (gancho falado + frases em sequência, com retakes — a última versão completa
  de cada frase é a que vale). Enquadramento por detecção de rosto, cortes de
  silêncio agressivos, legendas queimadas de no máximo 2 palavras, gancho
  textual nos primeiros 3s, busca de b-rolls no YouTube/TikTok via yt-dlp.
  Skill autossuficiente: helpers de transcrição (ElevenLabs Scribe), smart
  crop e fontes vêm bundled. Use quando pedirem para montar um short, reel,
  TikTok, vídeo vertical, ou transformar footage falada em vídeo curto.
argument-hint: "[vídeo falado + pasta de b-rolls (opcional)]"
---

# Video Editor — Shorts (meia-tela 9:16)

Formato: canvas **1080x1920 @ 30fps**. Metade de baixo (1080x960) = você
falando, com crop centrado no rosto. Metade de cima (1080x960) = timeline de
b-rolls que troca em sincronia com o que está sendo dito. Áudio vem 100% da
fala; **b-rolls SEMPRE mudos** (o `build_split.py` já extrai com `-an`).

## Autossuficiente — o que vem bundled

- `helpers/transcribe.py` — ElevenLabs Scribe, word-level verbatim, cache por
  arquivo (precisa de `ELEVENLABS_API_KEY` no ambiente ou `.env`; dep: `requests`).
- `helpers/pack_transcripts.py` — transcripts JSON → `takes_packed.md`
  (leitura em frases com timestamps; é o que você lê para decidir cortes).
- `helpers/smart_crop.py` — centro de crop por rosto (OpenCV Haar, múltiplos
  frames dos primeiros 3s) com fallback de saliência visual (PIL):
  `python smart_crop.py --video <v> --aspect 1.125 --json` (1.125 = 1080/960).
- `helpers/make_srt.py` — gera as legendas (`.ass`, estilo embutido: amarelo
  88px, 1 linha, topo fixo) no timeline de SAÍDA a partir do transcript +
  `split.json`: blocos de no máx. 2 palavras, UPPERCASE, nunca unindo
  palavras através de um corte ("BINGX." + "COM" viraria "BINGX. COM") nem
  sobrepondo tempos — **dois eventos simultâneos = 2 linhas empilhadas na
  tela**. O script clampa o `end` de cada palavra ao início da seguinte (o
  Scribe estica ends sobre pausas), aplica o teto de não-sobreposição por
  ÚLTIMO (nenhuma regra de duração mínima pode passar dele) e se
  auto-verifica com assert. Se mexer nesse código, rode e confira o assert.
- `assets/sfx/` — pack curado com 31 SFX (fornecido pelo usuário, inclui os
  virais atuais), normalizados a 48k/-6dB, em 5 pastas: `meme/` (8), `ui/` (7),
  `transition/` (7), `cinematic/` (5), `action/` (4) — ver passo 9 do pipeline
  para a regra de uso (poucos e diegéticos). Faltando um efeito específico
  (ex. `cartoon/pop`, `gaming/coin`), gerar via ElevenLabs sound-generation e
  normalizar a 48k/-6dB antes de usar.
- `assets/fonts/` — Montserrat Black/Bold para as legendas queimadas.
- `templates/build_split.py` — o montador executável do formato (ver abaixo).
- Windows: rodar todo helper com `PYTHONIOENCODING=utf-8`.

**Ambiente / deps (vendorizado no video-use, Linux):**
- `smart_crop.py` precisa de `opencv-python-headless` + `pillow`
  (`pip install opencv-python-headless pillow`). O modelo neural YuNet NÃO
  vem no pacote — sem `assets/models/face_detection_yunet_2023mar.onnx` o
  detector cai automaticamente no Haar cascade (frontal + perfil), que já
  resolve a maioria dos casos. Para máxima robustez (cabeça baixa/boné/perfil),
  baixe o YuNet do repo do OpenCV Zoo e coloque nesse caminho.
- `transcribe.py` usa ElevenLabs Scribe (`ELEVENLABS_API_KEY`); sem a chave,
  use o fallback local whisper.cpp da skill irmã `remotion-captions`
  (`template/transcribe.mjs`) — ele emite o mesmo formato `{words:[...]}`.
- Caminhos no `build_split.py`/`make_srt.py` funcionam em POSIX; ignore os
  exemplos com letra de drive `C:/` do docstring.

Skills irmãs do pack são **opcionais** (extras, não dependências):
`../video-editor-youtube/templates/` tem componentes Remotion (KeywordPop,
FunPop) e SFX normalizados para overlays pontuais; as regras duras de produção
de lá (fades 30ms, fps forçado, legendas por último, verificação frame a frame
antes de entregar) estão embutidas no `build_split.py` e neste documento.

## O material de entrada (como esses vídeos são gravados)

Gravação **roteirizada**: gancho falado na abertura, depois frases em
sequência. É normal uma frase aparecer **repetida, incompleta ou errada** —
o falante corta e regrava na hora. Regra de seleção de retake: **a ÚLTIMA
ocorrência de cada frase é a que vale** (é a completa/correta); as anteriores
são descartadas no EDL. Detecte retakes no `takes_packed.md` por similaridade
de texto entre frases vizinhas — uma frase truncada seguida de outra que
começa igual é um retake, não conteúdo.

**GOTCHA 1 — leitura sussurrada antes da take.** Padrão real de gravação: o
falante LÊ a frase do roteiro (sussurrando ou em voz de leitura) e logo em
seguida grava a take valendo. O Scribe transcreve a leitura como se fosse
fala normal — no transcript do vídeo inteiro as duas viram "takes" e a
primeira é a leitura. Nunca escolha a primeira ocorrência sem confirmar; em
snippet isolado o Scribe marca "(sussurrando)" explicitamente.

**GOTCHA 2 — timestamps do vídeo inteiro não servem para corte fino.** No
arquivo longo, o Scribe estica o `end` de palavras sobre pausas (uma palavra
de 0.4s pode aparecer com 6s) e funde takes vizinhas. **Workflow obrigatório
de corte:** (1) use o transcript completo só para MAPEAR as frases e escolher
a região da última take; (2) extraia cada região como snippet de áudio
(`ffmpeg -ss <t> -t <dur> -vn -ac 1 -ar 16000`) e re-transcreva o snippet —
timestamps ficam precisos e a leitura sussurrada aparece rotulada; (3) monte
o range final com as palavras do snippet (offset = início do snippet), pad
~50ms antes / ~100ms depois.

**Anti-sussurro (obrigatório no self-check).** Mesmo com o workflow de
snippet, uma leitura sussurrada pode passar. Detecção objetiva: rode
`volumedetect` por segmento (na fonte ao montar o EDL, E no output final):
`mean_volume` de fala normal fica em −15 a −22 dB; leitura sussurrada fica
< −28 dB — qualquer segmento abaixo disso é take errada. Se a frase NÃO tem
take falada (o falante desistiu dela), **drope a frase** e emende o corte —
nunca use a sussurrada.

**Cortes SECOS (obrigatório).** Nada de ar morto: rode
`silencedetect=noise=-35dB:d=0.15` na fonte para conhecer as bordas reais de
fala, e valide o OUTPUT com `silencedetect=noise=-35dB:d=0.2` — o resultado
deve ter **zero** silêncios internos >0.2s. Se aparecer um, o corte está
frouxo: aperte e re-renderize.

## O que muda em relação ao long-form (não confundir os dois modos)

| | long-form (video-editor-youtube) | shorts (esta skill) |
|---|---|---|
| Material | conversa natural, sem roteiro | roteirizado, com retakes (última vale) |
| Silêncios | corta só >3.5s, preserva ar | corta >0.4–0.7s, ritmo denso |
| Pad nas bordas | 0.4s | 60–120ms |
| Legendas | NÃO por padrão | SIM, sempre — máx. 2 palavras por bloco |
| Duração | livre | alvo 30–60s |
| fps | 24 | 30, forçado em TODO clipe (`-r 30` + `fps=30` no -vf) |
| Grade | neutro | neutro + saturação levemente maior ok (`saturation=1.05–1.1`) |

## Pipeline

1. **Transcrever** o vídeo falado (`helpers/transcribe.py`), gerar
   `takes_packed.md` (`helpers/pack_transcripts.py`) e ler.
2. **Resolver retakes**: marcar frases repetidas/incompletas; manter sempre a
   última versão completa de cada frase, na ordem do roteiro.
3. **EDL da fala**: cortes em fronteira de palavra, gaps >0.4–0.7s removidos,
   pad 60–120ms. Jump cuts são aceitos e esperados no formato.
4. **Crop do rosto**: `helpers/smart_crop.py --aspect 1.125` na metade do
   falante. Se o rosto se move muito entre segmentos, calcule por segmento.
5. **Plano de b-roll**: para cada beat da narração, um clipe que ilustre a
   ideia falada. **Troca a cada 3–5s no MÁXIMO** (feedback real: b-roll parado
   >5s mata o ritmo), sempre em fronteira de palavra. Todo clipe precisa de
   movimento: still SEMPRE vira Ken Burns (zoompan supersampled, zoom ~1.09,
   máx ~3.5s por still); vídeo precisa ter cenas variadas — um clipe longo
   parado não conta como "vídeo".
   **Padrões que funcionam:**
   - *Recorte de reportagem*: NUNCA still puro — card com sombra (PIL) sobre
     VÍDEO de fundo em movimento (advogado/tema andando), fundo escurecido
     `eq=brightness=-0.08:saturation=0.9`. Reusar o card mais tarde como
     callback rápido (~2s) quando a fala referencia a notícia de novo.
   - *Produto/plataforma*: pedir/usar vídeo de apresentação + screenshots
     reais do usuário. Vídeo widescreen com texto nas laterais NÃO aguenta
     crop central 1.125 — renderizar scale-fit num canvas 1080x960 da MESMA
     cor do fundo do vídeo (amostrar o pixel do canto) = seamless.
     **Onde usar (feedback real): SÓ na janela do CTA** (quando a fala
     menciona a ferramenta pelo nome / oferece o link / "comenta X").
     Mostrar a marca durante toda a explicação do conceito passa recibo de
     institucional/publicidade — no corpo do vídeo (explicando o problema, o
     conceito, o benefício genérico) usar b-roll GENÉRICO do tema (advocacia/
     tribunal/tech: martelo+balança, livro+Têmis, rede de dados abstrata,
     mãos digitando, relógio pra "isso levava X, agora leva Y") e só revelar
     o produto quando o roteiro literalmente pede pra agir.
   - Headline de notícia real: buscar o caso na web e capturar via Chrome
     headless (`chrome --headless=new --screenshot=<abs.png>
     --window-size=1400,1000 <url>`; paths absolutos Windows).
   Fontes, em ordem de preferência:
   - pasta de b-rolls do usuário (footage própria);
   - imagens/vídeos que o usuário indicar;
   - **busca externa via yt-dlp** quando faltar material: YouTube
     (`yt-dlp "ytsearch5:<termo> b-roll 4k" --get-id --get-title` para
     avaliar, depois baixar o escolhido) ou URL de TikTok direto. Baixar em
     1080p+ (`-f "bv*[height>=1080]"`), cortar só o trecho necessário.
     **Avisar o usuário no relatório que material de terceiros foi usado e de
     onde veio** — direitos de uso são responsabilidade editorial dele.
   Sem b-roll adequado para um trecho → estique o anterior; nunca deixe
   buraco preto. B-roll genérico bonito > b-roll "quase relacionado" confuso.

   **Prints/screenshots como b-roll (vídeos de produto/notícia).** Imagens
   estáticas viram clipes com Ken Burns: compor o print num canvas 1080x960
   (fundo escuro ou claro, sombra suave, padding ~36px), depois
   `zoompan z='1+0.07*on/N'` supersampled em 3x (3240x2880) e downscale —
   zoom direto na resolução final treme (shimmer). Padrões que funcionam:
   - **headline de notícia real como hook visual** (capturar com
     `chrome --headless=new --screenshot=... --window-size=1400,1000 <url>`,
     crop na área da manchete) — vale mais que texto genérico; nesse caso o
     overlay de texto do gancho vira uma tarja menor (ex. "CASO REAL") sobre
     a foto, sem cobrir a manchete;
   - **prints reais do produto na 2ª metade** (dashboard → feature → prova →
     CTA), sincronizando cada print com o beat falado — ex.: print de
     comparação "3h vs 5min" na tela exatamente quando a fala diz isso.
6. **Montar** com `templates/build_split.py`: extrai segmentos da fala com
   fades de 30ms, concat, crop das duas metades, fila de b-rolls mudos
   casando a duração total (tpad clona o último frame se faltar fonte),
   `vstack`, encode único.
7. **Gancho textual (primeiros 3s, obrigatório)**: precisa gerar EMOÇÃO e
   abrir um GAP de curiosidade que o meio/fim do vídeo preenche — nunca um
   rótulo estático ("CASO REAL" = fraco; "O ERRO DE R$ 20 MILHÕES" = forte:
   qual erro? a resposta vem depois). Fórmula: consequência concreta +
   elemento faltante. Junto com o gancho falado. Estilo:
   **fundo PREENCHIDO** (barra vermelha por linha de texto), texto branco com
   borda preta (stroke ~5px), Montserrat Black — texto solto sem fundo não
   segura sobre b-roll claro. PNG via PIL + `overlay=enable='between(t,0.2,3.2)'`,
   ou overlay Remotion (KeywordPop da skill irmã, se instalada).
8. **Legendas queimadas** (SEMPRE por último): **máximo 2 palavras
   UPPERCASE por bloco, SEMPRE em 1 linha só** (o `make_srt.py` quebra em
   bloco de 1 palavra se as 2 somarem >20 chars). Estilo: **Montserrat Black
   88px, AMARELO, outline preto 4**, na costura das duas metades.
   **Gerar `.ass`, nunca `.srt`** (o `make_srt.py` já emite .ass): com .srt +
   `force_style`, o libass ancora pela BASE (o texto "pula" conforme
   descendentes/acentos), pode ignorar Alignment/MarginV, e blocos com tempos
   sobrepostos empilham em 2 linhas. O .ass usa PlayRes = resolução real
   (FontSize 1:1 em pixels) e Alignment=8 (topo, `MarginV=905`) — posição
   idêntica sempre. Offsets no timeline de SAÍDA (pós-cortes).
9. **SFX** (bundled em `assets/sfx/`, 56 efeitos em 7 pastas: `meme/` vine_boom,
   bruh, huh…; `ui/` mouse_click, notification, keyboard_typing…; `transition/`
   woosh1/2, deep_woosh…; `cinematic/` boom, hit, heartbeat…; `action/`,
   `cartoon/` pop, womp_womp…; `gaming/` coin_collect, level_up…).
   **Regra de uso (feedback real, 2 rodadas): POUCOS e DIEGÉTICOS.** 2–3 por
   vídeo no máximo, e só quando o som liga com a palavra/ação exata: woosh na
   entrada do gancho textual, vine_boom/boom num punchline de impacto
   ("multa de VINTE MILHÕES"), mouse_click quando fala "clica/comenta".
   SFX espalhado como decoração genérica soa forçado — na dúvida, NÃO põe.
   Volumes: 0.25–0.40 (`adelay=<ms>|<ms>,volume=X` + `amix normalize=0`),
   sincronizado com a palavra no timeline de saída. Faltando algum, gerar via ElevenLabs
   sound-generation e normalizar igual. **Overlays opcionais** (parcimônia):
   componentes Remotion via **alpha real** — `--codec=prores
   --prores-profile=4444 --image-format=png --pixel-format=yuva444p10le`,
   background `transparent`, composite `overlay` puro; verificar
   `ffprobe pix_fmt` = `yuva…` antes de compor.
10. **Loudnorm** 2-pass (-14 LUFS) e **verificação obrigatória**: frames nas
    trocas de b-roll (sem frame preto/duplicado), legenda legível e na
    costura, gancho textual presente nos primeiros 3s, duração v/a
    consistente, fps=30 exato no ffprobe. Só apresente depois de verificar.

## Estilo Jonata (preset dinâmico — referência: corte manual do usuário)

Analisado frame a frame de um reel editado À MÃO pelo usuário como referência
do que ele quer. Números medidos e padrões observados:

**Hook (0–3s) = densidade máxima, em CAMADAS que empilham:**
1. vídeo em movimento no fundo (filme/stock do tema, nunca still);
2. card da manchete/print por cima;
3. **stickers/logos das marcas CITADAS na fala** entrando no beat de cada
   nome (falou "iFood, Rappi e Uber" → os três logos pipocam na tela);
4. **anotações progressivas em vermelho** sobre o card: seta apontando a
   manchete no início, círculo desenhado no número-chave (~3s) — o mesmo
   card ganha elementos novos ao longo do tempo em vez de ficar parado;
5. legenda + fala simultâneas.

**Ritmo do corpo:** troca de cena a cada **2–2.5s** (mais rápido que o teto
de 3–5s do modo padrão), com **rajadas de micro-cortes (0.2–0.4s)** em
momentos de energia — montagem acelerada tipo Limitless. Nunca >4s parado.

**B-roll de FILME/SÉRIE como metáfora e humor:** cenas reconhecíveis que
traduzem a fala — o vilão lendo um documento = o juiz recebendo a petição
falsa; Limitless no laptop = o superpoder da ferramenta; personagem cômico
de escritório = quem cometeu o erro; lupa no olho = "checar as fontes".
Buscar via yt-dlp ("<filme> <cena> scene"). Registrar as fontes no
relatório (responsabilidade editorial de uso é do usuário).

**Print da coisa citada, não stock genérico:** falou "ChatGPT" → print real
da interface do ChatGPT; falou da notícia → o card da notícia; falou da
ferramenta → a ferramenta (mas produto completo só no CTA; no meio, entrada
pontual como PROVA quando a fala é "eu testei").

**Legenda neste estilo: 1 palavra por vez, BRANCA** (Montserrat bold, na
costura). A variante amarela 2 palavras continua válida como estilo default;
confirmar com o usuário qual dos dois no primeiro uso.

**SFX neste estilo: mais presentes, marcando ENTRADAS visuais** (~5–8 num
vídeo de 60s): pop/plin quando um sticker/logo entra, whoosh nas trocas de
cena maiores, boom no punchline numérico, click em "clica/comenta". Continua
valendo: cada SFX ancorado num evento visual ou falado específico — o que
não pode é SFX solto sem nada acontecendo na tela.

**Como produzir com o build_split:** os composites em camadas (fundo + card
+ stickers + anotações com janelas de tempo) são pré-renderizados como
clipes de b-roll (ffmpeg overlay com enable=between por camada, PNGs via
PIL); as rajadas viram vários itens curtos na fila de broll. O formato do
split.json não muda.

## Zonas seguras (UI das plataformas por cima do vídeo)

- **Topo 220px**: nada crítico (username/áudio do Reels cobrem).
- **Base 320px**: nada crítico (legenda da plataforma, botões, descrição).
- **Direita 120px**: evitar texto (coluna de likes/comentários).
- A legenda na costura (~y960) está sempre segura. B-roll pode "sangrar"
  nessas zonas, texto não.

## Brand kit

`brand.json` por projeto/canal define accent, fontes e voz das CTAs (**azul
como cor primária para o Jonata; vermelho SÓ alertas**). Confirme na primeira
sessão, persista, reutilize.

## Template bundled

- `templates/build_split.py` — montador do formato meia-tela. Recebe um
  `split.json` com: vídeo da fala + ranges do EDL + centro do crop, lista de
  b-rolls (arquivo, início, duração), SRT opcional, saída. Faz tudo até o
  vstack + legendas. Ler o próprio script antes de usar — é curto e é a
  especificação executável do formato.
