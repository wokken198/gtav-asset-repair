"""Tkinter front-end for gtatools: badge diffuse -> tangent-space normal map.

One window, no console. Two languages (EN / 中文) and two themes (light / dark)
switchable from the header. Defaults: light theme, Chinese.

DDS encode/decode is delegated to texconv.exe. When frozen as a single exe the
binary is unpacked next to the program, so nothing has to be installed.
"""

from __future__ import annotations

import json
import math
import os
import queue
import sys
import tempfile
import threading
import time
import tkinter as tk
import uuid
from tkinter import filedialog, ttk

import numpy as np
from PIL import Image, ImageTk

from . import dds as ddsmod
from .normals import height_field, normal_from_height, shade_preview

APP_TITLE = "gtatools - texture dictionary toolkit (Enhanced & Legacy)"
VERSION = "0.6.0"

LANG = {
    "en": {
        "tagline": "Enhanced & Legacy textures",
        "nav.ped": "PED repair (YDD/YMT)",
    "nav.normal": "Normal map generate (DDS)",
        "nav.mip": "Mip check (YTD/DDS)",
        "nav.ytd": "Texture compression (YTD)",
        "title": "Badge normal map",
        "subtitle": "pick files or a folder, tune the slope, write next to the input",
        "page.normals.title": "Normal map generate",
        "page.normals.sub": "single .dds or a whole folder, tunable parameters; builds normal maps for vehicle badges and writes them next to the source",
        "report": "Report",
        "page.mips.title": "Mipmap check & fill",
        "page.mips.sub": "detect missing mip levels and fill the chain automatically - fixes shimmer and moire at distance and cuts render cost; the original .ytd / .dds is backed up as .bak",
        "page.ytd.title": "Texture compression",
        "page.ytd.sub": "batch-shrink the textures inside .ytd files and write them back to the same folder; the original file is backed up as .bak",
        "page.ped.title": "PED YMT repair",
    "page.ped.sub": "validate the .ymt against its .ydd and correct the parameter drift - fixes misplaced parts, broken LODs, wrong textures, random loading and spawn crashes",
    "ped.files": "PED files",
    "ped.add": "Add folder",
    "ped.clear": "Clear",
    "ped.check": "Check",
    "ped.fix": "Repair selected",
    "ped.pick": "no folder yet - add one first",
    "ped.done": "checked {n} ped(s): {ok} ok, {bad} with problems",
    "ped.fixed": "repaired {n} ped(s)",
    "ped.clean": "every ped already matches its .ydd",
    "ped.fixing": "repairing {name} ...",
    "ped.checking": "checking {name} ...",
    "page.ped.title": "PED YMT 修复",
    "page.ped.sub": "校验 YMT 与 YDD 资源匹配关系，修正参数偏差，解决模型错位、LOD 异常、贴图错乱、随机加载及 Spawn 崩溃",
    "ped.files": "PED 文件",
    "ped.add": "添加文件夹",
    "ped.clear": "清空",
    "ped.check": "检查",
    "ped.fix": "修复选定",
    "ped.pick": "还没有选文件夹",
    "ped.done": "检查完成：{n} 个 PED，{ok} 个正常，{bad} 个有问题",
    "ped.fixed": "修复完成：{n} 个 PED",
    "ped.clean": "所有 PED 都与 .ydd 一致",
    "ped.fixing": "正在修复 {name} ...",
    "ped.checking": "正在检查 {name} ...",
    "mips.files": "Files",
        "mips.add": "Add DDS / YTD",
        "mips.add_dir": "Add folder",
        "mips.check": "Check",
        "mips.clear": "Clear",
        "mips.empty": "nothing to check: add files first",
        "mips.done": "checked {n} texture(s): {bad} incomplete, {ok} ok",
        "mips.all": "Select all",
        "mips.none": "Select none",
        "mips.count": "{n} / {m} selected",
        "mips.f_skip": "Deselect: hair / alpha",
        "mips.fix": "Fix selected",
        "mips.pick": "click a red file to select it",
        "mips.fix_none": "select at least one red file",
        "mips.fixed": "fixed {n} texture(s) -> {out}",
        "mips.clean": "no file needs more mips",
        "ytd.cw": "CodeWalker",
        "ytd.cw_browse": "Browse",
        "ytd.cw_detect": "Detect",
        "ytd.cw_ok": "found",
        "ytd.cw_missing": "not found - pick the CodeWalker folder",
        "ytd.files": "YTD files",
        "ytd.add": "Add YTD",
        "ytd.clear": "Clear",
        "ytd.params": "Compression",
        "ytd.mode": "Mode",
        "ytd.cap": "Long edge limit",
        "ytd.plan": "Analyze",
        "ytd.analyze": "Analyze",
        "ytd.start": "Compress",
        "ytd.none": "add a .ytd file first",
        "ytd.no_cw": "set the CodeWalker folder first",
        "ytd.legacy": "Legacy asset - convert it with CodeWalker before using it in the Enhanced edition.",
        "ytd.version_gen9": "GEN9",
        "ytd.version_gen8": "GEN8",
        "ytd.done": "done: {out}",
        "state.busy": "working...",
        "state.scanning": "reading dictionaries...",
        "state.analyzing": "analysing...",
        "state.compressing": "compressing...",
        "mips.filter": "Filter",
        "mips.f_long": "Select: long edge >= 1024 and missing 3+ mips",
        "mips.f_raw": "Select: uncompressed formats",
        "mips.f_mid": "Select: long edge 512-1024",
        "mips.f_alpha": "skip hair/alpha textures",
        "mips.c_sel": "",
        "mips.c_file": "File",
        "mips.c_tex": "Texture",
        "mips.c_size": "Size",
        "mips.c_fmt": "Format",
        "mips.c_mips": "Mips",
        "ytd.limit": "Long edge",
        "ytd.limit_off": "tier mode ignores this",
        "ytd.add_dir": "Add folder",
        "ytd.mem": "memory  {before:.1f} MB -> {after:.1f} MB  ({pct}%)",
        "ytd.file": "files   {before:.1f} MB -> {after:.1f} MB  ({pct}%)",
        "mode.cap": "Ceiling",
        "mode.tier": "Snap to tier",
        "mode.agg": "Reformat (changes formats)",
        "mode.cap.desc": "Anything longer than {cap} is scaled down to {cap}; textures under 1024 px stay untouched.",
        "mode.tier.desc": "The long edge drops to the closest of 1024 / 1536 / 2048 below it.",
        "mode.agg.desc": "Ceiling at {cap}, plus format swaps: uncompressed -> DXT5, opaque DXT5 -> DXT1. Test the result in game.",
        "help.ytd": (
            "Cap - anything longer than the limit is scaled down to it.\n"
            "Tier - the long edge snaps to 1024 / 1536 / 2048.\n"
            "Aggressive - Cap, plus format swaps: uncompressed -> DXT5,\n"
            "opaque DXT5 -> DXT1. Textures under 1024 px are left alone,\n"
            "normal and spec maps keep their format. Test the result in game."
        ),
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
        "out_hint": "output -> <input folder>",
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
        "prev.src": "diffuse",
        "prev.nrm": "normal map",
        "prev.lit": "lit preview",
        "missing_texconv": "texconv.exe not found - put it next to this program or set TEXCONV",
        "help.params": (
            "Strength - how steep the slopes get.\n"
            "vanilla: 0.7-2 deg median, 25-35 deg bevels\n"
            "recommended (default): 4.5, a touch above vanilla\n"
            "\n"
            "Blur - smoothing before the slope is taken.\n"
            "vanilla badges: hardly any blur in the art\n"
            "recommended (default): 1.2, keeps strokes crisp\n"
            "\n"
            "Alpha weight - how much the silhouette adds.\n"
            "vanilla: the shape comes from the alpha cut-out\n"
            "recommended (default): 0.3, slightly thicker edges"
        ),
    },
    "zh": {
        "tagline": "增强版 & 旧版贴图",
        "nav.ped": "PED 修复（YDD/YMT）",
    "nav.normal": "法线生成（DDS）",
        "nav.mip": "MIP 检查（YTD/DDS）",
        "nav.ytd": "纹理压缩（YTD）",
        "title": "车标法线",
        "subtitle": "选择文件或文件夹，调整参数，结果写到输入所在目录",
        "page.normals.title": "法线生成",
        "page.normals.sub": "支持单张 DDS 或批量目录导入，可配置参数，专为车标贴图生成法线贴图，输出至原目录",
        "report": "报告",
        "page.mips.title": "Mipmap 校验与补全",
        "page.mips.sub": "检测贴图 Mip 链缺失，自动补齐 Mip 层级，改善远距离贴图闪烁、摩尔纹问题，优化渲染性能；原 YTD/DDS 自动备份为 .bak",
        "page.ytd.title": "纹理压缩",
        "page.ytd.sub": "批量压缩 YTD 内贴图，输出至同目录；原文件自动备份为 .bak",
        "mips.files": "文件",
        "mips.add": "添加 DDS / YTD",
        "mips.add_dir": "添加文件夹",
        "mips.check": "开始检查",
        "mips.clear": "清空",
        "mips.empty": "先添加文件",
        "mips.done": "检查完成：{n} 张，{bad} 张缺 mip，{ok} 张正常",
        "mips.all": "全选",
        "mips.none": "全不选",
        "mips.count": "已选 {n} / {m}",
        "mips.f_skip": "不勾选：毛发/alpha",
        "mips.fix": "补齐选定",
        "mips.pick": "点一下标红的文件即可勾选",
        "mips.fix_none": "先勾选至少一个标红的文件",
        "mips.fixed": "补齐完成：{n} 张 -> {out}",
        "mips.clean": "没有需要补 mip 的文件",
        "ytd.cw": "CodeWalker",
        "ytd.cw_browse": "浏览",
        "ytd.cw_detect": "自动探测",
        "ytd.cw_ok": "已找到",
        "ytd.cw_missing": "未找到，请选择 CodeWalker 目录",
        "ytd.files": "YTD 文件",
        "ytd.add": "添加 YTD",
        "ytd.clear": "清空",
        "ytd.params": "压缩参数",
        "ytd.mode": "模式",
        "ytd.cap": "长边上限",
        "ytd.plan": "分析",
        "ytd.analyze": "分析",
        "ytd.start": "开始压缩",
        "ytd.none": "先添加 .ytd 文件",
        "ytd.no_cw": "先设置 CodeWalker 目录",
        "ytd.legacy": "这是 Legacy 资产，若要增强版使用请先用 CodeWalker 进行转换。",
        "ytd.version_gen9": "GEN9",
        "ytd.version_gen8": "GEN8",
        "ytd.done": "完成：{out}",
        "state.busy": "处理中…",
        "state.scanning": "正在读取字典…",
        "state.analyzing": "分析中…",
        "state.compressing": "压缩中…",
        "mips.filter": "筛选",
        "mips.f_long": "勾选：长边 ≥1024 且缺口 ≥3",
        "mips.f_raw": "勾选：未压缩格式",
        "mips.f_mid": "勾选：长边 512–1024",
        "mips.f_alpha": "跳过毛发/透明类",
        "mips.c_sel": "",
        "mips.c_file": "文件",
        "mips.c_tex": "贴图",
        "mips.c_size": "尺寸",
        "mips.c_fmt": "格式",
        "mips.c_mips": "Mip",
        "ytd.limit": "长边上限",
        "ytd.limit_off": "归档模式不使用此上限",
        "ytd.add_dir": "添加文件夹",
        "ytd.mem": "显存  {before:.1f} MB -> {after:.1f} MB  ({pct}%)",
        "ytd.file": "文件  {before:.1f} MB -> {after:.1f} MB  ({pct}%)",
        "mode.cap": "封顶",
        "mode.tier": "归档",
        "mode.agg": "换格式",
        "mode.cap.desc": "超过 {cap} 的贴图缩到 {cap}；长边低于 1024 的不动。",
        "mode.tier.desc": "长边就近下调到 1024 / 1536 / 2048。",
        "mode.agg.desc": "在封顶 {cap} 的基础上改格式：未压缩→DXT5，不透明 DXT5→DXT1。建议压完进游戏验证。",
        "help.ytd": (
            "上限：长边超过限制就压到限制。\n"
            "档位：长边就近落到 1024 / 1536 / 2048。\n"
            "激进：在上限基础上再改格式（未压缩→DXT5、不透明 DXT5→DXT1）。\n"
            "小于 1024 一律不动；法线与 spec 类不改格式。压完请进游戏验证。"
        ),
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
        "out_hint": "输出 -> <输入目录>",
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
        "prev.src": "原图",
        "prev.nrm": "法线",
        "prev.lit": "合成效果",
        "missing_texconv": "找不到 texconv.exe：放到本程序旁边，或设置 TEXCONV",
        "help.params": (
            "强度 —— 坡度放大的倍数。\n"
            "原版车标：中位 0.7–2°，倒角 25–35°\n"
            "推荐（本软件默认）：4.5，比原版略突出\n"
            "\n"
            "模糊 —— 算坡度之前的平滑。\n"
            "原版车标：素材本身几乎没有模糊\n"
            "推荐（本软件默认）：1.2，保留笔画锐度\n"
            "\n"
            "Alpha 权重 —— 轮廓剪影占高度的比例。\n"
            "原版：形状来自 alpha 镂空\n"
            "推荐（本软件默认）：0.3，边缘略厚一点"
        ),
    },
}

# --- Ped repair strings (kept in one place so both languages stay in sync) ---
PED_TEXT = {
    "en": {
        "page.ped.title": "PED YMT repair",
        "page.ped.sub": "validate the .ymt against its .ydd and correct the parameter drift - fixes misplaced parts, broken LODs, wrong textures, random loading and spawn crashes",
        "ped.files": "PED files",
        "ped.add": "Add folder",
        "ped.clear": "Clear",
        "ped.check": "Check",
        "ped.fix": "Fix selected",
        "ped.align": "Align to YDD",
        "ped.aligning": "aligning {name} ...",
        "ped.pick": "no folder yet - add one that holds .ydd + .ymt pairs",
        "ped.checking": "checking {name} ...",
        "ped.fixing": "fixing {name} ...",
        "ped.done": "checked {n} PED(s): {ok} ok, {bad} with problems",
        "ped.fixed": "fixed {n} PED(s)",
        "ped.picked": "{n} selected",
        "ped.clean": "every PED matches its .ydd",
        "ped.hdr.check": "Check {n} PED(s)",
        "ped.hdr.fix": "Repair {n} PED(s)",
        "ped.folder": "folder: {path}",
    },
    "zh": {
        "page.ped.title": "PED YMT 修复",
        "page.ped.sub": "校验 YMT 与 YDD 资源匹配关系，修正参数偏差，解决模型错位、LOD 异常、贴图错乱、随机加载及 Spawn 崩溃",
        "ped.files": "PED 文件",
        "ped.add": "添加文件夹",
        "ped.clear": "清空",
        "ped.check": "开始检查",
        "ped.fix": "修复选定",
        "ped.align": "对齐到 YDD",
        "ped.aligning": "正在对齐 {name} ...",
        "ped.pick": "还没有选文件夹（需要同时含 .ydd 与 .ymt）",
        "ped.checking": "正在检查 {name} …",
        "ped.fixing": "正在修复 {name} …",
        "ped.done": "检查完成：{n} 个 PED，{ok} 个正常，{bad} 个有问题",
        "ped.fixed": "修复完成：{n} 个 PED",
        "ped.picked": "已选 {n} 个",
        "ped.clean": "所有 PED 都与 .ydd 一致",
        "ped.hdr.check": "检查 {n} 个 PED",
        "ped.hdr.fix": "修复 {n} 个 PED",
        "ped.folder": "目录：{path}",
    },
}
for _lang, _items in PED_TEXT.items():
    LANG.setdefault(_lang, {}).update(_items)
LANG["en"].update({k: v for k, v in PED_TEXT["en"].items()})
LANG["zh"].update({k: v for k, v in PED_TEXT["zh"].items()})

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


class Switch(tk.Canvas):
    """Two labels with a track between them; the knob eases from side to side."""

    ANIM_MS = 170
    FRAME_MS = 16

    def __init__(self, master, app: "App", options, on_pick, each: int = 38, height: int = 26,
                 track: int = 44):
        self.app = app
        self.options = list(options)
        self.on_pick = on_pick
        self.value = self.options[0][0]
        self._each, self._h, self._track = each, height, track
        self._pos = 0.0
        self._anim_job = None
        width = each * 2 + track
        super().__init__(master, width=width, height=height,
                         highlightthickness=0, bd=0, cursor="hand2")
        self.bind("<Button-1>", self._click)
        app.switches.append(self)

    def _pill(self, x0, y0, x1, y1, fill):
        r = min((y1 - y0) / 2, (x1 - x0) / 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0 + (y1 - y0) / 2, x1 - r, y1, x0 + r, y1,
               x0, y0 + (y1 - y0) / 2]
        self.create_polygon(pts, smooth=True, splinesteps=24, fill=fill, outline="")

    def redraw(self):
        c = self.app.c
        L, T, H = self._each, self._track, self._h
        self.configure(bg=c("bg"))
        self.delete("all")
        ty0, ty1 = H / 2 - 8, H / 2 + 8
        self._pill(L, ty0, L + T, ty1, c("inset"))
        d = 20
        travel = T - d - 4
        kx = L + 2 + travel * self._pos
        self.create_oval(kx, H / 2 - d / 2, kx + d, H / 2 + d / 2,
                         fill=c("accent"), outline=c("accent_dark"), width=1)
        for i, (_code, text) in enumerate(self.options):
            cx = L / 2 if i == 0 else L + T + L / 2
            self.create_text(cx, H / 2 + 1, text=text,
                             fill=c("dim") if i == int(round(self._pos)) else c("faint"),
                             font=_font(8, i == int(round(self._pos))))

    # -- state -------------------------------------------------------------
    def set_value(self, code):
        self.value = code
        self._stop()
        self._pos = float(self._index(code))
        self.redraw()

    def _index(self, code) -> int:
        for i, (c, _t) in enumerate(self.options):
            if c == code:
                return i
        return 0

    def _stop(self):
        if self._anim_job is not None:
            try:
                self.after_cancel(self._anim_job)
            except tk.TclError:
                pass
            self._anim_job = None

    def _animate_to(self, target: int):
        self._stop()
        start = self._pos
        end = float(target)
        ticks = max(1, self.ANIM_MS // self.FRAME_MS)

        def step(i):
            t = i / ticks
            ease = 0.5 - 0.5 * math.cos(math.pi * t)   # ease-in-out
            self._pos = start + (end - start) * ease
            self.redraw()
            if i < ticks:
                self._anim_job = self.after(self.FRAME_MS, lambda: step(i + 1))
            else:
                self._pos = end
                self._anim_job = None
                self.redraw()

        step(0)

    def _click(self, event):
        mid = self._each + self._track / 2
        idx = 0 if event.x < mid else 1
        idx = max(0, min(len(self.options) - 1, idx))
        code = self.options[idx][0]
        if code != self.value:
            self.value = code
            self._animate_to(idx)
            self.on_pick(code)


class Card(tk.Frame):
    """A 1px-bordered panel with a small caps title and a padded body."""

    def __init__(self, master, app: "App", title_key: str = "", help_key: str = ""):
        super().__init__(master, bg=app.c("card"), highlightbackground=app.c("stroke"),
                         highlightthickness=1, bd=0)
        self.app = app
        self.active = False
        app.cards.append(self)
        head = tk.Frame(self, bg=app.c("card"))
        head.pack(fill="x", padx=14, pady=(9, 0))
        app.style_widget(head, "card")
        self.title = tk.Label(head, text="", bg=app.c("card"), fg=app.c("faint"), font=_font(9, True))
        self.title.pack(side="left")
        if help_key:
            self.help = tk.Label(head, text="?", bg=app.c("card"), fg=app.c("faint"),
                                 font=_font(9, True), cursor="hand2", padx=4)
            self.help.pack(side="left", padx=(6, 0))
            app.style_widget(self.help, "card", "faint")
            self.help.bind("<Enter>", lambda _e: app.tip_show(app.t(help_key), self.help))
            self.help.bind("<Leave>", lambda _e: app.tip_hide())
            self.help.bind("<Button-1>", lambda _e: app.tip_show(app.t(help_key), self.help))
        self.body = tk.Frame(self, bg=app.c("card"))
        self.body.pack(fill="both", expand=True, padx=14, pady=(10, 14))
        app.style_widget(self, "card")
        app.style_widget(self.title, "card", "faint")
        app.style_widget(self.body, "card")
        if title_key:
            app.bind_text(self.title, title_key)


class Segmented(tk.Canvas):
    """A fixed-width segmented picker: one pill per option, no layout shift."""

    def __init__(self, master, app: "App", options, on_pick, each: int = 0, height: int = 26):
        self.app = app
        self.options = list(options)
        self.on_pick = on_pick
        self.value = self.options[0][0]
        self._each, self._h = each or 80, height
        super().__init__(master, width=self._each * len(self.options), height=height,
                         highlightthickness=0, bd=0, cursor="hand2")
        if not each:
            font = _font(9, True)
            widest = 0
            for _code, text in self.options:
                widest = max(widest, int(self.tk.call("font", "measure", font, text)))
            self._each = widest + 26
            self.configure(width=self._each * len(self.options))
        self.bind("<Button-1>", self._click)
        app.switches.append(self)

    def _round(self, x0, y0, x1, y1, fill):
        r = min((y1 - y0) / 2, (x1 - x0) / 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0 + (y1 - y0) / 2, x1 - r, y1, x0 + r, y1,
               x0, y0 + (y1 - y0) / 2]
        self.create_polygon(pts, smooth=True, splinesteps=24, fill=fill, outline="")

    def redraw(self):
        c = self.app.c
        E, H = self._each, self._h
        self.configure(bg=c("bg"))
        self.delete("all")
        w = E * len(self.options)
        self._round(0, 2, w, H - 2, c("inset"))
        active = self._index(self.value)
        for i, (_code, text) in enumerate(self.options):
            x0 = i * E + 2
            x1 = x0 + E - 4
            on = i == active
            if on:
                self._round(x0, 4, x1, H - 4, c("accent"))
            self.create_text((x0 + x1) / 2, H / 2 + 1, text=text,
                             fill=c("on_accent") if on else c("faint"), font=_font(9, on))

    def set_value(self, code):
        self.value = code
        self.redraw()

    def _index(self, code) -> int:
        for i, (c, _t) in enumerate(self.options):
            if c == code:
                return i
        return 0

    def _click(self, event):
        idx = max(0, min(len(self.options) - 1, int(event.x // self._each)))
        code = self.options[idx][0]
        if code == self.value:
            return
        self.set_value(code)
        self.on_pick(code)


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
    Switch = Switch
    Segmented = Segmented

    def __init__(self):
        super().__init__()
        self.cfg = load_config()
        self.page_objects = {}
        self.core_dir = self.cfg.get("cw", "")
        if self.core_dir and not os.path.isdir(self.core_dir):
            self.core_dir = ""
        self.current_page = "normals"
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
        self.cards: list = []
        self.text_bindings: list[tuple] = []
        self.lang_buttons: dict = {}
        self.theme_buttons: dict = {}
        self.switches: list = []
        self._tip = None
        try:
            self.texconv = ddsmod.resolve_texconv(os.environ.get("TEXCONV", "texconv.exe"))
        except FileNotFoundError:
            self.texconv = ""

        self.title(APP_TITLE)
        self.geometry("1220x800")
        self.minsize(1120, 700)
        self.configure(bg=self.c("bg"))
        self._set_icon()
        self.report_callback_exception = self._on_callback_error

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
        self._purge_stale_temp()
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

    def tree_style(self):
        """Return a ttk style name painted with the current theme."""
        from tkinter import ttk

        name = "Pav.Treeview"
        style = ttk.Style(self)
        try:
            style.theme_use("clam")
        except tk.TclError:
            pass
        style.configure(name, background=self.c("inset"), fieldbackground=self.c("inset"),
                        foreground=self.c("dim"), rowheight=20, borderwidth=0, font=_mono(8))
        style.configure(name + ".Heading", background=self.c("card"), foreground=self.c("faint"),
                        relief="flat", borderwidth=0)
        style.map(name, background=[("selected", self.c("hover"))],
                  foreground=[("selected", self.c("fg"))])
        return name

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
        except Exception:
            pass
        for canvas in getattr(self, "preview_canvases", []):
            try:
                canvas.configure(bg=self.c("inset"), highlightbackground=self.c("stroke"))
            except tk.TclError:
                pass
        for card in getattr(self, "cards", []):
            try:
                card.configure(bg=self.c("card"),
                               highlightbackground=self.c("accent") if card.active
                               else self.c("stroke"))
                card.body.configure(bg=self.c("card"))
                card.title.configure(bg=self.c("card"), fg=self.c("faint"))
            except tk.TclError:
                pass
        self._retranslate_pages()
        self._paint_nav(getattr(self, "current_page", "normals"))
        try:
            self.scroll_style()
        except Exception:                                     # noqa: BLE001
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
        for sw in self.switches:
            sw.redraw()

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
        self._update_titles()
        self._retranslate_pages()
        for widget, key in self.text_bindings:
            try:
                widget.configure(text=self.t(key))
            except tk.TclError:
                pass
        for code, btn in self.theme_buttons.items():
            btn.configure(text=self.t(code))
        sw = getattr(self, "sw_theme", None)
        if sw is not None:
            sw.options = [("light", self.t("light")), ("dark", self.t("dark"))]
            sw.redraw()
        if getattr(self, "status", None) is not None and not self.running:
            self.status.configure(text=self.t("idle"))

    def _retranslate_pages(self):
        for page in getattr(self, "page_objects", {}).values():
            hook = getattr(page, "retranslate", None)
            if hook is not None:
                try:
                    hook()
                except Exception as exc:  # noqa: BLE001 - a page must not break switching
                    self.log_line("err retranslate: %s" % exc)

    def set_lang(self, code: str):
        if code == self.lang:
            return
        self.lang = code
        if getattr(self, "sw_lang", None) is not None:
            self.sw_lang.set_value(code)
        self._apply_lang()
        self._apply_theme()
        self._refresh_count()
        self._save()

    def _drop_pages(self):
        for key in ("mips", "ytd"):
            page = self.pages.pop(key, None)
            self.page_objects.pop(key, None)
            if page is not None:
                page.destroy()
        alive = []
        for sw in getattr(self, "switches", []):
            try:
                if sw.winfo_exists():
                    alive.append(sw)
            except tk.TclError:
                pass
        self.switches = alive
        self.current_page = "normals"

    def set_theme(self, code: str):
        if code == self.theme:
            return
        self.theme = code
        if getattr(self, "sw_theme", None) is not None:
            self.sw_theme.set_value(code)
        self._apply_theme()
        for page in list(getattr(self, "page_objects", {}).values()):
            try:
                page.retranslate()
            except Exception:                                 # noqa: BLE001
                pass
        self._save()

    def scroll_style(self):
        """A flat ttk scrollbar that follows the theme."""
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Pav.Vertical.TScrollbar", gripcount=0,
                        background=self.c("stroke"), darkcolor=self.c("card"),
                        lightcolor=self.c("card"), troughcolor=self.c("inset"),
                        bordercolor=self.c("inset"), arrowcolor=self.c("faint"),
                        relief="flat", arrowsize=11, width=11)
        style.map("Pav.Vertical.TScrollbar",
                  background=[("pressed", self.c("stroke_hi")), ("active", self.c("stroke_hi"))],
                  arrowcolor=[("active", self.c("fg"))])
        return "Pav.Vertical.TScrollbar"

    def _paint_nav(self, name):
        for key, (row, lab, accent) in getattr(self, "nav_rows", {}).items():
            active = key == name
            bg = self.c("hover") if active else self.c("nav")
            row.configure(bg=bg)
            lab.configure(bg=bg, fg=self.c("fg") if active else self.c("faint"),
                          font=_font(10, active))
            accent.configure(bg=self.c("accent") if active else self.c("nav"))

    def _save(self):
        self.cfg.update(dict(lang=self.lang, theme=self.theme, cw=self.core_dir,
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
        for key, value in LANG[self.lang].items():
            if value == text:
                self.bind_text(btn, key)
                break
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
        self._nav = tk.Frame(self, bg=self.c("nav"), width=232)
        self._nav.pack(side="left", fill="y")
        self._nav.pack_propagate(False)
        brand = tk.Label(self._nav, text="gtatools", bg=self.c("nav"), fg=self.c("fg"), font=_font(15, True))
        brand.pack(anchor="w", padx=18, pady=(20, 2))
        self.style_widget(brand, "nav", "fg")
        tag = self.bind_text(tk.Label(self._nav, text="", bg=self.c("nav"), fg=self.c("faint"),
                                      font=_font(9)), "tagline")
        tag.pack(anchor="w", padx=18, pady=(0, 18))
        self.style_widget(tag, "nav", "faint")

        self.nav_rows = {}
        for page, key in (("normals", "nav.normal"), ("ytd", "nav.ytd"), ("mips", "nav.mip"), ("ped", "nav.ped")):
            active = page == "normals"
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
            row.bind("<Button-1>", lambda _e, p=page: self.show_page(p))
            lab.bind("<Button-1>", lambda _e, p=page: self.show_page(p))
            self.nav_rows[page] = (row, lab, accent)

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
        h1 = tk.Label(titles, text="", bg=self.c("bg"), fg=self.c("fg"), font=_font(17, True))
        self.h1 = h1
        h1.pack(anchor="w")
        self.style_widget(h1, "bg", "fg")
        sub = tk.Label(titles, text="", bg=self.c("bg"), fg=self.c("faint"), font=_font(10),
                       justify="left", anchor="w", wraplength=840)
        self.sub = sub
        sub.pack(anchor="w", pady=(2, 0))
        self.style_widget(sub, "bg", "faint")

        toggles = tk.Frame(head, bg=self.c("bg"))
        toggles.pack(side="right", anchor="n")
        self.style_widget(toggles, "bg")
        self.sw_lang = Switch(toggles, self, [("en", "EN"), ("zh", "\u4e2d\u6587")],
                              self.set_lang, each=46, height=26)
        self.sw_lang.pack(side="left", padx=(0, 12))
        self.sw_lang.set_value(self.lang)
        sep = tk.Frame(toggles, bg=self.c("stroke"), width=1, height=18)
        sep.pack(side="left", padx=(0, 12))
        self.sw_theme = Switch(toggles, self,
                               [("light", self.t("light")), ("dark", self.t("dark"))],
                               self.set_theme, each=56, height=26)
        self.sw_theme.pack(side="left")
        self.sw_theme.set_value(self.theme)

        self.page_host = tk.Frame(self._main, bg=self.c("bg"))
        self.page_host.pack(fill="both", expand=True, pady=(14, 0))
        self.style_widget(self.page_host, "bg")

        self.page_normals = tk.Frame(self.page_host, bg=self.c("bg"))
        self.style_widget(self.page_normals, "bg")
        self.pages = {"normals": self.page_normals}
        self.page_normals.pack(fill="both", expand=True)
        main = self.page_normals
        body = tk.Frame(main, bg=self.c("bg"))
        body.pack(fill="both", expand=True)
        self.style_widget(body, "bg")

        params = Card(body, self, "params", help_key="help.params")
        self.params_card = params
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
        self.bind_text(self._button(btnrow, "", self.remove_selected), "remove").pack(side="left")
        self.bind_text(self._button(btnrow, "", self.clear_files), "clear").pack(side="right")

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
                                  float(cfg.get("strength", 4.5)))
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
        self.footer = footer
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
        self.bottom = bottom
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
        self.preview_canvases = []
        for key in ("prev.src", "prev.nrm", "prev.lit"):
            col = tk.Frame(prev.body, bg=self.c("card"))
            col.pack(side="left", fill="both", expand=True, padx=(0, 8))
            self.style_widget(col, "card")
            cap = self.bind_text(tk.Label(col, text="", bg=self.c("card"), fg=self.c("faint"),
                                          font=_font(8, True), anchor="w"), key)
            cap.pack(fill="x")
            self.style_widget(cap, "card", "faint")
            canvas = tk.Canvas(col, bg=self.c("inset"), highlightthickness=1,
                               highlightbackground=self.c("stroke"), width=10, height=150)
            canvas.pack(fill="both", expand=True, pady=(3, 0))
            canvas.bind("<Configure>", lambda _e: self._schedule_preview())
            self.preview_canvases.append(canvas)
        self._preview_job = None
        self._preview_photo = None

    # ------------------------------------------------------------ page switching
    def show_page(self, name):
        if name not in self.pages:
            from .gui_pages import build_mips_page, build_ped_page, build_ytd_page

            page = tk.Frame(self.page_host, bg=self.c("bg"))
            self.style_widget(page, "bg")
            self.pages[name] = page
            builder = {"mips": build_mips_page, "ped": build_ped_page,
                       "ytd": build_ytd_page}[name]
            holder = builder(self, page)
            self.page_objects[name] = holder.owner
        for key, page in self.pages.items():
            if key == name:
                page.pack(fill="both", expand=True)
            else:
                page.pack_forget()
        self._paint_nav(name)
        self.current_page = name
        if name == "normals":
            self.footer.pack(fill="x", pady=(12, 0))
            self.bottom.pack(fill="x", pady=(12, 0))
        else:
            self.footer.pack_forget()
            self.bottom.pack_forget()
        self._update_titles()

    def _update_titles(self):
        page = getattr(self, "current_page", "normals")
        try:
            self.h1.configure(text=self.t("page.%s.title" % page))
            self.sub.configure(text=self.t("page.%s.sub" % page))
        except tk.TclError:
            pass

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
            self.log_line(f"added {added} file(s)")

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
    def _schedule_preview(self):
        if getattr(self, "_preview_job", None) is not None:
            try:
                self.after_cancel(self._preview_job)
            except tk.TclError:
                pass
        self._preview_job = self.after(120, self._draw_preview)

    def _draw_preview(self):
        self._preview_job = None
        canvases = getattr(self, "preview_canvases", [])
        if not canvases:
            return
        for canvas in canvases:
            canvas.delete("all")
        self._preview_photos = []
        path = self.selected_file()
        if not path:
            cv = canvases[0]
            cv.create_text(max(cv.winfo_width(), 120) // 2, max(cv.winfo_height(), 80) // 2,
                           text=self.t("no_preview"), fill=self.c("faint"), font=_font(9))
            return
        try:
            rgba = self._load_preview_rgba(path)
            alpha_w = float(self.sl_alpha.value.get())
            hf = height_field(rgba, luma_weight=1.0 - alpha_w, mask_weight=alpha_w,
                              blur=float(self.sl_blur.value.get()))
            nrm = normal_from_height(hf, strength=float(self.sl_strength.value.get()))
            lit = shade_preview(rgba, nrm, ambient=0.28, diffuse=1.05, spec=0.45)
            tiles = [self._to_rgb(rgba), Image.fromarray(nrm, "RGB"),
                     Image.fromarray((lit * 255).astype(np.uint8), "RGB")]
        except Exception as exc:  # noqa: BLE001
            cv = canvases[0]
            cv.create_text(max(cv.winfo_width(), 120) // 2, max(cv.winfo_height(), 80) // 2,
                           text=str(exc)[:90], fill=self.c("danger"), font=_font(9))
            return
        for canvas, tile in zip(canvases, tiles):
            cw, ch = max(canvas.winfo_width(), 80), max(canvas.winfo_height(), 60)
            img = tile.copy()
            img.thumbnail((cw - 10, ch - 10), Image.LANCZOS)
            photo = ImageTk.PhotoImage(img)
            canvas.create_image(cw // 2, ch // 2, image=photo, anchor="center")
            self._preview_photos.append(photo)

    def _to_rgb(self, rgba: np.ndarray) -> Image.Image:
        im = Image.fromarray((rgba * 255).astype(np.uint8), "RGBA")
        bg = Image.new("RGBA", im.size, (255, 255, 255, 255))
        bg.alpha_composite(im)
        return bg.convert("RGB")

    def _scratch_roots(self) -> list[str]:
        roots = [os.path.join(tempfile.gettempdir(), "gtatools")]
        local = os.environ.get("LOCALAPPDATA")
        if local:
            roots.append(os.path.join(local, "gtatools", "_tmp"))
        roots.append(os.path.join(self._app_dir(), "_tmp"))
        return roots

    @staticmethod
    def _app_dir() -> str:
        if getattr(sys, "frozen", False):
            return os.path.dirname(os.path.abspath(sys.executable))
        return os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

    def _scratch(self, near: str | None = None) -> str:
        """Fresh work dir: %TEMP% first, then LOCALAPPDATA, exe dir, finally next to the input."""
        candidates = self._scratch_roots()
        if near:
            base = os.path.dirname(os.path.abspath(near)) if os.path.isfile(near) else os.path.abspath(near)
            candidates.append(os.path.join(base, ".gtatools_tmp"))
        last = None
        for root in candidates:
            try:
                os.makedirs(root, exist_ok=True)
                work = os.path.join(root, "run-" + uuid.uuid4().hex[:10])
                os.makedirs(work, exist_ok=True)
                return work
            except OSError as exc:
                last = exc
        raise OSError(f"no writable temp directory ({last})")

    def _purge_stale_temp(self):
        """Drop leftovers from an interrupted run (older than a day)."""
        cutoff = time.time() - 86400
        for root in self._scratch_roots()[:2]:
            try:
                for name in os.listdir(root):
                    path = os.path.join(root, name)
                    if not name.startswith("run-") or not os.path.isdir(path):
                        continue
                    if os.path.getmtime(path) < cutoff:
                        self._cleanup(path)
            except OSError:
                pass

    def tip_show(self, text: str, anchor):
        self.tip_hide()
        try:
            x = anchor.winfo_rootx() + 18
            y = anchor.winfo_rooty() + anchor.winfo_height() + 8
        except tk.TclError:
            return
        top = tk.Toplevel(self)
        top.wm_overrideredirect(True)
        top.configure(bg=self.c("stroke"))
        box = tk.Frame(top, bg=self.c("card"))
        box.pack(padx=1, pady=1)
        tk.Label(box, text=text, justify="left", bg=self.c("card"), fg=self.c("dim"),
                 font=_font(9), padx=12, pady=10, wraplength=400).pack()
        top.wm_geometry(f"+{x}+{y}")
        top.lift()
        top.attributes("-topmost", True)
        top.update_idletasks()
        tip_w = top.winfo_width()
        right_edge = self.winfo_rootx() + self.winfo_width() - 10
        bottom_edge = self.winfo_rooty() + self.winfo_height() - 10
        if anchor.winfo_rootx() > self.winfo_rootx() + self.winfo_width() // 2:
            x = anchor.winfo_rootx() - tip_w - 16
        elif x + tip_w > right_edge:
            x = max(self.winfo_rootx() + 10, anchor.winfo_rootx() - tip_w - 16)
        if y + top.winfo_height() > bottom_edge:
            y = max(self.winfo_rooty() + 10, anchor.winfo_rooty() - top.winfo_height() - 12)
        top.wm_geometry(f"+{x}+{y}")
        if x + top.winfo_width() > self.winfo_screenwidth() - 8:
            x = max(8, anchor.winfo_rootx() - top.winfo_width() - 12)
            top.wm_geometry(f"+{x}+{y}")
        self._tip = top

    def tip_hide(self):
        if self._tip is not None:
            try:
                self._tip.destroy()
            except tk.TclError:
                pass
            self._tip = None

    def _cleanup(self, path: str):
        import shutil
        shutil.rmtree(path, ignore_errors=True)
        parent = os.path.dirname(path)
        if os.path.basename(path).startswith("run-"):
            try:
                if not os.listdir(parent):
                    os.rmdir(parent)
            except OSError:
                pass

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

    def _on_callback_error(self, exc, value, tb):
        """Never let a widget callback kill the app; put it in the log instead."""
        import traceback

        detail = "".join(traceback.format_exception(exc, value, tb))
        try:
            self.log_line(f"err {value}")
            for line in detail.strip().splitlines()[-4:]:
                self.log_line(f"    {line.strip()}")
            self.status.configure(text=str(value))
        except Exception:  # noqa: BLE001 - logging must not recurse
            pass

    def run(self):
        if self.running:
            return
        if not self.files:
            self.status.configure(text=self.t("nothing"))
            return
        if not self.texconv or not os.path.isfile(self.texconv):
            self.status.configure(text=self.t("missing_texconv"))
            self.log_line("err texconv.exe not found: put it next to this program")
            return
        self._save()
        self.running = True
        self.cancel.clear()
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=len(self.files))
        self.status.configure(text=self.t("processing", n=0))
        first = self.files[0]
        out_dir = os.path.dirname(os.path.abspath(first))
        self.log_line(f"start: {len(self.files)} file(s) -> {out_dir}")
        params = dict(fmt=self.fmt.get(),
                      strength=float(self.sl_strength.value.get()),
                      blur=float(self.sl_blur.value.get()),
                      alpha_w=float(self.sl_alpha.value.get()),
                      resize=self.resize.get(),
                      max_mips=self.max_mips.get())
        self.worker = threading.Thread(target=self._work, args=(params,), daemon=True)
        self.worker.start()

    def cancel_run(self):
        self.cancel.set()
        self.status.configure(text=self.t("cancelling"))

    def _work(self, params):
        made = failed = 0
        fmt = params["fmt"]
        strength = params["strength"]
        blur = params["blur"]
        alpha_w = params["alpha_w"]
        resize = params["resize"]
        max_mips = params["max_mips"]
        total = len(self.files)
        for idx, path in enumerate(list(self.files), 1):
            if self.cancel.is_set():
                break
            try:
                dest = self._one(path, fmt, strength, blur, alpha_w, resize, max_mips)
                made += 1
                self.queue.put(("ok", (path, dest)))
            except Exception as exc:  # noqa: BLE001
                failed += 1
                self.queue.put(("fail", (path, str(exc))))
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
            stem = os.path.splitext(os.path.basename(path))[0]
            return self._publish(produced, path, stem)
        finally:
            self._cleanup(tmp)

    @staticmethod
    def _publish(produced: str, source: str, stem: str) -> str:
        """Move the fresh dds next to its source; fall back when that folder is locked."""
        candidates = [os.path.dirname(os.path.abspath(source)),
                      os.path.join(os.path.expanduser("~"), "Documents", "gtatools", "normals"),
                      os.path.join(os.path.expanduser("~"), "gtatools-output")]
        last = None
        for folder in candidates:
            try:
                os.makedirs(folder, exist_ok=True)
            except OSError as exc:
                last = exc
                continue
            for n in range(6):
                name = f"{stem}_n.dds" if n == 0 else f"{stem}_n_{n + 1}.dds"
                dest = os.path.join(folder, name)
                try:
                    if os.path.exists(dest):
                        try:
                            os.chmod(dest, 0o666)
                        except OSError:
                            pass
                    os.replace(produced, dest)
                    return dest
                except OSError as exc:
                    last = exc
                    if not os.path.exists(produced):
                        raise
        raise OSError(f"cannot write the result ({last})")

    def _pump(self):
        try:
            while True:
                kind, payload = self.queue.get_nowait()
                if kind == "progress":
                    idx, total = payload
                    self.progress.configure(value=idx)
                    self.status.configure(text=self.t("processing", n=idx))
                elif kind == "ok":
                    src, dest = payload
                    size = ""
                    try:
                        size = f" ({os.path.getsize(dest):,} B)"
                    except OSError:
                        pass
                    self.log_line(f"ok {os.path.basename(src)} -> {dest}{size}")
                elif kind == "fail":
                    src, err = payload
                    self.log_line(f"err {os.path.basename(src)}: {err}")
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
