"""Render assets/audy.ico from the painted mark. Run before building."""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtCore import QBuffer, QIODevice
from PySide6.QtWidgets import QApplication

from audy import icons

SIZES = (16, 20, 24, 32, 40, 48, 64, 128, 256)


def main():
    app = QApplication([])  # noqa: F841 (needed for QPixmap)
    out = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "assets", "audy.ico")
    os.makedirs(os.path.dirname(out), exist_ok=True)

    from PIL import Image
    import io

    images = []
    for size in SIZES:
        buf = QBuffer()
        buf.open(QIODevice.OpenModeFlag.WriteOnly)
        icons.app_pixmap(size).save(buf, "PNG")
        images.append(Image.open(io.BytesIO(bytes(buf.data()))).convert("RGBA"))
    images[-1].save(out, format="ICO", sizes=[(s, s) for s in SIZES], append_images=images[:-1])
    print("wrote", out)


if __name__ == "__main__":
    main()
