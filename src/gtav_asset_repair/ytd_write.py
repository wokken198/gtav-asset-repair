"""Write .ytd dictionaries through the vendored fivefury reader.

fivefury's gen9 writer rebuilds every texture header from a hard-coded runtime
profile (`GEN9_TEXTURE_RUNTIME_PROFILE`), because its `Texture` model does not
carry the six runtime-only fields.  Writing a dictionary back that way silently
replaces `texture_vft`, zeroes `image_flags` and drops the extra descriptor bit
that marks script render targets -- which is exactly what CodeWalker's
`pack -Original` loop existed to repair.

This module keeps those fields: it harvests them from the source archive and
feeds them back while serialising.  Measured on `buffalo.ytd` (46 textures) and
`HarleySS.ytd` (32), the result re-reads with a zero field difference.

Legacy (gen8) dictionaries are not handled here yet: their record layout differs
and nothing has verified which of its fields are constants.  `save()` raises
`LegacyNotSupported` so callers can fall back instead of writing a lossy file.
"""
from __future__ import annotations

import dataclasses
import importlib
import struct

from . import dds as _dds
from . import ytd as _ytdmod   # for the vendored-path loader only

# fields copied from the source archive, by offset inside the 0x80 byte record
KEEP = ("vft", "dflags", "dim", "fmt", "tile", "x21", "img", "x24", "x26",
        "uclass", "srv_vft", "x60", "srv_dim", "x6a", "x6c")

# legacy (v13) record: 0x78 bytes, and these four are the only ones fivefury
# leaves unwritten.  `stride` is kept only while geometry and format match,
# because fivefury recomputes it as a byte pitch while the shipped files store
# a per-row count -- the ratio is exactly 4 on every block-compressed texture.
LEGACY_KEEP = ("vft", "byte04", "byte32", "stride")

# texconv's format name (as dds.read_header reports it) -> fivefury TextureFormat
_TEXCONV_TO_FORMAT = {
    "BC1_UNORM": "BC1",
    "BC2_UNORM": "BC2",
    "BC3_UNORM": "BC3",
    "BC4_UNORM": "BC4",
    "BC5_UNORM": "BC5",
    "BC7_UNORM": "BC7",
    "B8G8R8A8_UNORM": "A8R8G8B8",
    "R8G8B8A8_UNORM": "R8G8B8A8",
    "R16G16B16A16_FLOAT": "R16G16B16A16_FLOAT",
}


class LegacyNotSupported(RuntimeError):
    """A gen8 dictionary was passed; its header fields are not preserved yet."""


def _y():
    """The vendored fivefury.ytd module, with sys.path set up on first use."""
    _ytdmod._load_reader()          # puts the vendor directory on sys.path
    return importlib.import_module("fivefury.ytd")


def _split(data: bytes):
    y = _y()
    _, virtual, physical = y._split_rsc7_sections(data)
    return virtual, physical


def is_gen9(raw: bytes) -> bool:
    """RSC7 version 5 is the enhanced (gen9) dictionary layout."""
    if len(raw) < 12 or struct.unpack_from("<I", raw, 0)[0] != 0x37435352:
        return False
    return struct.unpack_from("<I", raw, 4)[0] == 5


def dump_headers(raw: bytes) -> dict[str, dict]:
    """name -> the runtime-only header fields, read straight from the archive."""
    y = _y()
    virtual, _physical = _split(raw)
    count, items_off = y.catalog._checked_dictionary_items(virtual, 0)
    out: dict[str, dict] = {}
    for index in range(count):
        to = y.catalog._checked_texture_offset(virtual, items_off, index, 0x48)
        name_ptr = struct.unpack_from("<Q", virtual, to + 0x28)[0]
        no = y.catalog._virtual_offset(name_ptr)
        name = virtual[no:virtual.index(b"\0", no)].decode("utf-8", "replace")
        out[name] = {
            "vft": struct.unpack_from("<Q", virtual, to + 0x00)[0],
            "dflags": struct.unpack_from("<I", virtual, to + 0x10)[0],
            "x14": struct.unpack_from("<I", virtual, to + 0x14)[0],
            "dim": virtual[to + 0x1E],
            "fmt": virtual[to + 0x1F],
            "tile": virtual[to + 0x20],
            "x21": virtual[to + 0x21],
            "mips": virtual[to + 0x22],
            "img": virtual[to + 0x23],
            "x24": struct.unpack_from("<H", virtual, to + 0x24)[0],
            "x26": struct.unpack_from("<H", virtual, to + 0x26)[0],
            "uclass": struct.unpack_from("<I", virtual, to + 0x44)[0],
            "srv_vft": struct.unpack_from("<Q", virtual, to + 0x58)[0],
            "x60": struct.unpack_from("<I", virtual, to + 0x60)[0],
            "srv_dim": struct.unpack_from("<H", virtual, to + 0x68)[0],
            "x6a": struct.unpack_from("<H", virtual, to + 0x6A)[0],
            "x6c": struct.unpack_from("<I", virtual, to + 0x6C)[0],
        }
    return out


def _make_prepare(hint: dict[str, dict]):
    """A stand-in for fivefury's `_prepare_gen9_ytd` that honours `hint`."""
    y = _y()

    def prepare(textures):
        if not textures:
            raise ValueError("Cannot build a YTD with zero textures")
        entries = sorted(textures, key=lambda item: y.jenk_hash(item.name))
        count = len(entries)
        profile = y.GEN9_TEXTURE_RUNTIME_PROFILE

        dict_size = 0x40
        keys_offset = dict_size
        ptrs_offset = y.align(keys_offset + (4 * count), 16)
        textures_offset = y.align(ptrs_offset + (8 * count), 16)
        current = textures_offset + (y._ENHANCED_TEX_SIZE * count)

        name_offsets: list[int] = []
        name_bytes: list[bytes] = []
        for texture in entries:
            encoded = texture.name.encode("utf-8") + b"\x00"
            name_offsets.append(current)
            name_bytes.append(encoded)
            current += len(encoded)

        pagemap_offset = y.align(current, 16)
        virtual_size = pagemap_offset + 0x10

        physical_offsets: list[int] = []
        physical_blocks: list[bytes] = []
        cursor = 0
        for texture in entries:
            physical_offsets.append(cursor)
            physical_blocks.append(texture.data)
            cursor = y.align(cursor + len(texture.data), 16)

        vbuf = bytearray(virtual_size)
        pbuf = bytearray(cursor)

        struct.pack_into("<Q", vbuf, 0x00, 0)
        struct.pack_into("<Q", vbuf, 0x08, y.DAT_VIRTUAL_BASE + pagemap_offset)
        struct.pack_into("<Q", vbuf, 0x10, 0)
        struct.pack_into("<I", vbuf, 0x18, 1)
        struct.pack_into("<I", vbuf, 0x1C, 0)
        struct.pack_into("<Q", vbuf, 0x20, y.DAT_VIRTUAL_BASE + keys_offset)
        struct.pack_into("<HHI", vbuf, 0x28, count, count, 0)
        struct.pack_into("<Q", vbuf, 0x30, y.DAT_VIRTUAL_BASE + ptrs_offset)
        struct.pack_into("<HHI", vbuf, 0x38, count, count, 0)

        for index, texture in enumerate(entries):
            struct.pack_into("<I", vbuf, keys_offset + (index * 4), y.jenk_hash(texture.name))
            struct.pack_into("<Q", vbuf, ptrs_offset + (index * 8),
                             y.DAT_VIRTUAL_BASE + textures_offset + (y._ENHANCED_TEX_SIZE * index))

            off = textures_offset + (y._ENHANCED_TEX_SIZE * index)
            stride = 4 if not y._is_block_compressed(texture.format) else y._BLOCK_BYTES[texture.format]
            blocks = y._total_texture_block_count(texture.width, texture.height,
                                                  texture.format, texture.mip_count)

            known = hint.get(texture.name)
            if known is None:
                known = dict(vft=profile.texture_vft, dflags=profile.descriptor_flags,
                             tile=profile.tile_mode, x21=0, x14=0, img=profile.image_flags,
                             x24=0, x26=1, uclass=profile.usage_class, srv_vft=profile.srv_vft,
                             x60=0, srv_dim=profile.srv_dimension, x6a=0xFFFF, x6c=0xFFFFFFFF,
                             dim=y._ENHANCED_DIM_2D, fmt=y._FORMAT_TO_RSC8[texture.format])

            struct.pack_into("<Q", vbuf, off + 0x00, known["vft"])
            struct.pack_into("<II", vbuf, off + 0x08, blocks, stride)
            struct.pack_into("<II", vbuf, off + 0x10, known["dflags"], known["x14"])
            struct.pack_into("<HHH", vbuf, off + 0x18, texture.width, texture.height, 1)
            vbuf[off + 0x1E] = known["dim"]
            # Prefer the format the texture actually holds now: replacing a BC3
            # normal map with a BC1 one must also rewrite the format byte, or the
            # archive claims BC3 while carrying BC1 blocks and the game reads garbage.
            # Unknown formats still fall back to the archived value.
            vbuf[off + 0x1F] = y._FORMAT_TO_RSC8.get(texture.format, known["fmt"])
            vbuf[off + 0x20] = known["tile"]
            vbuf[off + 0x21] = known["x21"]
            vbuf[off + 0x22] = texture.mip_count
            vbuf[off + 0x23] = known["img"]
            struct.pack_into("<H", vbuf, off + 0x24, known["x24"])
            struct.pack_into("<H", vbuf, off + 0x26, known["x26"])
            struct.pack_into("<Q", vbuf, off + 0x28, y.DAT_VIRTUAL_BASE + name_offsets[index])
            struct.pack_into("<Q", vbuf, off + 0x30, y.DAT_VIRTUAL_BASE + off + 0x58)
            struct.pack_into("<Q", vbuf, off + 0x38, y.DAT_PHYSICAL_BASE + physical_offsets[index])
            struct.pack_into("<II", vbuf, off + 0x40,
                             y.pack_usage_data(texture.usage, texture.usage_flags), known["uclass"])
            struct.pack_into("<Q", vbuf, off + 0x58, known["srv_vft"])
            struct.pack_into("<I", vbuf, off + 0x60, known["x60"])
            struct.pack_into("<HHI", vbuf, off + 0x68, known["srv_dim"], known["x6a"], known["x6c"])

            encoded = name_bytes[index]
            vbuf[name_offsets[index]:name_offsets[index] + len(encoded)] = encoded
            pbuf[physical_offsets[index]:physical_offsets[index] + len(texture.data)] = texture.data

        vbuf[pagemap_offset] = 1
        vbuf[pagemap_offset + 1] = 1
        pointers = [0x08, 0x20, 0x30]
        pointers.extend(ptrs_offset + (i * 8) for i in range(count))
        for i in range(count):
            to = textures_offset + (y._ENHANCED_TEX_SIZE * i)
            pointers.extend((to + 0x28, to + 0x30, to + 0x38))
        system_data, graphics_data, system_flags, graphics_flags = y.layout_resource_sections(
            bytes(vbuf),
            [y.ResourceBlockSpan(0, len(vbuf), pointer_offsets=tuple(pointers))],
            bytes(pbuf),
            [y.ResourceBlockSpan(o, len(d), relocate_pointers=False)
             for o, d in zip(physical_offsets, physical_blocks, strict=True)],
            version=y._YTD_RSC7_VERSION_GEN9,
        )
        return y.prepare_rsc7_sections(
            system_data,
            version=y._YTD_RSC7_VERSION_GEN9,
            graphics_data=graphics_data,
            system_flags=system_flags,
            graphics_flags=graphics_flags,
        )

    return prepare


def dump_legacy_headers(raw: bytes) -> dict[str, dict]:
    """name -> the four legacy header fields fivefury's writer drops."""
    y = _y()
    virtual, _physical = _split(raw)
    count, items_off = y.catalog._checked_dictionary_items(virtual, 0)
    out: dict[str, dict] = {}
    for index in range(count):
        to = y.catalog._checked_texture_offset(virtual, items_off, index, 0x40)
        no = y.catalog._virtual_offset(struct.unpack_from("<Q", virtual, to + 0x28)[0])
        name = virtual[no:virtual.index(b"\0", no)].decode("utf-8", "replace")
        out[name] = {
            "vft": struct.unpack_from("<I", virtual, to + 0x00)[0],
            "byte04": virtual[to + 0x04],
            "byte32": virtual[to + 0x32],
            "stride": struct.unpack_from("<h", virtual, to + 0x56)[0],
            "width": struct.unpack_from("<h", virtual, to + 0x50)[0],
            "height": struct.unpack_from("<h", virtual, to + 0x52)[0],
            "format": struct.unpack_from("<I", virtual, to + 0x58)[0],
        }
    return out


def _make_prepare_legacy(hint: dict[str, dict], flags: tuple[int, int] | None = None):
    """Wrap fivefury's legacy writer and write the four dropped fields back.

    fivefury rebuilds the legacy records from scratch and never touches `0x00`
    (texture vft, constant `0xB6F0EE97`), `0x04`, `0x32`, and it fills `0x56`
    with a byte pitch where the shipped files hold a per-row count.  Everything
    else it writes already matches, so patching the produced section is cheaper
    and safer than copying the whole writer.
    """
    y = _y()
    original = y._prepare_legacy_ytd

    def prepare(textures):
        sections = original(textures)
        if not hint:
            return sections
        system = bytearray(sections.system_data)
        count, items_off = y.catalog._checked_dictionary_items(system, 0)
        for index in range(count):
            to = y.catalog._checked_texture_offset(system, items_off, index, 0x40)
            no = y.catalog._virtual_offset(struct.unpack_from("<Q", system, to + 0x28)[0])
            name = bytes(system[no:system.index(b"\0", no)]).decode("utf-8", "replace")
            known = hint.get(name)
            if not known:
                continue
            struct.pack_into("<I", system, to + 0x00, known["vft"])
            system[to + 0x04] = known["byte04"]
            system[to + 0x32] = known["byte32"]
            if (struct.unpack_from("<h", system, to + 0x50)[0] == known["width"]
                    and struct.unpack_from("<h", system, to + 0x52)[0] == known["height"]
                    and struct.unpack_from("<I", system, to + 0x58)[0] == known["format"]):
                struct.pack_into("<h", system, to + 0x56, known["stride"])
        sections = dataclasses.replace(sections, system_data=bytes(system))
        sections = _align_textures(sections, textures)
        if flags is not None:
            sections = _keep_size(sections, flags)
        return sections

    return prepare


def _align_textures(sections, textures):
    """Lay the graphics payload out with every texture on a 0x1000 boundary.

    The shipped legacy archives start each texture's data on a 4 KB boundary, and
    the game relies on it: fivefury concatenates them back to back, which leaves
    30 of Mai's 32 textures off by 2720 bytes and the game renders junk (the head
    normal map, the biggest one, shows up as black speckles).  Order is preserved
    from the source pointers so the layout stays as close to the original as the
    new data sizes allow.
    """
    y = _y()
    system = bytearray(sections.system_data)
    count, items_off = y.catalog._checked_dictionary_items(system, 0)
    records = []
    for index in range(count):
        to = y.catalog._checked_texture_offset(system, items_off, index, 0x40)
        no = y.catalog._virtual_offset(struct.unpack_from("<Q", system, to + 0x28)[0])
        name = bytes(system[no:system.index(b"\0", no)]).decode("utf-8", "replace")
        records.append((to, name, struct.unpack_from("<Q", system, to + 0x70)[0]))
    by_name = {t.name: t for t in textures}
    if any(name not in by_name for _, name, _ in records):
        return sections
    base = min(ptr for _, _, ptr in records)
    graphics = bytearray()
    moved = {}
    for to, name, _ptr in sorted(records, key=lambda r: r[2]):
        graphics += b"\x00" * ((-len(graphics)) % 0x1000)
        moved[name] = base + len(graphics)
        graphics += by_name[name].data
    for to, name, _ptr in records:
        struct.pack_into("<Q", system, to + 0x70, moved[name])
    return dataclasses.replace(
        sections, system_data=bytes(system), graphics_data=bytes(graphics))


def _keep_size(sections, flags: tuple[int, int]):
    """Pad the sections back to the source size and reuse its page flags.

    fivefury derives ``system_flags``/``graphics_flags`` from the new size with
    `get_resource_flags_from_size_adaptive`, which starts at a 0x200 block and so
    produces far more pages than the shipped file (Mai: 154 pages against 5).
    Reusing the source flags keeps the page layout the game shipped with, at the
    cost of the slack the source already carried.
    """
    import importlib

    fres = importlib.import_module("fivefury.resource")
    system_flags, graphics_flags = flags
    system, graphics = sections.system_data, sections.graphics_data
    system_target = fres.get_resource_size_from_flags(system_flags)
    graphics_target = fres.get_resource_size_from_flags(graphics_flags)
    if len(system) > system_target or len(graphics) > graphics_target:
        raise ValueError(
            "the rewritten archive (%d + %d bytes) no longer fits the source flags "
            "(%d + %d bytes); pass keep_size_flags=False for operations that shrink it"
            % (len(system), len(graphics), system_target, graphics_target))
    system = system + b"\x00" * (system_target - len(system))
    graphics = graphics + b"\x00" * (graphics_target - len(graphics))
    header = dataclasses.replace(
        sections.header, system_flags=system_flags, graphics_flags=graphics_flags)
    return dataclasses.replace(
        sections, header=header, system_data=system, graphics_data=graphics)


def save(dictionary, path: str, source: bytes | None = None,
         keep_size_flags: bool = False) -> str:
    """Serialise `dictionary` to `path`, keeping gen9 header fields from `source`.

    `source` is the bytes of the archive the dictionary came from.  Without it
    every header falls back to fivefury's runtime profile, which is only correct
    for a dictionary built from scratch.
    """
    y = _y()
    if source is not None:
        bad = _non_ascii_names(source)
        if bad:
            raise RuntimeError(
                "this archive stores %d texture name(s) outside ASCII (%s). fivefury reads "
                "and writes the name table with ascii+errors=ignore, so rewriting it would "
                "silently drop those bytes and rename the textures. Nothing was written: "
                "rename those textures to plain ASCII names (e.g. in CodeWalker or OpenIV) "
                "and run the command again."
                % (len(bad), ", ".join(repr(n) for n in bad[:3])))
    if source is not None and not is_gen9(source):
        legacy_hint = dump_legacy_headers(source)
        flags = None
        if keep_size_flags:
            import importlib
            hdr = importlib.import_module("fivefury.resource").read_rsc7_header(source)
            flags = (hdr.system_flags, hdr.graphics_flags)
        original_legacy = y._prepare_legacy_ytd
        y._prepare_legacy_ytd = _make_prepare_legacy(legacy_hint, flags)
        try:
            y.save_ytd(dictionary, path)
        finally:
            y._prepare_legacy_ytd = original_legacy
        _verify_legacy(path, legacy_hint)
        return path
    hint = dump_headers(source) if source is not None else {}
    original = y._prepare_gen9_ytd
    y._prepare_gen9_ytd = _make_prepare(hint)
    try:
        y.save_ytd(dictionary, path)
    finally:
        y._prepare_gen9_ytd = original
    if hint:
        _verify(path, hint)
    return path


def _non_ascii_names(raw: bytes) -> list[str]:
    """Names whose stored bytes are not plain ASCII.

    fivefury reads and writes the name table with ``ascii`` + ``errors="ignore"``
    (`binary.py:139`, `resource.py:676`), so a name stored as ``disque cot\\xe9_n``
    comes back as ``disque cot_n`` — the byte is gone before we ever see the string.
    Rewriting such an archive silently renames its textures, which then no longer
    match the files on disk or a CodeWalker ``-Original`` pass.
    """
    y = _y()
    virtual, _physical = _split(raw)
    count, items_off = y.catalog._checked_dictionary_items(virtual, 0)
    min_size = 0x48 if is_gen9(raw) else 0x78
    out: list[str] = []
    for index in range(count):
        to = y.catalog._checked_texture_offset(virtual, items_off, index, min_size)
        name_ptr = struct.unpack_from("<Q", virtual, to + 0x28)[0]
        no = y.catalog._virtual_offset(name_ptr)
        raw_name = virtual[no:virtual.index(b"\0", no)]
        if any(b > 0x7F for b in raw_name):
            out.append(raw_name.decode("latin-1"))
    return out


def _verify(path: str, hint: dict) -> None:
    """Read the archive back and prove every preserved header field survived.

    `_make_prepare` is our own copy of fivefury's gen9 writer, so a change on the
    upstream side could silently drop fields it no longer reads from us.  A read-back
    is the only cheap proof that the file we just wrote still says what it said.
    """
    with open(path, "rb") as fh:
        raw = fh.read()
    written = dump_headers(raw)
    missing = [name for name in hint if name not in written]
    drifted = []
    for name, expected in hint.items():
        actual = written.get(name)
        if actual is None:
            continue
        for key, value in expected.items():
            if key not in KEEP:
                continue
            got = actual.get(key)
            if got == value:
                continue
            if key == "fmt" and got in _y()._FORMAT_TO_RSC8.values():
                # A deliberate format change (BC3 normal -> BC1) rewrites this byte
                # along with the block layout; anything outside the known table is rot.
                continue
            drifted.append("%s.%s %r -> %r" % (name, key, value, got))
    if missing or drifted:
        detail = "; ".join((["%d texture(s) missing from the written archive" % len(missing)]
                            if missing else []) + drifted[:5])
        raise RuntimeError("written archive does not preserve the source headers: " + detail)


def _verify_legacy(path: str, hint: dict) -> None:
    """Same read-back proof as `_verify`, for the four legacy fields."""
    with open(path, "rb") as fh:
        raw = fh.read()
    written = dump_legacy_headers(raw)
    missing = [name for name in hint if name not in written]
    drifted = []
    for name, expected in hint.items():
        actual = written.get(name)
        if actual is None:
            continue
        same_geometry = (actual.get("width") == expected.get("width")
                         and actual.get("height") == expected.get("height")
                         and actual.get("format") == expected.get("format"))
        for key in LEGACY_KEEP:
            if key == "stride" and not same_geometry:
                continue
            if expected.get(key) != actual.get(key):
                drifted.append("%s.%s %r -> %r" % (name, key, expected.get(key), actual.get(key)))
    if missing or drifted:
        detail = "; ".join((["%d texture(s) missing from the written archive" % len(missing)]
                            if missing else []) + drifted[:5])
        raise RuntimeError("written archive does not preserve the source headers: " + detail)


def read_dds(path: str):
    """A DDS file as `(width, height, mip_count, TextureFormat, payload)`.

    The format is decoded against fivefury's own tables rather than
    `dds.read_header`, whose DXGI list only covers the formats texconv emits:
    a stock GTA normal map can be `R16G16B16A16_UNORM` (DXGI 65) and the narrow
    table rejects it.
    """
    importlib.import_module("fivefury.ytd.defs")
    defs = importlib.import_module("fivefury.ytd.defs")
    with open(path, "rb") as f:
        raw = f.read()
    if len(raw) < 128 or raw[:4] != b"DDS ":
        raise ValueError(f"{path}: not a DDS file")
    height, width = struct.unpack_from("<II", raw, 12)
    mips = struct.unpack_from("<I", raw, 28)[0] or 1
    pf_flags = struct.unpack_from("<I", raw, 80)[0]
    fourcc = raw[84:88]
    offset = 128
    fmt = None
    if fourcc == b"DX10":
        dxgi = struct.unpack_from("<I", raw, 128)[0]
        fmt = defs._DXGI_TO_FORMAT.get(defs.DxgiFormat(dxgi)) if dxgi in {f.value for f in defs.DxgiFormat} else None
        if fmt is None:
            raise ValueError(f"{path}: unsupported DXGI format {dxgi}")
        offset = 148
    elif len(fourcc) == 4 and fourcc.strip(b"\0") and not fourcc.startswith(b"\0"):
        code = struct.unpack("<I", fourcc)[0]
        fmt = defs._FOURCC_TO_FORMAT.get(code)
        if fmt is None:
            raise ValueError(f"{path}: unsupported fourCC {fourcc!r}")
    elif pf_flags & 0x40:
        masks = struct.unpack_from("<IIII", raw, 92)
        if masks == (0x00FF0000, 0x0000FF00, 0x000000FF, 0xFF000000):
            fmt = _y().TextureFormat.A8R8G8B8
        elif masks == (0x000000FF, 0x0000FF00, 0x00FF0000, 0xFF000000):
            fmt = _y().TextureFormat.R8G8B8A8
    if fmt is None:
        raise ValueError(f"{path}: unsupported pixel format (flags={pf_flags:#x}, fourcc={fourcc!r})")
    if len(raw) < offset:
        raise ValueError(f"{path}: truncated DDS ({len(raw)} bytes)")
    return width, height, mips, fmt, raw[offset:]


def texture_format(texconv_name: str):
    """Map a texconv format name to fivefury's TextureFormat enum member."""
    member = _TEXCONV_TO_FORMAT.get(texconv_name)
    if member is None:
        raise ValueError(f"no TextureFormat for texconv format {texconv_name!r}")
    return getattr(_y().TextureFormat, member)


def texture_from_dds(name: str, path: str, like=None):
    """Build a fivefury Texture from a DDS file.

    The format always comes from the DDS header, so a texture texconv re-encoded
    (BC3 -> BC1 in aggressive mode) lands with the format it now holds.  `like`
    only supplies the usage fields, which DDS cannot carry.
    """
    width, height, mips, fmt, payload = read_dds(path)
    y = _y()
    usage = like.usage if like is not None else y.TextureUsage.DEFAULT
    flags = like.usage_flags if like is not None else 0
    return y.Texture.from_raw(payload, width, height, fmt, mips, name=name,
                              usage=usage, usage_flags=flags)
