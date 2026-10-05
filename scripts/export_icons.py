"""Render the geometric SVG to a transparent PNG and six-size Windows icon."""
from __future__ import annotations

import os
from pathlib import Path

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
from PIL import Image
from PySide6.QtCore import QRectF
from PySide6.QtGui import QGuiApplication, QImage, QPainter
from PySide6.QtSvg import QSvgRenderer


def main() -> None:
    """Export resolution-independent source art into Windows bitmap assets."""
    app = QGuiApplication.instance() or QGuiApplication([])
    assets = Path(__file__).resolve().parents[1] / "assets"
    renderer = QSvgRenderer(str(assets / "logo.svg"))
    if not renderer.isValid():
        raise RuntimeError("assets/logo.svg is not a valid SVG")
    bitmap = QImage(512, 512, QImage.Format.Format_ARGB32)
    bitmap.fill(0)
    painter = QPainter(bitmap)
    renderer.render(painter, QRectF(0, 0, 512, 512))
    painter.end()
    output = assets / "logo.png"
    if not bitmap.save(str(output)):
        raise OSError(f"Cannot write {output}")
    with Image.open(output) as image:
        image.save(assets / "logo.ico", format="ICO", sizes=[(n, n) for n in (16, 32, 48, 64, 128, 256)])
    print("Created assets/logo.png and assets/logo.ico (16, 32, 48, 64, 128, 256 px)")
    del app


if __name__ == "__main__":
    main()
