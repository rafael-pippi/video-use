#!/usr/bin/env python3
"""Smart Crop — encontra o melhor ponto de corte de um vídeo.

Prioridade 1: detecção de rosto (Haar cascade/OpenCV) nos primeiros ~3s do
vídeo (múltiplos frames, não só o primeiro) — pega o personagem principal
mesmo que ele se mova/vire a cabeça no início do clipe.
Prioridade 2 (fallback): densidade de bordas (saliência visual, PIL) no
primeiro frame, usada quando nenhum rosto é detectado (b-roll, paisagem,
gameplay, etc.)

Uso:
    python smart_crop.py --video input.mp4 --json
    python smart_crop.py --video input.mp4 --aspect 1.0
"""
import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from typing import Optional, Tuple


def _extract_first_frame(video_path: str, output_path: str) -> bool:
    """Extrai o primeiro frame do vídeo via ffmpeg."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return False
    cmd = [
        ffmpeg, "-y", "-v", "quiet",
        "-i", video_path,
        "-frames:v", "1",
        "-f", "image2",
        "-update", "1",
        output_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    return result.returncode == 0 and os.path.isfile(output_path)


def _get_duration(video_path: str) -> float:
    """Retorna a duração do vídeo em segundos via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0.0
    cmd = [ffprobe, "-v", "quiet", "-print_format", "json", "-show_format", video_path]
    try:
        result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
        data = json.loads(result.stdout)
        return float(data.get("format", {}).get("duration", 0))
    except Exception:
        return 0.0


def _extract_frames_window(video_path: str, out_dir: str, max_seconds: float = 3.0,
                           n_frames: int = 5) -> list:
    """Extrai n_frames espaçados uniformemente nos primeiros max_seconds do
    vídeo (ou na duração toda, se ela for menor). Retorna lista de paths."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []

    duration = _get_duration(video_path)
    window = min(max_seconds, duration) if duration else max_seconds
    if window <= 0:
        window = max_seconds
    fps = n_frames / window

    pattern = os.path.join(out_dir, "frame_%02d.png")
    cmd = [
        ffmpeg, "-y", "-v", "quiet",
        "-i", video_path,
        "-t", f"{window:.3f}",
        "-vf", f"fps={fps:.4f}",
        "-frames:v", str(n_frames),
        pattern,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception:
        return []

    return sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir)
        if f.startswith("frame_") and f.endswith(".png")
    )


def _extract_frames_mid(video_path: str, out_dir: str, duration: float,
                        n_frames: int = 5) -> list:
    """Extrai n_frames do trecho 25%-75% da duração (janela de fallback)."""
    ffmpeg = shutil.which("ffmpeg")
    if not ffmpeg:
        return []
    start = duration * 0.25
    window = duration * 0.5
    fps = n_frames / window
    pattern = os.path.join(out_dir, "mid_%02d.png")
    cmd = [
        ffmpeg, "-y", "-v", "quiet",
        "-ss", f"{start:.3f}",
        "-i", video_path,
        "-t", f"{window:.3f}",
        "-vf", f"fps={fps:.4f}",
        "-frames:v", str(n_frames),
        pattern,
    ]
    try:
        subprocess.run(cmd, capture_output=True, text=True, timeout=30)
    except Exception:
        return []
    return sorted(
        os.path.join(out_dir, f) for f in os.listdir(out_dir)
        if f.startswith("mid_") and f.endswith(".png")
    )


_CASCADES = None


def _get_cascades():
    """Carrega os classificadores Haar uma vez só (cache no módulo).
    frontal_default + profileface: o frontal sozinho falha em cabeça baixa /
    boné / perfil 3-4 (caso real: John Cena de boné olhando pra baixo —
    0 detecções em 5 frames; o profile pegou 5/5)."""
    global _CASCADES
    if _CASCADES is not None:
        return _CASCADES
    try:
        import cv2
        loaded = []
        for xml in ("haarcascade_frontalface_default.xml",
                    "haarcascade_profileface.xml"):
            path = os.path.join(cv2.data.haarcascades, xml)
            if os.path.isfile(path):
                c = cv2.CascadeClassifier(path)
                if not c.empty():
                    loaded.append(c)
        _CASCADES = loaded or None
    except ImportError:
        _CASCADES = None
    return _CASCADES


_YUNET = None
_YUNET_PATH = os.path.normpath(os.path.join(
    os.path.dirname(os.path.abspath(__file__)),
    "..", "assets", "models", "face_detection_yunet_2023mar.onnx"))


def _get_yunet():
    """Detector neural YuNet (OpenCV FaceDetectorYN). Muito mais robusto que
    Haar pra cabeça baixa/boné/perfil — o Haar de perfil gerava falsos
    positivos gigantes (mão/microfone) que dominavam a média por área."""
    global _YUNET
    if _YUNET is not None:
        return _YUNET or None
    try:
        import cv2
        if os.path.isfile(_YUNET_PATH) and hasattr(cv2, "FaceDetectorYN"):
            _YUNET = cv2.FaceDetectorYN.create(
                _YUNET_PATH, "", (320, 320), score_threshold=0.6)
        else:
            _YUNET = False
    except Exception:
        _YUNET = False
    return _YUNET or None


def _detect_face_center_from_frames(frame_paths: list) -> Optional[Tuple[int, int]]:
    """Detecta rostos nos frames e retorna o centro médio ponderado por
    área × confiança (rosto maior + detecção mais confiante = personagem
    principal) — combinado entre frames pra suavizar outliers.

    Primário: YuNet (neural). Fallback: Haar frontal, se o modelo onnx
    não estiver disponível."""
    if not frame_paths:
        return None
    try:
        import cv2
    except ImportError:
        return None

    weighted_x = 0.0
    weighted_y = 0.0
    total_weight = 0.0

    yunet = _get_yunet()
    if yunet is not None:
        for fp in frame_paths:
            img = cv2.imread(fp)
            if img is None:
                continue
            h, w = img.shape[:2]
            yunet.setInputSize((w, h))
            _, faces = yunet.detect(img)
            if faces is None:
                continue
            for f in faces:
                x, y, fw, fh = f[:4]
                conf = float(f[14])
                weight = float(fw * fh) * conf
                weighted_x += (x + fw / 2) * weight
                weighted_y += (y + fh / 2) * weight
                total_weight += weight
    else:
        cascades = _get_cascades()
        if not cascades:
            return None
        for fp in frame_paths:
            img = cv2.imread(fp)
            if img is None:
                continue
            gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            for cascade in cascades:
                for (x, y, w, h) in cascade.detectMultiScale(
                        gray, scaleFactor=1.1, minNeighbors=5, minSize=(40, 40)):
                    area = float(w * h)
                    weighted_x += (x + w / 2) * area
                    weighted_y += (y + h / 2) * area
                    total_weight += area

    if total_weight <= 0:
        return None
    return int(weighted_x / total_weight), int(weighted_y / total_weight)


def _get_video_dimensions(video_path: str) -> Tuple[int, int]:
    """Retorna (width, height) do vídeo via ffprobe."""
    ffprobe = shutil.which("ffprobe")
    if not ffprobe:
        return 0, 0
    cmd = [
        ffprobe, "-v", "quiet", "-print_format", "json",
        "-select_streams", "v:0",
        "-show_streams", video_path,
    ]
    result = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    if result.returncode != 0:
        return 0, 0
    try:
        data = json.loads(result.stdout)
        stream = data["streams"][0]
        return int(stream["width"]), int(stream["height"])
    except (KeyError, IndexError, ValueError):
        return 0, 0


def find_best_crop_center(video_path: str) -> Tuple[int, int]:
    """Retorna o melhor centro de corte (x, y).

    1) Detecção de rosto nos primeiros ~3s (múltiplos frames) — pega o
       personagem principal mesmo que ele se mova no início do clipe.
    2) Fallback: densidade de bordas em grade 3x3 no primeiro frame.
    3) Fallback final: centro geométrico.
    """
    w, h = _get_video_dimensions(video_path)
    if not w or not h:
        return 0, 0

    # 1) Tentar detecção de rosto nos primeiros ~3s; se nada, tentar uma
    # segunda janela no meio do vídeo (o personagem pode aparecer depois
    # de uma intro/b-roll — o crop é estático, qualquer posição confiável
    # de rosto é melhor que a heurística de bordas)
    face_tmp_dir = tempfile.mkdtemp(prefix="facecrop_")
    try:
        frames = _extract_frames_window(video_path, face_tmp_dir, max_seconds=3.0, n_frames=5)
        face_center = _detect_face_center_from_frames(frames)
        janela = "0-3s"
        if not face_center:
            duration = _get_duration(video_path)
            if duration > 6:
                mid_dir = os.path.join(face_tmp_dir, "mid")
                os.makedirs(mid_dir, exist_ok=True)
                frames_mid = _extract_frames_mid(video_path, mid_dir, duration)
                face_center = _detect_face_center_from_frames(frames_mid)
                janela = "meio do vídeo"
        if face_center:
            cx, cy = face_center
            cx = max(w // 6, min(cx, w - w // 6))
            cy = max(h // 6, min(cy, h - h // 6))
            print(f"  [smart_crop] rosto detectado ({janela}), centro=({cx},{cy})", file=sys.stderr)
            return cx, cy
    finally:
        shutil.rmtree(face_tmp_dir, ignore_errors=True)

    # 2) Fallback: densidade de bordas no primeiro frame
    with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tf:
        frame_path = tf.name

    try:
        if not _extract_first_frame(video_path, frame_path):
            return w // 2, h // 2

        from PIL import Image, ImageFilter, ImageStat

        img = Image.open(frame_path).convert("L")  # grayscale
        edges = img.filter(ImageFilter.FIND_EDGES)

        # Dividir em grade 3x3
        grid_w = w // 3
        grid_h = h // 3

        best_score = -1
        best_cell = (1, 1)  # centro por padrão

        for row in range(3):
            for col in range(3):
                x1 = col * grid_w
                y1 = row * grid_h
                x2 = x1 + grid_w
                y2 = y1 + grid_h
                cell = edges.crop((x1, y1, x2, y2))
                stat = ImageStat.Stat(cell)
                score = stat.mean[0]  # densidade média de bordas

                # BIAS: penalizar cantos para preferir centro
                # Distância Manhattan do centro da grade (1,1)
                dist = abs(col - 1) + abs(row - 1)
                # Reduzir score proporcional à distância do centro
                score *= (1.0 - 0.15 * dist)

                if score > best_score:
                    best_score = score
                    best_cell = (col, row)

        # Converter célula de volta para coordenadas centrais
        cx = best_cell[0] * grid_w + grid_w // 2
        cy = best_cell[1] * grid_h + grid_h // 2

        # Clamp para não sair dos limites
        cx = max(w // 6, min(cx, w - w // 6))
        cy = max(h // 6, min(cy, h - h // 6))

        print(f"  [smart_crop] sem rosto, saliência visual, centro=({cx},{cy})", file=sys.stderr)
        return cx, cy

    except ImportError:
        return w // 2, h // 2
    except Exception:
        return w // 2, h // 2
    finally:
        if os.path.isfile(frame_path):
            os.remove(frame_path)


def find_best_crop_region(video_path: str, target_aspect: float = 1.0) -> dict:
    """Retorna o melhor crop box para o aspecto desejado.
    Returns: {"x": int, "y": int, "width": int, "height": int}
    """
    w, h = _get_video_dimensions(video_path)
    if not w or not h:
        return {"x": 0, "y": 0, "width": 0, "height": 0}

    cx, cy = find_best_crop_center(video_path)

    current_aspect = w / h

    if current_aspect > target_aspect:
        # Mais largo que target → cortar laterais
        crop_w = int(h * target_aspect)
        crop_h = h
    else:
        # Mais alto que target → cortar topo/base
        crop_w = w
        crop_h = int(w / target_aspect)

    # Ajustar centro para não sair dos limites
    x = max(0, min(cx - crop_w // 2, w - crop_w))
    y = max(0, min(cy - crop_h // 2, h - crop_h))

    return {"x": x, "y": y, "width": crop_w, "height": crop_h}


def main():
    parser = argparse.ArgumentParser(description="Smart Crop — encontra o melhor ponto de corte")
    parser.add_argument("--video", required=True, help="Caminho do vídeo")
    parser.add_argument("--aspect", type=float, default=1.0, help="Aspecto alvo (1.0 = quadrado)")
    parser.add_argument("--json", action="store_true", help="Saída JSON")
    args = parser.parse_args()

    if args.json:
        center = find_best_crop_center(args.video)
        region = find_best_crop_region(args.video, args.aspect)
        print(json.dumps({
            "video": args.video,
            "best_center": {"x": center[0], "y": center[1]},
            "crop_region": region,
        }, indent=2))
    else:
        center = find_best_crop_center(args.video)
        region = find_best_crop_region(args.video, args.aspect)
        print(f"Vídeo: {args.video}")
        print(f"Melhor centro: ({center[0]}, {center[1]})")
        print(f"Região de corte: x={region['x']} y={region['y']} "
              f"w={region['width']} h={region['height']}")


if __name__ == "__main__":
    main()
