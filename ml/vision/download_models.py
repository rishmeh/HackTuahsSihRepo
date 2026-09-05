"""
vision/download_models.py — Fetch the pretrained ONNX models from OpenCV Zoo.

Run once per machine:

    python -m vision.download_models

Two models, both pretrained, both CPU-only:

  YuNet  (~340 KB)  detects faces and their five landmarks
  SFace  (~37 MB)   turns an aligned face crop into a 128-d embedding

Nothing here trains anything. Face recognition is a solved problem with
published weights; training your own would need millions of labelled faces,
a GPU cluster, and would end up worse than these.
"""

from __future__ import annotations

import sys
import urllib.request
from pathlib import Path

# GitHub serves LFS-tracked files as small pointer stubs from raw.githubusercontent;
# media.githubusercontent.com/media/... returns the real binary.
_ZOO = "https://media.githubusercontent.com/media/opencv/opencv_zoo/main/models"

MODELS: dict[str, str] = {
    "face_detection_yunet_2023mar.onnx": (
        f"{_ZOO}/face_detection_yunet/face_detection_yunet_2023mar.onnx"
    ),
    "face_recognition_sface_2021dec.onnx": (
        f"{_ZOO}/face_recognition_sface/face_recognition_sface_2021dec.onnx"
    ),
}

# An ONNX file always starts with these bytes. Git LFS pointers and GitHub
# error pages do not — checking catches a "download" that saved a text file.
_ONNX_MAGIC = b"\x08"


def download(models_dir: Path) -> None:
    models_dir.mkdir(parents=True, exist_ok=True)

    for filename, url in MODELS.items():
        target = models_dir / filename
        if target.exists() and target.stat().st_size > 1024:
            print(f"[skip] {filename} already present ({target.stat().st_size:,} bytes)")
            continue

        print(f"[get ] {filename} <- {url}")
        urllib.request.urlretrieve(url, target)

        size = target.stat().st_size
        head = target.read_bytes()[:1]
        if size < 1024 or head != _ONNX_MAGIC:
            target.unlink(missing_ok=True)
            raise RuntimeError(
                f"{filename} did not download as a real ONNX file "
                f"({size} bytes). Download it by hand from {url}"
            )
        print(f"[ok  ] {filename} ({size:,} bytes)")


if __name__ == "__main__":
    target_dir = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).parent.parent / "models"
    download(target_dir)
    print(f"\nModels ready in {target_dir.resolve()}")
