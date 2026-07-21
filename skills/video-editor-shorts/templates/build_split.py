"""Montador do formato meia-tela 9:16 (1080x1920 @ 30fps).

Metade de baixo: fala do usuário (EDL de cortes de silêncio, crop centrado no
rosto). Metade de cima: fila de b-rolls MUDOS trocando em sincronia com a
narração. vstack -> encode único -> legendas por último.

Uso:
    python build_split.py split.json

split.json:
{
  "user_video": "C:/.../fala.mp4",
  "crop_center_x": 0.5,          // 0..1, do smart_crop.py (react-video)
  "ranges": [[58.2, 61.9], [62.6, 66.1]],   // EDL da fala (s no arquivo fonte)
  "broll": [                     // fila em ordem; durações somam >= fala
    {"file": "C:/.../broll1.mp4", "start": 30.0, "dur": 4.0},
    {"file": "C:/.../broll2.mp4", "start": 131.0, "dur": 5.0}
  ],
  "srt": "C:/.../legenda.srt",   // opcional; offsets no timeline de SAÍDA
  "grade": "eq=contrast=1.06:saturation=1.08",   // opcional
  "out": "C:/.../short.mp4"
}

Regras herdadas da skill longa (video-editor-youtube): fades de áudio de 30ms
em toda borda de segmento; fps FORÇADO (30) em todo clipe antes de concat;
legendas aplicadas por último; verificar o output antes de entregar.
O último b-roll é estendido (tpad clone) se a fila for mais curta que a fala.

GOTCHA sync (2 causas, ambas resolvidas aqui): montar a fala por
arquivos-segmento + concat demuxer desincroniza áudio/vídeo progressivamente:
(1) AAC por segmento carrega ~21-44ms de priming que o concat não desconta;
(2) pior: o vídeo de cada segmento arredonda PRA BAIXO na grade de fps
(-t 3.74 @ 30fps = 112 frames = 3.733s) enquanto o áudio fica exato (3.740s)
— ~20ms por corte, ~0.2-0.3s de fala atrasada em 9 segmentos. Por isso a
metade da fala é montada em UMA passada de filter_complex (trim/atrim do
mesmo input + concat filter): áudio e vídeo cortados no mesmo ponto, PTS
contínuo, um encode só.

Legendas: campo "srt" aceita .ass (preferido — estilo embutido, posição
estável; gerar com helpers/make_srt.py) ou .srt (aplica force_style legado).
"""
import json
import subprocess
import sys
import tempfile
from pathlib import Path

FPS = 30
W, H_HALF = 1080, 960
VC = ["-c:v", "libx264", "-preset", "fast", "-crf", "19", "-pix_fmt", "yuv420p", "-r", str(FPS)]
AC = ["-c:a", "aac", "-b:a", "192k", "-ar", "48000"]
# GOTCHA: libass renderiza SRT num script de 384x288 (PlayRes). FontSize e
# MarginV são NESSA escala, não em pixels do canvas 1920. MarginV=140 ~ costura
# (y~960); FontSize=11 ~ 73px renderizados. MarginV=900 joga o texto pra fora.
SUB_STYLE = (
    "FontName=Montserrat Black,FontSize=11,Bold=1,"
    "PrimaryColour=&H00FFFFFF,OutlineColour=&H00000000,"
    "BorderStyle=1,Outline=1,Shadow=0,Alignment=2,MarginV=140"
)


def run(cmd):
    print("  $", " ".join(str(c) for c in cmd)[:200])
    r = subprocess.run(cmd, capture_output=True, text=True)
    if r.returncode != 0:
        print(r.stderr[-3000:])
        sys.exit(f"FALHOU: {cmd[0]} ...")


def probe_dur(p):
    r = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration",
         "-of", "default=noprint_wrappers=1:nokey=1", str(p)],
        capture_output=True, text=True)
    return float(r.stdout.strip())


def crop_filter(cx: float, grade: str) -> str:
    # crop 1080x960-equivalente (aspecto 1.125) centrado em cx, depois escala.
    # ow/oh calculados sobre o frame fonte mantendo o aspecto do half.
    g = f",{grade}" if grade else ""
    return (
        "crop='min(iw,ih*1.125)':'min(ih,iw/1.125)':"
        f"'(iw-ow)*{cx:.3f}':'(ih-oh)/2',"
        f"scale={W}:{H_HALF},fps={FPS}{g}"
    )


def main():
    cfg = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    work = Path(tempfile.mkdtemp(prefix="split_"))
    grade = cfg.get("grade", "")
    cx = float(cfg.get("crop_center_x", 0.5))

    # 1) metade de baixo: UMA passada de filter_complex — trim/atrim de cada
    # range do mesmo input, fades de 30ms, crop no rosto, concat filter.
    # (ver GOTCHA sync no docstring: nunca montar por arquivos + concat demuxer)
    # snap dos cortes na grade de frames da fonte: corte fora da grade faz o
    # fps= descartar/realinhar video dentro do segmento enquanto o atrim corta
    # exato -> ~8ms de erro por corte, cumulativo (~60ms em 7 segmentos).
    src_fps = 30.0  # ajustar se a fonte nao for 30fps (ffprobe r_frame_rate)
    parts = []
    for i, (s, e) in enumerate(cfg["ranges"]):
        s = round(s * src_fps) / src_fps
        e = round(e * src_fps) / src_fps
        dur = e - s
        parts.append(
            f"[0:v]trim=start={s:.3f}:end={e:.3f},setpts=PTS-STARTPTS,"
            f"{crop_filter(cx, grade)}[v{i}];"
            f"[0:a]atrim=start={s:.3f}:end={e:.3f},asetpts=PTS-STARTPTS,"
            f"afade=t=in:st=0:d=0.03,afade=t=out:st={max(0, dur-0.03):.3f}:d=0.03[a{i}]"
        )
    n = len(cfg["ranges"])
    pairs = "".join(f"[v{i}][a{i}]" for i in range(n))
    parts.append(f"{pairs}concat=n={n}:v=1:a=1[vc][ac]")
    # container MOV, nao MKV: o MKV arredonda PTS pra milissegundos (timebase
    # 1/1000) e o proximo estagio CFR duplica frames -> video atrasa ~0.1s+
    # progressivo. MOV preserva o timebase exato e aceita PCM.
    bottom = work / "bottom.mov"
    run(["ffmpeg", "-y", "-i", cfg["user_video"],
         "-filter_complex", ";".join(parts),
         "-map", "[vc]", "-map", "[ac]",
         *VC, "-c:a", "pcm_s16le", "-ar", "48000", str(bottom)])
    total = probe_dur(bottom)
    print(f"fala total: {total:.2f}s")

    # 2) metade de cima: fila de b-rolls mudos, mesma duração total
    brolls = []
    acc = 0.0
    for i, b in enumerate(cfg["broll"]):
        if acc >= total:
            break
        dur = min(float(b["dur"]), total - acc)
        is_last = (i == len(cfg["broll"]) - 1)
        if is_last and acc + dur < total:
            dur = total - acc  # estica o último (tpad clona o frame final se faltar fonte)
        out = work / f"broll_{i:02d}.mp4"
        vf = crop_filter(0.5, grade) + f",tpad=stop_mode=clone:stop_duration=10"
        run(["ffmpeg", "-y", "-ss", f"{float(b['start']):.3f}", "-i", b["file"],
             "-t", f"{dur + 0.5:.3f}", "-vf", vf, "-an", *VC,
             "-t", f"{dur:.3f}", str(out)])
        brolls.append(out)
        acc += dur
    lst2 = work / "broll.txt"
    lst2.write_text("".join(f"file '{p.as_posix()}'\n" for p in brolls), encoding="utf-8")
    top = work / "top.mp4"
    run(["ffmpeg", "-y", "-f", "concat", "-safe", "0", "-i", str(lst2), "-c", "copy", str(top)])

    # 3) vstack + legendas (LAST). Fontes bundled na propria skill.
    fonts_dir = Path(__file__).resolve().parents[1] / "assets" / "fonts"
    fonts_esc = fonts_dir.as_posix().replace(":", r"\:")  # ffmpeg filter parser: escapar ':' de drive
    vf_parts = [f"[1:v][0:v]vstack=inputs=2[stacked]"]
    label = "[stacked]"
    if cfg.get("srt"):
        sub = str(Path(cfg["srt"]).resolve()).replace("\\", "/").replace(":", r"\:")
        if cfg["srt"].lower().endswith(".ass"):  # estilo embutido no arquivo
            style_arg = ""
        else:
            style_arg = f":force_style='{SUB_STYLE}'"
        vf_parts.append(
            f"{label}subtitles='{sub}':fontsdir='{fonts_esc}'{style_arg}[outv]")
        label = "[outv]"
    else:
        vf_parts[-1] = vf_parts[-1].replace("[stacked]", "[outv]")
    run(["ffmpeg", "-y", "-i", str(bottom), "-i", str(top),
         "-filter_complex", ";".join(vf_parts),
         "-map", "[outv]", "-map", "0:a", *VC, *AC, cfg["out"]])
    print(f"\npronto: {cfg['out']}  ({probe_dur(cfg['out']):.2f}s)")
    print(f"(intermediários em {work} — apagar depois de verificar)")


if __name__ == "__main__":
    main()
