"""程序化生成应用图标（军事题材：钢盔 + 红星 + 硝烟底）。

输出 icon.png (1024x1024)，再用系统 iconutil 转 .icns。
纯标准库 + 手写 PNG 编码，无第三方依赖。
"""
import math, struct, zlib, os

S = 1024
img = bytearray(S * S * 4)   # 全透明起始（alpha=0）


def px(x, y, c, a=255):
    if 0 <= x < S and 0 <= y < S:
        i = (y * S + x) * 4
        # 背景：直接覆盖
        # alpha 混合
        if a >= 255:
            img[i] = c[0]; img[i+1] = c[1]; img[i+2] = c[2]; img[i+3] = 255
        else:
            sa = a / 255.0
            da = img[i+3] / 255.0
            oa = sa + da * (1 - sa)
            if oa <= 0:
                return
            img[i]   = int((c[0]*sa + img[i]  *da*(1-sa)) / oa)
            img[i+1] = int((c[1]*sa + img[i+1]*da*(1-sa)) / oa)
            img[i+2] = int((c[2]*sa + img[i+2]*da*(1-sa)) / oa)
            img[i+3] = int(oa * 255)


def rrect(x0, y0, x1, y1, r, c, a=255):
    for y in range(int(y0), int(y1) + 1):
        for x in range(int(x0), int(x1) + 1):
            dx = max(x0 + r - x, 0, x - (x1 - r))
            dy = max(y0 + r - y, 0, y - (y1 - r))
            if dx * dx + dy * dy <= r * r:
                px(x, y, c, a)


def circle(cx, cy, r, c, a=255):
    for y in range(int(cy - r), int(cy + r) + 1):
        for x in range(int(cx - r), int(cx + r) + 1):
            if (x - cx) ** 2 + (y - cy) ** 2 <= r * r:
                px(x, y, c, a)


def ellipse(cx, cy, rx, ry, c, a=255):
    for y in range(int(cy - ry), int(cy + ry) + 1):
        for x in range(int(cx - rx), int(cx + rx) + 1):
            if rx > 0 and ry > 0 and ((x-cx)/rx)**2 + ((y-cy)/ry)**2 <= 1:
                px(x, y, c, a)


def vgrad(x0, y0, x1, y1, c0, c1):
    h = max(1, y1 - y0)
    for y in range(int(y0), int(y1) + 1):
        t = (y - y0) / h
        c = (int(c0[0] + (c1[0]-c0[0])*t),
             int(c0[1] + (c1[1]-c0[1])*t),
             int(c0[2] + (c1[2]-c0[2])*t))
        for x in range(int(x0), int(x1) + 1):
            px(x, y, c)


def star(cx, cy, r_out, r_in, c, rot=-math.pi/2, points=5):
    pts = []
    for i in range(points * 2):
        ang = rot + i * math.pi / points
        r = r_out if i % 2 == 0 else r_in
        pts.append((cx + r*math.cos(ang), cy + r*math.sin(ang)))
    ys = [p[1] for p in pts]
    for y in range(int(min(ys)), int(max(ys)) + 1):
        xs = []
        n = len(pts)
        for i in range(n):
            ax, ay = pts[i]; bx, by = pts[(i+1) % n]
            if (ay <= y < by) or (by <= y < ay):
                t = (y - ay) / (by - ay) if by != ay else 0
                xs.append(ax + t*(bx-ax))
        xs.sort()
        for i in range(0, len(xs)-1, 2):
            for x in range(int(xs[i]), int(xs[i+1])+1):
                px(x, y, c)


# ---------- 绘制 ----------
BG_DEEP = (18, 16, 13)
PANEL   = (36, 32, 26)
GOLD    = (201, 162, 39)
GOLD_HI = (240, 205, 96)
STEEL   = (90, 100, 112)
STEEL_D = (58, 64, 72)
RED     = (168, 50, 45)
EMBER   = (181, 101, 29)

# 圆角底（macOS 风格圆角）
R = int(S * 0.22)
rrect(0, 0, S-1, S-1, R, BG_DEEP)
# 硝烟渐变底
for y in range(int(S*0.10), int(S*0.92)):
    t = (y - S*0.10) / (S*0.82)
    c = (int(BG_DEEP[0] + (EMBER[0]-BG_DEEP[0])*t*0.22),
         int(BG_DEEP[1] + (EMBER[1]-BG_DEEP[1])*t*0.22),
         int(BG_DEEP[2] + (EMBER[2]-BG_DEEP[2])*t*0.22))
    for x in range(int(S*0.04), int(S*0.96)):
        dx = max(R - x, 0, x - (S-1-R))
        dy = max(R - y, 0, y - (S-1-R))
        if dx*dx + dy*dy <= R*R:
            px(x, y, c)

# 金色外框
for w in range(8):
    rr = R - w
    for y in range(S):
        for x in range(S):
            dx = max(R - x, 0, x - (S-1-R))
            dy = max(R - y, 0, y - (S-1-R))
            d = dx*dx + dy*dy
            if (rr-1)**2 < d <= rr*rr:
                px(x, y, GOLD if w < 5 else GOLD_HI)

# 钢盔（军事语汇）
helm_cy = int(S * 0.46)
helm_r  = int(S * 0.235)
# 盔体（半圆）
for y in range(helm_cy - helm_r, helm_cy + int(helm_r*0.18)):
    for x in range(S//2 - helm_r, S//2 + helm_r + 1):
        if (x - S//2)**2 + (y - helm_cy)**2 <= helm_r*helm_r:
            t = (y - (helm_cy - helm_r)) / (helm_r * 1.18)
            c = (int(STEEL_D[0] + (STEEL[0]-STEEL_D[0])*t),
                 int(STEEL_D[1] + (STEEL[1]-STEEL_D[1])*t),
                 int(STEEL_D[2] + (STEEL[2]-STEEL_D[2])*t))
            px(x, y, c)
# 盔沿
ellipse(S//2, helm_cy + int(helm_r*0.16), helm_r*1.12, helm_r*0.17, STEEL_D)
ellipse(S//2, helm_cy + int(helm_r*0.13), helm_r*1.08, helm_r*0.13, STEEL)
# 盔体柔和高光（沿盔顶弧线，不画斜线，避免出现白刺）
for i in range(int(helm_r * 0.75)):
    t = i / max(1, helm_r * 0.75)
    a = int(90 * (1 - t) ** 2)
    x = S // 2 - int(helm_r * 0.45) + int(i * 0.55)
    y = helm_cy - int(helm_r * 0.58) + int(i * 0.30)
    if a > 3:
        px(x, y, (200, 215, 230), a)
        px(x + 1, y, (200, 215, 230), a // 2)

# 红星（帽徽）
star(S//2, helm_cy - int(helm_r*0.10), int(helm_r*0.40), int(helm_r*0.17), RED)

# 下方金色横条 + 三条军衔杠
bar_y = int(S * 0.755)
rrect(int(S*0.30), bar_y, int(S*0.70), bar_y + int(S*0.020), 8, GOLD)
for i in range(3):
    yy = bar_y + int(S*0.048) + i * int(S*0.030)
    rrect(int(S*0.395), yy, int(S*0.605), yy + int(S*0.014), 6, GOLD_HI)

# ---------- 写 PNG ----------
raw = bytearray()
for y in range(S):
    raw.append(0)
    raw.extend(img[y*S*4:(y+1)*S*4])


def chunk(t, d):
    return struct.pack('>I', len(d)) + t + d + struct.pack('>I', zlib.crc32(t+d) & 0xffffffff)


_HERE = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(_HERE, 'icon.png')
_png = (b'\x89PNG\r\n\x1a\n' +
        chunk(b'IHDR', struct.pack('>IIBBBBB', S, S, 8, 6, 0, 0, 0)) +
        chunk(b'IDAT', zlib.compress(bytes(raw), 9)) +
        chunk(b'IEND', b''))
open(out, 'wb').write(_png)
print("wrote", out)


# ---------- 额外：Windows 需要的 .ico ----------
# ICO 可以直接内嵌 PNG（Vista 以后都支持），所以不用做 BMP 转换。
# 多塞几个尺寸，任务栏 / 资源管理器 / 缩略图各取所需。
def _write_ico(path: str, png_bytes: bytes, sizes) -> None:
    n = len(sizes)
    header = struct.pack('<HHH', 0, 1, n)          # reserved, type=1(icon), count
    entries = b''
    offset = 6 + n * 16
    body = b''
    for (w, h) in sizes:
        entries += struct.pack('<BBBBHHII',
                               w if w < 256 else 0,
                               h if h < 256 else 0,
                               0, 0, 1, 32,
                               len(png_bytes), offset)
        body += png_bytes
        offset += len(png_bytes)
    with open(path, 'wb') as f:
        f.write(header + entries + body)


try:
    ico = os.path.join(_HERE, 'icon.ico')
    _write_ico(ico, _png, [(16, 16), (32, 32), (48, 48), (64, 64),
                           (128, 128), (256, 256)])
    print("wrote", ico)
except Exception as exc:
    print("ico skipped:", exc)


# ---------- 额外：Linux 用的各种尺寸 ----------
try:
    lin = os.path.join(_HERE, 'icons_linux')
    os.makedirs(lin, exist_ok=True)
    for sz in (48, 128, 256, 512):
        # 直接复用同一张 1024 PNG（桌面环境自己会缩放）
        with open(os.path.join(lin, 'steelfrontline-%d.png' % sz), 'wb') as f:
            f.write(_png)
    print("wrote", lin)
except Exception as exc:
    print("linux icons skipped:", exc)
