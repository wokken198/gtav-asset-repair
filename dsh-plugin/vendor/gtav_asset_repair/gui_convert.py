"""Gen8 -> Gen9 folder converter page.

The shape follows CodeWalker's "Convert Assets" dialog and Cfx's Alchemist: an
input folder, an output folder, one big report pane and a single Convert/Stop
button. The engine in :mod:`gtav_asset_repair.gen8to9` does the real work -- this
module only walks the tree, filters files it cannot convert, and reports what
happened without ever blocking the Tk main loop.
"""

import os
import queue
import threading
import time
import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import gen8to9
from .gui import Card, _font, _mono
from .gui_pages import _human, _size_of

SUPPORTED = (".ytd", ".ydd", ".yft", ".ymt", ".yld")

# RSC7 version a file already sitting in the gen9 layout carries. ``.ymt`` and
# ``.yld`` use the same version in both layouts, so they are not filtered here:
# the engine copies them byte for byte and reports the action as "copied".
_GEN9_VERSION = {
    ".ytd": gen8to9.GEN9_YTD_VERSION,
    ".ydd": gen8to9.GEN9_YDD_VERSION,
    ".yft": gen8to9.GEN9_YFT_VERSION,
}


def _rsc7_version(path):
    """The RSC7 version read from the first 8 bytes, or None for foreign data."""
    try:
        with open(path, "rb") as handle:
            head = handle.read(8)
    except OSError:
        return None
    return gen8to9.rsc7_version(head)


def _collect(root):
    """Every file under *root*, as (absolute path, relative path).

    Files whose extension is not supported are collected too: the report then
    says "extension not supported" instead of silently dropping them.
    """
    found = []
    for dirpath, dirnames, filenames in os.walk(root):
        dirnames.sort()
        for name in sorted(filenames):
            full = os.path.join(dirpath, name)
            found.append((full, os.path.relpath(full, root)))
    found.sort(key=lambda pair: pair[1].lower())
    return found


class ConvertPage(tk.Frame):
    """Folder-to-folder gen8 -> gen9 converter (no per-file picker)."""

    def __init__(self, app, parent):
        super().__init__(parent, bg=app.c("bg"))
        self.app = app
        self.owner = self

        self.busy = False
        self.stop_flag = False
        self._stop_armed = False
        self._events = queue.Queue()
        # Rows are kept as data, not as rendered text: switching language has to
        # re-render the report, and the note text is translated at draw time.
        self._rows: list[tuple[int, int, dict]] = []
        self._counts: tuple[dict, int] | None = None
        self._stopped_line = ""
        self._total = 0
        self._done = 0
        self._auto_out = True
        self._setting_out = False
        self._progress_job = None

        self.in_var = tk.StringVar()
        self.out_var = tk.StringVar()
        self.out_var.trace_add("write", self._out_edited)

        pad = int(16 * app.sx)

        # -- why this is not a byte patcher ---------------------------------
        self.about = Card(self, app, "convert.about")
        self.about.pack(fill="x", padx=pad, pady=(pad, 0))
        self.desc = tk.Label(self.about.body, text="", bg=app.c("card"), fg=app.c("dim"),
                             font=_font(9), anchor="w", justify="left",
                             wraplength=int(660 * app.sx))
        self.desc.pack(fill="x")
        app.style_widget(self.desc, "card", "dim")
        app.bind_text(self.desc, "convert.desc")
        self.desc.bind("<Configure>", lambda e: self.desc.configure(
            wraplength=max(320, e.width - 4)))

        # -- folders ---------------------------------------------------------
        self.folders = Card(self, app, "convert.folders")
        self.folders.pack(fill="x", padx=pad, pady=(10, 0))

        self.in_entry = self._folder_row("convert.input", self.in_var, self.pick_input, True)
        self.out_entry = self._folder_row("convert.output", self.out_var, self.pick_output,
                                          False)
        self.out_hint = tk.Label(self.folders.body, text="", bg=app.c("card"),
                                 fg=app.c("faint"), font=_font(8), anchor="w",
                                 justify="left", wraplength=int(660 * app.sx))
        self.out_hint.pack(fill="x", pady=(2, 0))
        app.style_widget(self.out_hint, "card", "faint")
        app.bind_text(self.out_hint, "convert.out_hint")
        self.out_hint.bind("<Configure>", lambda e: self.out_hint.configure(
            wraplength=max(320, e.width - 4)))

        # -- report ----------------------------------------------------------
        self.report_card = Card(self, app, "convert.report")
        self.report_card.pack(fill="both", expand=True, padx=pad, pady=(10, 0))
        wrap = tk.Frame(self.report_card.body, bg=app.c("card"))
        wrap.pack(fill="both", expand=True)
        app.style_widget(wrap, "card")
        self.text = tk.Text(wrap, wrap="word", height=12, bg=app.c("inset"),
                            fg=app.c("fg"), font=_mono(8), relief="flat", bd=0,
                            highlightthickness=0, padx=10, pady=8, state="disabled")
        self.text.pack(side="left", fill="both", expand=True)
        scroll = ttk.Scrollbar(wrap, orient="vertical", command=self.text.yview,
                               style=app.scroll_style())
        scroll.pack(side="right", fill="y")
        self.text.configure(yscrollcommand=scroll.set)
        self._paint_tags()

        # -- bottom bar ------------------------------------------------------
        self.bottom = tk.Frame(self, bg=app.c("bg"))
        self.bottom.pack(fill="x", padx=pad, pady=(10, pad))
        app.style_widget(self.bottom, "bg")
        self.action_btn = app._button(self.bottom, app.t("convert.start"),
                                      self._toggle, primary=True, fixed=150)
        self.action_btn.pack(side="left")
        # the caption flips between Convert and Stop, so the page owns it instead
        # of the generic text-binding pass that would pin it to one key.
        self._unbind_button()
        self.progress = tk.Frame(self.bottom, bg=app.c("track"), height=8)
        self.progress.pack(side="left", fill="x", expand=True, padx=(14, 14))
        self.bar = tk.Frame(self.progress, bg=app.c("accent"), height=8)
        self.bar.place(x=0, y=0, relwidth=0.0, relheight=1.0)
        self.status = tk.Label(self.bottom, text="", bg=app.c("bg"), fg=app.c("dim"),
                               font=_font(9), anchor="e")
        self.status.pack(side="right")
        app.style_widget(self.status, "bg", "dim")

        self._status(app.t("convert.idle"))

    # -- rows ------------------------------------------------------------
    def _folder_row(self, key, var, on_browse, readonly):
        row = tk.Frame(self.folders.body, bg=self.app.c("card"))
        row.pack(fill="x", pady=(0, 6))
        self.app.style_widget(row, "card")
        label = tk.Label(row, text="", bg=self.app.c("card"), fg=self.app.c("dim"),
                         font=_font(9), width=14, anchor="w")
        self.app.bind_text(label, key)
        self.app.style_widget(label, "card", "dim")
        label.pack(side="left")
        entry = tk.Entry(row, textvariable=var,
                         state="readonly" if readonly else "normal",
                         bg=self.app.c("inset"), fg=self.app.c("fg"), font=_mono(8),
                         relief="flat", bd=0, highlightthickness=1,
                         highlightbackground=self.app.c("stroke"),
                         highlightcolor=self.app.c("accent"),
                         readonlybackground=self.app.c("inset"))
        entry.pack(side="left", fill="x", expand=True, padx=(8, 8))
        btn = self.app._button(row, self.app.t("convert.browse"), on_browse,
                               kind="neutral", fixed=88)
        btn.pack(side="right")
        return entry

    def _unbind_button(self):
        self.app.text_bindings = [(w, k) for (w, k) in self.app.text_bindings
                                  if w is not self.action_btn]

    # -- folder pickers --------------------------------------------------
    def pick_input(self):
        path = filedialog.askdirectory(parent=self, title=self.app.t("convert.input"))
        if path:
            self.set_input(path)

    def pick_output(self):
        path = filedialog.askdirectory(parent=self, title=self.app.t("convert.output"))
        if path:
            self._set_output(os.path.normpath(path), False)

    def set_input(self, path):
        path = os.path.normpath(path)
        self.in_var.set(path)
        if self._auto_out or not self.out_var.get().strip():
            self._set_output(self._default_output(path), True)

    @staticmethod
    def _default_output(path):
        """``<name>-gen9`` as a sibling of the picked input folder."""
        path = os.path.normpath(path)
        parent, name = os.path.dirname(path), os.path.basename(path)
        if not parent or not name:
            return ""
        return os.path.join(parent, name + "-gen9")

    def _set_output(self, path, auto):
        self._auto_out = auto
        self._setting_out = True
        try:
            self.out_var.set(path)
        finally:
            self._setting_out = False

    def _out_edited(self, *_args):
        if self._setting_out:
            return
        # a hand-edited path wins over the automatic sibling for this session
        self._auto_out = False

    # -- run -------------------------------------------------------------
    def _toggle(self):
        if self.busy:
            if self._stop_armed:
                return
            # Stop acts at once: flip the button back and let the worker finish
            # the file it is on. While it winds down, further clicks are ignored.
            self._stop_armed = True
            self.stop_flag = True
            self._status(self.app.t("stopping"))
            self._set_running(True)
        else:
            self.start()

    def start(self):
        if self.busy:
            return
        src = self.in_var.get().strip()
        dst = self.out_var.get().strip()
        if not src or not os.path.isdir(src):
            self._status(self.app.t("convert.need_in"))
            return
        if not dst:
            self._status(self.app.t("convert.need_out"))
            return
        if os.path.normcase(os.path.abspath(src)) == os.path.normcase(os.path.abspath(dst)):
            self._status(self.app.t("convert.same_dir"))
            return
        if not os.path.isdir(dst):
            # CodeWalker asks the same question before it starts; saying yes has
            # to create the folder here, otherwise the report opens on failures.
            if not messagebox.askyesno(
                    self.app.t("convert.create_title"),
                    self.app.t("convert.confirm_create").replace("{path}", dst),
                    parent=self):
                return
        problem = self._ensure_writable(dst)
        if problem:
            # Put the reason where the operator is already looking: a one-line
            # status bar is easy to miss and there is no other output yet.
            self._clear_report()
            self._append(problem, "skipped")
            self._status(self.app.t("convert.idle"))
            return

        self.busy = True
        self.stop_flag = False
        self._stop_armed = False
        self._total = 0
        self._done = 0
        self._set_running(True)
        self._clear_report()
        self._bar(0, 1)
        self._status(self.app.t("convert.scanning"))
        self.app.busy_owner = self
        thread = threading.Thread(target=self._work, args=(src, dst), daemon=True)
        thread.start()
        self._progress_job = self.after(80, self._pump)

    def _ensure_writable(self, path):
        """Return an operator message when ``path`` cannot take files, else None.

        Windows can refuse to create a folder even for an administrator (the
        Desktop is a protected location under Controlled Folder Access), and
        the raw OSError mentions only the path. Probing once up front turns a
        report full of identical failures into a single actionable line.
        """
        try:
            os.makedirs(path, exist_ok=True)
            probe = os.path.join(path, ".write_check")
            with open(probe, "wb") as handle:
                handle.write(b"x")
            os.remove(probe)
        except OSError:
            return self.app.t("convert.need_writable").replace("{path}", path)
        return None

    def _work(self, src, dst):
        counts = {"converted": 0, "copied": 0, "placeholder": 0, "skipped": 0}
        failed = 0
        total = 0
        try:
            pairs = _collect(src)
            total = len(pairs)
            self._events.put(("total", total))
            if not total:
                self._events.put(("empty", None))
            for index, (path, rel) in enumerate(pairs, start=1):
                if self.stop_flag:
                    break
                row = self._convert_one(path, dst, rel)
                if row["failed"]:
                    failed += 1
                counts[row["action"]] = counts.get(row["action"], 0) + 1
                self._events.put(("row", (index, total, row)))
                # The worker is CPU bound and the Tk main loop shares the GIL;
                # without a yield the window freezes and language/theme switches
                # crawl until the batch ends.
                time.sleep(0.002)
        except Exception as exc:                                    # noqa: BLE001
            self._events.put(("error", str(exc)))
        finally:
            self._events.put(("finish", (counts, failed, total,
                                         bool(self.stop_flag))))

    def _convert_one(self, path, out_root, rel):
        size = _size_of(path)
        dst = os.path.join(out_root, rel)
        row = {"action": "skipped", "rel": rel, "src": size, "dst": 0,
               "note": "", "note_key": "", "problems": [], "failed": False}
        ext = os.path.splitext(path)[1].lower()
        if ext not in SUPPORTED:
            row["note_key"] = "convert.skip.ext"
            return row
        expected = _GEN9_VERSION.get(ext)
        if expected is not None and _rsc7_version(path) == expected:
            row["note_key"] = "convert.skip.gen9"
            return row
        try:
            os.makedirs(os.path.dirname(dst), exist_ok=True)
            res = gen8to9.convert_file(path, dst)
        except OSError as exc:
            row["note"] = self.app.t("convert.need_writable").replace(
                "{path}", os.path.dirname(dst))
            row["failed"] = True
            return row
        except (gen8to9.UnsupportedResource, gen8to9.PlaceholderArchive) as exc:
            row["note"] = str(exc)
            return row
        except Exception as exc:                                    # noqa: BLE001
            row["note_key"] = "convert.skip.read"
            row["note"] = str(exc)
            row["failed"] = True
            return row
        row.update(action=res.action, dst=res.dst_size, src=res.src_size,
                   note=res.note or "", problems=list(res.problems),
                   failed=res.action in ("skipped", "failed"))
        return row

    # -- worker -> Tk thread ---------------------------------------------
    def _pump(self):
        self._progress_job = None
        try:
            # Drain in slices: a fast batch can queue hundreds of rows.  Rows
            # are gathered into one insert because every single insert plus a
            # scroll re-lays-out the whole text widget -- doing that 40 times
            # per slice froze the window for ~437 ms mid-run.
            batch = []
            status = None
            bar = None
            for _ in range(40):
                kind, payload = self._events.get_nowait()
                if kind == "total":
                    self._total = payload
                    bar = (0, max(1, payload))
                elif kind == "row":
                    index, total, row = payload
                    self._rows.append((index, total, row))
                    batch.append((self._row_text(index, total, row), row["action"]))
                    self._done = index
                    bar = (index, max(1, total))
                    status = self.app.t("convert.bar", n=index, total=total)
                elif kind == "empty":
                    batch.append((self.app.t("convert.empty"), "skipped"))
                elif kind == "error":
                    batch.append((self.app.t("convert.error", err=payload), "skipped"))
                elif kind == "finish":
                    self._flush_rows(batch)
                    batch = []
                    bar = None
                    status = None
                    self._finish(*payload)
            self._flush_rows(batch)
            if bar:
                self._bar(*bar)
            if status:
                self._status(status)
        except queue.Empty:
            pass
        except Exception as exc:                                    # noqa: BLE001
            self._append(self.app.t("convert.error", err=str(exc)), "skipped")
        if self.busy:
            self._progress_job = self.after(80, self._pump)

    def _flush_rows(self, batch):
        """Insert a whole slice of report rows with a single scrollbar update."""
        if not batch:
            return
        self.text.configure(state="normal")
        try:
            for text, tag in batch:
                self.text.insert("end", text + "\n", tag or ())
            self.text.see("end")
        finally:
            self.text.configure(state="disabled")

    def _finish(self, counts, failed, total, stopped):
        self.busy = False
        self.stop_flag = False
        self._stop_armed = False
        if getattr(self.app, "busy_owner", None) is self:
            self.app.busy_owner = None
        self._set_running(False)
        summary = self._summary_text(counts, failed)
        self._append(summary, "summary")
        self._counts = (counts, failed)
        self._stopped_line = ""
        if stopped:
            self._stopped_line = self.app.t("convert.stopped", n=self._done)
            self._append(self._stopped_line, "summary")
        self._status(summary)
        self.app.log_line(summary)

    # -- report helpers ---------------------------------------------------
    def _row_text(self, index, total, row):
        action = self.app.t("convert.act.%s" % row["action"])
        size = _human(row["src"]) + " \u2192 " + (_human(row["dst"]) if row["dst"] else "\u2014")
        note = row["note"] or ""
        key = row.get("note_key") or ""
        if key:
            label = self.app.t(key)
            note = ("%s: %s" % (label, note)) if note else label
        if row["problems"]:
            extra = "; ".join(row["problems"])
            note = ("%s %s" % (note, extra)).strip() if note else extra
        line = "[%3d/%3d]  %-9s  %-38s  %s" % (index, total, action, row["rel"], size)
        if note:
            line += "  " + note
        return line

    def _append(self, text, tag=None):
        self.text.configure(state="normal")
        try:
            self.text.insert("end", text + "\n", tag or ())
            self.text.see("end")
        finally:
            self.text.configure(state="disabled")

    def _clear_report(self):
        self.text.configure(state="normal")
        try:
            self.text.delete("1.0", "end")
        finally:
            self.text.configure(state="disabled")
        self._rows = []
        self._counts = None
        self._stopped_line = ""

    def _render_all(self):
        counts = self._counts
        self.text.configure(state="normal")
        try:
            self.text.delete("1.0", "end")
            for index, total, row in self._rows:
                self.text.insert("end", self._row_text(index, total, row) + "\n",
                                 row["action"])
            if counts is not None:
                self.text.insert("end", self._summary_text(*counts) + "\n", "summary")
            if counts is not None and self._stopped_line:
                self.text.insert("end",
                                 self.app.t("convert.stopped", n=self._done) + "\n",
                                 "summary")
            self.text.see("end")
        finally:
            self.text.configure(state="disabled")
        # Tk leaves stale glyphs behind when a Text is refilled while the window
        # is busy; forcing a paint clears the ghosted text.
        self.update_idletasks()

    def _summary_text(self, counts, failed):
        return self.app.t("convert.summary",
                          converted=counts.get("converted", 0),
                          copied=counts.get("copied", 0),
                          placeholder=counts.get("placeholder", 0),
                          skipped=counts.get("skipped", 0),
                          failed=failed)

    def _paint_tags(self):
        c = self.app.c
        self.text.tag_configure("converted", foreground=c("fg"))
        self.text.tag_configure("copied", foreground=c("dim"))
        self.text.tag_configure("placeholder", foreground=c("warning"))
        self.text.tag_configure("skipped", foreground=c("danger"))
        self.text.tag_configure("failed", foreground=c("danger"))
        self.text.tag_configure("summary", foreground=c("accent"))

    def _bar(self, done, total):
        try:
            self.bar.place_configure(relwidth=min(1.0, done / float(max(1, total))))
        except tk.TclError:
            pass

    def _status(self, text):
        try:
            self.status.configure(text=text)
        except tk.TclError:
            pass

    def _set_running(self, on):
        # a Stop click flips the button back at once; the worker winds down in
        # the background and further clicks are ignored until it reports.
        stop_shown = on and not self._stop_armed
        self.action_btn.configure(state="normal",
                                  text=self.app.t("convert.stop" if stop_shown else "convert.start"))

    # -- language / theme -------------------------------------------------
    def retranslate(self):
        """Repaint the page and re-render the report in the new language.

        Rows are stored as data and formatted at draw time, so switching
        language redraws the pane instead of leaving older rows in the previous
        language. There used to be a second retranslate above that re-rendered
        only -- this one silently replaced it, which is why the report stayed in
        the old language.
        """
        c = self.app.c
        self.text.configure(bg=c("inset"), fg=c("fg"), insertbackground=c("fg"))
        for entry in (self.in_entry, self.out_entry):
            entry.configure(bg=c("inset"), fg=c("fg"),
                            highlightbackground=c("stroke"),
                            highlightcolor=c("accent"),
                            readonlybackground=c("inset"))
        self.bottom.configure(bg=c("bg"))
        self.progress.configure(bg=c("track"))
        self.bar.configure(bg=c("accent"))
        self.status.configure(bg=c("bg"), fg=c("dim"))
        self._paint_tags()
        self._set_running(self.busy)
        if self.busy:
            self._status(self.app.t("convert.bar", n=self._done, total=self._total))
        elif self._counts is not None:
            # A finished run keeps its summary in the status bar; re-derive it
            # in the new language instead of leaving the last progress line
            # ("16 / 16 files") frozen there after a language switch.
            self._status(self._summary_text(*self._counts))
        else:
            self._status(self.app.t("convert.idle"))
        self._render_all()


def build_convert_page(app, parent):
    page = ConvertPage(app, parent)
    # _Page subclasses pack their own frame in __init__; this page is a bare
    # tk.Frame, so it has to claim its slot or the page renders blank.
    page.pack(fill="both", expand=True)
    page.owner = page
    return page
