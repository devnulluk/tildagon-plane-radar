"""Dependency-free QR code for the Plane Radar instructions page."""

INSTRUCTIONS_URL = "https://github.com/devnulluk/tildagon-plane-radar/blob/main/TILDAGON.md"
QR_SIZE = 33
QR_ROWS = (
    0x1FC58E27F,
    0x1054E1041,
    0x174151C5D,
    0x175D4805D,
    0x17485325D,
    0x105B7C541,
    0x1FD55557F,
    0x000E27C00,
    0x1F7A4A7AA,
    0x113597E47,
    0x14F435D3A,
    0x07A1608D4,
    0x0C4D687B8,
    0x11B897263,
    0x15F7708F2,
    0x063A35CE4,
    0x11574A4B2,
    0x159D1724B,
    0x18D174DCA,
    0x1F8010A84,
    0x1E7549712,
    0x171E03A4B,
    0x15482DDEA,
    0x12BC45AFC,
    0x13776E5F1,
    0x001A1EB1D,
    0x1FD5F8B5A,
    0x104E53F1F,
    0x17534A5F2,
    0x175797BB0,
    0x1751ED74E,
    0x105A77CAC,
    0x1FDB4A70A,
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
