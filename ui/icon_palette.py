"""Theme-aware editorial line icons used by the desktop workspace."""

from __future__ import annotations

import math

from PIL import Image, ImageDraw, ImageTk


def render_icon(name: str, color: str, size: int = 24, scale: int = 4) -> Image.Image:
    """Render a crisp, transparent icon from the shared editorial geometry."""
    logical = 24
    factor = max(1, int(scale)) * float(size) / logical
    canvas_size = max(1, int(round(logical * factor)))
    image = Image.new("RGBA", (canvas_size, canvas_size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    width = max(1, int(round(1.8 * factor)))

    def p(value):
        return int(round(value * factor))

    def box(values):
        return tuple(p(value) for value in values)

    def line(points, *, fill=color, stroke=width, close=False):
        pts = [(p(x), p(y)) for x, y in points]
        if close and pts:
            pts.append(pts[0])
        draw.line(pts, fill=fill, width=stroke, joint="curve")
        radius = stroke / 2
        for x, y in pts:
            draw.ellipse((x - radius, y - radius, x + radius, y + radius), fill=fill)

    def ellipse(values, *, outline=color, stroke=width, fill=None):
        draw.ellipse(box(values), outline=outline, width=stroke, fill=fill)

    def arc(values, start, end, *, stroke=width):
        draw.arc(box(values), start=start, end=end, fill=color, width=stroke)

    if name in {"library", "book"}:
        line([(3, 5), (6, 4), (10.5, 5.2), (12, 7), (12, 20), (10.2, 18.2), (6, 17.2), (3, 18.2), (3, 5)])
        line([(21, 5), (18, 4), (13.5, 5.2), (12, 7)])
        line([(21, 5), (21, 18.2), (18, 17.2), (13.8, 18.2), (12, 20)])
    elif name == "author":
        ellipse((8, 3, 16, 11))
        arc((4.5, 10, 19.5, 23), 180, 360)
        line([(5, 16.5), (5, 20), (19, 20), (19, 16.5)])
    elif name == "series":
        for dy in (0, 4.5, 9):
            line([(4, 5 + dy), (12, 1.5 + dy), (20, 5 + dy), (12, 8.5 + dy), (4, 5 + dy)], stroke=max(1, int(width * 0.9)))
    elif name == "tag":
        line([(4, 4), (13, 4), (20, 11), (11, 20), (4, 13), (4, 4)], close=True)
        ellipse((7, 7, 9.5, 9.5), fill=color, stroke=max(1, width // 2))
    elif name == "favorite":
        # A compact, symmetrical heart built from two round lobes and a point.
        arc((3, 3, 13, 13), 150, 350)
        arc((11, 3, 21, 13), 190, 390)
        line([(3.8, 8.5), (12, 20), (20.2, 8.5)])
    elif name == "import":
        line([(12, 2.5), (12, 14), (7.8, 9.8)])
        line([(12, 14), (16.2, 9.8)])
        line([(4, 14), (4, 20), (20, 20), (20, 14)])
        line([(4, 14), (8, 14)])
        line([(16, 14), (20, 14)])
    elif name == "reviews":
        line([(4, 4), (20, 4), (20, 16), (12, 16), (7, 20), (7, 16), (4, 16), (4, 4)], close=True)
        line([(8, 9), (10.5, 11.5), (16, 7.5)])
    elif name == "search":
        ellipse((3, 3, 16, 16))
        line([(14.5, 14.5), (21, 21)])
    elif name == "grid":
        for x in (3, 13):
            for y in (3, 13):
                draw.rounded_rectangle(box((x, y, x + 7, y + 7)), radius=p(1.2), outline=color, width=width)
    elif name == "list":
        for y in (6, 12, 18):
            ellipse((3, y - 1, 5, y + 1), fill=color, stroke=max(1, width // 2))
            line([(8, y), (21, y)])
    elif name == "details":
        draw.rounded_rectangle(box((5, 2.5, 19, 21.5)), radius=p(2), outline=color, width=width)
        for y in (8, 12, 16):
            line([(9, y), (15, y)], stroke=max(1, int(width * 0.85)))
    elif name == "settings":
        ellipse((8.5, 8.5, 15.5, 15.5))
        ellipse((4.5, 4.5, 19.5, 19.5))
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            line([
                (12 + 7.5 * math.cos(radians), 12 + 7.5 * math.sin(radians)),
                (12 + 10 * math.cos(radians), 12 + 10 * math.sin(radians)),
            ])
    elif name == "sun":
        ellipse((7.5, 7.5, 16.5, 16.5))
        for angle in range(0, 360, 45):
            radians = math.radians(angle)
            line([
                (12 + 7 * math.cos(radians), 12 + 7 * math.sin(radians)),
                (12 + 9.5 * math.cos(radians), 12 + 9.5 * math.sin(radians)),
            ])
    elif name == "moon":
        arc((4, 2.5, 20, 21.5), 65, 285)
        arc((8, 2.5, 22, 18.5), 92, 270)
        line([(6.4, 18.2), (9.3, 20.2)])
    elif name == "open":
        line([(4, 8), (4, 20), (16, 20), (16, 16)])
        line([(10, 4), (20, 4), (20, 14)])
        line([(11, 13), (20, 4)])
    elif name == "edit":
        line([(5, 19), (7, 13), (16, 4), (20, 8), (11, 17), (5, 19)], close=True)
        line([(7, 13), (11, 17)])
    elif name == "more":
        for x in (5, 12, 19):
            ellipse((x - 1.2, 10.8, x + 1.2, 13.2), fill=color, stroke=max(1, width // 2))
    elif name == "folder":
        line([(3, 7), (9, 7), (11, 9), (21, 9), (21, 19), (3, 19), (3, 7)], close=True)
    elif name == "sort":
        line([(6, 4), (6, 20), (3, 17)])
        line([(6, 20), (9, 17)])
        for index, y in enumerate((6, 11, 16)):
            line([(12, y), (21 - index * 2, y)])
    elif name == "undo":
        arc((5, 5, 21, 21), 200, 500)
        line([(8, 5), (3, 9), (8, 13)])
    elif name == "activity":
        ellipse((3, 3, 21, 21))
        line([(12, 7), (12, 12), (16, 14)])
    else:
        raise ValueError(f"Unknown icon: {name}")

    if image.size != (size, size):
        image = image.resize((size, size), Image.Resampling.LANCZOS)
    return image


def create_icon(name: str, color: str, size: int = 24, master=None) -> ImageTk.PhotoImage:
    return ImageTk.PhotoImage(render_icon(name, color, size=size), master=master)
