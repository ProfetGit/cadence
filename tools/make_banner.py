"""Renders docs/banner.webp: a seamless 3 s loop at 60 fps (frame durations 17/17/16 ms = 50 ms per 3 frames).

Run: QT_QPA_PLATFORM=offscreen python3 tools/make_banner.py docs/banner.webp
"""
import math
import os
import sys

from PIL import Image
from PyQt6.QtCore import QByteArray, QPointF, QRectF, Qt
from PyQt6.QtGui import QBrush, QColor, QFont, QGuiApplication, QImage, QLinearGradient, QPainter, QPen, QRadialGradient
from PyQt6.QtSvg import QSvgRenderer

W, H = 960, 240
FPS, SECONDS = 60, 3
N = FPS * SECONDS
HERE = os.path.dirname(os.path.abspath(__file__))
ICON = os.path.join(HERE, "..", "data", "cadence.svg")
TAU = 2 * math.pi


def ease(x):
    x = max(0.0, min(1.0, x))
    return x * x * (3 - 2 * x)


def blobs(p, ph):
    spec = [
        (QColor(124, 92, 255), 0.22, 0.30, 1, 0.0, 330),
        (QColor(255, 106, 136), 0.78, 0.65, 1, 2.1, 300),
        (QColor(79, 163, 255), 0.55, 0.20, 2, 4.0, 260),
    ]
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_Plus)
    for col, fx, fy, k, off, r in spec:
        cx = W * fx + math.sin(ph * k + off) * 90
        cy = H * fy + math.cos(ph * k * 1.0 + off) * 40
        g = QRadialGradient(QPointF(cx, cy), r)
        c0 = QColor(col)
        c0.setAlpha(88)
        c1 = QColor(col)
        c1.setAlpha(0)
        g.setColorAt(0, c0)
        g.setColorAt(1, c1)
        p.fillRect(0, 0, W, H, g)
    p.setCompositionMode(QPainter.CompositionMode.CompositionMode_SourceOver)


def bars(p, t):
    n, x0, bw, gap = 26, W - 372, 9.0, 5.0
    base = H * 0.62
    for i in range(n):
        v = 0.0
        for k, (f, a) in enumerate(((1, 0.5), (2, 0.3), (3, 0.2))):
            v += a * math.sin(TAU * (f * t / SECONDS) + i * 0.55 * (k + 1) + k)
        h = 22 + 52 * (0.5 + 0.5 * v) * (0.55 + 0.45 * math.sin(i / n * math.pi))
        x = x0 + i * (bw + gap)
        g = QLinearGradient(0, base - h, 0, base + h * 0.35)
        g.setColorAt(0, QColor(255, 255, 255, 235))
        g.setColorAt(1, QColor(255, 255, 255, 40))
        p.setPen(Qt.PenStyle.NoPen)
        p.setBrush(QBrush(g))
        p.drawRoundedRect(QRectF(x, base - h, bw, h * 1.35), 4.5, 4.5)


def frame(i, icon):
    t = i / FPS
    ph = TAU * t / SECONDS
    img = QImage(W, H, QImage.Format.Format_RGBA8888)
    img.fill(QColor(13, 13, 18))
    p = QPainter(img)
    p.setRenderHints(QPainter.RenderHint.Antialiasing | QPainter.RenderHint.TextAntialiasing
                     | QPainter.RenderHint.SmoothPixmapTransform)
    blobs(p, ph)
    v = QLinearGradient(0, 0, 0, H)
    v.setColorAt(0, QColor(0, 0, 0, 40))
    v.setColorAt(1, QColor(0, 0, 0, 120))
    p.fillRect(0, 0, W, H, v)

    bob = math.sin(ph) * 4
    icon.render(p, QRectF(54, 48 + bob, 144, 144))

    cyc = t / SECONDS
    prog = ease(cyc / 0.62)
    fade = 1.0 if cyc < 0.82 else max(0.0, 1.0 - (cyc - 0.82) / 0.18)
    f = QFont("Noto Sans")
    f.setPixelSize(74)
    f.setWeight(QFont.Weight.Black)
    f.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, -1.5)
    p.setFont(f)
    tx, ty = 232, 118
    wtxt = p.fontMetrics().horizontalAdvance("Cadence")
    p.setPen(QColor(255, 255, 255, 70))
    p.drawText(QPointF(tx, ty), "Cadence")
    edge = tx + prog * (wtxt + 40) - 20
    g = QLinearGradient(edge - 34, 0, edge + 10, 0)
    g.setColorAt(0, QColor(255, 255, 255, int(255 * fade)))
    g.setColorAt(1, QColor(255, 255, 255, 0))
    glow = QColor(168, 140, 255, int(60 * fade))
    p.setPen(glow)
    for dx, dy in ((-2, 0), (2, 0), (0, -2), (0, 2)):
        p.save()
        p.setClipRect(QRectF(0, 0, edge, H))
        p.drawText(QPointF(tx + dx, ty + dy), "Cadence")
        p.restore()
    p.setPen(QPen(QBrush(g), 1))
    p.drawText(QPointF(tx, ty), "Cadence")

    f2 = QFont("Noto Sans")
    f2.setPixelSize(21)
    f2.setWeight(QFont.Weight.Medium)
    p.setFont(f2)
    p.setPen(QColor(255, 255, 255, 170))
    p.drawText(QPointF(tx + 3, ty + 40), "YouTube Music, native on Linux.")
    f3 = QFont("Noto Sans")
    f3.setPixelSize(14)
    f3.setWeight(QFont.Weight.DemiBold)
    f3.setLetterSpacing(QFont.SpacingType.AbsoluteSpacing, 1.4)
    p.setFont(f3)
    p.setPen(QColor(255, 255, 255, 95))
    p.drawText(QPointF(tx + 3, ty + 74), "MPRIS   ·   SYNCED LYRICS   ·   MINI PLAYER   ·   PLASMA WIDGET")
    bars(p, t)
    p.end()
    return img


def main():
    out = sys.argv[1] if len(sys.argv) > 1 else "banner.webp"
    app = QGuiApplication(["banner"])  # noqa: F841
    icon = QSvgRenderer(QByteArray(open(ICON, "rb").read()))
    frames = []
    for i in range(N):
        q = frame(i, icon)
        frames.append(Image.frombuffer("RGBA", (W, H), bytes(q.constBits().asarray(W * H * 4)), "raw", "RGBA", 0, 1).convert("RGB"))
    durations = [17, 17, 16] * (N // 3)
    frames[0].save(out, "WEBP", save_all=True, append_images=frames[1:], duration=durations, loop=0,
                   quality=72, method=4, minimize_size=False)
    print("wrote", out, os.path.getsize(out) // 1024, "KiB,", N, "frames, total", sum(durations), "ms")


if __name__ == "__main__":
    main()
