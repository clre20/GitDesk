"""Render the app icon to PNG (Linux) and ICO (Windows). Run: python packaging/make_icons.py"""
import os
import sys

os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from PySide6.QtWidgets import QApplication  # noqa: E402

app = QApplication(sys.argv)
from gitdesk.icons import app_icon  # noqa: E402

here = os.path.dirname(os.path.abspath(__file__))
icon = app_icon()
sizes = [16, 24, 32, 48, 64, 128, 256]
pngs = []
for s in sizes:
    p = os.path.join(here, f"icon_{s}.png")
    icon.pixmap(s, s).save(p, "PNG")
    pngs.append(p)
icon.pixmap(256, 256).save(os.path.join(here, "gitdesk.png"), "PNG")

# Build a multi-size .ico from the PNGs (PNG-compressed entries, Vista+)
import struct  # noqa: E402

entries, data = [], b""
offset = 6 + 16 * len(pngs)
for s, p in zip(sizes, pngs):
    b = open(p, "rb").read()
    entries.append(struct.pack("<BBBBHHII", s % 256, s % 256, 0, 0, 1, 32, len(b), offset + len(data)))
    data += b
with open(os.path.join(here, "gitdesk.ico"), "wb") as f:
    f.write(struct.pack("<HHH", 0, 1, len(pngs)) + b"".join(entries) + data)
for p in pngs:
    os.remove(p)
print("wrote gitdesk.png and gitdesk.ico")
