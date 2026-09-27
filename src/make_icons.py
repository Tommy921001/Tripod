"""
홈 화면 아이콘 생성 — 삼각대(트라이팟) 마크.
한 번만 돌리면 되고, 결과 PNG 는 리포지토리에 커밋한다.
  python3 src/make_icons.py
"""
import math
import os

from PIL import Image, ImageDraw

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
DOCS = os.path.join(ROOT, "docs")

INK = (17, 27, 30)
TEAL = (13, 106, 96)
CREAM = (242, 245, 244)


def draw(size, pad_ratio, bg, legs, hub):
    S = size * 4  # 4배로 그린 뒤 축소해서 안티에일리어싱
    im = Image.new("RGB", (S, S), bg)
    d = ImageDraw.Draw(im)
    cx, cy = S / 2, S * 0.44
    r = S * (0.5 - pad_ratio)
    w = max(2, int(S * 0.052))

    # 세 다리 — 위 꼭짓점 하나, 아래 둘 (삼각대)
    apex = (cx, cy - r * 0.62)
    for ang in (90 + 55, 90 - 55):
        a = math.radians(ang)
        end = (cx + r * math.cos(a) * 1.05, cy + r * math.sin(a) * 1.05)
        d.line([apex, end], fill=legs, width=w)
    d.line([apex, (cx, cy + r * 1.05)], fill=legs, width=w)

    # 상판(플랫폼)
    ph = S * 0.055
    d.rounded_rectangle([cx - r * 0.72, apex[1] - ph * 1.9,
                         cx + r * 0.72, apex[1] - ph * 0.3],
                        radius=ph * 0.5, fill=hub)
    return im.resize((size, size), Image.LANCZOS)


def main():
    os.makedirs(DOCS, exist_ok=True)
    specs = [
        ("icon-192.png", 192, 0.12, CREAM, INK, TEAL),
        ("icon-512.png", 512, 0.12, CREAM, INK, TEAL),
        ("icon-512-maskable.png", 512, 0.24, TEAL, CREAM, CREAM),
        ("apple-touch-icon.png", 180, 0.14, CREAM, INK, TEAL),
    ]
    for name, size, pad, bg, legs, hub in specs:
        img = draw(size, pad, bg, legs, hub)
        img.save(os.path.join(DOCS, name), optimize=True)
        print(f"{name}  {size}x{size}  {os.path.getsize(os.path.join(DOCS, name))}B")


if __name__ == "__main__":
    main()
