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
from PIL import Image, ImageDraw, ImageTk

from . import dds as ddsmod
from .normals import height_field, normal_from_height, shade_preview

APP_TITLE = "GTA5 tools - texture dictionary toolkit (Enhanced & Legacy)"
VERSION = "0.6.3"
ISSUE_URL = "https://github.com/wokken198/gtav-toolkit/issues"

LANG = {
    "en": {
        "mips.skip_note": "script_rt_* render targets are skipped on purpose - their mip chain is not rebuilt",
        "help.script_rt": "script_rt_* textures are written by the game at runtime: dashboard dials, in-car screens, camera feeds.\nTheir mip chain follows the render-target size, so forcing extra mips blurs or breaks the live picture. The tool never touches them, so they stay listed as incomplete - that is expected.",
        "tagline": "Enhanced & Legacy textures",
        "nav.ped": "Ped repair (YMT)",
    "nav.normal": "Normal maps (DDS)",
        "nav.mip": "Mip check (YTD)",
        "nav.ytd": "Textures (YTD)",
        "title": "Badge normal map",
        "subtitle": "pick files or a folder, tune the slope, write next to the input",
        "page.normals.title": "Generate Normal Maps",
        "page.normals.sub": "Generate normal maps for vehicle badges from .dds files or entire folders. Features tunable parameters; outputs are saved next to the source files.",
        "report": "Report",
        "page.mips.title": "Mipmap check & fill",
        "page.mips.sub": "Detects missing mip levels and auto-fills the chain. Fixes distant shimmer/moire and cuts render cost. Original .ytd/.dds backed up as a .bak file.",
        "page.ytd.title": "Texture compression",
        "page.ytd.sub": "Batch-compress textures within .ytd files and save them to the original folder. The original files are backed up as .bak.",
        "page.ped.title": "Ped YMT repair",
    "page.ped.sub": "Validate the .ymt against its .ydd and correct the parameter drift, which may cause misplaced parts, broken LODs, wrong textures, random loading and spawn crashes.",
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
    "page.ped.sub": "Validate the .ymt against its .ydd and correct the parameter drift, which may cause misplaced parts, broken LODs, wrong textures, random loading and spawn crashes.",
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
        "ytd.cw_missing": "not set",
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
        "cancel": "Stop",
        "stopping": "stopping...",
        "hint": "back up the original files first - then verify in game",
        "note.before": "",
        "note.backup": "Back up files before aggressive processing; test in-game afterward.",
        "note.mid": "",
        "note.test": "",
        "note.after": "",
        "note.bug": "Bug reports & inquiries:",
        "busy_other": "another page is still working - wait for it to finish",
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
        "mips.skip_note": "脚本渲染目标贴图（script_rt_*）默认跳过，不补 mip",
        "help.script_rt": "script_rt_* 是游戏运行时写入的渲染目标（仪表盘、车载屏幕、镜头画面）。\n它们的 mip 链由渲染目标尺寸决定，人为补齐会让动态画面变糊甚至崩溃，所以工具一律不动它们，它们会一直显示为“缺”，属于正常。",
        "tagline": "增强版 & 旧版贴图",
        "nav.ped": "PED 修复（YMT）",
    "nav.normal": "法线生成（DDS）",
        "nav.mip": "MIP 检查（YTD/DDS）",
        "nav.ytd": "纹理压缩（YTD）",
        "title": "车标法线",
        "subtitle": "选择文件或文件夹，调整参数，结果写到输入所在目录",
        "page.normals.title": "生成法线贴图",
        "page.normals.sub": "处理 .dds 文件或整个文件夹（支持参数调整）；为车辆徽章生成法线贴图，并将其保存在源文件同级目录下。",
        "report": "报告",
        "page.mips.title": "Mipmap 校验与补全",
        "page.mips.sub": "自动检测缺失的 mip 层级并填充链——修复远处的闪烁和摩尔纹，并降低渲染开销；原 .ytd/.dds 文件将备份为 .bak 文件。",
        "page.ytd.title": "纹理压缩",
        "page.ytd.sub": "批量缩小 .ytd 文件内的纹理，并将其保存回原文件夹；原文件将备份为 .bak 文件。",
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
        "ytd.cw_missing": "未设置",
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
        "mode.tier": "降档",
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
        "cancel": "停止",
        "stopping": "正在停止...",
        "hint": "动手前先备份原件 - 改完请进游戏验证",
        "note.before": "",
        "note.backup": "处理前请备份文件，处理后请在游戏内测试。",
        "note.mid": "",
        "note.test": "",
        "note.after": "",
        "note.bug": "Bug 反馈与咨询：",
        "busy_other": "另一页还在运行 - 请等它结束",
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
        "page.ped.title": "Ped YMT repair",
        "page.ped.sub": "Validate the .ymt against its .ydd and correct the parameter drift, which may cause misplaced parts, broken LODs, wrong textures, random loading and spawn crashes.",
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
        "page.ped.sub": "用对应的 ydd 校验 .ymt，并纠正参数漂移；该问题可能导致部件错位、LOD 断裂、纹理错误、随机加载及生成崩溃。",
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
    "light": dict(bg="#edf1f7", nav="#e7ecf4", card="#ffffff", hover="#f1f5fa", inset="#f7f9fc",
                  stroke="#dde4ee", stroke_hi="#b7c1d0", fg="#101725", dim="#48536a",
                  faint="#7d8798", accent="#0f9d67", accent_dark="#0b7a50", on_accent="#ffffff",
                  green="#0f8f5f", danger="#d32f45", warning="#a9731b", track="#dbe2ec",
                  btn="#eef8f2", btn_hover="#d5efdf", btn_press="#c2e7d2", btn_stroke="#cfe7da"),
    "dark": dict(bg="#090a0c", nav="#060709", card="#111317", hover="#171b21", inset="#07080a",
                 stroke="#272c34", stroke_hi="#48515e", fg="#f4f6f9", dim="#a3aab5",
                 faint="#5b6471", accent="#34d094", accent_dark="#14885e", on_accent="#17130a",
                 green="#45e09a", danger="#ff4858", warning="#ffbe4b", track="#2b3039",
                 btn="#131c18", btn_hover="#1c3128", btn_press="#254435", btn_stroke="#28382f"),
}

FORMATS = ["DXT1", "DXT5", "BC5_UNORM", "BC7_UNORM"]
RESIZE_CHOICES = ["KEEP", "2048", "1024", "512", "256", "128"]
MIP_CHOICES = ["FULL", "13", "12", "11", "10", "9", "8", "7", "6"]


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


_ROUND_CACHE: dict = {}


def _round_photo(app: "App", w: int, h: int, radius: int, fill: str, stroke: str | None = None):
    """A cached rounded-rectangle photo; supersampled 2x so the corners stay clean."""
    from PIL import ImageDraw

    w, h = max(1, int(w)), max(1, int(h))
    key = (w, h, radius, fill, stroke, getattr(app, "theme", ""))
    photo = _ROUND_CACHE.get(key)
    if photo is not None:
        return photo
    ss = 2
    im = Image.new("RGBA", (w * ss, h * ss), (0, 0, 0, 0))
    draw = ImageDraw.Draw(im)
    draw.rounded_rectangle((0, 0, w * ss - 1, h * ss - 1), radius=radius * ss, fill=fill)
    if stroke:
        # inset by half a pixel so the outline sits inside the fill and keeps the
        # same silhouette as a borderless button
        inset = ss // 2
        draw.rounded_rectangle((inset, inset, w * ss - 1 - inset, h * ss - 1 - inset),
                               radius=max(1, radius * ss - inset), outline=stroke, width=ss)
    im = im.resize((w, h), Image.LANCZOS)
    photo = ImageTk.PhotoImage(im)
    _ROUND_CACHE[key] = photo
    return photo


class PillButton(tk.Canvas):
    """A rounded button drawn on a canvas: primary / secondary / ghost, with hover and press."""

    def __init__(self, master, app: "App", text: str, command=None, kind: str = "secondary",
                 icon: str = ""):
        self.app = app
        self.kind = "primary" if kind in (True, "primary") else kind
        self.command = command
        self.icon = icon
        self._text = text
        self._state = "normal"
        self._hover = False
        self._press = False
        self._pad = int(16 * app.sx)
        self._h = int(34 * app.sx)
        super().__init__(master, width=int(88 * app.sx), height=self._h, bg=app.c("bg"),
                         highlightthickness=0, bd=0, cursor="hand2", takefocus=0)
        self._pw = self._measure()
        super().configure(width=self._pw)
        if not hasattr(app, "pill_buttons"):
            app.pill_buttons = []
        app.pill_buttons.append(self)
        self.bind("<Enter>", self._on_enter)
        self.bind("<Leave>", self._on_leave)
        self.bind("<ButtonPress-1>", self._on_press)
        self.bind("<ButtonRelease-1>", self._on_release)
        self._photo = None
        self._draw()

    def _font(self):
        return _font(9, True)

    def _label(self) -> str:
        return (self.icon + "  " if self.icon else "") + self._text

    def _measure(self) -> int:
        try:
            tw = int(self.tk.call("font", "measure", self._font(), self._label()))
        except tk.TclError:
            tw = len(self._label()) * 7
        return int(max(88 * self.app.sx, tw + self._pad * 2))

    def _colors(self):
        c = self.app.c
        if self._state == "disabled":
            return c("inset"), c("faint"), c("stroke")
        if self.kind == "primary":
            fill = c("accent_dark") if (self._hover or self._press) else c("accent")
            return fill, c("on_accent"), None
        if self.kind == "ghost":
            fill = c("hover") if (self._hover or self._press) else c("bg")
            return fill, c("fg") if self._hover else c("dim"), None
        # secondaries sit on a faint green so they read as buttons at rest and
        # deepen toward the accent under the pointer.
        if self._press:
            return c("btn_press"), c("accent_dark"), c("accent")
        if self._hover:
            return c("btn_hover"), c("accent_dark"), c("accent")
        return c("btn"), c("dim"), c("btn_stroke")

    def _draw(self):
        if getattr(self, "_drawing", False):
            return
        self._drawing = True
        try:
            super().configure(bg=self.app.c("bg"))
            self.delete("all")
            fill, fg, stroke = self._colors()
            radius = int(8 * self.app.sx)
            self._photo = _round_photo(self.app, self._pw, self._h, radius, fill, stroke)
            self.create_image(0, 0, image=self._photo, anchor="nw")
            self.create_text(self._pw / 2, self._h / 2 + 1, text=self._label(), fill=fg,
                             font=self._font())
        finally:
            self._drawing = False

    def _on_enter(self, _e=None):
        if self._state == "disabled":
            return
        self._hover = True
        self._draw()

    def _on_leave(self, _e=None):
        self._hover = False
        self._press = False
        self._draw()

    def _on_press(self, _e=None):
        if self._state == "disabled":
            return
        self._press = True
        self._draw()

    def _on_release(self, _e=None):
        if self._state == "disabled":
            return
        self._press = False
        self._draw()
        if self.command:
            self.command()

    def configure(self, **kw):
        if "text" in kw:
            self._text = kw.pop("text")
            self._pw = self._measure()
            kw["width"] = self._pw
        if "state" in kw:
            self._state = kw.pop("state")
        if kw:
            super().configure(**kw)
        if self._photo is not None:
            self._draw()

    config = configure

    def cget(self, key):
        if key == "text":
            return self._text
        if key == "state":
            return self._state
        return super().cget(key)

    def invoke(self):
        if self._state != "disabled" and self.command:
            self.command()


class Dot(tk.Canvas):
    """A small round status dot."""

    def __init__(self, master, app: "App", color_key: str = "faint", size: int = 8):
        px = max(6, int(size * app.sx))
        super().__init__(master, width=px, height=px, bg=app.c("bg"),
                         highlightthickness=0, bd=0)
        self.app = app
        self.color_key = color_key
        self._px = px
        if not hasattr(app, "dots"):
            app.dots = []
        app.dots.append(self)
        self.redraw()

    def redraw(self, color_key: str | None = None):
        if color_key:
            self.color_key = color_key
        self.configure(bg=self.app.c("bg"))
        self.delete("all")
        pad = 1
        self.create_oval(pad, pad, self._px - pad, self._px - pad,
                         fill=self.app.c(self.color_key), outline="")


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

    def _round(self, x0, y0, x1, y1, r, fill, outline=""):
        """Rounded rectangle with a fixed corner radius (not a capsule)."""
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
               x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
               x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        self.create_polygon(pts, smooth=True, splinesteps=16, fill=fill, outline=outline)

    def redraw(self):
        c = self.app.c
        L, T, H = self._each, self._track, self._h
        self.configure(bg=c("bg"))
        self.delete("all")
        ty0, ty1 = H / 2 - 9, H / 2 + 9
        on = self._pos >= 0.5
        self._round(L, ty0, L + T, ty1, 8, c("accent") if on else c("track"))
        d = 14
        travel = T - d - 4
        kx = L + 2 + travel * self._pos
        self._round(kx, H / 2 - d / 2, kx + d, H / 2 + d / 2, 5,
                    c("card"), c("stroke"))
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


class HelpDot(tk.Canvas):
    """A small circled question mark that looks like a button and shows a tooltip."""

    SIZE = 18

    def __init__(self, master, app: "App", key: str):
        size = int(18 * getattr(app, "sx", 1.0))
        super().__init__(master, width=size, height=size, bg=app.c("card"),
                         highlightthickness=0, bd=0, cursor="hand2")
        self.app = app
        self.key = key
        if not hasattr(app, "help_dots"):
            app.help_dots = []
        app.help_dots.append(self)
        self.configure(bg=app.c("card"))
        self._draw()
        self.bind("<Enter>", lambda _e: app.tip_show(app.t(key), self))
        self.bind("<Leave>", lambda _e: app.tip_hide())
        self.bind("<Button-1>", lambda _e: app.tip_show(app.t(key), self))

    def _draw(self):
        self.delete("all")
        size = int(18 * getattr(self.app, "sx", 1.0))
        pad = 2
        self.create_oval(pad, pad, size - pad, size - pad,
                         outline=self.app.c("stroke_hi"), width=1,
                         fill=self.app.c("card"))
        self.create_text(size / 2, size / 2 + 1, text="?",
                         fill=self.app.c("dim"), font=_font(8, True))

    def redraw(self):
        self.configure(bg=self.app.c("card"))
        self._draw()



class FileList(tk.Frame):
    """ttk.Treeview dressed up as a file list: 28 px rows, zebra stripes, hover.

    Mirrors the handful of Listbox calls the pages already make, so swapping one in only
    requires changing the constructor line.
    """

    def repaint(self):
        """Re-apply the palette after a theme switch (styles are global, not per widget)."""
        c = self.app.c
        style = ttk.Style(self)
        style.configure("Files.Treeview", background=c("inset"), fieldbackground=c("inset"),
                        foreground=c("dim"), borderwidth=0, relief="flat",
                        rowheight=int(20 * self.app.sx), font=_font(9))
        style.map("Files.Treeview",
                  background=[("selected", c("hover"))], foreground=[("selected", c("fg"))])
        self.configure(bg=c("inset"))
        self.scroll.configure(bg=c("inset"), troughcolor=c("inset"))
        self.tree.tag_configure("odd", background=c("inset"))
        self.tree.tag_configure("even", background=c("card"))
        self.tree.tag_configure("hover", background=c("hover"))

    def __init__(self, master, app, **kw):
        pad = int(6 * app.sx)
        super().__init__(master, bg=app.c("inset"), highlightthickness=0, bd=0)
        style = ttk.Style(self)
        style.theme_use("clam")
        style.configure("Files.Treeview",
                        background=app.c("inset"), fieldbackground=app.c("inset"),
                        foreground=app.c("dim"), borderwidth=0, relief="flat",
                        rowheight=int(20 * app.sx), font=_font(9))
        style.map("Files.Treeview",
                  background=[("selected", app.c("hover"))],
                  foreground=[("selected", app.c("fg"))])
        style.layout("Files.Treeview", [("Files.Treeview.treearea", {"sticky": "nswe"})])
        self.app = app
        app.file_lists.append(self)
        self.tree = ttk.Treeview(self, style="Files.Treeview", show="",
                                 selectmode="browse", columns=("name",))
        self.tree.column("#1", anchor="w", stretch=True, width=int(200 * app.sx))
        self.tree.tag_configure("odd", background=app.c("inset"))
        self.tree.tag_configure("even", background=app.c("card"))
        self.tree.tag_configure("hover", background=app.c("hover"))
        self.scroll = tk.Scrollbar(self, command=self.tree.yview, bg=app.c("inset"),
                                   troughcolor=app.c("inset"), highlightthickness=0, bd=0)
        self.tree.configure(yscrollcommand=self.scroll.set)
        self.scroll.pack(side="right", fill="y")
        self.tree.pack(side="left", fill="both", expand=True, padx=pad, pady=pad)
        self._hover_row = None
        self._row_fg = {}
        self.tree.bind("<Motion>", self._on_motion)
        self.tree.bind("<Leave>", lambda _e: self._paint_hover(None))

    # --- Listbox-shaped API -------------------------------------------------
    def insert(self, index, text):
        where = "end" if index in ("end", tk.END) else index
        self.tree.insert("", where, values=(text,))
        self._retag()

    def _retag(self):
        """Zebra every row, then re-apply any per-row foreground override."""
        for i, item in enumerate(self.tree.get_children()):
            tags = ["odd" if i % 2 == 0 else "even"]
            colour = self._row_fg.get(i)
            if colour:
                name = "fg%d" % i
                self.tree.tag_configure(name, foreground=colour)
                tags.append(name)
            self.tree.item(item, tags=tuple(tags))

    def itemconfigure(self, index, **kw):
        kids = self.tree.get_children()
        if index in ("end", tk.END):
            index = len(kids) - 1
        if not isinstance(index, int) or not (0 <= index < len(kids)):
            return
        colour = kw.get("foreground")
        if colour:
            self._row_fg[index] = colour
        elif colour == "":
            self._row_fg.pop(index, None)
        self._retag()

    def set_row(self, index, text, fg=None):
        """Rewrite one row in place (keeps the selection and the zebra order)."""
        kids = self.tree.get_children()
        if not isinstance(index, int) or not (0 <= index < len(kids)):
            return
        self.tree.item(kids[index], values=(text,))
        if fg:
            self._row_fg[index] = fg
        self._retag()

    def nearest(self, y):
        item = self.tree.identify_row(y)
        return self.tree.index(item) if item else -1

    def delete(self, first, last=None):
        kids = self.tree.get_children()
        if first in (0, "0") and last in ("end", tk.END):
            self.tree.delete(*kids)
            self._row_fg.clear()
            return
        if isinstance(first, int):
            self._row_fg.clear()
            first = kids[first]
        self.tree.delete(first)
        self._retag()

    def get(self, index, last=None):
        kids = self.tree.get_children()
        if last is not None:
            return [str(self.tree.item(k, "values")[0]) for k in kids[index:last + 1]]
        return str(self.tree.item(kids[index], "values")[0])

    def size(self):
        return len(self.tree.get_children())

    def curselection(self):
        return tuple(self.tree.index(i) for i in self.tree.selection())

    def selection_clear(self, first=None, last=None):
        self.tree.selection_remove(*self.tree.selection())

    def selection_set(self, index):
        kids = self.tree.get_children()
        if 0 <= index < len(kids):
            self.tree.selection_set(kids[index])

    def see(self, index):
        kids = self.tree.get_children()
        if 0 <= index < len(kids):
            self.tree.see(kids[index])

    def bind(self, sequence=None, func=None, add=None):
        if sequence == "<<ListboxSelect>>":
            sequence = "<<TreeviewSelect>>"
        return self.tree.bind(sequence, func, add)

    def yview(self, *args):
        return self.tree.yview(*args)

    def configure(self, **kw):
        mode = kw.get("selectmode")
        if mode in ("browse", "extended", "none"):
            self.tree.configure(selectmode=mode)
        bg = kw.get("bg")
        fg = kw.get("fg")
        sel = kw.get("selectbackground")
        style = ttk.Style(self)
        if fg:
            style.configure("Files.Treeview", foreground=fg)
        if bg:
            self.tree.tag_configure("odd", background=bg)
            style.configure("Files.Treeview", fieldbackground=bg)
        if sel:
            style.map("Files.Treeview", background=[("selected", sel)])

    config = configure

    # --- hover --------------------------------------------------------------
    def _paint_hover(self, tree_item):
        if self._hover_row and self.tree.exists(self._hover_row):
            base = "odd" if self.tree.index(self._hover_row) % 2 == 0 else "even"
            tags = (base,)
            colour = self._row_fg.get(self.tree.index(self._hover_row))
            if colour:
                tags = tags + ("fg%d" % self.tree.index(self._hover_row),)
            self.tree.item(self._hover_row, tags=tags)
        self._hover_row = tree_item
        if tree_item and tree_item not in self.tree.selection():
            self.tree.item(tree_item, tags=("hover",))

    def _on_motion(self, event):
        item = self.tree.identify_row(event.y)
        if item != self._hover_row:
            self._paint_hover(item or None)


class Card(tk.Frame):
    """A rounded panel: a background canvas draws the card, children stack on top."""

    def __init__(self, master, app: "App", title_key: str = "", help_key: str = ""):
        super().__init__(master, bg=app.c("bg"), bd=0, highlightthickness=0)
        self.app = app
        self.active = False
        app.cards.append(self)
        self._bg = tk.Canvas(self, bg=app.c("bg"), highlightthickness=0, bd=0)
        self._bg.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_img = None
        head = tk.Frame(self, bg=app.c("card"))
        head.pack(fill="x", padx=16, pady=(11, 0))
        app.style_widget(head, "card")
        self.head = head
        self.title = tk.Label(head, text="", bg=app.c("card"), fg=app.c("faint"),
                              font=_font(9, True))
        self.title.pack(side="left")
        if help_key:
            self.help = HelpDot(head, app, help_key)
            self.help.pack(side="left", padx=(7, 1), pady=(1, 0))
        self.body = tk.Frame(self, bg=app.c("card"))
        self.body.pack(fill="both", expand=True, padx=16, pady=(10, 15))
        app.style_widget(self.body, "card")
        app.style_widget(self.title, "card", "faint")
        self.bind("<Configure>", self._on_resize)
        if title_key:
            app.bind_text(self.title, title_key)

    def _on_resize(self, event=None):
        self.paint()

    def paint(self):
        w = self.winfo_width()
        h = self.winfo_height()
        if w < 4 or h < 4:
            return
        self.configure(bg=self.app.c("bg"))
        self._bg.configure(bg=self.app.c("bg"))
        stroke = self.app.c("accent") if self.active else self.app.c("stroke")
        self._bg_img = _round_photo(self.app, w, h, int(8 * self.app.sx),
                                    self.app.c("card"), stroke)
        self._bg.delete("all")
        self._bg.create_image(0, 0, image=self._bg_img, anchor="nw")
        # Canvas.lower() is the *item* command (needs a tag), so lower the widget itself.
        self.tk.call("lower", self._bg._w)



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


class PillScale(tk.Canvas):
    """Horizontal slider drawn on a canvas: rounded track, rounded thumb, theme aware."""

    def __init__(self, master, app: "App", var, lo: float, hi: float, on_change):
        self.app, self.var, self.lo, self.hi = app, var, lo, hi
        self.on_change = on_change
        h = int(18 * app.sx)
        super().__init__(master, height=h, highlightthickness=0, bd=0,
                         bg=app.c("card"), cursor="hand2")
        self.bind("<Button-1>", self._jump)
        self.bind("<B1-Motion>", self._jump)
        self.bind("<Configure>", lambda _e: self.redraw())
        app.pill_scales.append(self)

    def _round(self, x0, y0, x1, y1, r, fill):
        r = min(r, (x1 - x0) / 2, (y1 - y0) / 2)
        pts = [x0 + r, y0, x1 - r, y0, x1, y0, x1, y0 + r,
               x1, y1 - r, x1, y1, x1 - r, y1, x0 + r, y1,
               x0, y1, x0, y1 - r, x0, y0 + r, x0, y0]
        self.create_polygon(pts, smooth=True, splinesteps=16, fill=fill, outline="")

    def redraw(self):
        c = self.app.c
        self.configure(bg=c("card"))
        self.delete("all")
        w = max(self.winfo_width(), 40)
        h = int(18 * self.app.sx)
        mid = h / 2
        track_h = int(6 * self.app.sx)
        y0, y1 = mid - track_h / 2, mid + track_h / 2
        self._round(0, y0, w, y1, track_h / 2, c("track"))
        span = max(self.hi - self.lo, 1e-9)
        frac = (float(self.var.get()) - self.lo) / span
        frac = max(0.0, min(1.0, frac))
        d = int(14 * self.app.sx)
        travel = max(w - d, 1)
        thumb = d / 2 + travel * frac
        self._round(0, y0, max(thumb, track_h), y1, track_h / 2, c("accent"))
        self._round(thumb - d / 2, mid - d / 2, thumb + d / 2, mid + d / 2, 5, c("card"))
        self._round(thumb - d / 2, mid - d / 2, thumb + d / 2, mid + d / 2, 5, "")
        self.create_polygon(thumb - d / 2, mid - d / 2, thumb + d / 2, mid - d / 2,
                            thumb + d / 2, mid + d / 2, thumb - d / 2, mid + d / 2,
                            fill="", outline=c("stroke"), width=1)

    def _jump(self, event):
        w = max(self.winfo_width(), 40)
        d = int(14 * self.app.sx)
        travel = max(w - d, 1)
        frac = max(0.0, min(1.0, (event.x - d / 2) / travel))
        self.var.set(self.lo + (self.hi - self.lo) * frac)
        self.redraw()
        if self.on_change:
            self.on_change()

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
        self.scale = PillScale(self, app, self.value, lo, hi, self._changed)
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
        if self.cfg.get("cfg_version") != 2:
            # first run of this build: shipped defaults are English + light
            self.cfg.update(lang="en", theme="light", cfg_version=2)
        self.page_objects = {}
        self.core_dir = self.cfg.get("cw", "")
        if self.core_dir and not os.path.isdir(self.core_dir):
            self.core_dir = ""
        self.current_page = "normals"
        self.lang = self.cfg.get("lang", "en")
        self.theme = self.cfg.get("theme", "light")
        if self.lang not in LANG:
            self.lang = "en"
        if self.theme not in THEMES:
            self.theme = "light"

        self.files: list[str] = []
        self.queue: "queue.Queue[tuple]" = queue.Queue()
        self.cancel = threading.Event()
        self.running = False
        self.worker = None
        self.style_widgets: list[tuple] = []
        self.file_lists: list = []
        self.cards: list = []
        self.text_bindings: list[tuple] = []
        self.lang_buttons: dict = {}
        self.theme_buttons: dict = {}
        self.switches: list = []
        self.pill_scales: list = []
        self._tip = None
        try:
            self.texconv = ddsmod.resolve_texconv(os.environ.get("TEXCONV", "texconv.exe"))
        except FileNotFoundError:
            self.texconv = ""

        self.title(APP_TITLE)
        # Pin the whole layout to 96 dpi: widgets are laid out in pixels, so letting Tk recompute
        # fonts from a 120/144 dpi monitor makes them grow inside a fixed-size window and clip.
        try:
            self.tk.call("tk", "scaling", 96.0 / 72.0)
        except Exception:
            pass
        self.sx = 1.0
        self.geometry("%dx%d" % (min(int(1360 * self.sx), self.winfo_screenwidth() - 40),
                                  min(int(820 * self.sx), self.winfo_screenheight() - 80)))
        self.minsize(int(1120 * self.sx), int(700 * self.sx))
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

    def _schedule_bg(self, _event=None):
        if getattr(self, "_bg_job", None):
            try:
                self.after_cancel(self._bg_job)
            except Exception:
                pass
        self._bg_job = self.after(120, self._paint_bg)

    def _paint_bg(self):
        """Faint 24 px grid behind everything, so cards read as panels."""
        self._bg_job = None
        canvas = getattr(self, "_bg_canvas", None)
        if canvas is None:
            return
        w, h = self.winfo_width(), self.winfo_height()
        if w < 40 or h < 40:
            return
        radius = 24 * self.sx
        line = "#e2e9f3" if self.theme == "light" else "#151a21"
        base = Image.new("RGB", (w, h), self.c("bg"))
        draw = ImageDraw.Draw(base)
        x = 0.0
        while x < w:
            draw.line([(x, 0), (x, h)], fill=line, width=1)
            x += radius
        y = 0.0
        while y < h:
            draw.line([(0, y), (w, y)], fill=line, width=1)
            y += radius
        canvas.delete("all")
        self._bg_photo = ImageTk.PhotoImage(base)
        canvas.create_image(0, 0, image=self._bg_photo, anchor="nw")
        self.tk.call("lower", canvas._w)

    def _apply_theme(self):
        note = getattr(self, "note", None)
        if note is not None:
            try:
                note.configure(bg=self.c("nav"), fg=self.c("faint"))
                self._build_note()
            except tk.TclError:
                pass
        for fl in getattr(self, "file_lists", []):
            try:
                fl.repaint()
            except tk.TclError:
                pass
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
        self._paint_bg()
        self._paint_nav(self.current_page)
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
        for dot in getattr(self, "help_dots", []):
            try:
                dot.redraw()
            except Exception:
                pass
        for canvas in getattr(self, "preview_canvases", []):
            try:
                canvas.configure(bg=self.c("inset"), highlightbackground=self.c("stroke"))
            except tk.TclError:
                pass
        for card in getattr(self, "cards", []):
            try:
                card.configure(bg=self.c("bg"))
                card._bg.configure(bg=self.c("bg"))
                card.body.configure(bg=self.c("card"))
                card.head.configure(bg=self.c("card"))
                card.title.configure(bg=self.c("card"), fg=self.c("faint"))
                card.paint()
            except tk.TclError:
                pass
        for btn in getattr(self, "pill_buttons", []):
            try:
                btn._draw()
            except tk.TclError:
                pass
        for dot in getattr(self, "dots", []):
            try:
                dot.redraw()
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
        for sc in self.pill_scales:
            try:
                sc.redraw()
            except tk.TclError:
                pass
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

    def _build_note(self):
        """The warning + issue link under the nav, rebuilt on every language switch."""
        if not getattr(self, "note", None):
            return
        t = self.t
        self.note.configure(state="normal")
        self.note.delete("1.0", "end")
        self.note.insert("end", t("note.before"))
        self.note.insert("end", t("note.backup"), "b")
        self.note.insert("end", t("note.mid"))
        self.note.insert("end", t("note.test"), "b")
        self.note.insert("end", t("note.after") + "\n\n")
        self.note.insert("end", t("note.bug") + "\n")
        self.note.insert("end", ISSUE_URL, "link")
        self.note.configure(state="disabled")
        self.note.tag_configure("b", font=_font(8, True), foreground=self.c("dim"))
        self.note.tag_configure("link", underline=True, foreground=self.c("accent"))

    def _note_click(self, event):
        idx = self.note.index(f"@{event.x},{event.y}")
        if "link" in self.note.tag_names(idx):
            import webbrowser
            webbrowser.open(ISSUE_URL)
            return "break"

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
            self.set_status(self.t("idle"), "faint")
        if hasattr(self, "_fit_nav"):
            self._fit_nav()

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
        self._build_note()
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


    def _fit_sub(self, event=None):
        """Wrap the subtitle to whatever width the title column actually got."""
        try:
            width = event.width if event is not None else self._titles.winfo_width()
        except Exception:
            return
        if width > 120:
            self.sub.configure(wraplength=max(200, width - 6))

    def _fit_nav(self):
        """The nav column is fixed; labels wrap inside it instead of widening it."""
        self._nav.configure(width=int(212 * self.sx))

    def _nav_enter(self, page):
        self._nav_hover = page
        self._paint_nav(self.current_page)

    def _nav_leave(self, page):
        if self._nav_hover == page:
            self._nav_hover = None
        self._paint_nav(self.current_page)

    def _paint_nav(self, name):
        """Draw every nav row as a rounded pill; the active one is filled."""
        for page, row in getattr(self, "nav_rows", {}).items():
            active = page == name
            hover = (not active) and (getattr(self, "_nav_hover", None) == page)
            row.configure(bg=self.c("nav"))
            row.delete("all")
            w = max(row.winfo_width(), int(180 * self.sx))
            h = int(36 * self.sx)
            if active or hover:
                fill = self.c("card") if active else self.c("hover")
                stroke = self.c("accent") if active else self.c("nav")
                photo = _round_photo(self, w, h, int(8 * self.sx), fill, stroke)
                row.create_image(0, 0, image=photo, anchor="nw")
                row._photo = photo
            if active:
                row.create_rectangle(0, int(9 * self.sx), int(3 * self.sx), h - int(9 * self.sx),
                                     fill=self.c("accent"), width=0)
            fg = self.c("fg") if active else (self.c("dim") if hover else self.c("faint"))
            row.create_text(int(16 * self.sx), h // 2, text=row._icon, anchor="w",
                            fill=self.c("accent") if active else fg, font=_font(9))
            row.create_text(int(34 * self.sx), h // 2, text=self.t(row._key), anchor="w",
                            fill=fg, font=_font(10, active), width=int(148 * self.sx),
                            justify="left")

    def _save(self):
        self.cfg.update(dict(lang=self.lang, theme=self.theme, cw=self.core_dir,
                             strength=float(self.sl_strength.value.get()),
                             blur=float(self.sl_blur.value.get()),
                             alpha=float(self.sl_alpha.value.get()),
                             fmt=self.fmt.get(), resize=self.resize.get().lower(),
                             maxmips=self.max_mips.get().lower()))
        save_config(self.cfg)

    # ---------------------------------------------------------------- widgets
    def _button(self, master, text, command, primary=False, kind: str | None = None, icon: str = ""):
        btn = PillButton(master, self, text, command,
                         kind=kind or ("primary" if primary else "secondary"), icon=icon)
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
        self._nav = tk.Frame(self, bg=self.c("nav"), width=int(232 * self.sx))
        self._nav.pack_propagate(False)
        self._nav.pack(side="left", fill="y")
        self._nav.pack_propagate(False)
        brand = tk.Label(self._nav, text="GTA5 tools", bg=self.c("nav"), fg=self.c("fg"), font=_font(15, True))
        brand.pack(anchor="w", padx=18, pady=(20, 2))
        self.style_widget(brand, "nav", "fg")
        tag = self.bind_text(tk.Label(self._nav, text="", bg=self.c("nav"), fg=self.c("faint"),
                                      font=_font(9)), "tagline")
        tag.pack(anchor="w", padx=18, pady=(0, 18))
        self.style_widget(tag, "nav", "faint")

        self.nav_rows = {}
        self._nav_hover = None
        icons = {"normals": "◆", "ytd": "▤", "mips": "▥", "ped": "⚙"}
        for page, key in (("normals", "nav.normal"), ("ytd", "nav.ytd"), ("mips", "nav.mip"), ("ped", "nav.ped")):
            row = tk.Canvas(self._nav, bg=self.c("nav"), highlightthickness=0, bd=0,
                            height=int(36 * self.sx), width=int(192 * self.sx))
            row.pack(fill="x", padx=10, pady=1)
            row._page, row._key, row._icon = page, key, icons[page]
            row.bind("<Button-1>", lambda _e, p=page: self.show_page(p))
            row.bind("<Enter>", lambda _e, p=page: self._nav_enter(p))
            row.bind("<Leave>", lambda _e, p=page: self._nav_leave(p))
            self.nav_rows[page] = row
        self._paint_nav("normals")

        ver = tk.Label(self._nav, text=f"v{VERSION}", bg=self.c("nav"), fg=self.c("faint"), font=_font(9))
        ver.pack(side="bottom", anchor="w", padx=18, pady=14)
        self.style_widget(ver, "nav", "faint")

        self.note = tk.Text(self._nav, wrap="word", width=int(26 * self.sx), height=7,
                            bg=self.c("nav"), fg=self.c("faint"), font=_font(8),
                            relief="flat", bd=0, highlightthickness=0, padx=0, pady=0,
                            spacing1=0, spacing3=1, cursor="arrow", takefocus=0)
        self.note.pack(side="bottom", anchor="w", padx=18, pady=(0, 8))
        self.note.tag_configure("b", font=_font(8, True), foreground=self.c("dim"))
        self.note.tag_configure("link", underline=True, foreground=self.c("accent"))
        self.note.bind("<Button-1>", self._note_click)
        self._build_note()

        self._bg_canvas = tk.Canvas(self, bg=self.c("bg"), highlightthickness=0, bd=0)
        self._bg_canvas.place(x=0, y=0, relwidth=1, relheight=1)
        self._bg_photo = None
        self._bg_job = None
        self.bind("<Configure>", self._schedule_bg, add="+")

        self._main = tk.Frame(self, bg=self.c("bg"))
        self._main.pack(side="left", fill="both", expand=True, padx=(18, 18), pady=(16, 16))
        self.style_widget(self._main, "bg")

        head = tk.Frame(self._main, bg=self.c("bg"))
        head.pack(fill="x")
        self.style_widget(head, "bg")
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

        titles = tk.Frame(head, bg=self.c("bg"))
        self._titles = titles
        titles.pack(side="left", fill="x", expand=True)
        self.style_widget(titles, "bg")
        h1 = tk.Label(titles, text="", bg=self.c("bg"), fg=self.c("fg"), font=_font(17, True))
        self.h1 = h1
        h1.pack(anchor="w")
        self.style_widget(h1, "bg", "fg")
        sub = tk.Label(titles, text="", bg=self.c("bg"), fg=self.c("faint"), font=_font(10),
                       justify="left", anchor="w", wraplength=int(840 * self.sx))
        self.sub = sub
        sub.configure(height=2, anchor="nw", justify="left")
        sub.pack(anchor="w", pady=(2, 0), fill="x")
        self.style_widget(sub, "bg", "faint")
        titles.bind("<Configure>", self._fit_sub)

        self.page_host = tk.Frame(self._main, bg=self.c("bg"))
        self.page_host.pack(fill="both", expand=True, pady=(14, 0))
        self.style_widget(self.page_host, "bg")

        self.page_normals = tk.Frame(self.page_host, bg=self.c("bg"))
        self.style_widget(self.page_normals, "bg")
        self.pages = {"normals": self.page_normals}
        self.page_normals.pack(fill="both", expand=True)
        self.after(0, self._fit_nav)
        main = self.page_normals
        body = tk.Frame(main, bg=self.c("bg"))
        body.pack(fill="both", expand=True)
        self.style_widget(body, "bg")

        # ---- left column: files (same slim column as the other pages)
        files = Card(body, self, "files")
        files.configure(width=int(290 * self.sx))
        files.pack(side="left", fill="y")
        files.pack_propagate(False)

        tools = tk.Frame(files.head, bg=self.c("card"))
        tools.pack(side="right")
        self.style_widget(tools, "card")
        self.bind_text(self._button(tools, "", self.clear_files), "clear").pack(side="right")
        self.bind_text(self._button(tools, "", self.remove_selected), "remove").pack(side="right", padx=(0, 6))

        btnrow = tk.Frame(files.body, bg=self.c("card"))
        btnrow.pack(fill="x")
        self.style_widget(btnrow, "card")
        self.bind_text(self._button(btnrow, "", self.pick_files, primary=True), "add_files").pack(side="left")
        self.bind_text(self._button(btnrow, "", self.pick_folder), "add_folder").pack(side="left", padx=8)

        wrap = tk.Frame(files.body, bg=self.c("inset"), highlightbackground=self.c("stroke"),
                        highlightthickness=1)
        wrap.pack(fill="both", expand=True, pady=(10, 0))
        self.style_widget(wrap, "inset")
        self.listbox = FileList(wrap, self)
        self.listbox.pack(fill="both", expand=True)
        self.listbox.bind("<<ListboxSelect>>", lambda _e: self._draw_preview())
        self.count_label = tk.Label(files.body, text="", bg=self.c("card"), fg=self.c("faint"),
                                    font=_font(9))
        self.count_label.pack(anchor="w", pady=(8, 0))
        self.style_widget(self.count_label, "card", "faint")

        # ---- middle column: three tall preview panes
        prev = Card(body, self, "preview")
        prev.pack(side="left", fill="both", expand=True, padx=12)
        self.preview_canvases = []
        pane = prev.body
        pane.columnconfigure(0, weight=1)
        for row, key in enumerate(("prev.src", "prev.nrm", "prev.lit")):
            cap = self.bind_text(tk.Label(pane, text="", bg=self.c("card"), fg=self.c("faint"),
                                          font=_font(8, True), anchor="w"), key)
            cap.grid(row=row * 2, column=0, sticky="ew", pady=(0, 2))
            self.style_widget(cap, "card", "faint")
            canvas = tk.Canvas(pane, bg=self.c("inset"), highlightthickness=1,
                               highlightbackground=self.c("stroke"), width=10, height=20)
            canvas.grid(row=row * 2 + 1, column=0, sticky="nsew", pady=(0, 8))
            pane.rowconfigure(row * 2 + 1, weight=1, uniform="prev")
            canvas.bind("<Configure>", lambda _e: self._schedule_preview())
            self.preview_canvases.append(canvas)
        self._preview_job = None
        self._preview_photo = None

        # ---- right column: parameters on top, log below
        right = tk.Frame(body, bg=self.c("bg"))
        right.configure(width=int(320 * self.sx))
        right.pack(side="right", fill="y")
        right.pack_propagate(False)
        self.style_widget(right, "bg")

        params = Card(right, self, "params", help_key="help.params")
        self.params_card = params
        params.pack(fill="x")
        pbody = params.body

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
        self.resize = tk.StringVar(value=str(cfg.get("resize", "KEEP")).upper())
        self._combo(pbody, "resize", self.resize, RESIZE_CHOICES)
        self.max_mips = tk.StringVar(value=str(cfg.get("maxmips", "FULL")).upper())
        self._combo(pbody, "maxmips", self.max_mips, MIP_CHOICES)

        hint = self.bind_text(tk.Label(pbody, text="", bg=self.c("card"), fg=self.c("faint"),
                                       font=_font(9), anchor="w", justify="left",
                                       wraplength=272), "out_hint")
        hint.pack(fill="x", pady=(2, 0))
        self.style_widget(hint, "card", "faint")

        logs = Card(right, self, "log")
        logs.pack(fill="both", expand=True, pady=(12, 0))
        self.log = tk.Text(logs.body, bg=self.c("inset"), fg=self.c("dim"), insertbackground=self.c("fg"),
                           bd=0, highlightthickness=0, font=_mono(9), wrap="word", width=1, height=8)
        self.log.pack(fill="both", expand=True)
        self.log.configure(state="disabled")

        # ---- action footer (full width, under the three columns)
        footer = tk.Frame(main, bg=self.c("bg"))
        self.footer = footer
        footer.pack(fill="x", pady=(12, 0))
        self.style_widget(footer, "bg")
        self.run_btn = self.bind_text(self._button(footer, "", self.run, primary=True), "generate")
        self.run_btn.pack(side="left")
        self.cancel_btn = self.bind_text(self._button(footer, "", self.cancel_run), "cancel")
        self.cancel_btn.pack(side="left", padx=8)
        self.cancel_btn.configure(state="disabled")
        # the footnote block above already carries this text; keep the label but leave it empty
        self.hint = tk.Label(footer, text="", bg=self.c("bg"), fg=self.c("faint"),
                             font=_font(8), anchor="w")
        self.hint.pack(side="left", padx=(14, 0))
        self.style_widget(self.hint, "bg", "faint")
        self.progress = ttk.Progressbar(footer, style="Pav.Horizontal.TProgressbar",
                                        orient="horizontal", mode="determinate")
        self.progress.pack(side="left", fill="x", expand=True, padx=14)
        self.status_dot = Dot(footer, self, "faint", 8)
        self.status_dot.pack(side="right", padx=(0, 6))
        self.status = tk.Label(footer, text="", bg=self.c("bg"), fg=self.c("faint"),
                               font=_font(9), anchor="e")
        self.status.pack(side="right")
        self.style_widget(self.status, "bg", "faint")

    def set_status(self, text: str, kind: str = "faint"):
        """kind: faint (idle) / dim (working) / green (ok) / danger (failed) / warning."""
        try:
            self.status.configure(text=text, fg=self.c(kind))
            if hasattr(self, "status_dot"):
                self.status_dot.redraw(kind)
        except tk.TclError:
            pass

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
        self._update_titles()
        self.after_idle(self._grow_to_fit)

    def _grow_to_fit(self):
        """Some page layouts ask for more width than the default window; grow once, never shrink."""
        try:
            self.update_idletasks()
            need = self.winfo_reqwidth()
            have = self.winfo_width()
            limit = self.winfo_screenwidth() - 20
            if need > have and need <= limit:
                self.geometry("%dx%d" % (need, self.winfo_height()))
        except Exception:
            pass

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
            img.thumbnail((cw - int(32 * self.sx), ch - int(32 * self.sx)), Image.LANCZOS)
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
            self.set_status(str(value), "danger")
        except Exception:  # noqa: BLE001 - logging must not recurse
            pass

    def run(self):
        if self.running:
            return
        if not self.files:
            self.set_status(self.t("nothing"), "faint")
            return
        if not self.texconv or not os.path.isfile(self.texconv):
            self.set_status(self.t("missing_texconv"), "danger")
            self.log_line("err texconv.exe not found: put it next to this program")
            return
        self._save()
        self.running = True
        self.cancel.clear()
        self.run_btn.configure(state="disabled")
        self.cancel_btn.configure(state="normal")
        self.progress.configure(value=0, maximum=len(self.files))
        self.set_status(self.t("processing", n=0), "dim")
        first = self.files[0]
        out_dir = os.path.dirname(os.path.abspath(first))
        self.log_line(f"start: {len(self.files)} file(s) -> {out_dir}")
        params = dict(fmt=self.fmt.get(),
                      strength=float(self.sl_strength.value.get()),
                      blur=float(self.sl_blur.value.get()),
                      alpha_w=float(self.sl_alpha.value.get()),
                      resize=self.resize.get().lower(),
                      max_mips=self.max_mips.get().lower())
        self.worker = threading.Thread(target=self._work, args=(params,), daemon=True)
        self.worker.start()

    def cancel_run(self):
        self.cancel.set()
        self.set_status(self.t("cancelling"), "warning")

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
                    self.set_status(self.t("processing", n=idx), "dim")
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
                    kind = "warning" if self.cancel.is_set() else ("green" if not failed else "danger")
                    self.set_status(self.t(key, made=made, failed=failed), kind)
                    self.running = False
                    self.run_btn.configure(state="normal")
                    self.cancel_btn.configure(state="disabled")
        except queue.Empty:
            pass
        self.after(80, self._pump)


def _fix_dpi():
    """Keep the layout identical to the source runs.

    PyInstaller ships a DPI-aware manifest, so on a 125% display Tk lays the UI out in
    physical pixels and the fixed-width panels get clipped. Declaring the process
    DPI-unaware makes Windows scale the whole window instead, which matches what the
    source build looks like. Proper per-monitor scaling is a later task.
    """
    if sys.platform != "win32":
        return
    try:
        import ctypes

        ctypes.windll.user32.SetProcessDpiAwarenessContext(1)  # system DPI aware: no bitmap stretching
    except Exception:
        pass


def main():
    _fix_dpi()
    App().mainloop()


if __name__ == "__main__":
    main()
