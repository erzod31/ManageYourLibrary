import tkinter as tk
from functools import lru_cache
from collections import OrderedDict

from PIL import Image, ImageDraw, ImageTk


def _render_full_surface(width, height, radius, outer, fill, border, scale):
    width = max(2, int(width))
    height = max(2, int(height))
    scale = max(2, int(scale))
    radius = max(1, min(int(radius), width // 2, height // 2))
    large = Image.new("RGB", (width * scale, height * scale), outer)
    draw = ImageDraw.Draw(large)
    inset = scale
    draw.rounded_rectangle(
        (
            inset,
            inset,
            width * scale - inset - 1,
            height * scale - inset - 1,
        ),
        radius=radius * scale,
        fill=fill,
        outline=border,
        width=scale,
    )
    return large.resize((width, height), Image.Resampling.LANCZOS)


@lru_cache(maxsize=128)
def _corner_template(radius, outer, fill, border, scale):
    side = 2 * (radius + 2)
    return _render_full_surface(side, side, radius, outer, fill, border, scale)


def render_rounded_surface(width, height, radius, outer, fill, border, scale=4):
    """Supersample corners, not the entire large flat card background."""
    width, height = max(2, int(width)), max(2, int(height))
    scale = max(2, int(scale))
    radius = max(1, min(int(radius), width // 2, height // 2))
    corner = radius + 2
    if min(width, height) < 2 * corner:
        return _render_full_surface(width, height, radius, outer, fill, border, scale)
    template = _corner_template(radius, outer, fill, border, scale)
    surface = Image.new("RGB", (width, height), fill)
    for source_x, destination_x in ((0, 0), (corner, width - corner)):
        for source_y, destination_y in ((0, 0), (corner, height - corner)):
            surface.paste(template.crop((source_x, source_y, source_x + corner, source_y + corner)),
                          (destination_x, destination_y))
    if width > 2 * corner:
        for y, target_y in ((0, 0), (corner, height - corner)):
            strip = template.crop((corner, y, corner + 1, y + corner))
            surface.paste(strip.resize((width - 2 * corner, corner), Image.Resampling.NEAREST), (corner, target_y))
    if height > 2 * corner:
        for x, target_x in ((0, 0), (corner, width - corner)):
            strip = template.crop((x, corner, x + corner, corner + 1))
            surface.paste(strip.resize((corner, height - 2 * corner), Image.Resampling.NEAREST), (target_x, corner))
    return surface


@lru_cache(maxsize=64)
def _cached_button_surface(width, height, radius, outer, fill, border):
    """Reuse identical button surfaces so pointer hover never stalls Tk."""
    return render_rounded_surface(width, height, radius, outer, fill, border, scale=4)




class RoundedCard(tk.Frame):
    def __init__(
        self,
        master,
        radius=18,
        padding=14,
        bg_outer="#f3f4f6",
        bg_inner="#ffffff",
        border="#e5e7eb",
        min_height=1,
        auto_height=True,
        **kwargs
    ):
        super().__init__(master, bg=bg_outer, **kwargs)
        self.radius = radius
        self.padding = padding
        self.bg_outer = bg_outer
        self.bg_inner = bg_inner
        self.border = border
        self.min_height = max(1, int(min_height))
        self.auto_height = auto_height
        self._surface_photo = None
        self._draw_after = None
        self._height_after = None

        self.canvas = tk.Canvas(
            self,
            width=1,
            height=self.min_height,
            highlightthickness=0,
            bd=0,
            bg=bg_outer
        )
        self.canvas.pack(fill="both", expand=True)

        self.inner = tk.Frame(self.canvas, bg=bg_inner)
        self.window = self.canvas.create_window(
            (padding, padding),
            window=self.inner,
            anchor="nw"
        )

        self.canvas.bind("<Configure>", self._on_canvas)
        self.inner.bind("<Configure>", self._on_inner)

        self._schedule_height_adjust()

    def set_theme(self, bg_outer, bg_inner, border):
        if (bg_outer, bg_inner, border) == (self.bg_outer, self.bg_inner, self.border):
            return
        self.bg_outer = bg_outer
        self.bg_inner = bg_inner
        self.border = border
        self.configure(bg=bg_outer)
        self.canvas.configure(bg=bg_outer)
        self.inner.configure(bg=bg_inner)
        self._draw()

    def _schedule_quality_draw(self, delay=90):
        if self._draw_after is not None:
            try:
                self.after_cancel(self._draw_after)
            except tk.TclError:
                pass
        self._draw_after = self.after(delay, self._finish_quality_draw)

    def _finish_quality_draw(self):
        self._draw_after = None
        self._draw()

    def _schedule_height_adjust(self):
        if self._height_after is not None:
            try:
                self.after_cancel(self._height_after)
            except tk.TclError:
                pass
        self._height_after = self.after(16, self._ajustar_altura_al_contenido)

    def _ajustar_altura_al_contenido(self):
        self._height_after = None
        if not self.auto_height:
            self._schedule_quality_draw()
            return

        try:
            requerido = self.inner.winfo_reqheight() + self.padding * 2
            requerido = max(self.min_height, requerido)

            actual = int(float(self.canvas.cget("height")))
            if abs(actual - requerido) > 2:
                self.canvas.configure(height=requerido)
        except (tk.TclError, TypeError, ValueError):
            pass

        self._schedule_quality_draw()

    def _on_inner(self, event=None):
        self._schedule_height_adjust()

    def _on_canvas(self, event=None):
        try:
            ancho = max(10, self.canvas.winfo_width() - self.padding * 2)

            if self.auto_height:
                # Compact cards only constrain width, otherwise their content can
                # force oversized heights during Tk layout recalculation.
                self.canvas.itemconfig(self.window, width=ancho)
            else:
                # Fixed/expandable cards need both dimensions to keep scroll areas stable.
                alto = max(10, self.canvas.winfo_height() - self.padding * 2)
                self.canvas.itemconfig(self.window, width=ancho, height=alto)

        except (tk.TclError, TypeError, ValueError):
            pass

        # A native Tk surface keeps sash dragging responsive. The supersampled
        # surface is restored once resize events settle.
        self._draw(fast=True)
        self._schedule_quality_draw()

    def _shape(self, item_id):
        self.canvas.addtag_withtag("bg_shape", item_id)
        return item_id

    def _draw_round_rect(self, x1, y1, x2, y2, r, fill, outline):
        c = self.canvas

        self._shape(c.create_arc(x1, y1, x1 + 2*r, y1 + 2*r, start=90, extent=90, fill=fill, outline=outline))
        self._shape(c.create_arc(x2 - 2*r, y1, x2, y1 + 2*r, start=0, extent=90, fill=fill, outline=outline))
        self._shape(c.create_arc(x2 - 2*r, y2 - 2*r, x2, y2, start=270, extent=90, fill=fill, outline=outline))
        self._shape(c.create_arc(x1, y2 - 2*r, x1 + 2*r, y2, start=180, extent=90, fill=fill, outline=outline))

        self._shape(c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill))
        self._shape(c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=fill))

        self._shape(c.create_line(x1 + r, y1, x2 - r, y1, fill=outline))
        self._shape(c.create_line(x1 + r, y2, x2 - r, y2, fill=outline))
        self._shape(c.create_line(x1, y1 + r, x1, y2 - r, fill=outline))
        self._shape(c.create_line(x2, y1 + r, x2, y2 - r, fill=outline))

    def _draw(self, fast=False):
        try:
            self.canvas.delete("bg_shape")

            ancho = self.canvas.winfo_width()
            alto = self.canvas.winfo_height()

            if ancho <= 2 or alto <= 2:
                return

            if fast or self.bg_outer.lower() == "#ff00ff":
                self._draw_round_rect(
                    1,
                    1,
                    ancho - 2,
                    alto - 2,
                    self.radius,
                    self.bg_inner,
                    self.border,
                )
                self.canvas.tag_lower("bg_shape")
                self.canvas.tag_raise(self.window)
                return

            surface = render_rounded_surface(
                ancho,
                alto,
                self.radius,
                self.bg_outer,
                self.bg_inner,
                self.border,
                scale=2,
            )
            self._surface_photo = ImageTk.PhotoImage(surface, master=self.canvas)
            self._shape(
                self.canvas.create_image(
                    0,
                    0,
                    anchor="nw",
                    image=self._surface_photo,
                )
            )

            self.canvas.tag_lower("bg_shape")
            self.canvas.tag_raise(self.window)

        except (OSError, tk.TclError, TypeError, ValueError):
            pass


class RoundedButton(tk.Canvas):
    def __init__(
        self,
        master,
        text="",
        image=None,
        command=None,
        width=190,
        height=46,
        radius=16,
        font=("Segoe UI", 10),
        anchor="center",
        accessible_name="",
        **kwargs,
    ):
        kwargs.setdefault("takefocus", True)
        super().__init__(master, width=width, height=height, highlightthickness=0, bd=0, **kwargs)
        self.command = command
        self.text = text
        self.accessible_name = str(accessible_name or text or "")
        self.image = image
        self.radius = radius
        self.font = font
        self.anchor = anchor
        self.state = "normal"
        self._hover = False
        self._focused = False
        self._surface_photo = None
        self._surface_photos = OrderedDict()
        self._last_draw_signature = None
        self._draw_after = None
        self.theme = {
            "bg": "#ffffff",
            "fg": "#111827",
            "border": "#d1d5db",
            "active": "#f3f4f6",
            "disabled_bg": "#f3f4f6",
            "disabled_fg": "#9ca3af",
            "focus": "#8f4935",
        }
        # Usar el configure nativo de Canvas aquí evita llamar a _draw()
        # antes de terminar de inicializar todos los atributos.
        tk.Canvas.configure(self, cursor="hand2")
        self.bind("<Configure>", self._on_resize)
        self.bind("<Button-1>", self._click)
        self.bind("<Key-Return>", self._activate_from_keyboard)
        self.bind("<Key-space>", self._activate_from_keyboard)
        self.bind("<FocusIn>", self._focus_in)
        self.bind("<FocusOut>", self._focus_out)
        self.bind("<Enter>", self._enter)
        self.bind("<Leave>", self._leave)
        self._draw()

    def _on_resize(self, _event=None):
        self._draw(fast=True)
        if self._draw_after is not None:
            try:
                self.after_cancel(self._draw_after)
            except tk.TclError:
                pass
        self._draw_after = self.after(90, self._finish_quality_draw)

    def _finish_quality_draw(self):
        self._draw_after = None
        self._draw()

    def config(self, **kwargs):
        return self.configure(**kwargs)

    def configure(self, **kwargs):
        if "state" in kwargs:
            self.state = kwargs.pop("state")
        if "text" in kwargs:
            self.text = kwargs.pop("text")
            if self.text:
                self.accessible_name = str(self.text)
        if "accessible_name" in kwargs:
            self.accessible_name = str(kwargs.pop("accessible_name") or "")
        if "image" in kwargs:
            self.image = kwargs.pop("image")
        if "command" in kwargs:
            self.command = kwargs.pop("command")
        if "font" in kwargs:
            self.font = kwargs.pop("font")
        if "anchor" in kwargs:
            self.anchor = kwargs.pop("anchor")
        result = super().configure(**kwargs) if kwargs else None
        tk.Canvas.configure(self, cursor="arrow" if self.state == "disabled" else "hand2")
        self._draw()
        return result

    def set_theme(self, bg, fg, border, active, disabled_bg, disabled_fg):
        theme = {
            "bg": bg,
            "fg": fg,
            "border": border,
            "active": active,
            "disabled_bg": disabled_bg,
            "disabled_fg": disabled_fg,
            "focus": fg,
        }
        outer = self.master.cget("bg")
        if theme == self.theme and str(self.cget("bg")) == str(outer):
            return
        self.theme = theme
        tk.Canvas.configure(self, bg=outer)
        self._draw()

    def _click(self, event=None):
        self.focus_set()
        self.invoke()

    def invoke(self):
        """Run the command for mouse and keyboard activation."""
        if self.state != "disabled" and self.command:
            return self.command()
        return None

    def _activate_from_keyboard(self, _event=None):
        self.invoke()
        return "break"

    def _focus_in(self, _event=None):
        self._focused = True
        self._draw()

    def _focus_out(self, _event=None):
        self._focused = False
        self._draw()

    def _enter(self, event=None):
        self._hover = True
        self._draw()

    def _leave(self, event=None):
        self._hover = False
        self._draw()

    def _draw_round_rect(self, x1, y1, x2, y2, r, fill, outline):
        c = self
        c.create_arc(x1, y1, x1 + 2*r, y1 + 2*r, start=90, extent=90, fill=fill, outline=outline)
        c.create_arc(x2 - 2*r, y1, x2, y1 + 2*r, start=0, extent=90, fill=fill, outline=outline)
        c.create_arc(x2 - 2*r, y2 - 2*r, x2, y2, start=270, extent=90, fill=fill, outline=outline)
        c.create_arc(x1, y2 - 2*r, x1 + 2*r, y2, start=180, extent=90, fill=fill, outline=outline)
        c.create_rectangle(x1 + r, y1, x2 - r, y2, fill=fill, outline=fill)
        c.create_rectangle(x1, y1 + r, x2, y2 - r, fill=fill, outline=fill)
        c.create_line(x1 + r, y1, x2 - r, y1, fill=outline)
        c.create_line(x1 + r, y2, x2 - r, y2, fill=outline)
        c.create_line(x1, y1 + r, x1, y2 - r, fill=outline)
        c.create_line(x2, y1 + r, x2, y2 - r, fill=outline)

    def _draw(self, fast=False):
        measured_width = self.winfo_width()
        measured_height = self.winfo_height()
        w = max(2, measured_width if measured_width > 1 else int(self.cget("width")))
        h = max(2, measured_height if measured_height > 1 else int(self.cget("height")))

        if self.state == "disabled":
            bg = self.theme["disabled_bg"]
            fg = self.theme["disabled_fg"]
        else:
            bg = self.theme["active"] if self._hover else self.theme["bg"]
            fg = self.theme["fg"]

        outline = self.theme["focus"] if self._focused else self.theme["border"]
        outer = self.cget("bg")
        signature = (w, h, bg, fg, outline, outer, self.text, self.font, self.anchor, self.image, fast)
        if signature == self._last_draw_signature:
            return
        self._last_draw_signature = signature
        self.delete("all")
        if fast:
            self._draw_round_rect(1, 1, w - 2, h - 2, self.radius, bg, outline)
        else:
            try:
                key = (w, h, self.radius, outer, bg, outline)
                if key not in self._surface_photos:
                    surface = _cached_button_surface(*key)
                    self._surface_photos[key] = ImageTk.PhotoImage(surface, master=self)
                    if len(self._surface_photos) > 6:
                        self._surface_photos.popitem(last=False)
                self._surface_photos.move_to_end(key)
                self._surface_photo = self._surface_photos[key]
                self.create_image(0, 0, anchor="nw", image=self._surface_photo)
            except (OSError, tk.TclError, TypeError, ValueError):
                self._draw_round_rect(1, 1, w - 2, h - 2, self.radius, bg, outline)

        x = w // 2
        if self.image:
            image_x = 24 if self.text else x
            self.create_image(image_x, h // 2, image=self.image)
            if self.text:
                self.create_text(
                    image_x + 24,
                    h // 2,
                    text=self.text,
                    fill=fg,
                    font=self.font,
                    anchor="w",
                    width=max(20, w - image_x - 34),
                    justify="left"
                )
        else:
            anchor = "w" if self.anchor == "w" else "center"
            text_x = 16 if anchor == "w" else x
            self.create_text(
                text_x,
                h // 2,
                text=self.text,
                fill=fg,
                font=self.font,
                anchor=anchor,
                width=max(20, w - 18),
                justify="left" if anchor == "w" else "center"
            )
