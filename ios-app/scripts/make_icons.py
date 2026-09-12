# -*- coding: utf-8 -*-
"""Generate iOS AppIcon PNGs from the Android ic_launcher.png (pure Python, no deps)."""
import struct, zlib, os

SRC = r"E:\app\单词助手\android-app\app\src\main\res\mipmap-xxxhdpi\ic_launcher.png"
OUT_DIR = r"E:\app\单词助手\ios-app\WordAssistant\Assets.xcassets\AppIcon.appiconset"

SIZES = [
    ("AppIcon-20@2x.png", 40),
    ("AppIcon-20@3x.png", 60),
    ("AppIcon-29@2x.png", 58),
    ("AppIcon-29@3x.png", 87),
    ("AppIcon-40@2x.png", 80),
    ("AppIcon-40@3x.png", 120),
    ("AppIcon-60@2x.png", 120),
    ("AppIcon-60@3x.png", 180),
    ("AppIcon-1024.png", 1024),
]

def decode_png(path):
    data = open(path, "rb").read()
    assert data[:8] == b"\x89PNG\r\n\x1a\n"
    pos = 8
    idat = b""
    w = h = 0
    while pos < len(data):
        length = struct.unpack(">I", data[pos:pos+4])[0]
        ctype = data[pos+4:pos+8]
        chunk = data[pos+8:pos+8+length]
        if ctype == b"IHDR":
            w, h, bitdepth, colortype, _, _, interlace = struct.unpack(">IIBBBBB", chunk)
            assert bitdepth == 8 and colortype == 6 and interlace == 0, "unsupported PNG"
        elif ctype == b"IDAT":
            idat += chunk
        pos += 12 + length
    raw = zlib.decompress(idat)
    stride = w * 4
    out = bytearray()
    prev = bytearray(stride)
    p = 0
    for y in range(h):
        f = raw[p]; p += 1
        line = bytearray(raw[p:p+stride]); p += stride
        if f == 1:
            for i in range(4, stride):
                line[i] = (line[i] + line[i-4]) & 0xFF
        elif f == 2:
            for i in range(stride):
                line[i] = (line[i] + prev[i]) & 0xFF
        elif f == 3:
            for i in range(stride):
                a = line[i-4] if i >= 4 else 0
                line[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
        elif f == 4:
            for i in range(stride):
                a = line[i-4] if i >= 4 else 0
                b = prev[i]
                c = prev[i-4] if i >= 4 else 0
                pp = a + b - c
                pa = abs(pp - a); pb = abs(pp - b); pc = abs(pp - c)
                pr = a if (pa <= pb and pa <= pc) else (b if pb <= pc else c)
                line[i] = (line[i] + pr) & 0xFF
        out += line
        prev = line
    return w, h, bytes(out)

def resize(src, sw, sh, tw, th):
    out = bytearray(tw * th * 4)
    for ty in range(th):
        y0 = (ty * sh) // th
        y1 = max(y0 + 1, ((ty + 1) * sh + th - 1) // th)
        for tx in range(tw):
            x0 = (tx * sw) // tw
            x1 = max(x0 + 1, ((tx + 1) * sw + tw - 1) // tw)
            r = g = b = a = n = 0
            for yy in range(y0, y1):
                row = yy * sw * 4
                for xx in range(x0, x1):
                    i = row + xx * 4
                    r += src[i]; g += src[i+1]; b += src[i+2]; a += src[i+3]
                    n += 1
            o = (ty * tw + tx) * 4
            out[o] = r // n; out[o+1] = g // n; out[o+2] = b // n; out[o+3] = a // n
    return bytes(out)

def write_png(path, w, h, rgba):
    def chunk(ct, payload):
        return struct.pack(">I", len(payload)) + ct + payload + struct.pack(">I", zlib.crc32(ct + payload) & 0xFFFFFFFF)
    raw = b""
    stride = w * 4
    for y in range(h):
        raw += b"\x00" + rgba[y*stride:(y+1)*stride]
    idat = zlib.compress(raw, 9)
    ihdr = struct.pack(">IIBBBBB", w, h, 8, 6, 0, 0, 0)
    png = b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", ihdr) + chunk(b"IDAT", idat) + chunk(b"IEND", b"")
    with open(path, "wb") as f:
        f.write(png)

def main():
    sw, sh, rgba = decode_png(SRC)
    print(f"decoded {sw}x{sh}")
    os.makedirs(OUT_DIR, exist_ok=True)
    for name, size in SIZES:
        out = resize(rgba, sw, sh, size, size)
        write_png(os.path.join(OUT_DIR, name), size, size, out)
        print(f"wrote {name} ({size}x{size})")

if __name__ == "__main__":
    main()
