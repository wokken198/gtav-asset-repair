"""The MIP check and YTD compression pages.

Both pages share one idea: pick files on the left, read what is inside on the
right.  Reading a dictionary runs on worker threads so the UI stays responsive.
The only step that still needs CodeWalker is repacking an .rpf, because that is
what makes the freed space reach disk.
"""

import os
import queue
import tempfile
import threading
import tkinter as tk

from . import ped
from types import SimpleNamespace
from tkinter import ttk
from concurrent.futures import ThreadPoolExecutor
from tkinter import filedialog

from . import dds as ddsmod
from . import gen8to9, lite, rpf, settings, ytd as ytdmod
from .gui import Card, FileList, HelpDot, _font, _mono

SUFFIX_TEX = (".dds", ".ytd")
SUFFIX_YTD = (".ytd",)
SUFFIX_GEN8 = (".ytd", ".ydd", ".yft", ".ymt", ".yld")




def _size_of(path):
    try:
        return os.path.getsize(path)
    except OSError:
        return 0


def _human(size):
    if size >= 1048576:
        return "%.1f MB" % (size / 1048576.0)
    if size >= 1024:
        return "%.0f KB" % (size / 1024.0)
    return "%d B" % size


def _pick_files(app, title, patterns):
    paths = filedialog.askopenfilenames(parent=app, title=title, filetypes=patterns)
    return list(paths or [])


def _pick_dir(app, title):
    path = filedialog.askdirectory(parent=app, title=title)
    return path or ""


def _walk(folder, suffixes):
    found = []
    for root, dirs, files in os.walk(folder):
        dirs.sort()
        for name in sorted(files):
            if name.lower().endswith(suffixes):
                found.append(os.path.join(root, name))
    return found


def _inspect_one(path):
    """Read one dictionary; returns a small dict, never raises."""
    if path.lower().endswith(".dds"):
        # A loose DDS has one texture and no RSC7 wrapper, so the dictionary
        # reader cannot open it.  Read the header instead; the mip page treats
        # a .dds exactly like a one-texture dictionary.
        try:
            header = ddsmod.read_header(path)
        except Exception as exc:                              # noqa: BLE001
            return {"path": path, "error": str(exc), "textures": [], "version": 0,
                    "legacy": False}
        tex = SimpleNamespace(name=os.path.basename(path), width=header.width,
                              height=header.height, format=header.label,
                              mips=header.mips, bytes=_size_of(path))
        return {"path": path, "error": "", "textures": [tex], "version": 0,
                "legacy": False}
    try:
        version = ytdmod.rsc7_version(path)
        info = ytdmod.inspect([path])[0]
    except Exception as exc:                                  # noqa: BLE001
        return {"path": path, "error": str(exc), "textures": [], "version": 0}
    return {
        "path": path,
        "error": info.error or "",
        "textures": getattr(info, "textures", []) or [],
        "version": version,
        "legacy": version == ytdmod.YTD_VERSION_LEGACY,
    }


def _inspect_many(paths, workers=4, progress=None):
    """Inspect several dictionaries at once; `progress(done, total)` on the caller thread."""
    results = []
    total = max(1, len(paths))
    with ThreadPoolExecutor(max_workers=max(1, workers)) as pool:
        futures = [pool.submit(_inspect_one, p) for p in paths]
        for index, future in enumerate(futures, start=1):
            results.append(future.result())
            if progress:
                progress(index, total)
    return results


class _Page:
    suffixes = SUFFIX_TEX
    file_title = "files"

    def __init__(self, app, parent):
        self.app = app
        self.frame = tk.Frame(parent, bg=app.c("bg"))
        self.frame.pack(fill="both", expand=True)
        app.style_widget(self.frame, "bg")

        self.body = tk.Frame(self.frame, bg=app.c("bg"))
        self.body.pack(fill="both", expand=True)
        # Do not let the tallest column drive the page height: every page then fills the
        # window identically instead of the report-heavy pages pushing the file column
        # taller (or shorter) than the others.
        self.body.pack_propagate(False)
        app.style_widget(self.body, "bg")

        # left: files
        self.left = tk.Frame(self.body, bg=app.c("bg"), width=int(290 * app.sx))
        self.left.pack(side="left", fill="y", padx=(0, 12))
        self.left.pack_propagate(False)
        app.style_widget(self.left, "bg")

        self.card = Card(self.left, app, self.file_title)
        self.card.pack(fill="both", expand=True)

        # remove / clear live in the card header, right aligned, on every page
        self.head_tools = tk.Frame(self.card.head, bg=app.c("card"))
        self.head_tools.pack(side="right")
        app.style_widget(self.head_tools, "card")
        self.btn_clear = app._button(self.head_tools, app.t("clear"), self.clear, fixed=96)
        self.btn_clear.pack(side="right")
        app.bind_text(self.btn_clear, "clear")
        self.btn_remove = app._button(self.head_tools, app.t("remove"), self.remove_selected, fixed=96)
        self.btn_remove.pack(side="right", padx=(0, 6))
        app.bind_text(self.btn_remove, "remove")

        self.btnrow = tk.Frame(self.card.body, bg=app.c("card"))
        self.btnrow.pack(fill="x")
        app.style_widget(self.btnrow, "card")

        wrap = tk.Frame(self.card.body, bg=app.c("inset"),
                        highlightbackground=app.c("stroke"), highlightthickness=1)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        app.style_widget(wrap, "inset")
        self.listbox = FileList(wrap, app)
        self.listbox.pack(side="left", fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", self._on_pick_file)

        self.note = tk.Label(self.card.body, text="", bg=app.c("card"),
                             fg=app.c("faint"), font=_font(8), anchor="w")
        self.note.pack(fill="x", pady=(6, 0))
        app.style_widget(self.note, "card", "faint")

        # right: filled by the subclass
        self.right = tk.Frame(self.body, bg=app.c("bg"))
        self.right.pack(side="left", fill="both", expand=True)
        app.style_widget(self.right, "bg")

        self.files = []
        self.busy = False
        self.stop_flag = False
        self._payload = None
        self._events = queue.Queue()

    # -- file list -------------------------------------------------------
    def add_paths(self, paths):
        missing = 0
        for path in paths:
            path = os.path.abspath(path)
            if not os.path.isfile(path):
                missing += 1
                continue
            if path.lower().endswith(self.suffixes) and path not in self.files:
                self.files.append(path)
                self.listbox.insert("end", os.path.basename(path))
        if missing:
            self.app.log_line("skipped %d missing file(s)" % missing)
        self.note.configure(text="%d file(s)" % len(self.files) if self.files else "")
        self._after_add()

    def _after_add(self):
        pass

    def clear(self):
        self.files.clear()
        self.listbox.delete(0, "end")
        self.note.configure(text="")
        self._cleared()

    def remove_selected(self):
        picked = sorted(self.listbox.curselection(), reverse=True)
        for index in picked:
            self.listbox.delete(index)
            try:
                del self.files[index]
            except IndexError:
                pass
        self.note.configure(text="")
        self._after_remove()

    def _after_remove(self):
        self._cleared()

    def _cleared(self):
        pass

    def _on_pick_file(self, _event=None):
        pass

    def pick(self):
        raise NotImplementedError

    def pick_dir(self):
        raise NotImplementedError

    def _add_files(self):
        self.add_paths(self.pick())

    def _add_folder(self):
        self.add_paths(self.pick_dir())

    # -- worker plumbing -------------------------------------------------
    def spawn(self, work):
        if self.busy:
            return
        owner = getattr(self.app, "busy_owner", None)
        if owner not in (None, self):
            self.set_state(self.app.t("busy_other"))
            return
        self.app.busy_owner = self
        self.stop_flag = False
        self.busy = True
        self.set_state(self.app.t("state.busy"))

        def run():
            try:
                work()
            except Exception as exc:                          # noqa: BLE001
                self._events.put(("error", str(exc)))
            finally:
                self._events.put(("done", None))

        threading.Thread(target=run, daemon=True).start()
        self.frame.after(60, self._pump)

    def _pump(self):
        try:
            self._drain()
        except Exception as exc:                      # noqa: BLE001
            import traceback

            self.log_line("err page pump: " + traceback.format_exc().splitlines()[-1])
            self.busy = False
            self.set_state(str(exc))
            return
        if self.busy:
            self.frame.after(60, self._pump)

    def _drain(self):
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self.log_line(payload)
                elif kind == "error":
                    self.log_line("err " + payload)
                    self.set_state(payload)
                elif kind == "progress":
                    done, total = payload
                    self.set_bar(done, total)
                elif kind in ("scan", "plan", "report", "fixed"):
                    self._payload = (kind, payload)
                elif kind == "done":
                    self.busy = False
                    # Release the cross-page lock here, not in _finished(): subclasses
                    # override _finished() and would otherwise keep the app locked.
                    if getattr(self.app, "busy_owner", None) is self:
                        self.app.busy_owner = None
                    payload, self._payload = getattr(self, "_payload", None), None
                    self._finished(payload)
        except queue.Empty:
            pass

    def stop(self):
        """Cooperative stop: finished files stay, the rest is skipped."""
        if not self.busy:
            return
        self.stop_flag = True
        self.set_state(self.app.t("stopping"))
        self.log(self.app.t("report.stopped"))

    def log(self, text):
        self._events.put(("log", text))

    def tick(self, done, total):
        self._events.put(("progress", (done, total)))

    def _finished(self, payload=None):
        if getattr(self.app, "busy_owner", None) is self:
            self.app.busy_owner = None

    def retranslate(self):
        self._palette()

    def _palette(self):
        app = self.app
        for card in (self.card, getattr(self, "report_card", None)):
            if card is None:
                continue
            card.configure(bg=app.c("card"), highlightbackground=app.c("accent") if card.active
                           else app.c("stroke"))
            card.title.configure(bg=app.c("card"), fg=app.c("faint"))
            card.body.configure(bg=app.c("card"))
        try:
            self.listbox.configure(bg=app.c("inset"), fg=app.c("dim"),
                                   selectbackground=app.c("hover"), selectforeground=app.c("fg"))
        except tk.TclError:
            pass
        for widget in getattr(self, "_surfaces", []):
            try:
                widget.configure(bg=app.c("inset"))
            except tk.TclError:
                pass
        text = getattr(self, "text", None)
        if text is not None:
            try:
                text.configure(bg=app.c("inset"), fg=app.c("dim"), insertbackground=app.c("fg"))
            except tk.TclError:
                pass

    def log_line(self, text):
        self.app.log_line(text)

    def set_bar(self, done, total):
        pass

    def set_state(self, text):
        pass


class RichDesc(tk.Text):
    """Two-line description where {cap} renders bold, so the number reads as a variable."""

    def __init__(self, master, app, owner, lines=2):
        super().__init__(master, height=lines, width=10, wrap="word", bd=0, highlightthickness=0,
                         bg=app.c("card"), fg=app.c("faint"), font=_font(8), cursor="arrow",
                         takefocus=0, spacing1=1, spacing3=0)
        self.app = app
        self._owner = owner
        self.tag_configure("b", font=_font(8, True), foreground=app.c("fg"))
        self.configure(state="disabled")

    def bind_text(self, key, cap=False):
        self._key = key
        self._cap = cap
        self.retranslate()

    def retranslate(self):
        template = self.app.t(self._key)
        value = str(self._owner.cap.get()) if self._cap else ""
        self.configure(state="normal")
        self.delete("1.0", "end")
        if self._cap and "{cap}" in template:
            for index, part in enumerate(template.split("{cap}")):
                if index:
                    self.insert("end", value, "b")
                self.insert("end", part)
        else:
            self.insert("end", template)
        self.configure(state="disabled")

    def apply_theme(self):
        self.configure(bg=self.app.c("card"), fg=self.app.c("faint"))
        self.tag_configure("b", font=_font(8, True), foreground=self.app.c("fg"))


class ModePanel(tk.Frame):
    """Tier on its own row; the cap limit sits left of the two cards that use it."""

    def __init__(self, master, app, page):
        super().__init__(master, bg=app.c("bg"))
        self.app = app
        self.page = page
        self.cap = tk.IntVar(value=int(app.cfg.get("cap", 1024)))
        self.mode = app.cfg.get("mode", lite.MODE_CAP)
        if self.mode not in lite.MODES:
            self.mode = lite.MODE_CAP
        app.style_widget(self, "bg")

        tier = Card(self, app, "mode.tier")
        tier.pack(fill="x", pady=(0, 0))
        self.desc_tier = tk.Label(tier.body, text="", bg=app.c("card"), fg=app.c("faint"),
                                  font=_font(8), anchor="w", justify="left")
        self.desc_tier.pack(fill="x")
        app.style_widget(self.desc_tier, "card", "faint")
        app.bind_text(self.desc_tier, "mode.tier.desc")
        self.desc_tier.bind("<Configure>", lambda e: self.desc_tier.configure(wraplength=max(120, e.width - 8)))
        self._bind_card(tier, lite.MODE_TIER)
        self.card_tier = tier

        # Mode 4 sits under mode 1 and spans the same width: it never resizes, so it has
        # no business sharing the long-edge column.

        # three equal blocks side by side: the row is fixed height and splits its
        # width three ways, so the cards stay the same size whatever the window does
        # mode 1 across the top; below it a narrow "long edge" column on the left and
        # modes 2 + 3 stacked on the right, all four blocks the same height
        unit = int(80 * app.sx)

        tier.configure(height=unit)
        tier.pack_propagate(False)

        row = tk.Frame(self, bg=app.c("bg"), height=unit * 2 + 6)
        row.pack(fill="x", pady=(8, 0))
        row.pack_propagate(False)
        app.style_widget(row, "bg")

        card_limit = Card(row, app, "ytd.limit")
        card_limit.configure(width=int(150 * app.sx))
        card_limit.pack(side="left", fill="y")
        card_limit.pack_propagate(False)
        self.card_limit = card_limit
        self.limit_title = card_limit.title
        col = card_limit.body
        self.radios = []
        for value in (1024, 1536, 2048):
            rowf = tk.Frame(col, bg=app.c("card"), cursor="hand2")
            rowf.pack(fill="x", pady=2)
            app.style_widget(rowf, "card")
            dot = tk.Canvas(rowf, width=14, height=14, bg=app.c("card"), highlightthickness=0,
                            cursor="hand2")
            dot.pack(side="left")
            lab = tk.Label(rowf, text=str(value), bg=app.c("card"), fg=app.c("dim"),
                           font=_font(9), anchor="w", cursor="hand2")
            lab.pack(side="left", padx=(4, 0))
            app.style_widget(lab, "card", "dim")
            for widget in (rowf, dot, lab):
                widget.bind("<Button-1>", lambda _e, v=value: self.set_cap(v))
            self.radios.append((rowf, dot, lab))
        self.limit_hint = tk.Label(col, text="", bg=app.c("card"), fg=app.c("faint"),
                                   font=_font(7), anchor="w", justify="left", wraplength=110)
        self.limit_hint.pack(fill="x", pady=(6, 0))
        app.style_widget(self.limit_hint, "card", "faint")

        stack = tk.Frame(row, bg=app.c("bg"))
        stack.pack(side="left", fill="both", expand=True, padx=(6, 0))
        app.style_widget(stack, "bg")

        self.card_cap = Card(stack, app, "mode.cap")
        self.card_cap.pack(fill="both", expand=True)
        self.card_cap.pack_propagate(False)
        self.desc_cap = RichDesc(self.card_cap.body, app, self, lines=1)
        self.desc_cap.pack(fill="x", pady=(2, 0))
        self.desc_cap.bind_text("mode.cap.desc", cap=True)
        self._bind_card(self.card_cap, lite.MODE_CAP)

        self.card_agg = Card(stack, app, "mode.agg")
        self.card_agg.pack(fill="both", expand=True, pady=(6, 0))
        self.card_agg.pack_propagate(False)
        self.desc_agg = RichDesc(self.card_agg.body, app, self, lines=1)
        self.desc_agg.pack(fill="x", pady=(2, 0))
        self.desc_agg.bind_text("mode.agg.desc", cap=True)
        self._bind_card(self.card_agg, lite.MODE_AGGRESSIVE)

        self._refresh()

    def _bind_card(self, card, mode):
        def hit(_event=None):
            self.set_mode(mode)

        def walk(widget):
            try:
                widget.configure(cursor="hand2")
            except tk.TclError:
                pass
            widget.bind("<Button-1>", hit)
            for child in widget.winfo_children():
                walk(child)

        walk(card)

    # -- state -----------------------------------------------------------
    def value(self):
        return self.mode, int(self.cap.get())

    def set_mode(self, mode):
        if mode not in lite.MODES:
            return
        self.mode = mode
        self._refresh()
        self.page.mode_changed()

    def _limit_changed(self):
        self._refresh()
        self.page.mode_changed()

    def retranslate(self):
        for card, key in ((self.card_tier, "mode.tier"), (self.card_limit, "ytd.limit"),
                          (self.card_cap, "mode.cap"), (self.card_agg, "mode.agg")):
            card.title.configure(text=self.app.t(key))
        for widget in (self.desc_cap, self.desc_agg):
            widget.apply_theme()
            widget.retranslate()
        self._refresh()

    def _refresh(self):
        app = self.app
        tier = self.mode == lite.MODE_TIER
        for card in (self.card_tier, self.card_cap, self.card_agg):
            active = (card is self.card_tier and tier) or \
                     (card is self.card_cap and self.mode == lite.MODE_CAP) or \
                     (card is self.card_agg and self.mode == lite.MODE_AGGRESSIVE)
            if card.active != active:
                card.active = active
                card.paint()
        cap = int(self.cap.get())
        self.desc_cap.retranslate()
        self.desc_agg.retranslate()
        cap_now = int(self.cap.get())
        for value, (rowf, dot, lab) in zip((1024, 1536, 2048), self.radios):
            on = (value == cap_now) and not tier
            colour = app.c("faint") if tier else (app.c("fg") if on else app.c("dim"))
            lab.configure(fg=colour)
            dot.configure(bg=app.c("bg"))
            dot.delete("all")
            dot.create_oval(1, 1, 13, 13, outline=app.c("faint") if tier else app.c("stroke_hi"),
                            width=1, fill=app.c("bg"))
            if on:
                dot.create_oval(4, 4, 10, 10, outline="", fill=app.c("accent"))
        self.limit_hint.configure(text=app.t("ytd.limit_off") if tier else "")

    def set_cap(self, value):
        if self.mode == lite.MODE_TIER:
            return
        self.cap.set(int(value))
        self._limit_changed()


class MipsPage(_Page):
    suffixes = SUFFIX_TEX
    file_title = "mips.files"

    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.rows = []            # (file, name, width, height, fmt, have, need, rowid)
        self.checked = set()      # (file, name)
        self.scanned = {}         # path -> result dict
        self.filters = {
            "big": tk.BooleanVar(value=False),
            "raw": tk.BooleanVar(value=False),
            "mid": tk.BooleanVar(value=False),
            "alpha": tk.BooleanVar(value=False),
        }

        self.report_card = Card(self.right, app, "report")
        self.report_card.pack(fill="both", expand=True)

        tools = tk.Frame(self.report_card.body, bg=app.c("card"))
        tools.pack(fill="x")
        app.style_widget(tools, "card")
        self.filter_btn = tk.Menubutton(tools, text="", bg=app.c("card"), fg=app.c("dim"),
                                        activebackground=app.c("hover"), bd=0, relief="flat",
                                        font=_font(8), indicatoron=True, anchor="w", padx=8)
        app.bind_text(self.filter_btn, "mips.filter")
        self.menu = tk.Menu(self.filter_btn, tearoff=0)
        for kind, key in (("big", "mips.f_long"), ("raw", "mips.f_raw"),
                          ("mid", "mips.f_mid"), ("skip", "mips.f_skip")):
            self.menu.add_command(label=app.t(key), command=lambda k=kind: self.bulk(k))
        self.filter_btn.configure(menu=self.menu)
        self.filter_btn.pack(side="left")
        app._button(tools, app.t("mips.all"), self.select_all).pack(side="left", padx=(8, 0))
        app._button(tools, app.t("mips.none"), self.select_none).pack(side="left", padx=(6, 0))
        self.count = tk.Label(tools, text="", bg=app.c("card"), fg=app.c("faint"),
                              font=_font(8), anchor="e")
        self.count.pack(side="right")
        app.style_widget(self.count, "card", "faint")
        self.fix_btn = None

        wrap = tk.Frame(self.report_card.body, bg=app.c("inset"),
                        highlightbackground=app.c("stroke"), highlightthickness=1)
        wrap.pack(fill="both", expand=True, pady=(8, 0))
        app.style_widget(wrap, "inset")

        style = app.tree_style()
        self.tree = tk.ttk.Treeview(wrap, columns=("sel", "file", "tex", "size", "fmt", "mips"),
                                    show="headings", style=style, selectmode="none")
        for col, key, width in (("sel", "mips.c_sel", 30), ("file", "mips.c_file", 150),
                                ("tex", "mips.c_tex", 170), ("size", "mips.c_size", 92),
                                ("fmt", "mips.c_fmt", 92), ("mips", "mips.c_mips", 82)):
            self.tree.heading(col, text=app.t(key))
            self.tree.column(col, width=width, anchor="w", stretch=(col in ("tex", "file")))
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.tree.yview,
                           style=app.scroll_style())
        self.tree.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True, padx=6, pady=6)
        self.tree.tag_configure("missing", foreground=app.c("danger"))
        self.tree.tag_configure("ok", foreground=app.c("dim"))
        self.tree.tag_configure("fixed", foreground=app.c("green"))
        self.tree.tag_configure("odd", background=app.c("hover"))
        self.tree.tag_configure("even", background=app.c("inset"))
        self.tree.bind("<Button-1>", self._toggle_row)

        # the script_rt footnote lives in the Report header, not under the buttons:
        # that is what lets the button row and the bar sink to the bottom of the page
        note = tk.Frame(self.report_card.head, bg=app.c("card"))
        note.pack(side="right")
        app.style_widget(note, "card")
        hint = tk.Label(note, text="", bg=app.c("card"), fg=app.c("faint"), font=_font(8),
                        anchor="e", justify="right")
        hint.pack(side="left")
        app.style_widget(hint, "card", "faint")
        app.bind_text(hint, "mips.skip_note")
        HelpDot(note, app, "help.script_rt").pack(side="left", padx=(6, 0))

        action = tk.Frame(self.report_card.body, bg=app.c("card"))
        action.pack(fill="x", pady=(8, 0))
        app.style_widget(action, "card")
        self.actions = tk.Frame(action, bg=app.c("card"))
        self.actions.pack(fill="x")
        app.style_widget(self.actions, "card")
        app._button(self.actions, app.t("mips.check"), self.check, primary=True).pack(side="left")
        self.fix_btn = app._button(self.actions, app.t("mips.fix"), self.fix, primary=True)
        self.fix_btn.pack(side="left", padx=(8, 0))
        self.stop_btn = app._button(self.actions, app.t("cancel"), self.stop, kind="neutral")
        self.stop_btn.pack(side="left", padx=(8, 0))
        self.summary = tk.Label(action, text="", bg=app.c("card"), fg=app.c("dim"),
                                font=_font(9), anchor="w")
        self.summary.pack(fill="x", pady=(6, 0))

        app.style_widget(self.summary, "card", "dim")
        self.progress = tk.Frame(self.actions, bg=app.c("track"), height=6)
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.bar = tk.Frame(self.progress, bg=app.c("accent"), height=6)
        self.bar.place(x=0, y=0, relwidth=0.0, relheight=1.0)
        self.state = tk.Label(action, text="", bg=app.c("card"), fg=app.c("faint"),
                              font=_font(8), anchor="w", justify="left")
        self.state.pack(fill="x", pady=(4, 0))
        app.style_widget(self.state, "card", "faint")

        app._button(self.btnrow, app.t("mips.add_dir"), self._add_folder, fixed=128).pack(side="right")
        app._button(self.btnrow, app.t("mips.add"), self._add_files, primary=True, fixed=128).pack(side="right", padx=(0, 6))

    # -- files -----------------------------------------------------------
    def pick(self):
        return _pick_files(self.app, self.app.t("mips.add"), [("textures", "*.dds *.ytd"), ("all", "*.*")])

    def pick_dir(self):
        return _walk(_pick_dir(self.app, self.app.t("mips.add_dir")), self.suffixes)

    def _after_add(self):
        pass

    def _cleared(self):
        self.rows = []
        self.checked.clear()
        self.scanned.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        self.summary.configure(text="")
        self.state.configure(text="")
        self.set_bar(0, 1)

    def _on_pick_file(self, _event=None):
        sel = self.listbox.curselection()
        if not sel:
            return
        path = self.files[sel[0]]
        for file, _name, _w, _h, _f, _have, _need, rowid in self.rows:
            if file == path:
                self.tree.see(rowid)
                self.tree.selection_set(rowid)
                break

    # -- checking --------------------------------------------------------
    def check(self):
        if self.busy or not self.files:
            self.state.configure(text=self.app.t("mips.empty"))
            return
        files = list(self.files)

        def work():
            self.log("scanning %d file(s)" % len(files))
            results = _inspect_many(files, workers=4,
                                    progress=lambda done, total: self.tick(done, total))
            self.scanned = {res["path"]: res for res in results}
            self._events.put(("scan", None))

        self.spawn(work)

    def _on_scan_done(self):
        self.rows = []
        self.checked.clear()
        for item in self.tree.get_children():
            self.tree.delete(item)
        total = 0
        for path in self.files:
            res = self.scanned.get(path)
            if not res:
                continue
            for tex in res["textures"]:
                need = max(tex.width, tex.height).bit_length()
                have = tex.mips
                total += 1
                self.rows.append([path, tex.name, tex.width, tex.height, tex.format, have, need, None])
        self.render_rows()
        missing = sum(1 for row in self.rows if row[5] < row[6])
        self.summary.configure(text=self.app.t("mips.done", n=total, bad=missing, ok=total - missing))
        self.set_bar(1, 1)

    def _wanted(self, row):
        _file, name, width, height, fmt, have, need, _rowid = row
        long_side = max(width, height)
        if have >= need:
            return False
        if self.filters["big"].get() and long_side >= 1024 and (need - have) >= 3:
            return True
        if self.filters["raw"].get() and lite.BLOCK_BYTES.get(str(fmt).upper().replace("D3DFMT_", ""), 0) >= 4:
            return True
        if self.filters["mid"].get() and 512 <= long_side < 1024:
            return True
        if self.filters["alpha"].get() and "hair" in name.lower():
            return True
        if not any(var.get() for var in self.filters.values()):
            return True
        return False

    def render_rows(self):
        for rowid in self.tree.get_children():
            self.tree.delete(rowid)
        for row in self.rows:
            path, name, width, height, fmt, have, need, _ = row
            key = (path, name)
            mark = "☑" if key in self.checked else "☐"
            tag = "missing" if have < need else "ok"
            rowid = self.tree.insert("", "end", values=(mark, os.path.basename(path), name,
                                                        "%dx%d" % (width, height),
                                                        str(fmt).replace("D3DFMT_", ""),
                                                        "%d/%d" % (have, need)),
                                   tags=("odd" if len(self.tree.get_children()) % 2 else "even", tag))
            row[7] = rowid
        self._count()

    def _count(self):
        total = len(self.rows)
        picked = len(self.checked)
        self.count.configure(text=self.app.t("mips.count", n=picked, m=total))

    def _mark(self, row, on):
        key = (row[0], row[1])
        rowid = row[7]
        if not rowid:
            return
        if on:
            self.checked.add(key)
            self.tree.set(rowid, "sel", "☑")
        else:
            self.checked.discard(key)
            self.tree.set(rowid, "sel", "☐")

    def select_all(self):
        if self.busy:
            return
        for row in self.rows:
            self._mark(row, True)
        self._count()

    def select_none(self):
        if self.busy:
            return
        for row in self.rows:
            self._mark(row, False)
        self._count()

    def bulk(self, kind):
        if self.busy:
            return
        raw = ("A8R8G8B8", "B8G8R8A8", "A8B8G8R8", "X8R8G8B8", "R8G8B8A8")
        for row in self.rows:
            _path, name, width, height, fmt, have, need, _row = row
            long_side = max(width, height)
            norm = str(fmt).upper().replace("D3DFMT_", "")
            if kind == "big":
                on = long_side >= 1024 and (need - have) >= 3
            elif kind == "raw":
                on = norm in raw
            elif kind == "mid":
                on = 512 <= long_side < 1024
            else:  # skip: drop alpha / hair style half transparent sets
                on = "hair" in str(name).lower() or "alpha" in str(name).lower()
            if kind == "skip":
                if on:
                    self._mark(row, False)
            elif on:
                self._mark(row, True)
        self._count()

    def _toggle_row(self, event):
        col = self.tree.identify_column(event.x)
        rowid = self.tree.identify_row(event.y)
        if not rowid:
            return
        if col not in ("#1",):
            return
        values = self.tree.item(rowid, "values")
        path = None
        for row in self.rows:
            if row[7] == rowid:
                path = row
                break
        if not path:
            return
        key = (path[0], path[1])
        if key in self.checked:
            self.checked.discard(key)
            self.tree.item(rowid, values=("☐",) + tuple(values[1:]))
        else:
            self.checked.add(key)
            self.tree.item(rowid, values=("☑",) + tuple(values[1:]))

    # -- fixing ----------------------------------------------------------
    def fix(self):
        if self.busy:
            return
        picked = {}
        for path, name in self.checked:
            picked.setdefault(path, set()).add(name)
        if not picked:
            self.state.configure(text=self.app.t("mips.pick"))
            return
        core = ""
        texconv = self.app.texconv
        files = list(picked.items())

        def work():
            done = 0
            made = []
            for index, (path, names) in enumerate(files, start=1):
                if self.stop_flag:
                    break
                self.log("fixing %s (%d texture(s))" % (os.path.basename(path), len(names)))
                out, report = lite.fix_mips(
                    path, core_dir=core, texconv=texconv,
                    progress=lambda done, total, *_rest: self.tick(
                        index - 1 + done / float(max(1, total)), len(files)),
                    only=names, inplace=True)
                if out:
                    self.log("ok %s -> %s" % (os.path.basename(path), os.path.basename(out)))
                    made.append((path, out))
                    done += 1
                else:
                    self.log("skip %s: %s" % (os.path.basename(path), report.strip()))
                self.tick(index, len(files))
            self._events.put(("fixed", (done, made)))

        self.spawn(work)

    def _finished(self, payload=None):
        if payload and payload[0] == "scan":
            self._on_scan_done()
            self.scanned = {}
        elif payload and payload[0] == "fixed":
            done, made = payload[1]
            for old_path, new_path in made:
                if old_path in self.files:
                    self.files[self.files.index(old_path)] = new_path
                meta = getattr(self, "meta", None)
                if isinstance(meta, dict):
                    meta.pop(old_path, None)
            self.summary.configure(text=self.app.t("mips.fixed", n=done, out=""))
            self.note.configure(text="%d file(s)" % len(self.files) if self.files else "")
            self.scanned.clear()
            self.frame.after(80, self.check)
            return
        self.state.configure(text="")

    def set_bar(self, done, total):
        try:
            self.bar.place_configure(relwidth=min(1.0, done / float(max(1, total))))
            self.frame.update_idletasks()
        except tk.TclError:
            pass

    def set_state(self, text):
        self.state.configure(text=text)

    def retranslate(self):
        super().retranslate()
        self.filter_btn.configure(text=self.app.t("mips.filter"))
        menu = self.filter_btn.nametowidget(self.filter_btn["menu"])
        labels = ("mips.f_long", "mips.f_raw", "mips.f_mid", "mips.f_alpha")
        for index, key in enumerate(labels):
            menu.entryconfigure(index, label=self.app.t(key))
        for index, key in enumerate(("mips.f_long", "mips.f_raw", "mips.f_mid", "mips.f_skip")):
            self.menu.entryconfigure(index, label=self.app.t(key))
        self._count()
        for col, key in (("sel", "mips.c_sel"), ("file", "mips.c_file"), ("tex", "mips.c_tex"),
                         ("size", "mips.c_size"), ("fmt", "mips.c_fmt"), ("mips", "mips.c_mips")):
            self.tree.heading(col, text=self.app.t(key))


class YtdPage(_Page):
    suffixes = SUFFIX_YTD
    file_title = "ytd.files"

    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.meta = {}

        self.bad = tk.Label(self.right, text="", bg=app.c("bg"), fg=app.c("warning"),
                            font=_font(9), anchor="w")
        app.style_widget(self.bad, "bg", "warning")

        self.panel = ModePanel(self.right, app, self)
        self.panel.pack(fill="x", pady=(10, 0))

        # CodeWalker is not used anywhere any more: compression, MIP repair, PED
        # repair, audit and RPF defrag all run on the vendored fivefury + rpf7 code.
        self.cw_var = tk.StringVar(value="")

        self.report_card = Card(self.right, app, "report")
        self.report_card.pack(fill="both", expand=True, pady=(10, 0))
        self.text = tk.Text(self.report_card.body, bg=app.c("inset"), fg=app.c("dim"),
                            insertbackground=app.c("fg"), relief="flat", bd=0,
                            highlightthickness=1, highlightbackground=app.c("stroke"),
                            font=_mono(8), wrap="word", width=1, height=6)
        self.text.pack(fill="both", expand=True)
        app.style_widget(self.text, "inset", "dim")

        action = tk.Frame(self.report_card.body, bg=app.c("card"))
        action.pack(fill="x", pady=(8, 0))
        app.style_widget(action, "card")
        self.summary = tk.Label(action, text="", bg=app.c("card"), fg=app.c("dim"),
                                font=_font(9), anchor="w", justify="left")
        self.summary.pack(fill="x")
        app.style_widget(self.summary, "card", "dim")
        self.state = tk.Label(action, text="", bg=app.c("card"), fg=app.c("faint"),
                              font=_font(8), anchor="e", justify="right")
        self.state.pack(fill="x", pady=(4, 0))
        app.style_widget(self.state, "card", "faint")

        buttons = tk.Frame(action, bg=app.c("card"))
        buttons.pack(fill="x", pady=(8, 0), before=self.summary)
        app.style_widget(buttons, "card")
        app._button(buttons, app.t("ytd.plan"), self.plan).pack(side="left")
        app._button(buttons, app.t("ytd.start"), self.compress, primary=True).pack(side="left", padx=8)
        self.stop_btn = app._button(buttons, app.t("cancel"), self.stop, kind="neutral")
        self.stop_btn.pack(side="left")
        self.progress = tk.Frame(buttons, bg=app.c("track"), height=6)
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.bar = tk.Frame(self.progress, bg=app.c("accent"), height=6)
        self.bar.place(x=0, y=0, relwidth=0.0, relheight=1.0)


        app._button(self.btnrow, app.t("ytd.add_dir"), self._add_folder, fixed=128).pack(side="right")
        app._button(self.btnrow, app.t("ytd.add"), self._add_files, primary=True, fixed=128).pack(side="right", padx=(0, 6))

        self._sync_cw()

    # -- code walker -----------------------------------------------------
    def _sync_cw(self):
        """Kept as a no-op: CodeWalker is no longer part of any code path."""
        self.app.core_dir = ""
        # retranslate() ends up here on every language switch, so the legacy banner
        # has to follow the table instead of staying in the language it was packed in.
        self.bad.configure(text=self.app.t("ytd.legacy"))

    # -- files -----------------------------------------------------------
    def pick(self):
        return _pick_files(self.app, self.app.t("ytd.add"), [("texture dictionary", "*.ytd"), ("all", "*.*")])

    def pick_dir(self):
        return _walk(_pick_dir(self.app, self.app.t("ytd.add_dir")), self.suffixes)

    def _after_add(self):
        self.listbox.delete(0, "end")
        for path in self.files:
            self.listbox.insert("end", "%s  %s" % (os.path.basename(path), _human(_size_of(path))))
        self.scan_files()

    def _cleared(self):
        self.meta = {}
        self.write("")
        self.summary.configure(text="")
        self.bad.pack_forget()
        self.set_bar(0, 1)

    def scan_files(self):
        if self.busy or not self.files:
            return
        files = [p for p in self.files if p not in self.meta]
        if not files:
            return
        self.set_state(self.app.t("state.scanning"))

        def work():
            results = _inspect_many(files, workers=4,
                                    progress=lambda done, total: self.tick(done, total))
            for res in results:
                self.meta[res["path"]] = res
            self._events.put(("scan", None))

        self.spawn(work)

    def _on_scan_done(self):
        self.listbox.delete(0, "end")
        for path in self.files:
            res = self.meta.get(path, {})
            tag = "GEN9" if res.get("version") == ytdmod.YTD_VERSION_GEN9 else (
                "GEN8" if res.get("legacy") else "?")
            count = len(res.get("textures") or [])
            self.listbox.insert("end", "%s  %s  %d tex  %s" % (
                os.path.basename(path), tag, count, _human(_size_of(path))))
        legacy = [p for p in self.files if self.meta.get(p, {}).get("legacy")]
        if legacy:
            self.bad.configure(text=self.app.t("ytd.legacy"))
            self.bad.pack(fill="x", pady=(8, 0), before=self.panel)
        else:
            self.bad.pack_forget()
        self.set_state("")

    # -- plan / compress --------------------------------------------------
    def mode_changed(self):
        self.summary.configure(text="")

    def _params(self):
        mode, cap = self.panel.value()
        return mode, cap, self.app.core_dir, self.app.texconv

    def plan(self):
        if self.busy:
            return
        if not self.files:
            self.set_state(self.app.t("ytd.pick"))
            return
        mode, cap, core, texconv = self._params()
        files = list(self.files)
        self.write("")
        self.set_state(self.app.t("state.analyzing"))

        def work():
            before = after = 0
            file_before = 0
            done = 0
            lines = []
            raw = ("A8R8G8B8", "B8G8R8A8", "A8B8G8R8", "X8R8G8B8", "R8G8B8A8")
            keep = ("spec", "gloss", "dirt", "decal", "mask", "script_rt")
            for index, path in enumerate(files, start=1):
                if self.stop_flag:
                    break
                textures = (self.meta.get(path) or {}).get("textures") or []
                if not textures:
                    self.log("err %s: no texture info" % os.path.basename(path))
                    self.tick(index, len(files))
                    continue
                b = a = 0
                for tex in textures:
                    fmt = str(tex.format).upper().replace("D3DFMT_", "")
                    before_bytes = int(getattr(tex, "bytes", 0) or 0)
                    if not before_bytes:
                        before_bytes = lite.tex_bytes(tex.width, tex.height, fmt, tex.mips)
                    b += before_bytes
                    target = lite.target_size(tex.width, tex.height, mode, cap)
                    new_fmt = fmt
                    lower = str(tex.name).lower()
                    if mode == lite.MODE_AGGRESSIVE and not any(word in lower for word in keep):
                        if fmt in raw:
                            new_fmt = "DXT5"
                    if target is None and new_fmt == fmt:
                        a += before_bytes
                        continue
                    width, height = target or (tex.width, tex.height)
                    mips = 1 if tex.mips <= 1 else max(1, max(width, height).bit_length())
                    a += lite.tex_bytes(width, height, new_fmt, mips)
                before += b
                after += a
                size = os.path.getsize(path)
                file_before += size
                ratio = (a / float(b)) if b else 1.0
                lines.append("[%d/%d] %s  %.1f MB -> %.1f MB (-%d%%)" % (
                    index, len(files), os.path.basename(path), size / 1048576.0,
                    size * ratio / 1048576.0, round((1 - ratio) * 100)))
                done += 1
                self.tick(index, len(files))
            for line in lines[:80]:
                self.log(line)
            self._events.put(("plan", (before, after, file_before, done)))

        self.spawn(work)

    def _on_plan_done(self, payload):
        before, after, file_before, done = payload
        if done:
            ratio = (after / float(before)) if before else 1.0
            self.summary.configure(text="%s\n%s" % (
                self.app.t("ytd.mem", before=before / 1048576.0, after=after / 1048576.0,
                           pct=round((after - before) * 100.0 / before) if before else 0),
                self.app.t("ytd.file", before=file_before / 1048576.0,
                           after=file_before * ratio / 1048576.0,
                           pct=round((ratio - 1) * 100))))
        self.set_state("")
        self.set_bar(1, 1)

    def compress(self):
        if self.busy:
            return
        if not self.files:
            self.set_state(self.app.t("ytd.pick"))
            return
        mode, cap, core, texconv = self._params()
        files = list(self.files)
        self.write("")
        self.set_state(self.app.t("state.compressing"))

        def work():
            total_before = total_after = 0
            mem_before = mem_after = 0.0
            done = failed = skipped = 0
            for index, path in enumerate(files, start=1):
                if self.stop_flag:
                    break
                name = os.path.basename(path)
                try:
                    size_before = os.path.getsize(path)
                    out, report = lite.make_lite(path, mode=mode, cap=cap, core_dir=core,
                                                 texconv=texconv, inplace=True)
                    if not out:
                        skipped += 1
                        self.log("[%d/%d] %s skipped" % (index, len(files), name))
                    else:
                        for line in (report or "").splitlines():
                            if line.startswith("memory"):
                                nums = [float(tok) for tok in line.replace("MB", " ").split() if tok.replace(".", "").isdigit()]
                                if len(nums) >= 2:
                                    mem_before += nums[0]
                                    mem_after += nums[1]
                        size_after = os.path.getsize(out)
                        total_before += size_before
                        total_after += size_after
                        done += 1
                        self.log("[%d/%d] %s  %s -> %s  (%d%%)" % (
                            index, len(files), name, _human(size_before), _human(size_after),
                            round((size_after - size_before) * 100.0 / max(1, size_before))))
                except Exception as exc:                      # noqa: BLE001
                    failed += 1
                    self.log("[%d/%d] %s  err %s" % (index, len(files), name, exc))
                self.tick(index, len(files))
            self._events.put(("report", (done, failed, skipped, total_before, total_after,
                                        mem_before, mem_after)))

        self.spawn(work)

    def _on_compress_done(self, payload):
        self._last_compress = payload
        self._render_compress_summary(payload)

    def _render_compress_summary(self, payload):
        done, failed, skipped, before, after, mem_before, mem_after = payload
        lines = [self.app.t("ytd.done", done=done, failed=failed, skipped=skipped)]
        if mem_before:
            lines.append(self.app.t("ytd.mem", before=mem_before, after=mem_after,
                                    pct=round((mem_after - mem_before) * 100.0 / mem_before)))
        if before:
            lines.append(self.app.t("ytd.file", before=before / 1048576.0, after=after / 1048576.0,
                                    pct=round((after - before) * 100.0 / before)))
        lines.append(self.app.t("ytd.disk_note"))
        self.summary.configure(text="\n".join(lines))
        self.set_state("")

    # -- shared ----------------------------------------------------------
    def write(self, text):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        self.text.insert("end", text)
        self.text.configure(state="disabled")

    def log_line(self, text):
        self.text.configure(state="normal")
        self.text.insert("end", text + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")
        self.app.log_line(text)

    def set_bar(self, done, total):
        try:
            self.bar.place_configure(relwidth=min(1.0, done / float(max(1, total))))
        except tk.TclError:
            pass

    def set_state(self, text):
        self.state.configure(text=text)

    def _finished(self, payload=None):
        if not payload:
            self.set_state("")
            return
        kind, data = payload
        if kind == "scan":
            self._on_scan_done()
        elif kind == "plan":
            self._on_plan_done(data)
        elif kind == "report":
            self._on_compress_done(data)

    def retranslate(self):
        super().retranslate()
        self.panel.retranslate()
        self._sync_cw()
        # The summary is built once when a job finishes; rebuild it so switching
        # language does not leave the old table's wording behind.
        if getattr(self, "_last_compress", None) is not None:
            self._render_compress_summary(self._last_compress)


def build_mips_page(app, parent):
    page = MipsPage(app, parent)
    page.owner = page
    return page


def build_ytd_page(app, parent):
    page = YtdPage(app, parent)
    page.owner = page
    return page


class PedPage(_Page):
    """PED variation pages: every .ymt is checked against its .ydd."""

    suffixes = (".yd",)

    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.owner = self
        self.pairs = []
        self.status = []
        self.picked = set()
        self.listbox.configure(font=_mono(9), selectmode="extended",
                               activestyle="none",
                               selectbackground=self.app.c("hover"),
                               selectforeground=self.app.c("danger"))
        self.listbox.bind("<Button-1>", self._toggle_row, add="+")
        self.card.title.configure(text=app.t("ped.files"))

        self.report_card = Card(self.right, app, "report")
        self.report_card.pack(fill="both", expand=True)

        wrap = tk.Frame(self.report_card.body, bg=app.c("inset"),
                        highlightbackground=app.c("stroke"), highlightthickness=1)
        wrap.pack(fill="both", expand=True)
        app.style_widget(wrap, "inset")
        self.text = tk.Text(wrap, bg=app.c("inset"), fg=app.c("dim"), bd=0,
                            highlightthickness=0, font=_mono(9), wrap="word", width=1, height=10)
        sb = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview,
                           style=app.scroll_style())
        self.text.configure(yscrollcommand=sb.set)
        sb.pack(side="right", fill="y")
        self.text.pack(side="left", fill="both", expand=True, padx=6, pady=6)

        action = tk.Frame(self.report_card.body, bg=app.c("card"))
        action.pack(fill="x", pady=(8, 0))
        app.style_widget(action, "card")
        self.actions = tk.Frame(action, bg=app.c("card"))
        self.actions.pack(fill="x")
        app.style_widget(self.actions, "card")
        self.btn_check = app._button(self.actions, app.t("ped.check"), self.check_all, primary=True)
        self.stop_btn = app._button(self.actions, app.t("cancel"), self.stop, kind="neutral")
        self.btn_check.pack(side="left")
        app.bind_text(self.btn_check, "ped.check")
        self.btn_fix = app._button(self.actions, app.t("ped.fix"), self.fix_all)
        self.btn_fix.pack(side="left", padx=(8, 0))
        app.bind_text(self.btn_fix, "ped.fix")
        self.progress = tk.Frame(self.actions, bg=app.c("track"), height=6)
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 8))
        self.bar = tk.Frame(self.progress, bg=app.c("accent"), height=6)
        self.bar.place(x=0, y=0, relwidth=0.0, relheight=1.0)
        self.pick_label = tk.Label(self.actions, text="", bg=app.c("card"),
                                   fg=app.c("faint"), font=_font(8), anchor="e")
        self.pick_label.pack(side="right")
        app.style_widget(self.pick_label, "card", "faint")
        self.summary = tk.Label(action, text="", bg=app.c("card"), fg=app.c("dim"),
                                font=_font(9), anchor="e", justify="right")
        self.summary.pack(fill="x", pady=(6, 0))
        app.style_widget(self.summary, "card", "dim")
        self.state = tk.Label(action, text="", bg=app.c("card"), fg=app.c("faint"),
                              font=_font(8), anchor="e", justify="right")
        self.state.pack(fill="x", pady=(4, 0))
        app.style_widget(self.state, "card", "faint")

        app._button(self.btnrow, app.t("ped.add"), self._add_folder, primary=True, fixed=128).pack(side="right")
        self.set_state(app.t("ped.pick"))

    # -- file handling ---------------------------------------------------
    def pick(self):
        return []

    def pick_dir(self):
        from tkinter import filedialog

        folder = filedialog.askdirectory(title=self.app.t("ped.add"))
        return [] if not folder else [folder]

    def retranslate(self):
        super().retranslate()
        self._refresh_pick()
        if not self.listbox.size():
            self.set_state(self.app.t("ped.pick"))

    def remove_selected(self):
        picked = sorted(self.listbox.curselection(), reverse=True)
        for index in picked:
            self.listbox.delete(index)
            self.picked = set()
            for store in (self.pairs, self.status):
                try:
                    del store[index]
                except IndexError:
                    pass
        self._refresh_pick()
        self.set_state("")

    def _add_folder(self):
        folders = self.pick_dir()
        if not folders:
            return
        found = ped.pairs(folders[0])
        if not found:
            self.set_state(self.app.t("ped.pick"))
            return
        self.folder = folders[0]
        self.pairs = found
        self.status = [None] * len(found)
        self.picked = set()
        self.listbox.delete(0, "end")
        for stem, _ydd, _ymt in found:
            self.listbox.insert("end", "\u2610  " + stem)
            self.listbox.itemconfigure("end", foreground=self.app.c("faint"))
        self._refresh_pick()
        self.note.configure(text="%d ped(s)" % len(found))
        self.set_state("")

    def clear(self):
        self.pairs = []
        self.status = []
        self.picked = set()
        self.listbox.delete(0, "end")
        self.note.configure(text="")
        self.text.delete("1.0", "end")
        self.summary.configure(text="")
        self.set_bar(0, 1)
        self.set_state(self.app.t("ped.pick"))

    def _cleared(self):
        pass

    def _mark(self, index, state):
        self.status[index] = state
        mark = {"ok": "\u2713", "bad": "\u2611", None: "\u2610"}[state]
        color = {"ok": self.app.c("fg"), "bad": self.app.c("danger")}.get(state, self.app.c("faint"))
        text = "%s  %s" % (mark, self.pairs[index][0])
        if hasattr(self.listbox, "set_row"):
            self.listbox.set_row(index, text, color)
        else:
            self.listbox.delete(index)
            self.listbox.insert(index, text)
            self.listbox.itemconfigure(index, foreground=color)
        if state == "bad":
            self.picked.add(index)
        else:
            self.picked.discard(index)
        self._refresh_pick()

    def _toggle_row(self, event):
        """Clicking a red row flips its checkbox instead of the tk selection."""
        index = self.listbox.nearest(event.y)
        if index < 0 or index >= len(self.pairs) or self.status[index] != "bad":
            return None
        if index in self.picked:
            self.picked.discard(index)
            glyph, color = "\u2610", self.app.c("danger")
        else:
            self.picked.add(index)
            glyph, color = "\u2611", self.app.c("danger")
        self.listbox.selection_clear(0, "end")
        name = self.pairs[index][0]
        if hasattr(self.listbox, "set_row"):
            self.listbox.set_row(index, "%s  %s" % (glyph, name), color)
        else:
            self.listbox.delete(index)
            self.listbox.insert(index, "%s  %s" % (glyph, name))
            self.listbox.itemconfigure(index, foreground=color)
        self._refresh_pick()
        return "break"

    def _refresh_pick(self):
        picked = len(getattr(self, "picked", ()))
        try:
            self.pick_label.configure(text=self.app.t("ped.picked").format(n=picked))
            self.btn_fix.configure(state=("normal" if picked else "disabled"))
        except (tk.TclError, KeyError, AttributeError):
            pass

    # -- helpers ---------------------------------------------------------
    def set_bar(self, done, total):
        ratio = 0.0 if not total else max(0.0, min(1.0, done / float(total)))
        try:
            self.bar.place_configure(relwidth=ratio)
        except tk.TclError:
            pass

    def set_state(self, text):
        try:
            self.state.configure(text=text)
        except tk.TclError:
            pass

    def _core(self):
        return ""

    def _run(self, jobs, kind):
        owner = getattr(self.app, "busy_owner", None)
        if owner not in (None, self):
            self.set_state(self.app.t("busy_other"))
            return
        self.app.busy_owner = self
        self.stop_flag = False
        self.busy = True
        self.set_state(self.app.t("state.busy"))
        title = self.app.t("ped.hdr.fix" if kind in ("fix", "align", "auto") else "ped.hdr.check")
        self.text.insert("end", "\n" + "\u2500" * 6 + " " + title.format(n=len(jobs)) + " " + "\u2500" * 6 + "\n")
        if getattr(self, "folder", ""):
            self.text.insert("end", self.app.t("ped.folder").format(path=self.folder) + "\n")
        self.text.see("end")

        def work():
            ok = bad = fixed = 0
            for count, (index, stem, ydd, ymt) in enumerate(jobs, 1):
                if self.stop_flag:
                    self._events.put(("report", self.app.t("stopping")))
                    break
                self.tick(count - 1, len(jobs))
                self.log(self.app.t({"fix": "ped.fixing", "align": "ped.aligning"}.get(kind, "ped.checking")).format(name=stem))
                try:
                    if kind == "auto":
                        rep = ped.check_pair(stem, ydd, ymt, self._core())
                        structural = any(("drawable" in p) or ("compInfos" in p) for p in rep.problems)
                        if rep.ok:
                            ok += 1
                            self._events.put(("mark", (index, "ok")))
                            self._events.put(("report", "%s: already ok" % stem))
                            self.tick(count, len(jobs))
                            continue
                        if structural:
                            changes, _out = ped.align_pair(stem, ydd, ymt, self._core(), apply=True)
                            label = "aligned"
                        else:
                            changes, _out = ped.fix_pair(stem, ydd, ymt, self._core())
                            label = "repaired"
                        if changes:
                            fixed += 1
                            self._events.put(("mark", (index, "ok")))
                            self._events.put(("report", "%s: %s (%s)" % (stem, label, ", ".join(changes[:3]))))
                        else:
                            bad += 1
                            self._events.put(("mark", (index, "bad")))
                            self._events.put(("report", "%s: nothing repairable was found" % stem))
                    elif kind == "align":
                        changes, _out = ped.align_pair(stem, ydd, ymt, self._core(), apply=True)
                        if changes:
                            fixed += 1
                            self._events.put(("mark", (index, "ok")))
                            self._events.put(("report", "%s: %s" % (stem, "; ".join(changes[:4]))))
                        else:
                            bad += 1
                            self._events.put(("mark", (index, "bad")))
                            self._events.put(("report", "%s: nothing to align" % stem))
                    elif kind == "fix":
                        changes, _out = ped.fix_pair(stem, ydd, ymt, self._core())
                        if changes:
                            fixed += 1
                            self._events.put(("mark", (index, "ok")))
                            self._events.put(("report", "%s: %s" % (stem, "; ".join(changes[:4]))))
                        else:
                            bad += 1
                            self._events.put(("mark", (index, "bad")))
                            self._events.put(("report", "%s: nothing repairable was found" % stem))
                    else:
                        report = ped.check_pair(stem, ydd, ymt, self._core())
                        if report.ok:
                            ok += 1
                            self._events.put(("mark", (index, "ok")))
                        else:
                            bad += 1
                            self._events.put(("mark", (index, "bad")))
                            self._events.put(("report", "%s: %s" % (stem, "; ".join(report.problems[:4]))))
                            for note in report.notes[:2]:
                                self._events.put(("report", "   note: %s" % note))
                except Exception as exc:                      # noqa: BLE001
                    import traceback

                    bad += 1
                    self._events.put(("mark", (index, "bad")))
                    self._events.put(("report", "%s: %s" % (stem, traceback.format_exc().splitlines()[-1])))
                self.tick(count, len(jobs))
            self._events.put(("scan" if kind == "check" else "fixed", (len(jobs), ok, bad, fixed)))
            self._events.put(("done", None))

        threading.Thread(target=work, daemon=True).start()
        self.frame.after(60, self._pump)

    def check_all(self):
        if self.busy:
            return
        if not self.pairs:
            self.set_state(self.app.t("ped.pick"))
            return
        jobs = [(i, stem, ydd, ymt) for i, (stem, ydd, ymt) in enumerate(self.pairs)]
        self._run(jobs, "check")

    def fix_all(self):
        if self.busy:
            return
        if not self.pairs:
            self.set_state(self.app.t("ped.pick"))
            return
        picked = set(self.picked)
        jobs = [(i, stem, ydd, ymt) for i, (stem, ydd, ymt) in enumerate(self.pairs)
                if i in picked and self.status[i] == "bad"]
        if not jobs:
            self.set_state(self.app.t("ped.clean"))
            return
        self._run(jobs, "auto")

    def align_all(self):
        if self.busy:
            return
        if not self.pairs:
            self.set_state(self.app.t("ped.pick"))
            return
        jobs = [(i, stem, ydd, ymt) for i, (stem, ydd, ymt) in enumerate(self.pairs)
                if self.status[i] in ("bad", None)]
        if not jobs:
            self.set_state(self.app.t("ped.clean"))
            return
        self._run(jobs, "align")

    def _pump(self):
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "log":
                    self.log_line(payload)
                elif kind == "error":
                    self.log_line("err " + payload)
                    self.set_state(payload)
                elif kind == "progress":
                    self.set_bar(*payload)
                elif kind == "mark":
                    self._mark(*payload)
                elif kind == "report":
                    self.text.insert("end", payload + "\n")
                    self.text.see("end")
                elif kind in ("scan", "fixed"):
                    self._payload = (kind, payload)
                elif kind == "done":
                    self.busy = False
                    # Release the cross-page lock here, not in _finished(): subclasses
                    # override _finished() and would otherwise keep the app locked.
                    if getattr(self.app, "busy_owner", None) is self:
                        self.app.busy_owner = None
                    payload, self._payload = getattr(self, "_payload", None), None
                    self._finished(payload)
        except queue.Empty:
            pass
        if self.busy:
            self.frame.after(60, self._pump)

    def _finished(self, payload=None):
        if not payload:
            self.set_state("")
            return
        kind, data = payload
        if kind == "scan":
            total, ok, bad, _fixed = data
            self.summary.configure(text=self.app.t("ped.done").format(n=total, ok=ok, bad=bad),
                                   fg=self.app.c("danger" if bad else "green"))
            first_bad = next((i for i, state in enumerate(self.status) if state == "bad"), None)
            if first_bad is not None:
                self.listbox.see(first_bad)
        else:
            total, _ok, _bad, fixed = data
            self.summary.configure(text=self.app.t("ped.fixed").format(n=fixed),
                                   fg=self.app.c("green" if fixed else "dim"))
            self.listbox.selection_clear(0, "end")
            self._refresh_pick()
        self.set_state("")


def build_ped_page(app, parent):
    page = PedPage(app, parent)
    return page


class RpfPage(_Page):
    """Defragment .rpf archives: give the space freed by compression back to disk.

    This is the only page that needs CodeWalker, so the folder picker lives here
    instead of on the compression page where it looked like a compression setting.
    """

    suffixes = (".rpf",)
    file_title = "rpf.files"

    def __init__(self, app, parent):
        super().__init__(app, parent)
        self.owner = self

        # CodeWalker is not used any more: the defrag runs on the pure-Python RPF7
        # writer, so there is no folder to pick and no build to detect.
        self.cw_var = tk.StringVar(value="")

        self.report_card = Card(self.right, app, "report")
        self.report_card.pack(fill="both", expand=True, pady=(10, 0))
        self.text = tk.Text(self.report_card.body, bg=app.c("inset"), fg=app.c("dim"),
                            insertbackground=app.c("fg"), relief="flat", bd=0,
                            highlightthickness=1, highlightbackground=app.c("stroke"),
                            font=_mono(8), wrap="word", width=1, height=8)
        self.text.pack(fill="both", expand=True)
        app.style_widget(self.text, "inset", "dim")
        for name, color, font in (("title", "fg", _mono(9)), ("dim", "dim", None),
                                  ("ok", "green", None), ("warn", "warning", None),
                                  ("err", "danger", None), ("bak", "faint", None)):
            self._tag(name, color, font)

        action = tk.Frame(self.report_card.body, bg=app.c("card"))
        action.pack(fill="x", pady=(8, 0))
        app.style_widget(action, "card")
        self.summary = tk.Label(action, text="", bg=app.c("card"), fg=app.c("dim"),
                                font=_font(9), anchor="e", justify="right")
        self.summary.pack(fill="x")
        app.style_widget(self.summary, "card", "dim")
        self.state = tk.Label(action, text="", bg=app.c("card"), fg=app.c("faint"),
                              font=_font(8), anchor="e", justify="right", wraplength=560)
        self.state.pack(fill="x", pady=(4, 0))
        app.style_widget(self.state, "card", "faint")

        buttons = tk.Frame(action, bg=app.c("card"))
        buttons.pack(fill="x", pady=(8, 0), before=self.summary)
        app.style_widget(buttons, "card")
        self.repack_btn = app._button(buttons, app.t("rpf.start"), self.repack, primary=True)
        self.repack_btn.pack(side="left")
        self.stop_btn = app._button(buttons, app.t("cancel"), self.stop_work, kind="neutral")
        self.stop_btn.pack(side="left", padx=8)
        self.progress = tk.Frame(buttons, bg=app.c("track"), height=6)
        self.progress.pack(side="left", fill="x", expand=True, padx=(12, 0))
        self.bar = tk.Frame(self.progress, bg=app.c("accent"), height=6)
        self.bar.place(x=0, y=0, relwidth=0.0, relheight=1.0)

        self.add_dir_btn = app._button(self.btnrow, app.t("rpf.add_dir"), self._add_folder, fixed=128)
        self.add_dir_btn.pack(side="right")
        self.add_btn = app._button(self.btnrow, app.t("rpf.add"), self._add_files, primary=True, fixed=128)
        self.add_btn.pack(side="right", padx=(0, 6))

        self._set_busy(False)

    # -- files -----------------------------------------------------------
    def pick(self):
        return _pick_files(self.app, self.app.t("rpf.add"),
                           [("archives", "*.rpf"), ("all", "*.*")])

    def pick_dir(self):
        return _walk(_pick_dir(self.app, self.app.t("rpf.add_dir")), self.suffixes)

    def _after_add(self):
        self.listbox.delete(0, "end")
        for path in self.files:
            self.listbox.insert("end", "%s  %s" % (os.path.basename(path), _human(_size_of(path))))

    def write(self, text):
        self.text.configure(state="normal")
        self.text.delete("1.0", "end")
        if text:
            self.text.insert("end", text)
        self.text.configure(state="disabled")

    def write_line(self, text, tag=None):
        self.text.configure(state="normal")
        if tag:
            self.text.insert("end", text + "\n", tag)
        else:
            self.text.insert("end", text + "\n")
        self.text.see("end")
        self.text.configure(state="disabled")

    def _tag(self, name, color, font=None):
        options = {"foreground": self.app.c(color)}
        if font is not None:
            options["font"] = font
        self.text.tag_configure(name, **options)

    # -- repack ----------------------------------------------------------
    def _set_busy(self, busy):
        state = "disabled" if busy else "normal"
        for widget in (self.btn_clear, self.btn_remove, self.add_btn, self.add_dir_btn,
                       self.listbox):
            try:
                widget.configure(state=state)
            except Exception:                              # noqa: BLE001
                pass
        self.stop_btn.configure(state="normal" if busy else "disabled")
        self.repack_btn.configure(state="disabled" if busy else "normal")
        self.bar.place_configure(relwidth=0.0)

    def repack(self):
        paths = list(self.files)
        if not paths:
            self.set_state(self.app.t("rpf.need_files"))
            return
        if getattr(self, "_running", False):
            return
        self._running = True
        self._stop = False
        self._cancel = threading.Event()
        self.write("")
        self.summary.configure(text="")
        self.state.configure(text="starting...")
        self._set_busy(True)
        threading.Thread(target=self._work, args=(paths, ""), daemon=True).start()

    def stop_work(self):
        if getattr(self, "_running", False):
            self._stop = True
            self._cancel.set()
            self.state.configure(text="stopping: killing the worker process...")
            self._post(self.app.t("report.stopped"), "warn")

    def _post(self, text, tag=None):
        self.app.after(0, lambda t=text, g=tag: self.write_line(t, g))

    def _write_report(self, report, kept):
        """Lay one archive out as a block: what is inside, the backup, then the win."""
        if not isinstance(report, rpf.Report):
            self._post("ok   " + str(report), "ok")
            return
        self._post(report.leaf, "title")
        counts = "%d entr%s" % (report.entries, "y" if report.entries == 1 else "ies")
        if report.children:
            counts += ", %d nested archive%s" % (report.children,
                                                 "" if report.children == 1 else "s")
        if report.recursive:
            counts += ", recursed"
        self._post("    " + counts, "dim")
        if kept:
            self._post("    backup    " + kept, "bak")
        before = format(report.before, ",")
        after = format(report.after, ",")
        if report.saved:
            self._post("    %s -> %s bytes    -%.1f%%    %d ms"
                       % (before, after, report.pct, report.ms), "ok")
        else:
            self._post("    %s bytes    nothing to reclaim    %d ms"
                       % (before, report.ms), "dim")

    def _tick(self, index, total, name):
        self.state.configure(text="working  %d/%d  %s" % (index, total, name))
        self.bar.place_configure(relwidth=min(1.0, (index - 1) / float(max(1, total))))

    def _work(self, paths, core):
        total = len(paths)
        done = 0
        for index, path in enumerate(paths, 1):
            name = os.path.basename(path)
            if self._stop:
                self._post("stop  stopped before %s" % name)
                break
            self.app.after(0, lambda i=index, t=total, n=name: self._tick(i, t, n))
            kept = rpf.backup(path)
            if not kept:
                if os.path.getsize(path) > rpf.BACKUP_LIMIT:
                    self._post("    no backup: larger than 500 MB, copy it yourself first", "warn")
                elif not settings.keep_bak():
                    self._post("    no backup: 'Keep .bak files' is switched off", "warn")

            try:
                msg = rpf.defrag(path, recursive=True)
            except Exception as exc:                          # noqa: BLE001
                self._post(name, "title")
                self._post("    failed: %s" % str(exc)[:300], "err")
                continue
            done += 1
            self._write_report(msg, kept)
        self._running = False
        self.app.after(0, lambda: self.summary.configure(
            text="%d/%d archive(s) compacted" % (done, total)))
        self.app.after(0, lambda: self.bar.place_configure(relwidth=1.0))
        self.app.after(0, lambda: self.state.configure(text=""))
        self.app.after(0, lambda: self._set_busy(False))


def build_rpf_page(app, parent):
    page = RpfPage(app, parent)
    return page


def build_convert_page(app, parent):
    # the real page lives in gui_convert; keep this name so older imports work
    from .gui_convert import build_convert_page as build
    return build(app, parent)
