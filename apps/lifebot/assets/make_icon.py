"""Generate the Lifebot icon (icon.png + multi-size icon.ico). Run: python make_icon.py"""
from pathlib import Path

from PIL import Image, ImageDraw

HERE = Path(__file__).parent
S = 1024  # draw large, then downsample for smooth edges


def gradient(size: int) -> Image.Image:
    top, bottom = (169, 226, 61), (57, 125, 34)
    img = Image.new("RGB", (size, size))
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        row = tuple(round(top[i] + (bottom[i] - top[i]) * t) for i in range(3))
        for x in range(size):
            px[x, y] = row
    return img


def build() -> Image.Image:
    bg = gradient(S).convert("RGBA")
    mask = Image.new("L", (S, S), 0)
    ImageDraw.Draw(mask).rounded_rectangle((0, 0, S - 1, S - 1), radius=int(S * 0.23), fill=255)
    icon = Image.new("RGBA", (S, S), (0, 0, 0, 0))
    icon.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(icon)
    white = (255, 255, 255, 255)
    # chat bubble: rounded body + tail
    d.rounded_rectangle((200, 230, 824, 700), radius=150, fill=white)
    d.polygon([(330, 680), (330, 840), (520, 690)], fill=white)
    # checkmark inside the bubble
    check = (193, 68, 60, 255)
    d.line([(335, 470), (450, 585), (700, 340)], fill=check, width=70, joint="curve")
    for x, y in ((335, 470), (450, 585), (700, 340)):
        d.ellipse((x - 35, y - 35, x + 35, y + 35), fill=check)
    return icon


def main() -> None:
    icon = build()
    icon.resize((256, 256), Image.LANCZOS).save(HERE / "icon.png")
    sizes = [(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)]
    icon.resize((256, 256), Image.LANCZOS).save(HERE / "icon.ico", format="ICO", sizes=sizes)
    print("wrote icon.png and icon.ico")


if __name__ == "__main__":
    main()
