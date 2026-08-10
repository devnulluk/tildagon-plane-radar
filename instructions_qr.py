"""Dependency-free QR code for the Plane Radar instructions page."""

INSTRUCTIONS_URL = "https://github.com/devnulluk/tildagon-plane-radar/blob/main/TILDAGON.md"
QR_SIZE = 33
QR_ROWS = (
    0x01FC58E27F,
    0x01054E1041,
    0x0174151C5D,
    0x0175D4805D,
    0x017485325D,
    0x0105B7C541,
    0x01FD55557F,
    0x0000E27C00,
    0x01F7A4A7AA,
    0x0113597E47,
    0x014F435D3A,
    0x007A1608D4,
    0x00C4D687B8,
    0x011B897263,
    0x015F7708F2,
    0x0063A35CE4,
    0x011574A4B2,
    0x0159D1724B,
    0x018D174DCA,
    0x01F8010A84,
    0x01E7549712,
    0x0171E03A4B,
    0x015482DDEA,
    0x012BC45AFC,
    0x013776E5F1,
    0x0001A1EB1D,
    0x01FD5F8B5A,
    0x0104E53F1F,
    0x017534A5F2,
    0x0175797BB0,
    0x01751ED74E,
    0x0105A77CAC,
    0x01FDB4A70A,
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
