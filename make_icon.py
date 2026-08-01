"""
앱 아이콘 생성기 — icon.png (512) + icon.ico (Windows, 멀티사이즈)
+ icon.icns (macOS) 를 만듭니다.

디자인: YouTube 레드 라운드 스퀘어 배경 + 흰색 다운로드 화살표(아래 방향, 플레이 느낌의
뾰족한 촉) + 착지 트레이. "유튜브 영상을 내려받는다" 가 한눈에 읽히도록.

사용:
    pip install pillow
    python make_icon.py

.icns 는 macOS 의 iconutil 이 있으면 그걸로(가장 깨끗), 없으면 Pillow 로 저장합니다.
"""
import os
import shutil
import subprocess
import tempfile
from PIL import Image, ImageDraw

SS = 4  # 슈퍼샘플링 배수 (렌더 후 축소하여 안티에일리어싱)
BASE = 512
S = BASE * SS

RED_TOP = (255, 62, 62)
RED_BOT = (214, 26, 26)
WHITE = (255, 255, 255)


def rounded_mask(size, radius):
    m = Image.new('L', (size, size), 0)
    d = ImageDraw.Draw(m)
    d.rounded_rectangle([0, 0, size - 1, size - 1], radius=radius, fill=255)
    return m


def vertical_gradient(size, top, bottom):
    grad = Image.new('RGB', (1, size))
    for y in range(size):
        t = y / (size - 1)
        grad.putpixel((0, y), tuple(int(top[i] + (bottom[i] - top[i]) * t) for i in range(3)))
    return grad.resize((size, size))


def make(size):
    S = size * SS
    # 배경: 세로 그라디언트 + 라운드 마스크
    bg = vertical_gradient(S, RED_TOP, RED_BOT).convert('RGBA')
    mask = rounded_mask(S, radius=int(S * 0.235))
    img = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    img.paste(bg, (0, 0), mask)

    d = ImageDraw.Draw(img)
    cx = S / 2

    # 상단 은은한 하이라이트
    hi = Image.new('RGBA', (S, S), (0, 0, 0, 0))
    hd = ImageDraw.Draw(hi)
    hd.ellipse([S * 0.05, -S * 0.55, S * 0.95, S * 0.45], fill=(255, 255, 255, 38))
    img = Image.alpha_composite(img, Image.composite(hi, Image.new('RGBA', (S, S), (0, 0, 0, 0)), mask))
    d = ImageDraw.Draw(img)

    # 다운로드 화살표 (샤프트)
    shaft_w = S * 0.14
    shaft_top = S * 0.24
    shaft_bot = S * 0.52
    d.rounded_rectangle(
        [cx - shaft_w / 2, shaft_top, cx + shaft_w / 2, shaft_bot],
        radius=shaft_w / 2, fill=WHITE,
    )
    # 화살촉 (플레이 삼각형을 아래로 향하게 한 느낌)
    head_w = S * 0.34
    head_top = S * 0.46
    head_tip = S * 0.70
    d.polygon(
        [(cx - head_w / 2, head_top), (cx + head_w / 2, head_top), (cx, head_tip)],
        fill=WHITE,
    )
    # 착지 트레이 (다운로드 받침)
    tray_w = S * 0.40
    tray_h = S * 0.075
    tray_y = S * 0.76
    d.rounded_rectangle(
        [cx - tray_w / 2, tray_y, cx + tray_w / 2, tray_y + tray_h],
        radius=tray_h / 2, fill=WHITE,
    )

    return img.resize((size, size), Image.LANCZOS)


def make_icns(master):
    """macOS .icns 생성. iconutil 이 있으면 .iconset → icns, 없으면 Pillow."""
    # Apple 표준 iconset (사이즈, 파일명)
    spec = [
        (16, 'icon_16x16.png'), (32, 'icon_16x16@2x.png'),
        (32, 'icon_32x32.png'), (64, 'icon_32x32@2x.png'),
        (128, 'icon_128x128.png'), (256, 'icon_128x128@2x.png'),
        (256, 'icon_256x256.png'), (512, 'icon_256x256@2x.png'),
        (512, 'icon_512x512.png'), (1024, 'icon_512x512@2x.png'),
    ]
    if shutil.which('iconutil'):
        with tempfile.TemporaryDirectory() as tmp:
            iconset = os.path.join(tmp, 'icon.iconset')
            os.makedirs(iconset)
            for size, name in spec:
                master.resize((size, size), Image.LANCZOS).save(os.path.join(iconset, name))
            subprocess.run(['iconutil', '-c', 'icns', iconset, '-o', 'icon.icns'], check=True)
        print('wrote icon.icns (iconutil)')
    else:
        sizes = [16, 32, 64, 128, 256, 512, 1024]
        master.save('icon.icns', format='ICNS',
                    append_images=[master.resize((s, s), Image.LANCZOS) for s in sizes])
        print('wrote icon.icns (Pillow)')


def main():
    make(BASE).save('icon.png')
    print('wrote icon.png (512x512)')

    sizes = [16, 24, 32, 48, 64, 128, 256]
    # 가장 큰 이미지에서 각 사이즈로 저장 (Pillow 가 요청 사이즈별 엔트리를 생성)
    make(256).save('icon.ico', format='ICO', sizes=[(s, s) for s in sizes])
    print('wrote icon.ico', sizes)

    # macOS 용 고해상도 마스터(1024)에서 icns 생성
    make_icns(make(1024))


if __name__ == '__main__':
    main()
