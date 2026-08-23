#!/usr/bin/env python3
"""Generates authentic high-quality 2D layered sprite PNG assets for the Talking Portrait.

Uses standard Python library (struct + zlib) to write uncompressed/deflated RGBA PNGs:
- assets/base.png
- assets/eyes_closed.png
- assets/mouth_1.png
- assets/mouth_2.png
- assets/mouth_3.png
"""

import os
import struct
import zlib
import math

def write_png(filename: str, width: int, height: int, rgba_bytes: bytearray):
    os.makedirs(os.path.dirname(os.path.abspath(filename)), exist_ok=True)
    
    # PNG signature
    png_header = b"\x89PNG\r\n\x1a\n"
    
    # IHDR chunk: width(4), height(4), bit_depth(1), color_type(1=6 for RGBA), compression(1), filter(1), interlace(1)
    ihdr_data = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)
    ihdr_crc = zlib.crc32(b"IHDR" + ihdr_data)
    ihdr_chunk = struct.pack(">I", len(ihdr_data)) + b"IHDR" + ihdr_data + struct.pack(">I", ihdr_crc)
    
    # IDAT chunk: Scanlines with filter byte 0
    raw_scanlines = bytearray()
    row_stride = width * 4
    for y in range(height):
        raw_scanlines.append(0) # Filter byte: None
        start = y * row_stride
        raw_scanlines.extend(rgba_bytes[start : start + row_stride])
    
    compressed_idat = zlib.compress(bytes(raw_scanlines), 9)
    idat_crc = zlib.crc32(b"IDAT" + compressed_idat)
    idat_chunk = struct.pack(">I", len(compressed_idat)) + b"IDAT" + compressed_idat + struct.pack(">I", idat_crc)
    
    # IEND chunk
    iend_crc = zlib.crc32(b"IEND")
    iend_chunk = struct.pack(">I", 0) + b"IEND" + struct.pack(">I", iend_crc)
    
    with open(filename, "wb") as f:
        f.write(png_header + ihdr_chunk + idat_chunk + iend_chunk)
    print(f"Generated asset: {filename} ({width}x{height})")


def create_canvas(width: int, height: int) -> bytearray:
    return bytearray(width * height * 4)

def set_pixel(buf: bytearray, width: int, height: int, x: int, y: int, r: int, g: int, b: int, a: int):
    if 0 <= x < width and 0 <= y < height:
        idx = (y * width + x) * 4
        # Alpha blend over existing
        old_a = buf[idx + 3] / 255.0
        new_a = a / 255.0
        out_a = new_a + old_a * (1.0 - new_a)
        if out_a > 0:
            out_r = int((r * new_a + buf[idx] * old_a * (1.0 - new_a)) / out_a)
            out_g = int((g * new_a + buf[idx + 1] * old_a * (1.0 - new_a)) / out_a)
            out_b = int((b * new_a + buf[idx + 2] * old_a * (1.0 - new_a)) / out_a)
            buf[idx] = min(255, max(0, out_r))
            buf[idx + 1] = min(255, max(0, out_g))
            buf[idx + 2] = min(255, max(0, out_b))
            buf[idx + 3] = int(min(255, max(0, out_a * 255)))

def draw_rect(buf: bytearray, w: int, h: int, rx: int, ry: int, rw: int, rh: int, r: int, g: int, b: int, a: int):
    for y in range(ry, ry + rh):
        for x in range(rx, rx + rw):
            set_pixel(buf, w, h, x, y, r, g, b, a)

def draw_ellipse(buf: bytearray, w: int, h: int, cx: int, cy: int, rx: int, ry: int, r: int, g: int, b: int, a: int):
    for y in range(cy - ry, cy + ry + 1):
        for x in range(cx - rx, cx + rx + 1):
            if rx > 0 and ry > 0:
                dx = (x - cx) / rx
                dy = (y - cy) / ry
                if dx * dx + dy * dy <= 1.0:
                    set_pixel(buf, w, h, x, y, r, g, b, a)

def draw_circle(buf: bytearray, w: int, h: int, cx: int, cy: int, rad: int, r: int, g: int, b: int, a: int):
    draw_ellipse(buf, w, h, cx, cy, rad, rad, r, g, b, a)

def generate_all_assets():
    W = 512
    H = 512
    cx = W // 2
    cy = H // 2

    # ==================== 1. BASE.PNG ====================
    base_buf = create_canvas(W, H)

    # Castle Stone Wall Background
    for y in range(H):
        for x in range(W):
            dist = math.sqrt((x - cx)**2 + (y - cy)**2) / 360.0
            val = max(0.0, min(1.0, 1.0 - dist * 0.7))
            r = int(32 * val + 8)
            g = int(26 * val + 6)
            b = int(22 * val + 5)
            set_pixel(base_buf, W, H, x, y, r, g, b, 255)

    # Ornate Gold Frame Rim
    for y in range(H):
        for x in range(W):
            if x < 28 or x >= W - 28 or y < 28 or y >= H - 28:
                # Gilded wood molding
                bevel = (x + y) % 12
                gr = 180 + bevel * 4
                gg = 140 + bevel * 3
                gb = 45 + bevel * 2
                set_pixel(base_buf, W, H, x, y, min(255, gr), min(255, gg), min(255, gb), 255)
            elif x < 34 or x >= W - 34 or y < 34 or y >= H - 34:
                # Dark inner frame shadow
                set_pixel(base_buf, W, H, x, y, 45, 35, 20, 255)

    # Knight Shoulders & Polished Steel Armor
    draw_ellipse(base_buf, W, H, cx, cy + 175, 170, 110, 85, 95, 105, 255)
    # Armor Highlights
    draw_ellipse(base_buf, W, H, cx - 60, cy + 155, 75, 45, 140, 155, 170, 255)
    draw_ellipse(base_buf, W, H, cx + 60, cy + 155, 75, 45, 140, 155, 170, 255)
    # Crimson Gryffindor Sash
    for i in range(-12, 13):
        draw_ellipse(base_buf, W, H, cx + i * 8, cy + 160 + i * 4, 30, 20, 160, 32, 32, 255)
    # Gold Sash Trim
    draw_ellipse(base_buf, W, H, cx, cy + 185, 120, 12, 218, 165, 32, 255)

    # Curled Aristocratic White Wig
    draw_ellipse(base_buf, W, H, cx - 95, cy - 10, 35, 75, 235, 240, 245, 255)
    draw_ellipse(base_buf, W, H, cx + 95, cy - 10, 35, 75, 235, 240, 245, 255)
    draw_ellipse(base_buf, W, H, cx, cy - 85, 95, 45, 240, 245, 250, 255)
    # Wig Shadow
    draw_ellipse(base_buf, W, H, cx - 90, cy - 5, 28, 65, 195, 205, 215, 255)
    draw_ellipse(base_buf, W, H, cx + 90, cy - 5, 28, 65, 195, 205, 215, 255)

    # Face Oval (Noble weathered skin tone)
    draw_ellipse(base_buf, W, H, cx, cy - 5, 82, 100, 225, 190, 160, 255)
    # Cheeks & Rosy Warmth
    draw_ellipse(base_buf, W, H, cx - 45, cy + 10, 24, 18, 215, 160, 140, 180)
    draw_ellipse(base_buf, W, H, cx + 45, cy + 10, 24, 18, 215, 160, 140, 180)

    # Knight Eyebrows (Arched & Proud)
    draw_ellipse(base_buf, W, H, cx - 38, cy - 42, 26, 8, 90, 65, 40, 255)
    draw_ellipse(base_buf, W, H, cx + 38, cy - 42, 26, 8, 90, 65, 40, 255)

    # Open Eyes (Neutral gaze)
    eye_y = cy - 22
    left_eye_x = cx - 38
    right_eye_x = cx + 38
    # Sclera (Whites)
    draw_ellipse(base_buf, W, H, left_eye_x, eye_y, 16, 11, 245, 248, 250, 255)
    draw_ellipse(base_buf, W, H, right_eye_x, eye_y, 16, 11, 245, 248, 250, 255)
    # Blue / Lavender Wizard Iris
    draw_circle(base_buf, W, H, left_eye_x, eye_y, 7, 70, 110, 160, 255)
    draw_circle(base_buf, W, H, right_eye_x, eye_y, 7, 70, 110, 160, 255)
    # Pupils
    draw_circle(base_buf, W, H, left_eye_x, eye_y, 4, 15, 20, 30, 255)
    draw_circle(base_buf, W, H, right_eye_x, eye_y, 4, 15, 20, 30, 255)
    # Eye Catchlight Glint
    draw_circle(base_buf, W, H, left_eye_x - 2, eye_y - 2, 2, 255, 255, 255, 255)
    draw_circle(base_buf, W, H, right_eye_x - 2, eye_y - 2, 2, 255, 255, 255, 255)

    # Nose Bridge & Tip
    draw_ellipse(base_buf, W, H, cx, cy + 8, 8, 18, 205, 165, 135, 255)
    draw_circle(base_buf, W, H, cx, cy + 18, 7, 215, 175, 145, 255)

    # Proud Knight Mustache
    draw_ellipse(base_buf, W, H, cx - 22, cy + 32, 26, 12, 100, 70, 45, 255)
    draw_ellipse(base_buf, W, H, cx + 22, cy + 32, 26, 12, 100, 70, 45, 255)
    draw_circle(base_buf, W, H, cx, cy + 30, 8, 110, 75, 48, 255)

    # Chin & Goatee Beard
    draw_ellipse(base_buf, W, H, cx, cy + 68, 22, 16, 100, 70, 45, 255)

    write_png("assets/base.png", W, H, base_buf)

    # ==================== 2. EYES_CLOSED.PNG ====================
    eyes_buf = create_canvas(W, H)
    # Closed Eyelids (Skin tone matching face with dark eyelash crease)
    draw_ellipse(eyes_buf, W, H, left_eye_x, eye_y, 18, 12, 220, 185, 155, 255)
    draw_ellipse(eyes_buf, W, H, right_eye_x, eye_y, 18, 12, 220, 185, 155, 255)
    # Eyelash crease line
    draw_ellipse(eyes_buf, W, H, left_eye_x, eye_y + 1, 16, 3, 60, 40, 25, 255)
    draw_ellipse(eyes_buf, W, H, right_eye_x, eye_y + 1, 16, 3, 60, 40, 25, 255)
    write_png("assets/eyes_closed.png", W, H, eyes_buf)

    # ==================== 3. MOUTH_1.PNG (Closed Neutral) ====================
    m1_buf = create_canvas(W, H)
    # Mustache on top of mouth
    draw_ellipse(m1_buf, W, H, cx - 22, cy + 32, 26, 12, 100, 70, 45, 255)
    draw_ellipse(m1_buf, W, H, cx + 22, cy + 32, 26, 12, 100, 70, 45, 255)
    draw_circle(m1_buf, W, H, cx, cy + 30, 8, 110, 75, 48, 255)
    # Closed Lip Line
    draw_ellipse(m1_buf, W, H, cx, cy + 46, 18, 3, 90, 35, 30, 255)
    write_png("assets/mouth_1.png", W, H, m1_buf)

    # ==================== 4. MOUTH_2.PNG (Half Open / Speaking) ====================
    m2_buf = create_canvas(W, H)
    # Mustache
    draw_ellipse(m2_buf, W, H, cx - 22, cy + 31, 26, 12, 100, 70, 45, 255)
    draw_ellipse(m2_buf, W, H, cx + 22, cy + 31, 26, 12, 100, 70, 45, 255)
    draw_circle(m2_buf, W, H, cx, cy + 29, 8, 110, 75, 48, 255)
    # Mouth Cavity
    draw_ellipse(m2_buf, W, H, cx, cy + 47, 16, 9, 65, 18, 18, 255)
    # Upper Teeth
    draw_rect(m2_buf, W, H, cx - 9, cy + 42, 18, 4, 245, 245, 245, 255)
    # Lip Outline
    draw_ellipse(m2_buf, W, H, cx, cy + 47, 18, 11, 140, 60, 50, 160)
    write_png("assets/mouth_2.png", W, H, m2_buf)

    # ==================== 5. MOUTH_3.PNG (Wide Open / Loud Utterance) ====================
    m3_buf = create_canvas(W, H)
    # Mustache
    draw_ellipse(m3_buf, W, H, cx - 22, cy + 30, 26, 12, 100, 70, 45, 255)
    draw_ellipse(m3_buf, W, H, cx + 22, cy + 30, 26, 12, 100, 70, 45, 255)
    draw_circle(m3_buf, W, H, cx, cy + 28, 8, 110, 75, 48, 255)
    # Deep Mouth Cavity
    draw_ellipse(m3_buf, W, H, cx, cy + 50, 20, 16, 45, 10, 10, 255)
    # Upper Teeth
    draw_rect(m3_buf, W, H, cx - 12, cy + 41, 24, 6, 250, 250, 250, 255)
    # Tongue
    draw_ellipse(m3_buf, W, H, cx, cy + 58, 12, 6, 185, 65, 75, 255)
    # Lip Outline
    draw_ellipse(m3_buf, W, H, cx, cy + 50, 22, 18, 140, 60, 50, 160)
    write_png("assets/mouth_3.png", W, H, m3_buf)

    print("All 5 portrait sprite layers generated successfully!")

if __name__ == "__main__":
    generate_all_assets()
