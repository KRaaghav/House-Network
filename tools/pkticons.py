#!/usr/bin/env python3
"""
pkticons.py - the pictures of the things in the lab that Packet Tracer has no icon for

Packet Tracer has no smart TV, fridge or doorbell. In the lab they are PCs (they get an
address and answer ping like the real thing), and houselayout.py gives each one
a picture from here so the canvas shows what it is. The pictures are drawn by the code
below, pixel by pixel, and saved inside the .pkt file. No image files, nothing to install.

  python3 pkticons.py <folder>     write every picture as a .png file, to look at them

To change a picture, change its list of shapes in ICONS. A shape is
(kind, numbers, colour) on a 64 x 64 grid, later shapes are drawn over earlier ones:

  ("box", (left, top, right, bottom), colour)
  ("oval", (left, top, right, bottom), colour)
  ("line", (x1, y1, x2, y2, thickness), colour)
"""

import os
import struct
import sys
import zlib

SIZE = 64
FINE = 3                        # every pixel is worked out from 3 x 3 points, for smooth edges

INK = (40, 48, 60)
WHITE, GREY, DARK = (255, 255, 255), (198, 204, 212), (92, 102, 116)
RED, GREEN, BLUE, YELLOW = (226, 68, 62), (52, 178, 96), (56, 128, 226), (247, 200, 52)
BROWN, ORANGE, BLACK = (150, 100, 60), (240, 140, 50), (24, 28, 34)


def seven(x, y, digit, colour):
    """A digit like on a scoreboard, 9 wide and 16 high, made of up to seven bars."""
    bars = {"a": (x, y, x + 9, y + 2), "g": (x, y + 7, x + 9, y + 9), "d": (x, y + 14, x + 9, y + 16),
            "f": (x, y, x + 2, y + 9), "b": (x + 7, y, x + 9, y + 9),
            "e": (x, y + 7, x + 2, y + 16), "c": (x + 7, y + 7, x + 9, y + 16)}
    lit = {"0": "abcdef", "1": "bc", "2": "abged", "3": "abgcd", "4": "fgbc", "5": "afgcd",
           "6": "afgedc", "7": "abc", "8": "abcdefg", "9": "abfgcd"}[digit]
    return [("box", bars[bar], colour) for bar in lit]


ICONS = {
    # a dome camera under its ceiling plate
    "camera": [("oval", (10, -8, 54, 50), INK), ("oval", (13, -5, 51, 47), WHITE), ("box", (8, -10, 56, 9), None),
               ("box", (10, 8, 54, 16), INK), ("box", (12, 10, 52, 14), GREY),
               ("oval", (20, 16, 44, 40), INK), ("oval", (25, 21, 39, 35), BLUE), ("oval", (28, 23, 33, 28), WHITE),
               ("oval", (44, 18, 49, 23), RED)],
    # a grey box with a sheet going in at the top and coming out at the front
    "printer": [("box", (16, 4, 48, 26), INK), ("box", (18, 6, 46, 26), WHITE),
                ("box", (4, 22, 60, 48), INK), ("box", (6, 24, 58, 46), GREY),
                ("box", (12, 40, 52, 60), INK), ("box", (14, 42, 50, 58), WHITE),
                ("line", (19, 47, 45, 47, 2), DARK), ("line", (19, 52, 39, 52, 2), DARK),
                ("oval", (48, 28, 54, 34), GREEN), ("box", (10, 29, 26, 33), DARK)],
    # a flat TV on its foot, showing a sunset
    "tv": [("box", (1, 8, 63, 48), INK), ("box", (4, 11, 60, 45), (60, 90, 170)), ("box", (4, 30, 60, 45), (70, 150, 110)),
           ("oval", (36, 18, 50, 32), YELLOW), ("box", (4, 30, 60, 45), (70, 150, 110)),
           ("box", (29, 48, 35, 56), INK), ("box", (18, 55, 46, 60), INK)],
    # a game controller: grips, a cross on the left, four buttons on the right
    "console": [("oval", (2, 18, 30, 56), INK), ("oval", (34, 18, 62, 56), INK), ("box", (14, 16, 50, 44), INK),
                ("oval", (5, 21, 27, 53), GREY), ("oval", (37, 21, 59, 53), GREY), ("box", (16, 19, 48, 41), GREY),
                ("box", (11, 28, 25, 32), INK), ("box", (16, 23, 20, 37), INK),
                ("oval", (44, 22, 50, 28), GREEN), ("oval", (50, 28, 56, 34), RED), ("oval", (38, 28, 44, 34), BLUE),
                ("oval", (44, 34, 50, 40), YELLOW)],
    # a round thermostat on the wall, set to 72
    "thermostat": [("oval", (4, 4, 60, 60), INK), ("oval", (8, 8, 56, 56), ORANGE), ("oval", (13, 13, 51, 51), WHITE)]
                  + seven(20, 24, "7", INK) + seven(33, 24, "2", INK),
    # a fridge with two doors and handles
    "fridge": [("box", (14, 1, 50, 63), INK), ("box", (17, 4, 47, 22), WHITE), ("box", (17, 25, 47, 60), WHITE),
               ("box", (39, 9, 43, 18), GREY), ("box", (39, 30, 43, 45), GREY), ("box", (21, 30, 30, 36), (150, 220, 250))],
    # a smart speaker with its blue light ring
    "speaker": [("oval", (14, 4, 50, 16), INK), ("box", (14, 10, 50, 56), INK), ("oval", (14, 50, 50, 62), INK),
                ("box", (17, 12, 47, 55), DARK), ("oval", (17, 7, 47, 15), (90, 190, 255)),
                ("line", (21, 26, 43, 26, 1.5), INK), ("line", (21, 32, 43, 32, 1.5), INK), ("line", (21, 38, 43, 38, 1.5), INK)],
    # a video doorbell: lens on top, the glowing button below
    "doorbell": [("box", (20, 2, 44, 62), INK), ("box", (23, 5, 41, 59), GREY), ("oval", (25, 9, 39, 23), INK),
                 ("oval", (28, 12, 36, 20), BLUE), ("oval", (24, 36, 40, 52), (90, 190, 255)), ("oval", (28, 40, 36, 48), WHITE)],
    # a laptop, open
    "laptop": [("box", (10, 8, 54, 42), INK), ("box", (13, 11, 51, 39), (140, 200, 250)),
               ("box", (2, 42, 62, 52), INK), ("box", (5, 44, 59, 49), GREY), ("box", (26, 45, 38, 48), DARK)],
}


def inside(kind, numbers, x, y):
    if kind == "box":
        left, top, right, bottom = numbers
        return left <= x < right and top <= y < bottom
    if kind == "oval":
        left, top, right, bottom = numbers
        rx, ry = (right - left) / 2, (bottom - top) / 2
        return ((x - left - rx) / rx) ** 2 + ((y - top - ry) / ry) ** 2 <= 1
    x1, y1, x2, y2, thick = numbers                 # a line: how far is the point from it?
    dx, dy = x2 - x1, y2 - y1
    along = max(0, min(1, ((x - x1) * dx + (y - y1) * dy) / (dx * dx + dy * dy)))
    return (x - x1 - along * dx) ** 2 + (y - y1 - along * dy) ** 2 <= (thick / 2) ** 2


def pixels(shapes):
    """SIZE rows of SIZE (red, green, blue, alpha) values. A shape with colour None rubs out."""
    rows = []
    for py in range(SIZE):
        row = []
        for px in range(SIZE):
            total = [0, 0, 0, 0]
            for sy in range(FINE):
                for sx in range(FINE):
                    x, y = px + (sx + 0.5) / FINE, py + (sy + 0.5) / FINE
                    colour = None
                    for kind, numbers, shape_colour in shapes:
                        if inside(kind, numbers, x, y):
                            colour = shape_colour
                    if colour:
                        total = [total[0] + colour[0], total[1] + colour[1], total[2] + colour[2], total[3] + 1]
            hits = total[3]
            row.append((total[0] // hits, total[1] // hits, total[2] // hits, 255 * hits // FINE ** 2) if hits
                       else (0, 0, 0, 0))
        rows.append(row)
    return rows


def png(kind):
    """The picture of one kind of thing as the bytes of a .png file."""
    def chunk(name, data):
        return struct.pack(">I", len(data)) + name + data + struct.pack(">I", zlib.crc32(name + data))
    raw = b"".join(b"\x00" + bytes(value for pixel in row for value in pixel) for row in pixels(ICONS[kind]))
    return (b"\x89PNG\r\n\x1a\n" + chunk(b"IHDR", struct.pack(">IIBBBBB", SIZE, SIZE, 8, 6, 0, 0, 0))
            + chunk(b"IDAT", zlib.compress(raw, 9)) + chunk(b"IEND", b""))


def main(args):
    if len(args) != 1:
        print(__doc__)
        return 2
    os.makedirs(args[0], exist_ok=True)
    for kind in ICONS:
        with open(os.path.join(args[0], kind + ".png"), "wb") as f:
            f.write(png(kind))
        print(os.path.join(args[0], kind + ".png"))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv[1:]))
