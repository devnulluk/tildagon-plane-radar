"""Dependency-free QR code for the Plane Radar instructions page.

During draft/hardware testing this points at the development branch so the QR
works before the port is merged. Switch it to /blob/main/TILDAGON.md for the
release commit.
"""

INSTRUCTIONS_URL = "https://github.com/devnulluk/tildagon-plane-radar/blob/tildagon-port/TILDAGON.md"
QR_SIZE = 37
QR_ROWS = (
    0x1FD335CC7F,
    0x105DDC9441,
    0x17477ACE5D,
    0x174445EE5D,
    0x175EE85C5D,
    0x1052244141,
    0x1FD555557F,
    0x0017722400,
    0x1CDCCA21F3,
    0x1184CBB347,
    0x0EFA2E231B,
    0x01B08745F3,
    0x14E7B9326B,
    0x1B251B3B6F,
    0x0BCDDB7241,
    0x09B7701730,
    0x1E68CA716B,
    0x0018C3BA6F,
    0x08562A2241,
    0x02A4814288,
    0x17E3B93569,
    0x101D127BEB,
    0x1349DFBA61,
    0x1C8B772578,
    0x19C0D92269,
    0x0B30C3B747,
    0x194232EF25,
    0x0330975148,
    0x187FB911F2,
    0x00113BA919,
    0x1FC1E2A95D,
    0x1057571318,
    0x1748DB33FB,
    0x1744FB3096,
    0x175632BC1D,
    0x1054B035A8,
    0x1FDF971151,
)


def draw_qr(ctx, center_x=0, center_y=0, scale=3):
    """Draw the embedded QR with a four-module white quiet zone."""
    scale = max(1, int(scale))
    quiet = 4
    total_modules = QR_SIZE + quiet * 2
    total_px = total_modules * scale
    left = center_x - total_px / 2
    top = center_y - total_px / 2

    ctx.rgb(1, 1, 1).rectangle(left, top, total_px, total_px).fill()
    ctx.rgb(0, 0, 0)

    data_left = left + quiet * scale
    data_top = top + quiet * scale
    for row, bits in enumerate(QR_ROWS):
        col = 0
        while col < QR_SIZE:
            mask = 1 << (QR_SIZE - 1 - col)
            if not (bits & mask):
                col += 1
                continue
            start = col
            while col < QR_SIZE and bits & (1 << (QR_SIZE - 1 - col)):
                col += 1
            ctx.rectangle(
                data_left + start * scale,
                data_top + row * scale,
                (col - start) * scale,
                scale,
            ).fill()
