"""Gera as legendas queimadas (.ass) no timeline de SAÍDA (pós-cortes).

Blocos de no MÁXIMO 2 palavras, UPPERCASE, SEMPRE 1 linha. Emite .ass (não
.srt): o filtro subtitles do ffmpeg, ao converter .srt internamente, injeta
alinhamento por linha que pode IGNORAR Alignment/MarginV do force_style, e o
ancoramento pela BASE faz o texto "pular" conforme descendentes/acentos.
O .ass explícito usa PlayRes = resolução real (FontSize 1:1 em pixels) e
Alignment=8 (topo) — posição idêntica em todos os blocos.

Estilo padrão (mesma família do react-video): Montserrat 88px, amarelo,
outline preto 4, topo do texto em y=905 (costura do 9:16 em ~960).

Uso:
    python make_srt.py <transcript.json> <split.json> -o legenda.ass
"""
import argparse
import json
from pathlib import Path

PLAY_W, PLAY_H = 1080, 1920
FONTSIZE = 88
COLOR = "&H0000FFFF"   # amarelo (ASS = AABBGGRR)
OUTLINE = 4
MARGIN_V_TOP = 905      # topo do texto; costura fica em y=960


def ts(t: float) -> str:
    cs = int(round(t * 100))
    h, cs = divmod(cs, 360000)
    m, cs = divmod(cs, 6000)
    s, cs = divmod(cs, 100)
    return f"{h}:{m:02d}:{s:02d}.{cs:02d}"


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("transcript")
    ap.add_argument("split_json")
    ap.add_argument("-o", "--out", required=True)
    args = ap.parse_args()

    words = [w for w in json.loads(Path(args.transcript).read_text(encoding="utf-8"))["words"]
             if w.get("type") != "spacing"]
    ranges = json.loads(Path(args.split_json).read_text(encoding="utf-8"))["ranges"]

    # palavras -> timeline de saída. O Scribe estica o `end` de palavras sobre
    # pausas — clampar cada end ao start da PROXIMA palavra, senao os blocos
    # sobrepoem no tempo e o libass empilha 2 linhas na tela.
    out_words = []
    offset = 0.0
    for seg_i, (s, e) in enumerate(ranges):
        seg_words = [w for w in words if s - 0.05 <= w["start"] < e]
        for j, w in enumerate(seg_words):
            start = max(0.0, w["start"] - s) + offset
            end = min(w.get("end", w["start"] + 0.4), e) - s + offset
            if j + 1 < len(seg_words):
                end = min(end, seg_words[j + 1]["start"] - s + offset)
            out_words.append((start, max(end, start + 0.12), w["text"].strip(), seg_i))
        offset += e - s

    # blocos de ate 2 palavras, 1 linha; nunca atravessar corte (mudanca de
    # segmento) nem gap >0.6s; se as 2 palavras somam >20 chars vira 1 palavra
    MAX_CHARS = 20
    blocks = []
    cur = []
    for w in out_words:
        too_long = cur and len(cur[-1][2]) + 1 + len(w[2]) > MAX_CHARS
        if cur and (len(cur) == 2 or too_long or w[3] != cur[-1][3]
                    or w[0] - cur[-1][1] > 0.6):
            blocks.append(cur)
            cur = []
        cur.append(w)
    if cur:
        blocks.append(cur)

    events = []
    for i, blk in enumerate(blocks):
        start = blk[0][0]
        end = blk[-1][1]
        # estende ate perto do proximo bloco (max +0.4s), mas o teto de
        # nao-sobreposicao e ABSOLUTO: dois eventos simultaneos = 2 linhas
        # empilhadas na tela. Nenhuma regra de duracao minima pode passar dele.
        if i + 1 < len(blocks):
            nxt = blocks[i + 1][0][0]
            end = min(max(end, nxt - 0.04), end + 0.4)
            end = min(end, nxt - 0.02)   # hard cap, sempre por ultimo
        end = max(end, start + 0.01)
        text = " ".join(w[2] for w in blk).upper().rstrip(",")
        text = text.replace("{", "").replace("}", "")
        events.append((start, end, text))
    # auto-verificacao: nenhum evento pode sobrepor o seguinte
    for (s1, e1, t1), (s2, e2, t2) in zip(events, events[1:]):
        assert e1 <= s2, f"sobreposicao: '{t1}' ({e1:.2f}) x '{t2}' ({s2:.2f})"

    with open(args.out, "w", encoding="utf-8") as f:
        f.write("[Script Info]\nScriptType: v4.00+\n")
        f.write(f"PlayResX: {PLAY_W}\nPlayResY: {PLAY_H}\n\n")
        f.write("[V4+ Styles]\n")
        f.write("Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, "
                "OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, "
                "ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, "
                "Alignment, MarginL, MarginR, MarginV, Encoding\n")
        f.write(f"Style: Default,Montserrat Black,{FONTSIZE},{COLOR},&Hffffff,"
                f"&H00000000,&H80000000,-1,0,0,0,100,100,0,0,1,{OUTLINE},1,"
                f"8,20,20,{MARGIN_V_TOP},1\n\n")
        f.write("[Events]\n")
        f.write("Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text\n")
        for start, end, text in events:
            f.write(f"Dialogue: 0,{ts(start)},{ts(end)},Default,,0,0,0,,{text}\n")
    print(f"{len(events)} blocos -> {args.out}")


if __name__ == "__main__":
    main()
