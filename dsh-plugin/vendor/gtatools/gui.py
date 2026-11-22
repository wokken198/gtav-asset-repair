"""Tkinter front-end for gtatools: badge diffuse -> tangent-space normal map.

One window, no console. Two languages (EN / 中文) and two themes (light / dark)
switchable from the header. Defaults: light theme, Chinese.

DDS encode/decode is delegated to texconv.exe. When frozen as a single exe the
binary is unpacked next to the program, so nothing has to be installed.
"""

from __future__ import annotations

import json
import os
import queue
import sys
import tempfile
import threading
import tkinter as tk
import uuid
from tkinter import filedialog, ttk

import numpy as np
from PIL import Image, ImageTk

from . import dds as ddsmod
from .normals import height_field, normal_from_height, shade_preview

APP_TITLE = "gtatools - badge normal maps"
VERSION = "0.4.0"

LANG = {
    "en": {
        "tagline": "badge normal maps",
        "nav.normal": "Normal map",
        "nav.scale": "Scale",
        "nav.mip": "Mip check",
        "nav.ytd": "YTD list",
        "title": "Badge normal map",
        "subtitle": "pick files or a folder, tune the slope, write next to the input",
        "files": "Files",
        "params": "Parameters",
        "preview": "Preview",
        "log": "Log",
        "add_files": "Add files",
        "add_folder": "Add folder",
        "clear": "Clear",
        "remove": "Remove",
        "strength": "Strength",
        "blur": "Blur",
        "alpha": "Alpha weight",
        "format": "Format",
        "resize": "Resize long edge",
        "maxmips": "Max mips",
        "out_hint": "output -> <input folder>\\normals\\",
        "generate": "Generate",
        "cancel": "Cancel",
        "idle": "idle",
        "files_n": "{n} file(s)",
        "nothing": "nothing to do: add files first",
        "added": "added {n} file(s)",
        "cancelling": "cancelling...",
        "processing": "{n} processed",
        "done": "done: {made} written, {failed} failed",
        "cancelled": "cancelled: {made} written, {failed} failed",
        "light": "Light",
        "dark": "Dark",
        "pick": "Pick badge diffuse maps",
        "pick_dir": "Pick a folder",
        "no_preview": "select a file to preview",
        "missing_texconv": "texconv.exe not found - put it next to this program or set TEXCONV",
    },
    "zh": {
        "tagline": "车标法线",
        "nav.normal": "法线生成",
        "nav.scale": "缩放",
        "nav.mip": "Mip 检查",
        "nav.ytd": "YTD 列表",
        "title": "车标法线",
        "subtitle": "选择文件或文件夹，调整参数，结果写到输入所在目录",
        "files": "文件",
        "params": "参数",
        "preview": "预览",
        "log": "日志",
        "add_files": "添加文件",
        "add_folder": "添加文件夹",
        "clear": "清空",
        "remove": "移除",
        "strength": "强度",
        "blur": "模糊",
        "alpha": "Alpha 权重",
        "format": "格式",
        "resize": "缩放长边",
        "maxmips": "最大 mip",
        "out_hint": "输出 -> <输入目录>\\normals\\",
        "generate": "开始生成",
        "cancel": "取消",
        "idle": "空闲",
        "files_n": "{n} 个文件",
        "nothing": "没有可处理的内容：先添加文件",
        "added": "已添加 {n} 个文件",
        "cancelling": "正在取消...",
        "processing": "已处理 {n} 个",
        "done": "完成：写出 {made} 个，失败 {failed} 个",
        "cancelled": "已取消：写出 {made} 个，失败 {failed} 个",
        "light": "浅色",
        "dark": "深色",
        "pick": "选择车标漫反射贴图",
        "pick_dir": "选择文件夹",
        "no_preview": "选择一个文件以预览",
        "missing_texconv": "找不到 texconv.exe：放到本程序旁边，或设置 TEXCONV",
    },
}

THEMES = {
    "light": dict(bg="#f5f6f8", nav="#eceef2", card="#ffffff", hover="#eef1f5", inset="#f2f4f7",
                  stroke="#d9dde4", stroke_hi="#b5bcc7", fg="#15181d", dim="#4a5361",
                  faint="#8b93a1", accent="#0f9d67", accent_dark="#0b7a50", on_accent="#ffffff",
                  green="#0f8f5f", danger="#d32f45", warning="#a9731b", track="#e2e5eb"),
    "dark": dict(bg="#090a0c", nav="#060709", card="#111317", hover="#171b21", inset="#07080a",
                 stroke="#272c34", stroke_hi="#48515e", fg="#f4f6f9", dim="#a3aab5",
                 faint="#5b6471", accent="#34d094", accent_dark="#14885e", on_accent="#17130a",
                 green="#45e09a", danger="#ff4858", warning="#ffbe4b", track="#2b3039"),
}

FORMATS = ["DXT1", "DXT5", "BC5_UNORM", "BC7_UNORM"]
RESIZE_CHOICES = ["keep", "2048", "1536", "1024", "512", "256"]
MIP_CHOICES = ["full", "12", "10", "9", "8"]


def _config_dir() -> str:
    root = os.environ.get("APPDATA") or os.path.expanduser("~")
    return os.path.join(root, "gtatools")


def load_config() -> dict:
    try:
        with open(os.path.join(_config_dir(), "gui.json"), "r", encoding="utf-8") as fh:
            return json.load(fh)
    except Exception:
        return {}


def save_config(cfg: dict) -> None:
    try:
        os.makedirs(_config_dir(), exist_ok=True)
        with open(os.path.join(_config_dir(), "gui.json"), "w", encoding="utf-8") as fh:
            json.dump(cfg, fh, indent=2, ensure_ascii=False)
    except Exception:
        pass


def _font(size: int, bold: bool = False):
    family = "Microsoft YaHei UI" if sys.platform == "win32" else "Helvetica"
    return (family, size, "bold") if bold else (family, size)


def _mono(size: int):
    return ("Consolas" if sys.platform == "win32" else "Menlo", size)


class Card(tk.Frame):
    """A 1px-bordered panel with a small caps title and a padded body."""

    def __init__(self, master, app: "App", title_key: str = ""):
        super().__init__(master, bg=app.c("card"), highlightbackground=app.c("stroke"),
                         highlightthickness=1, bd=0)
        self.app = app
        self.title = tk.Label(self, text="", bg=app.c("card"), fg=app.c("faint"), font=_font(9, True))
        self.title.place(x=14, y=11)
        self.body = tk.Frame(self, bg=app.c("card"))
        self.body.pack(fill="both", expand=True, padx=14, pady=(32, 14))
        app.style_widget(self, "card")
        app.style_widget(self.title, "card", "faint")
        app.style_widget(self.body, "card")
        if title_key:
            app.bind_text(self.title, title_key)


class Slider(tk.Frame):
    def __init__(self, master, app: "App", key: str, lo: float, hi: float, step: float, value: float):
        super().__init__(master, bg=app.c("card"))
        self.app, self.key, self.step = app, key, step
        self.value = tk.DoubleVar(value=value)
        row = tk.Frame(self, bg=app.c("card"))
        row.pack(fill="x")
        self.label = tk.Label(row, text=app.t(key), bg=app.c("card"), fg=app.c("dim"), font=_font(10))
        self.label.pack(side="left")
        self.shown = tk.Label(row, text=f"{value:.2f}", bg=app.c("card"), fg=app.c("fg"), font=_mono(10))
        self.shown.pack(side="right")
        self.scale = ttk.Scale(self, from_=lo, to=hi, variable=self.value, command=self._changed,
                               orient="horizontal", style="Pav.Horizontal.TScale")
        self.scale.pack(fill="x", pady=(3, 0))
        for w in (self, row):
            app.style_widget(w, "card")
        app.style_widget(self.label, "card", "dim")
        app.style_widget(self.shown, "card", "fg")
        app.bind_text(self.label, key)

    def _changed(self, _=None):
        v = float(self.value.get())
        if self.step:
            v = round(round(v / self.step) * self.step, 2)
        self.shown.configure(text=f"{v:.2f}")


class App(tk.Tk):
    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.lang = self.cfg.get("lang", "zh")
        self.theme = self.cfg.get("theme", "light")
        if self.lang not in LANG:
            self.lang = "zh"
        if self.theme not in THEMES:
            self.theme = "light"

        self.files: list[str] = []
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.worker = None
        self.style_widgets: list[tuple] = []
        self.text_bindings: list[tuple] = []
        self.lang_buttons: dict = {}
        self.theme_buttons: dict = {}
        self.texconv = ddsmod.resolve_texconv(os.environ.get("TEXCONV", "texconv.exe"))

        self.title(APP_TITLE)
        self.geometry("1220x800")
        self.minsize(1120, 700)
        self.configure(bg=self.c("bg"))
        self._set_icon()

        style = ttk.Style(self)
        style.theme_use("clam")
        self.option_add("*TCombobox*Listbox.background", self.c("inset"))
        self.option_add("*TCombobox*Listbox.foreground", self.c("fg"))
        self.option_add("*TCombobox*Listbox.selectBackground", self.c("hover"))
        self.option_add("*TCombobox*Listbox.selectForeground", self.c("fg"))

        self._build()
        self._apply_theme()
        self._apply_lang()
        self._refresh_count()
        self._draw_preview()
        self.after(80, self._pump)

    # ------------------------------------------------------------------ utils
    def c(self, key: str) -> str:
        return THEMES[self.theme][key]

    def t(self, key: str, **kw) -> str:
        text = LANG[self.lang].get(key, LANG["en"].get(key, key))
        return text.format(**kw) if kw else text

    def style_widget(self, widget, bg_key=None, fg_key=None):
        self.style_widgets.append((widget, bg_key, fg_key))

    def bind_text(self, widget, key):
        self.text_bindings.append((widget, key))
        widget.configure(text=self.t(key))
        return widget

    def _set_icon(self):
        base = getattr(sys, "_MEIPASS", None) or os.path.dirname(os.path.dirname(os.path.dirname(
            os.path.abspath(__file__))))
        ico = os.path.join(base, "resources", "gtatools.ico")
        if os.path.isfile(ico):
            try:
                self.iconbitmap(ico)
            except Exception:
                pass

    def _apply_theme(self):
        for widget, bg_key, fg_key in self.style_widgets:
            opts = {}
            if bg_key:
                opts["bg"] = self.c(bg_key)
            if fg_key:
                opts["fg"] = self.c(fg_key)
            try:
                widget.configure(**opts)
            except tk.TclError:
                pass

        self.configure(bg=self.c("bg"))
        for name, key in (("_nav", "nav"), ("_main", "bg")):
            pass
        try:
            self._nav.configure(bg=self.c("nav"))
            self._main.configure(bg=self.c("bg"))
        except Exception:
            pass
        try:
            self.listbox.configure(bg=self.c("inset"), fg=self.c("dim"),
                                   selectbackground=self.c("hover"), selectforeground=self.c("fg"))
            self.log.configure(bg=self.c("inset"), fg=self.c("dim"), insertbackground=self.c("fg"))
            self.preview.configure(bg=self.c("inset"))
        except Exception:
            pass

        for code, btn in self.lang_buttons.items():
            active = code == self.lang
            btn.configure(bg=self.c("hover") if active else self.c("inset"),
                          fg=self.c("fg") if active else self.c("faint"))
        for code, btn in self.theme_buttons.items():
            active = code == self.theme
            btn.configure(bg=self.c("hover") if active else self.c("inset"),
                          fg=self.c("fg") if active else self.c("faint"),
                          text=self.t(code))

        style = ttk.Style(self)
        style.configure("TCombobox", fieldbackground=self.c("inset"), background=self.c("card"),
                        foreground=self.c("fg"), arrowcolor=self.c("dim"),
                        bordercolor=self.c("stroke"), lightcolor=self.c("card"),
                        darkcolor=self.c("card"), selectbackground=self.c("hover"),
                        selectforeground=self.c("fg"), padding=3)
        style.map("TCombobox", fieldbackground=[("readonly", self.c("inset"))],
                  foreground=[("readonly", self.c("fg"))],
                  bordercolor=[("focus", self.c("stroke_hi"))])
        style.configure("Pav.Horizontal.TProgressbar", background=self.c("accent"),
                        troughcolor=self.c("track"), bordercolor=self.c("track"),
                        lightcolor=self.c("accent"), darkcolor=self.c("accent"), thickness=6)
        style.configure("Pav.Horizontal.TScale", background=self.c("card"),
                        troughcolor=self.c("track"), bordercolor=self.c("card"),
                        lightcolor=self.c("accent"), darkcolor=self.c("accent"))
        self._draw_preview()

    def _apply_lang(self):
        for widget, key in self.text_bindings:
            try:
                widget.configure(text=self.t(key))
            except tk.TclError:
                pass
        for code, btn in self.theme_buttons.items():
            btn.configure(text=self.t(code))
        if getattr(self, "status", None) is not None and not self.running:
            self.status.configure(text=self.t("idle"))

    def set_lang(self, code: str):
        if code == self.lang:
            return
        self.lang = code
        self._apply_lang()
        self._apply_theme()
        self._refresh_count()
        self._save()

    def set_theme(self, code: str):
        if code == self.theme:
            return
        self.theme = code
        self._apply_theme()
        self._save()

    def _save(self):
        self.cfg.update(dict(lang=self.lang, theme=self.theme,
                             strength=float(self.sl_strength.value.get()),
                             blur=float(self.sl_blur.value.get()),
                             alpha=float(self.sl_alpha.value.get()),
                             fmt=self.fmt.get(), resize=self.resize.get(),
                             maxmips=self.max_mips.get()))
        save_config(self.cfg)

    # ---------------------------------------------------------------- widgets
    def _button(self, master, text, command, primary=False):
        bg = self.c("accent") if primary else self.c("card")
        fg = self.c("on_accent") if primary else self.c("fg")
        btn = tk.Button(master, text=text, command=command, bg=bg, fg=fg, bd=0, relief="flat",
                        padx=16, pady=7, font=_font(10, primary),
                        activebackground=self.c("accent_dark") if primary else self.c("hover"),
                        activeforeground=fg, cursor="hand2", highlightthickness=0)
        self.style_widget(btn, "accent" if primary else "card", "on_accent" if primary else "fg")
        return btn

    def _combo(self, master, key, var, values):
        row = tk.Frame(master, bg=self.c("card"))
        row.pack(fill="x", pady=(0, 8))
        self.style_widget(row, "card")
        label = self.bind_text(tk.Label(row, text="", bg=self.c("card"), fg=self.c("dim"),
                                        font=_font(10)), key)
        label.pack(side="left")
        self.style_widget(label, "card", "dim")
        ttk.Combobox(row, textvariable=var, values=values, state="readonly",
                     width=12).pack(side="right")

    def _build(self):
        self._nav = tk.Frame(self, bg=self.c("nav"), width=196)
        self._nav.pack(side="left", fill="y")
        self._nav.pack_propagate(False)
        brand = tk.Label(self._nav, text="gtatools", bg=self.c("nav"), fg=self.c("fg"), font=_font(15, True))
        brand.pack(anchor="w", padx=18, pady=(20, 2))
        self.style_widget(brand, "nav", "fg")
        tag = self.bind_text(tk.Label(self._nav, text="", bg=self.c("nav"), fg=self.c("faint"),
                                      font=_font(9)), "tagline")
        tag.pack(anchor="w", padx=18, pady=(0, 18))
        self.style_widget(tag, "nav", "faint")

        for key, active in (("nav.normal", True), ("nav.scale", False),
                            ("nav.mip", False), ("nav.ytd", False)):
            row = tk.Frame(self._nav, bg=self.c("hover") if active else self.c("nav"))
            row.pack(fill="x", padx=10, pady=2)
            accent = tk.Frame(row, bg=self.c("accent") if active else self.c("nav"), width=2)
            accent.pack(side="left", fill="y")
            lab = self.bind_text(tk.Label(row, text="", bg=self.c("hover") if active else self.c("nav"),
                                          fg=self.c("fg") if active else self.c("faint"),
                                          font=_font(10, active)), key)
            lab.pack(anchor="w", padx=12, pady=8)
            if active:
                self.style_widget(row, "hover")
                self.style_widget(lab, "hover", "fg")
            else:
                self.style_widget(row, "nav")
                self.style_widget(lab, "nav", "faint")

        ver = tk.Label(self._nav, text=f"v{VERSION}", bg=self.c("nav"), fg=self.c("faint"), font=_font(9))
        ver.pack(side="bottom", anchor="w", padx=18, pady=14)
        self.style_widget(ver, "nav", "faint")

        self._main = tk.Frame(self, bg=self.c("bg"))
        self._main.pack(side="left", fill="both", expand=True, padx=(18, 18), pady=(16, 16))
        self.style_widget(self._main, "bg")

        head = tk.Frame(self._main, bg=self.c("bg"))
        head.pack(fill="x")
        self.style_widget(head, "bg")
        titles = tk.Frame(head, bg=self.c("bg"))
        titles.pack(side="left", fill="x", expand=True)
        self.style_widget(titles, "bg")
        h1 = self.bind_text(tk.Label(titles, text="", bg=self.c("bg"), fg=self.c("fg"),
                                     font=_font(17, True)), "title")
        h1.pack(anchor="w")
        self.style_widget(h1, "bg", "fg")
        sub = self.bind_text(tk.Label(titles, text="", bg=self.c("bg"), fg=self.c("faint"),
                                      font=_font(10)), "subtitle")
        sub.pack(anchor="w", pady=(2, 0))
        self.style_widget(sub, "bg", "faint")

        toggles = tk.Frame(head, bg=self.c("bg"))
        toggles.pack(side="right", anchor="n")
        self.style_widget(toggles, "bg")
        for code, label in (("en", "EN"), ("zh", "\u4e2d\u6587")):
            b = tk.Label(toggles, text=label, bg=self.c("inset"), fg=self.c("faint"),
                         font=_font(9, True), padx=10, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 2))
            b.bind("<Button-1>", lambda _e, x=code: self.set_lang(x))
            self.lang_buttons[code] = b
        tk.Frame(toggles, bg=self.c("stroke"), width=1).pack(side="left", fill="y", padx=8)
        for code in ("light", "dark"):
            b = tk.Label(toggles, text=self.t(code), bg=self.c("inset"), fg=self.c("faint"),
                         font=_font(9, True), padx=10, pady=4, cursor="hand2")
            b.pack(side="left", padx=(0, 2))
            b.bind("<Button-1>", lambda _e, x=code: self.set_theme(x))
            self.theme_buttons[code] = b

        body = tk.Frame(self._main, bg=self.c("bg"))
        body.pack(fill="both", expand=True, pady=(14, 0))
        self.style_widget(body, "bg")

        params = Card(body, self, "params")
        params.configure(width=352)
        params.pack(side="right", fill="y", padx=(12, 0))
        params.pack_propagate(False)
        pbody = params.body

        files = Card(body, self, "files")
        files.pack(side="left", fill="both", expand=True)

        btnrow = tk.Frame(files.body, bg=self.c("card"))
        btnrow.pack(fill="x")
        self.style_widget(btnrow, "card")
        self.bind_text(self._button(btnrow, "", self.pick_files, primary=True), "add_files").pack(side="left")
        self.bind_text(self._button(btnrow, "", self.pick_folder), "add_folder").pack(side="left", padx=8)
        self.bind_text(self._button(btnrow, "", self.clear_files), "clear").pack(side="left")
        self.bind_text(self._button(btnrow, "", self.remove_selected), "remove").pack(side="right")

        wrap = tk.Frame(files.body, bg=self.c("inset"), highlightbackground=self.c("stroke"),
                        highlightthickness=1)
        wrap.pack(fill="both", expand=True, pady=(10, 0))
        self.style_widget(wrap, "inset")
        self.listbox = tk.Listbox(wrap, bg=self.c("inset"), fg=self.c("dim"),
                                  selectbackground=self.c("hover"), selectforeground=self.c("fg"),
                                  highlightthickness=0, bd=0, font=_mono(9), activestyle="none")
        sb = tk.Scrollbar(wrap, command=self.listbox.yview, bg=self.c("inset"),
                          troughcolor=self.c("inset"), highlightthickness=0, bd=0)
        self.listbox.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.listbox.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._draw_preview())
        self.count_label = tk.Label(files.body, text="", bg=self.c("card"), fg=self.c("faint"),
                                    font=_font(9))
        self.count_label.pack(anchor="w", pady=(8, 0))
        self.style_widget(self.count_label, "card", "faint")

        cfg = self.cfg
        self.sl_strength = Slider(pbody, self, "strength", 0.5, 12.0, 0.1,
                                  float(cfg.get("strength", 6.5)))
        self.sl_strength.pack(fill="x", pady=(0, 10))
        self.sl_blur = Slider(pbody, self, "blur", 0.0, 4.0, 0.1, float(cfg.get("blur", 1.2)))
        self.sl_blur.pack(fill="x", pady=(0, 10))
        self.sl_alpha = Slider(pbody, self, "alpha", 0.0, 1.0, 0.05, float(cfg.get("alpha", 0.3)))
        self.sl_alpha.pack(fill="x", pady=(0, 14))

        self.fmt = tk.StringVar(value=cfg.get("fmt", "DXT1"))
        self._combo(pbody, "format", self.fmt, FORMATS)
        self.resize = tk.StringVar(value=cfg.get("resize", "keep"))
        self._combo(pbody, "resize", self.resize, RESIZE_CHOICES)
        self.max_mips = tk.StringVar(value=cfg.get("maxmips", "full"))
        self._combo(pbody, "maxmips", self.max_mips, MIP_CHOICES)

        hint = self.bind_text(tk.Label(pbody, text="", bg=self.c("card"), fg=self.c("faint"),
                                       font=_font(9), anchor="w", justify="left",
                                       wraplength=300), "out_hint")
        hint.pack(fill="x", pady=(2, 0))
        self.style_widget(hint, "card", "faint")

        footer = tk.Frame(self._main, bg=self.c("bg"))
        footer.pack(fill="x", pady=(12, 0))
        self.style_widget(footer, "bg")
        self.run_btn = self.bind_text(self._button(footer, "", self.run, primary=True), "generate")
        self.run_btn.pack(side="left")
        self.cancel_btn = self.bind_text(self._button(footer, "", self.cancel_run), "cancel")
        self.cancel_btn.pack(side="left", padx=8)
        self.cancel_btn.configure(state="disabled")
        self.progress = ttk.Progressbar(footer, style="Pav.Horizontal.TProgressbar",
                                        orient="horizontal", mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=14)
        self.status = tk.Label(footer, text="", bg=self.c("bg"), fg=self.c("faint"),
                               font=_font(9), anchor="e")
        self.status.pack(side="right")
        self.style_widget(self.status, "bg", "faint")

        bottom = tk.Frame(self._main, bg=self.c("bg"), height=250)
        bottom.pack(fill="x", pady=(12, 0))
        bottom.pack_propagate(False)
        self.style_widget(bottom, "bg")

        logs = Card(bottom, self, "log")
        logs.configure(width=352)
        logs.pack(side="right", fill="both", padx=(12, 0))
        logs.pack_propagate(False)
        self.log = tk.Text(logs.body, bg=self.c("inset"), fg=self.c("dim"), insertbackground=self.c("fg"),
                           bd=0, highlightthickness=0, font=_mono(9), wrap="none", height=10)
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        prev = Card(bottom, self, "preview")
        prev.pack(side="left", fill="both", expand=True)
        self.preview = tk.Canvas(prev.body, bg=self.c("inset"), highlightthickness=0, height=170)
        self.preview.pack(fill="both", expand=True)

    # ------------------------------------------------------------- file list
    def pick_files(self):
        paths = filedialog.askopenfilenames(title=self.t("pick"),
                                            filetypes=[("DDS textures", "*.dds"), ("All files", "*.*")])
        if paths:
            self.add_files(list(paths))

    def pick_folder(self):
        folder = filedialog.askdirectory(title=self.t("pick_dir"))
        if not folder:
            return
        found = []
        for root, _dirs, names in os.walk(folder):
            for name in names:
                if name.lower().endswith(".dds"):
                    found.append(os.path.join(root, name))
        self.add_files(sorted(found))

    def add_files(self, paths):
        added = 0
        for p in paths:
            if p not in self.files:
                self.files.append(p)
                added += 1
        self._refresh_count()
        if added:
            self.log_line(self.t("added", n=added))

    def clear_files(self):
        self.files.clear()
        self._refresh_count()
        self._draw_preview()

    def remove_selected(self):
        for idx in reversed(list(self.listbox.curselection())):
            if 0 <= idx < len(self.files):
                self.files.pop(idx)
        self._refresh_count()
        self._draw_preview()

    def _refresh_count(self):
        self.listbox.delete(0, "end")
        for p in self.files:
            self.listbox.insert("end", os.path.basename(p))
        self.count_label.configure(text=self.t("files_n", n=len(self.files)))

    def selected_file(self):
        sel = self.listbox.curselection()
        if sel and sel[0] < len(self.files):
            return self.files[sel[0]]
        return self.files[0] if self.files else None

    # --------------------------------------------------------------- preview
    def _draw_preview(self):
        canvas = getattr(self, "preview", None)
        if canvas is None:
            return
        canvas.delete("all")
        w = max(canvas.winfo_width(), 260)
        h = max(canvas.winfo_height(), 120)
        path = self.selected_file()
        if not path:
            canvas.create_text(w // 2, h // 2, text=self.t("no_preview"),
                               fill=self.c("faint"), font=_font(9))
            return
        try:
            rgba = self._load_preview_rgba(path)
            alpha_w = float(self.sl_alpha.value.get())
            hf = height_field(rgba, luma_weight=1.0 - alpha_w, mask_weight=alpha_w,
                              blur=float(self.sl_blur.value.get()))
            nrm = normal_from_height(hf, strength=float(self.sl_strength.value.get()))
            lit = shade_preview(rgba, nrm)
            tiles = [self._to_rgb(rgba), Image.fromarray(nrm, "RGB"),
                     Image.fromarray((lit * 255).astype(np.uint8), "RGB")]
            gap = 8
            tw = max(48, (w - gap * 4) // 3)
            th = max(48, h - gap * 2)
            sheet = Image.new("RGB", (w, h), self.c("inset"))
            for i, tile in enumerate(tiles):
                img = tile.copy()
                img.thumbnail((tw, th), Image.LANCZOS)
                sheet.paste(img, (gap + i * (tw + gap) + (tw - img.size[0]) // 2,
                                  (h - img.size[1]) // 2))
            self._photo = ImageTk.PhotoImage(sheet)
            canvas.create_image(0, 0, image=self._photo, anchor="nw")
        except Exception as exc:  # noqa: BLE001
            canvas.create_text(w // 2, h // 2, text=str(exc)[:90],
                               fill=self.c("danger"), font=_font(9))

    def _to_rgb(self, rgba: np.ndarray) -> Image.Image:
        im = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        return bg.convert("RGB")

    def _scratch(self, near: str) -> str:
        base = os.path.dirname(os.path.abspath(near)) if os.path.isfile(near) else os.path.abspath(near)
        root = os.path.join(base, ".gtatools_tmp")
        try:
            os.makedirs(root, exist_ok=True)
            work = os.path.join(root, "run-" + uuid.uuid4().hex[:10])
            os.makedirs(work, exist_ok=True)
            return work
        except OSError:
            return tempfile.mkdtemp(prefix="gtatools-")

    def _cleanup(self, path: str):
        import shutil
        shutil.rmtree(path, ignore_errors=True)

    def _load_preview_rgba(self, path: str) -> np.ndarray:
        tmp = self._scratch(path)
        try:
            try:
                ddsmod.decode(tmp, [path], self.texconv)
            except Exception as exc:  # noqa: BLE001
                if not os.path.isfile(self.texconv):
                    raise RuntimeError(self.t("missing_texconv")) from exc
                raise
            pngs = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.lower().endswith(".png")]
            if not pngs:
                raise RuntimeError(self.t("missing_texconv"))
            return np.asarray(Image.open(pngs[0]).convert("RGBA")).astype(np.float32) / 255.0
        finally:
            self._cleanup(tmp)

    # ------------------------------------------------------------------- run
    def log_line(self, text: str):
        self.log.configure(state="normal")
        self.log.insert("end", text + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def run(self):
        if self.running:
            return
        if not self.files:
            self.status.configure(text=self.t("nothing"))
            return
        if not os.path.isfile(self.texconv):
            self.status.configure(text=self.t("missing_texconv"))
            return
        self._save()
        self.running = True
        self.cancel.clear()
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=len(self.files))
        self.status.configure(text=self.t("processing", n=0))
        self.worker = threading.Thread(target=self._work, daemon=True)
        self.worker.start()

    def cancel_run(self):
        self.cancel.set()
        self.status.configure(text=self.t("cancelling"))

    def _work(self):
        made = failed = 0
        fmt = self.fmt.get()
        strength = float(self.sl_strength.value.get())
        blur = float(self.sl_blur.value.get())
        alpha_w = float(self.sl_alpha.value.get())
        resize = self.resize.get()
        max_mips = self.max_mips.get()
        total = len(self.files)
        for idx, path in enumerate(list(self.files), 1):
            if self.cancel.is_set():
                break
            try:
                self._one(path, fmt, strength, blur, alpha_w, resize, max_mips)
                made += 1
                self.queue.put(("ok", path))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.queue.put(("fail", f"{os.path.basename(path)}: {exc}"))
            self.queue.put(("progress", (idx, total)))
        self.queue.put(("done", (made, failed)))

    def _one(self, path, fmt, strength, blur, alpha_w, resize, max_mips):
        tmp = self._scratch(path)
        try:
            ddsmod.decode(tmp, [path], self.texconv)
            pngs = [os.path.join(tmp, f) for f in os.listdir(tmp) if f.lower().endswith(".png")]
            if not pngs:
                raise RuntimeError("decode produced no png")
            im = Image.open(pngs[0]).convert("RGBA")
            if resize != "keep":
                target = int(resize)
                long_edge = max(im.size)
                if target < long_edge:
                    scale = target / long_edge
                    size = (max(1, round(im.size[0] * scale)), max(1, round(im.size[1] * scale)))
                    rgb = im.convert("RGB").resize(size, Image.LANCZOS)
                    al = im.getchannel("A").resize(size, Image.LANCZOS)
                    im = rgb.convert("RGBA")
                    im.putalpha(al)
            rgba = np.asarray(im).astype(np.float32) / 255.0
            hf = height_field(rgba, luma_weight=1.0 - alpha_w, mask_weight=alpha_w, blur=blur)
            nrm = normal_from_height(hf, strength=strength)
            out_png = os.path.join(tmp, "normal.png")
            Image.fromarray(nrm, "RGB").save(out_png)
            mips = 0 if max_mips == "full" else int(max_mips)
            produced = ddsmod.encode(out_png, fmt, mips, tmp, self.texconv)
            dest_dir = os.path.join(os.path.dirname(os.path.abspath(path)), "normals")
            os.makedirs(dest_dir, exist_ok=True)
            stem = os.path.splitext(os.path.basename(path))[0]
            dest = os.path.join(dest_dir, f"{stem}_n.dds")
            os.replace(produced, dest)
            return dest
        finally:
            self._cleanup(tmp)

    def _pump(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "progress":
                    idx, total = payload
                    self.progress.configure(value=idx)
                    self.status.configure(text=self.t("processing", n=idx))
                elif kind == "ok":
                    self.log_line("ok  " + os.path.basename(payload))
                elif kind == "fail":
                    self.log_line("err " + payload)
                elif kind == "done":
                    made, failed = payload
                    key = "cancelled" if self.cancel.is_set() else "done"
                    self.status.configure(text=self.t(key, made=made, failed=failed))
                    self.running = False
                    self.run_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(80, self._pump)


def main():
    App().mainloop()


if __name__ == "__main__":
    main()
