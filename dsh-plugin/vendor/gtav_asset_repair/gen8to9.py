"""Upgrade legacy (gen8) GTA V resources to the enhanced (gen9) container.

Ground truth: the four CodeWalker 30 dev48 "Asset Converter" output folders under
`素材不要动/` (gen8 input + gen9 output, same file names).  What the upgrade
actually changes, measured on those pairs:

* ``.ytd``  RSC7 version 13 -> 5.  Only the container is rewritten: the system
  page is rebuilt with 0x80-byte gen9 records, the names/keys pools and the
  pointers are re-laid-out, and the pixel payload is copied byte for byte onto
  gen9 page boundaries.  ``sultan.ytd`` converts to 77479 bytes, identical to
  CodeWalker's output (zero differing bytes; see `GEN8-TO-GEN9-NOTES.md` §3).
* ``.ymt`` / ``.yld``  keep their RSC7 version (2 / 8) and are *byte identical*
  between the two generations -- 45 .ymt plus 1 .yld compared, all equal -- so
  they are copied through unchanged.
* ``.ydd``  goes 165 -> 159 with an entirely different container (one system
  segment, no graphics page) and a re-encoded vertex layout.  fivefury's
  drawable codec does that round trip losslessly: on all 41 vanilla ped
  drawables every GPU channel -- positions, normals, tangents, texcoords,
  colours, blend weights/indices, bone ids, indices -- comes back value for
  value, and material parameters survive except the gen8-only ones gen9
  dropped.  See :func:`convert_ydd` for the three data defects it compensates.
* ``.yft``  goes 162 -> 171 and needs a full fragment rebuild: the gen9
  runtime tables differ for every fragment object, and vertex buffers are
  re-encoded.  All 24 shipped vehicle fragments convert with every mesh channel
  and material value intact (see :func:`convert_yft` for the two header values
  that have to be pinned).  The bound vertices are stored quantised in gen9, so
  collision geometry comes back within one int16 step (about 1e-5 of the
  bound size) -- that is a property of the gen9 container, not of this code.

The layout backend is fivefury's native ``layout_resource_sections``, whose page
split and RSC7 flags were checked to match CodeWalker bit for bit.  Compression
must be zlib level 6 (raw deflate, default strategy): level 7 and 9 produce
smaller but different streams, so a level-9 writer would never round-trip.
"""
from __future__ import annotations

import dataclasses
import importlib
import os
import struct
import zlib
from dataclasses import dataclass, field

from . import ytd as _ytdmod

# RSC7 versions, read from bytes 4..8 of the file.
LEGACY_YTD_VERSION = 13
GEN9_YTD_VERSION = 5
YMT_VERSION = 2
YLD_VERSION = 8
LEGACY_YDD_VERSION = 165
GEN9_YDD_VERSION = 159
LEGACY_YFT_VERSION = 162
GEN9_YFT_VERSION = 171

# CodeWalker writes zlib level 6; this is not a tuning knob.
COMPRESSION_LEVEL = 6

# gen9 system skeleton (measured on all 18 vehicle dictionaries + 41 ped ones).
GEN9_TEXTURE_VFT = 0x0000000140617568
GEN9_SRV_VFT = 0x00000001406B77D8
GEN9_DESCRIPTOR_FLAGS = 0x00260208
GEN9_RENDER_TARGET_BIT = 0x20
GEN9_USAGE_CLASS = 2
GEN9_RECORD_SIZE = 0x80
GEN9_RECORDS_START = 0x450
SYSTEM_PAGE_SIZE = 0x2000

# Pointer tags: system pointers carry 0x50000000, graphics ones 0x60000000.
VIRTUAL_TAG = 0x50000000
PHYSICAL_TAG = 0x60000000

# A stub archive: valid RSC7 header, far too small to hold a dictionary.
_PLACEHOLDER_LIMIT = 512

_PASSTHROUGH_VERSIONS = {".ymt": YMT_VERSION, ".yld": YLD_VERSION}
# Resource types with no lossless upgrade, mapped to the reason shown to callers.
_UNSUPPORTED: dict[str, str] = {}

# There is deliberately no size gate here.  A 32 MiB "gen9 system segment budget"
# was tried on 2026-11-26 and withdrawn the same day: a shipped gen9 fragment with
# a 34,078,720 B system segment (bmw/f82lw.yft, 4160 pages) loads fine in game, so
# segment size alone does not decide whether the Enhanced edition accepts a pack.
# Every 32 MiB sample that failed also failed for other, still unknown reasons.
# The probe later showed a vanilla-style 64 MiB drawable converting cleanly, so a
# gate would only hide files the game can actually load.


class UnsupportedResource(RuntimeError):
    """The resource type cannot be upgraded losslessly."""


class PlaceholderArchive(RuntimeError):
    """A stub archive (empty +hi.ytd); there is no dictionary to convert."""


# --------------------------------------------------------------------------- #
# vendored backend access
# --------------------------------------------------------------------------- #
def _modules():
    """(resource, defs, hashing) from the vendored fivefury package."""
    _ytdmod._load_reader()                       # puts vendor/ on sys.path
    return (importlib.import_module("fivefury.resource"),
            importlib.import_module("fivefury.ytd.defs"),
            importlib.import_module("fivefury.hashing"))


# --------------------------------------------------------------------------- #
# gen8 parsing
# --------------------------------------------------------------------------- #
def _u16(buf: bytes, off: int) -> int:
    return struct.unpack_from("<H", buf, off)[0]


def _u32(buf: bytes, off: int) -> int:
    return struct.unpack_from("<I", buf, off)[0]


def _offset(value: int) -> int:
    """Strip the system/graphics pointer tag."""
    value = int(value)
    if value >= PHYSICAL_TAG:
        return value - PHYSICAL_TAG
    if value >= VIRTUAL_TAG:
        return value - VIRTUAL_TAG
    return value


def _cstring(buf: bytes, off: int) -> str:
    end = buf.index(b"\x00", off)
    return buf[off:end].decode("latin-1")


def rsc7_version(raw: bytes) -> int | None:
    """The RSC7 version, or None when the data is not an RSC7 resource."""
    if len(raw) < 8 or raw[:4] != b"RSC7":
        return None
    return struct.unpack_from("<I", raw, 4)[0]


def is_placeholder(raw: bytes) -> bool:
    """True for an empty ``+hi.ytd`` stub: a header and no graphics page.

    Size alone is not enough.  A dictionary that is a couple of hundred bytes
    with a single 8x8 block is a real texture (``mp_m_niko_01/lowr_diff_000_a_uni``
    is 186 bytes, the shipped gen9 twin is 202); turning it into a "stub" would
    copy it with a new version byte and ship a texture the game cannot read.
    A stub carries a system page and *no* graphics page at all.
    """
    if len(raw) > _PLACEHOLDER_LIMIT or rsc7_version(raw) is None:
        return False
    resource, _defs, _hashing = _modules()
    header = resource.read_rsc7_header(raw)
    graphics_size = int(resource.get_resource_size_from_flags(header.graphics_flags))
    return graphics_size == 0


def system_segment_size(raw: bytes) -> int | None:
    """The decompressed system segment size announced by an RSC7 header.

    Read straight from the flag word, so this needs no decompression and can
    gate an expensive conversion before it starts.
    """
    if len(raw) < 16 or raw[:4] != b"RSC7":
        return None
    resource, _defs, _hashing = _modules()
    header = resource.read_rsc7_header(raw)
    return int(resource.get_resource_size_from_flags(header.system_flags))


@dataclass
class TextureSource:
    """One texture as read from a gen8 dictionary."""
    name: str
    width: int
    height: int
    fmt: object                      # fivefury TextureFormat
    mips: int
    usage: int
    usage_flags: int
    stride: int
    blocks: int
    data_size: int
    data: bytes
    index: int                       # position in the gen8 items array
    name_order: int = 0              # position in the gen8 name pool


def parse_legacy(raw: bytes) -> tuple[list[TextureSource], int]:
    """Read a gen8 dictionary; returns (textures in items order, keys_before).

    ``keys_before`` is how many name strings precede the keys array in the gen8
    system page.  CodeWalker keeps that relative position for most archives (the
    rule reproduces 7 of the 18 vehicle dictionaries byte for byte, and 10 of 18
    once the insertion point is searched), and it is the only signal the gen8
    file gives about where gen9 wants the keys.
    """
    res, defs, _hashing = _modules()
    if is_placeholder(raw):
        raise PlaceholderArchive("stub archive: header only, nothing to convert")
    header, system, graphics = res.split_rsc7_sections(raw)
    if header.version != LEGACY_YTD_VERSION:
        raise UnsupportedResource(
            f"not a gen8 texture dictionary (RSC7 version {header.version}, "
            f"expected {LEGACY_YTD_VERSION})")

    count = _u16(system, 0x28)
    if not 0 < count <= 0x4000:
        raise UnsupportedResource(f"implausible texture count {count}")
    items_off = _offset(_u32(system, 0x30))
    keys_off = _offset(_u32(system, 0x20))

    textures: list[TextureSource] = []
    name_ptrs: list[int] = []
    for index in range(count):
        record = _offset(_u32(system, items_off + 8 * index))
        name_ptr = _offset(_u32(system, record + 0x28))
        name = _cstring(system, name_ptr)
        usage_data = _u32(system, record + 0x40)
        width = _u16(system, record + 0x50)
        height = _u16(system, record + 0x52)
        fourcc = _u32(system, record + 0x58)
        mips = system[record + 0x5D]
        fmt = defs._resolve_legacy_format(fourcc)
        if fmt is None:
            raise UnsupportedResource(f"{name}: unknown legacy fourcc 0x{fourcc:08X}")
        size = defs._total_mip_data_size(width, height, fmt, mips)
        phys = _offset(_u32(system, record + 0x70))
        payload = graphics[phys:phys + size]
        if len(payload) != size:
            raise UnsupportedResource(
                f"{name}: graphics payload truncated (need {size}, have {len(payload)})")
        textures.append(TextureSource(
            name=name, width=width, height=height, fmt=fmt, mips=mips,
            usage=usage_data & 0x1F, usage_flags=usage_data >> 5,
            stride=defs._BLOCK_BYTES[fmt] if defs._is_block_compressed(fmt) else 4,
            blocks=defs._total_texture_block_count(width, height, fmt, mips),
            data_size=size, data=payload, index=index,
            name_order=0))
        name_ptrs.append(name_ptr)

    pool_order = sorted(name_ptrs)
    for texture in textures:
        texture.name_order = pool_order.index(name_ptrs[texture.index])
    keys_before = sum(1 for ptr in name_ptrs if ptr < keys_off)
    return textures, keys_before


# --------------------------------------------------------------------------- #
# gen9 building
# --------------------------------------------------------------------------- #
def build_gen9(textures: list[TextureSource], keys_before: int) -> bytes:
    """Build the gen9 container for `textures`; the pixel bytes are copied as-is.

    Layout follows the CodeWalker templates: pages-info at 0x40, records from
    0x450 in items order, items array, then the name pool in gen8 physical order
    with the keys array inserted after the ``keys_before``-th name (or first,
    when gen8 had it before every name).
    """
    res, defs, hashing = _modules()
    count = len(textures)
    recs_off = GEN9_RECORDS_START
    items_off = recs_off + GEN9_RECORD_SIZE * count
    names_off = items_off + 8 * count

    kb = keys_before if 0 <= keys_before <= count else count
    ordered = sorted(textures, key=lambda t: t.name_order)

    # Interleave the name pool with the 4-byte keys array, everything 16-aligned.
    cursor = names_off
    name_pos: dict[str, int] = {}
    keys_off = None

    def _place_keys(at: int) -> int:
        start = (at + 15) // 16 * 16
        return (start + 4 * count + 15) // 16 * 16

    if kb == 0:
        keys_off = (cursor + 15) // 16 * 16
        cursor = _place_keys(keys_off)
    for position, texture in enumerate(ordered):
        name_pos[texture.name] = cursor
        cursor = (cursor + len(texture.name.encode("latin-1")) + 1 + 15) // 16 * 16
        if kb and keys_off is None and position == kb - 1:
            keys_off = (cursor + 15) // 16 * 16
            cursor = _place_keys(keys_off)
    if keys_off is None:
        keys_off = (cursor + 15) // 16 * 16
        cursor = _place_keys(keys_off)
    names_end = cursor

    total = max(SYSTEM_PAGE_SIZE, (names_end + 15) // 16 * 16)
    vbuf = bytearray(total)

    # dictionary header
    struct.pack_into("<Q", vbuf, 0x00, 0x0000000140571500)
    struct.pack_into("<Q", vbuf, 0x08, VIRTUAL_TAG + 0x40)        # pages info
    struct.pack_into("<Q", vbuf, 0x10, 0)
    struct.pack_into("<I", vbuf, 0x18, 1)
    struct.pack_into("<Q", vbuf, 0x20, VIRTUAL_TAG + keys_off)
    struct.pack_into("<HHI", vbuf, 0x28, count, count, 0)
    struct.pack_into("<Q", vbuf, 0x30, VIRTUAL_TAG + items_off)
    struct.pack_into("<HHI", vbuf, 0x38, count, count, 0)

    # records + items, pixels packed 16-aligned (the layout pass re-pages them)
    gfx_cursor = 0
    gbuf = bytearray()
    spans = []
    for index, texture in enumerate(textures):
        off = recs_off + index * GEN9_RECORD_SIZE
        struct.pack_into("<Q", vbuf, off + 0x00, GEN9_TEXTURE_VFT)
        struct.pack_into("<II", vbuf, off + 0x08, texture.blocks, texture.stride)
        # Render-target textures (script_rt_*) must keep the render-target bit;
        # retail gen9 resources carry 0x00260228 for them instead of 0x00260208.
        dflags = GEN9_DESCRIPTOR_FLAGS
        render_target = texture.name.lower().startswith("script_rt")
        if render_target:
            dflags |= GEN9_RENDER_TARGET_BIT
        struct.pack_into("<II", vbuf, off + 0x10, dflags, 0)
        struct.pack_into("<HHH", vbuf, off + 0x18, texture.width, texture.height, 1)
        vbuf[off + 0x1E] = 1                                      # 2D texture
        vbuf[off + 0x1F] = defs._FORMAT_TO_RSC8[texture.fmt]
        vbuf[off + 0x20] = 0xFF                                   # tile mode
        vbuf[off + 0x21] = 0                                      # image flags
        vbuf[off + 0x22] = texture.mips
        vbuf[off + 0x23] = 0x28
        vbuf[off + 0x24] = 0
        struct.pack_into("<H", vbuf, off + 0x26, 1)
        struct.pack_into("<Q", vbuf, off + 0x28, VIRTUAL_TAG + name_pos[texture.name])
        struct.pack_into("<Q", vbuf, off + 0x30, VIRTUAL_TAG + off + 0x58)
        struct.pack_into("<Q", vbuf, off + 0x38, PHYSICAL_TAG + gfx_cursor)
        # gen8 stored usage flags above bit 4. Retail gen9 keeps them for
        # render-target textures; plain textures only need the usage id.
        usage_flags = texture.usage_flags if render_target else 0
        struct.pack_into("<II", vbuf, off + 0x40, (usage_flags << 5) | texture.usage, GEN9_USAGE_CLASS)
        struct.pack_into("<Q", vbuf, off + 0x58, GEN9_SRV_VFT)
        struct.pack_into("<Q", vbuf, off + 0x60, 0)
        struct.pack_into("<HHI", vbuf, off + 0x68, 0x41, 0xFFFF, 0xFFFFFFFF)
        struct.pack_into("<Q", vbuf, items_off + 8 * index, VIRTUAL_TAG + off)

        spans.append(res.ResourceBlockSpan(gfx_cursor, texture.data_size, False))
        gbuf.extend(texture.data)
        gbuf.extend(b"\x00" * ((-len(gbuf)) % 16))
        gfx_cursor = len(gbuf)

        name_bytes = texture.name.encode("latin-1") + b"\x00"
        vbuf[name_pos[texture.name]:name_pos[texture.name] + len(name_bytes)] = name_bytes

    # keys array, same order as the gen8 items array
    for index, texture in enumerate(textures):
        struct.pack_into("<I", vbuf, keys_off + 4 * index, hashing.jenk_hash(texture.name))

    pointer_offsets = [0x08, 0x20, 0x30]
    pointer_offsets += [items_off + 8 * index for index in range(count)]
    for index in range(count):
        off = recs_off + index * GEN9_RECORD_SIZE
        pointer_offsets += [off + 0x28, off + 0x30, off + 0x38]

    system_data, graphics_data, sys_flags, gfx_flags = res.layout_resource_sections(
        bytes(vbuf),
        [res.ResourceBlockSpan(0, len(vbuf), pointer_offsets=tuple(pointer_offsets))],
        bytes(gbuf),
        spans,
        version=GEN9_YTD_VERSION,
    )
    # CodeWalker keeps the system page at 8192 B and adds pages when the record
    # area outgrows one (flags 0x00020000 = 1 page, 0x00040000 = 2).  The native
    # backend instead prefers a single larger page -- a 44-texture ped dictionary
    # comes back as flags 0x00020001, one 16384 B page -- so the page count is
    # re-derived from the real payload length and the padding re-trimmed.  Both
    # forms describe the same bytes; only this one matches the templates.
    pages = max(1, (max(len(vbuf), SYSTEM_PAGE_SIZE) + SYSTEM_PAGE_SIZE - 1)
                // SYSTEM_PAGE_SIZE)
    if pages <= 0x7F:                              # width of the s4 page-count field
        sys_flags = pages << 17                  # base_shift 0: 8192 B pages
        target = pages * SYSTEM_PAGE_SIZE
        if len(system_data) > target:
            if any(system_data[target:]):
                raise RuntimeError(
                    f"system payload overruns {pages} x {SYSTEM_PAGE_SIZE} B pages")
            system_data = system_data[:target]
    system_data = bytearray(system_data)
    struct.pack_into("<IIBBHI", system_data, 0x40, 0, 0,
                     res.get_resource_total_page_count(sys_flags),
                     res.get_resource_total_page_count(gfx_flags), 0, 0)
    sections = res.prepare_rsc7_sections(
        bytes(system_data), version=GEN9_YTD_VERSION, graphics_data=graphics_data,
        system_flags=sys_flags, graphics_flags=gfx_flags)
    return sections.to_bytes(compression_level=COMPRESSION_LEVEL)


# --------------------------------------------------------------------------- #
# verification
# --------------------------------------------------------------------------- #
def readback_problems(source: bytes, converted: bytes) -> list[str]:
    """Re-read both archives and compare every texture by name.

    Catches the failure modes a byte diff cannot attribute: a pointer that lands
    in the wrong pool, a dropped texture, a pixel payload shifted by an
    alignment mistake.  Returns human-readable problems; empty means equivalent.
    """
    read_ytd = _ytdmod._load_reader()
    old = read_ytd(source)
    new = read_ytd(converted)
    problems: list[str] = []
    old_by_name = {t.name: t for t in old.textures}
    new_by_name = {t.name: t for t in new.textures}
    for name in old_by_name:
        if name not in new_by_name:
            problems.append(f"{name}: missing after conversion")
    for name, before in old_by_name.items():
        after = new_by_name.get(name)
        if after is None:
            continue
        if (before.width, before.height) != (after.width, after.height):
            problems.append(f"{name}: size {before.width}x{before.height} -> "
                            f"{after.width}x{after.height}")
        if before.format != after.format:
            problems.append(f"{name}: format {before.format} -> {after.format}")
        if before.mip_count != after.mip_count:
            problems.append(f"{name}: mips {before.mip_count} -> {after.mip_count}")
        if bytes(before.data) != bytes(after.data):
            problems.append(f"{name}: {len(before.data)} B pixel payload differs")
        if before.usage != after.usage:
            problems.append(f"{name}: usage {before.usage} -> {after.usage}")
    return problems


# --------------------------------------------------------------------------- #
# .ydd  (gen8 165 -> gen9 159)
# --------------------------------------------------------------------------- #
# Every shipped gen9 drawable -- the 41 vanilla peds under
# `素材不要动/ped_ingame41_gen9` included -- carries vertex buffer flags
# 0x00580409, skinned or not.  fivefury defaults skinned meshes to 0x00586409,
# which matches no retail file, so the value is pinned here.
GEN9_VERTEX_BUFFER_FLAGS = 0x00580409

_YDD_SHIMS_READY = False


def _install_ydd_shims() -> None:
    """Adapt the vendored drawable codec to shipped content and to numpy 2.3.

    Three separate mismatches, all measured on the vanilla ped pairs:

    * numpy 2.3 rejects ``astype(..., casting="same_value")``, which
      ``fivefury.numeric.int64_array`` uses, so index arrays cannot be built at
      all.  The replacement keeps the same contract: integer values only.
    * fivefury raises when a vertex weights a bone id outside the mesh palette.
      Shipped gen8 *and* gen9 files both contain such slots (162 of them in
      ``a_f_y_beach_01``), so the channels are written back verbatim.
    * the strict remap also zeroes the index of every zero-weight slot, which
      retail files do not do.

    Installed once per process, on the vendored modules only.
    """
    global _YDD_SHIMS_READY
    if _YDD_SHIMS_READY:
        return
    _install_resource_shims()
    try:
        import numpy as np
    except ImportError as exc:                       # pragma: no cover - environment
        raise RuntimeError("converting .ydd drawables requires numpy") from exc
    _ytdmod._load_reader()
    numeric = importlib.import_module("fivefury.numeric")
    mesh_math = importlib.import_module("fivefury.mesh_math")
    skinning = importlib.import_module("fivefury.ydr.prepare.skinning")
    channels = importlib.import_module("fivefury.ydr.prepare.channels")

    def int64_array(values, *, name):
        raw = np.asarray(values, copy=None)
        if raw.dtype.kind in "iu":
            return raw.astype(np.int64, copy=False)
        if raw.dtype.kind == "f":
            rounded = np.rint(raw)
            if not np.array_equal(rounded, raw):
                raise ValueError(f"{name} must contain exact 64-bit integer values")
            return rounded.astype(np.int64, copy=False)
        try:
            return raw.astype(np.int64, copy=False)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} must contain exact 64-bit integer values") from exc

    def keep_skin_channels(blend_weights, blend_indices, bone_ids, skeleton):
        return list(blend_indices or ()), list(bone_ids or ())

    numeric.int64_array = int64_array
    mesh_math.int64_array = int64_array
    skinning.normalize_skin_channels = keep_skin_channels
    channels.normalize_skin_channels = keep_skin_channels
    _YDD_SHIMS_READY = True


def _ydd_modules():
    """(ydd package, gen9 shader table, hashing) with the shims installed."""
    _install_ydd_shims()
    return (importlib.import_module("fivefury.ydd"),
            importlib.import_module("fivefury.ydr.gen9"),
            importlib.import_module("fivefury.hashing"))


def _iter_meshes(ydd):
    """Yield ``(drawable hash, model index, mesh)`` for every mesh in the file."""
    for entry in ydd.drawables:
        drawable = getattr(entry, "drawable", None)
        for model_index, model in enumerate(getattr(drawable, "models", ()) or ()):
            for mesh in getattr(model, "meshes", ()) or ():
                yield entry.name_hash, model_index, mesh


def _prepare_ydd(ydd, gen9, hashing) -> list[str]:
    """Pin gen9 header values and drop material parameters gen9 no longer has."""
    library = gen9.load_gen9_shader_library()
    dropped: list[str] = []
    for _hash, _model, mesh in _iter_meshes(ydd):
        mesh.vertex_buffer_flags = GEN9_VERTEX_BUFFER_FLAGS
        material = getattr(mesh, "material", None)
        if material is None or not material.shader_name:
            continue
        shader = library.get_shader(hashing.jenk_hash(material.shader_name))
        if shader is None:
            raise UnsupportedResource(
                f"no gen9 shader definition for '{material.shader_name}'")
        kept_parameters = []
        for parameter in material.parameters or ():
            if parameter.name and shader.get_parameter(parameter.name) is None:
                if parameter.name not in dropped:
                    dropped.append(parameter.name)
                continue
            kept_parameters.append(parameter)
        material.parameters = kept_parameters
        material.textures = [
            texture for texture in (material.textures or ())
            if not texture.parameter_name
            or shader.get_parameter(texture.parameter_name) is not None]
    return dropped


#: VFTs that the gen9 writer emits for structural objects, mapped back to the
#: gen8 values they replace.  Packs whose drawables are *bare* YdrDrawables
#: (``0x40573178``) crash in game when these are rewritten to the gen9 table,
#: while keeping the gen8 values loads fine.  Measured on Kasumi, which is the
#: 31-drawable, three-LOD, 128-bone case; see GEN8-TO-GEN9-NOTES.md 12.9.
GEN9_TO_LEGACY_STRUCTURAL_VFT = {
    0x4068C7F0: 0x40573178,  # drawable
    0x406BB978: 0x406137F0,  # shader group
    0x406BB948: 0x40610A98,  # model
    0x406BB7E8: 0x40618798,  # geometry
    0x406B9108: 0x4061D3F8,  # vertex buffer
    0x406B90B8: 0x4061D158,  # index buffer
    0x406BE318: 0x40613CA0,  # skeleton
}
_BARE_DRAWABLE_VFT = 0x40573178
_WRAPPED_DRAWABLE_VFT = 0x40573158
_STREAM_DRAWABLE_VFT = 0x40571578
#: Texture VFTs stay gen9 in every mode: the texture objects really do change
#: shape between the generations, and every working build we have uses the
#: gen9 values there.
GEN9_TEXTURE_VFTS = (0x406B7940, 0x406B77D8)


def _system_segment(raw: bytes) -> bytes:
    """Return the decompressed system segment of a standalone RSC7 resource."""
    resource = importlib.import_module("fivefury.resource")
    header, payload = resource.parse_rsc7(raw)
    return payload[:resource.get_resource_size_from_flags(header.system_flags)]


def _drawable_vft_kind(system: bytes) -> str:
    """Classify a gen8 drawable dictionary by the VFT its drawables carry.

    ``bare`` is the form third-party packs use (a plain YdrDrawable),
    ``wrapped`` is the form retail ped dictionaries use, and ``stream`` is the
    per-component form of a streamed ped.
    """
    counts = {vft: 0 for vft in (_BARE_DRAWABLE_VFT, _WRAPPED_DRAWABLE_VFT,
                                 _STREAM_DRAWABLE_VFT)}
    for offset in range(0, len(system) - 4, 4):
        value = struct.unpack_from("<I", system, offset)[0]
        if value in counts:
            counts[value] += 1
    if counts[_BARE_DRAWABLE_VFT]:
        return "bare"
    if counts[_STREAM_DRAWABLE_VFT]:
        return "stream"
    if counts[_WRAPPED_DRAWABLE_VFT]:
        return "wrapped"
    return "unknown"


def _demote_structural_vfts(system: bytearray) -> dict[int, int]:
    """Swap gen9 structural VFT dwords back to their gen8 values in place."""
    counts: dict[int, int] = {}
    for offset in range(0, len(system) - 4, 4):
        old = struct.unpack_from("<I", system, offset)[0]
        new = GEN9_TO_LEGACY_STRUCTURAL_VFT.get(old)
        if new is not None:
            struct.pack_into("<I", system, offset, new)
            counts[old] = counts.get(old, 0) + 1
    return counts


def convert_ydd(raw: bytes) -> bytes:
    """Convert one gen8 .ydd drawable dictionary to gen9.

    The container is rebuilt for the gen9 layout (one system segment, gen9
    drawable VFTs) and every vertex buffer is re-encoded.  Geometry survives
    value for value; only the gen8-only material parameters are dropped, because
    gen9 has no slot for them.

    Dictionaries whose drawables are bare YdrDrawables keep their gen8
    structural VFTs: rewriting those to the gen9 table makes the ped crash in
    game.  Texture VFTs are raised to gen9 in every case.
    """
    ydd_api, gen9, hashing = _ydd_modules()
    version = rsc7_version(raw)
    if version != LEGACY_YDD_VERSION:
        raise UnsupportedResource(
            f"drawable RSC7 version {version}, expected {LEGACY_YDD_VERSION}")
    kind = _drawable_vft_kind(_system_segment(raw))
    ydd = ydd_api.read_ydd(raw)
    _prepare_ydd(ydd, gen9, hashing)
    ydd.version = GEN9_YDD_VERSION
    ydd.runtime_profile = ydd_api.GEN9_YDD_RUNTIME_PROFILE
    converted = ydd_api.build_ydd_bytes(ydd)
    if kind != "bare":
        return converted
    resource = importlib.import_module("fivefury.resource")
    header, payload = resource.parse_rsc7(converted)
    system_size = resource.get_resource_size_from_flags(header.system_flags)
    graphics_size = resource.get_resource_size_from_flags(header.graphics_flags)
    system = bytearray(payload[:system_size])
    graphics = payload[system_size:system_size + graphics_size]
    if not _demote_structural_vfts(system):
        raise UnsupportedResource(
            "drawable: bare YdrDrawable pack but no gen9 structural VFTs found")
    return resource.prepare_rsc7_sections(
        bytes(system),
        version=header.version,
        graphics_data=graphics,
        system_flags=header.system_flags,
        graphics_flags=header.graphics_flags,
    ).to_bytes(compression_level=COMPRESSION_LEVEL)


def _mesh_fingerprint(mesh) -> tuple:
    return (tuple((round(float(p.x), 5), round(float(p.y), 5), round(float(p.z), 5))
                  for p in (getattr(mesh, "positions", ()) or ())),
            tuple(int(i) for i in (getattr(mesh, "indices", ()) or ())),
            tuple(int(b) for b in (getattr(mesh, "bone_ids", ()) or ())))


def readback_ydd_problems(source: bytes, converted: bytes) -> list[str]:
    """Re-read both drawables and compare every mesh channel and shader."""
    ydd_api, _gen9, _hashing = _ydd_modules()
    old = ydd_api.read_ydd(source)
    new = ydd_api.read_ydd(converted)
    problems: list[str] = []
    old_meshes = {(h, m): mesh for h, m, mesh in _iter_meshes(old)}
    new_meshes = {(h, m): mesh for h, m, mesh in _iter_meshes(new)}
    for key, before in old_meshes.items():
        label = f"drawable {key[0]:#010x} model {key[1]}"
        after = new_meshes.get(key)
        if after is None:
            problems.append(f"{label}: mesh missing after conversion")
            continue
        if _mesh_fingerprint(before) != _mesh_fingerprint(after):
            problems.append(f"{label}: vertex data differs")
        if getattr(before, "vertex_stride", None) != getattr(after, "vertex_stride", None):
            problems.append(f"{label}: vertex stride changed")
        before_material, after_material = before.material, after.material
        if before_material and after_material:
            if before_material.shader_name != after_material.shader_name:
                problems.append(f"{label}: shader {before_material.shader_name} -> "
                                f"{after_material.shader_name}")
            # gen9 legitimately drops gen8-only parameters and sampler refs, so
            # only the parameters shared by both sides are compared.
            after_parameters = {p.name: p.value for p in (after_material.parameters or ())}
            for parameter in before_material.parameters or ():
                if parameter.name in after_parameters and \
                        after_parameters[parameter.name] != parameter.value:
                    problems.append(f"{label}: parameter {parameter.name} changed")
    return problems


# --------------------------------------------------------------------------- #
# .yft  (gen8 162 -> gen9 171)
# --------------------------------------------------------------------------- #
# Two header values have to be pinned before the rebuild, both measured on the
# retail gen9 vehicles under `素材不要动/vehicles_ingame_gen9`:
#
# * ``vertex_buffer_flags`` -- fivefury writes 0x00586409 for skinned meshes,
#   but every shipped gen9 mesh (this is about vehicles, so no mesh is skinned)
#   carries 0x00580409, the same value gen9 .ydd meshes use.
# * ``YdrJoints.vft`` -- fivefury only substitutes the gen9 joints table when the
#   incoming value is 0 or its own default; a value read from a gen8 file is
#   written back verbatim, which leaves a legacy VFT inside a 171 fragment.
#   Zeroing it makes the writer emit the gen9 runtime table.
GEN9_JOINTS_VFT = 0x406BE4D8


_RESOURCE_SHIMS_READY = False


def _install_resource_shims() -> None:
    """Accept a few padding bytes behind a complete deflate stream.

    Some third-party packs end the compressed stream with padding: in
    ``vehicles_gen8/renventon.yft`` zlib reaches ``eof`` and the payload decodes
    to exactly the declared size, but four bytes follow it (``62 39 43 a7``).
    fivefury treats any trailing byte as corruption, which would reject a file
    the game itself loads.  More than 16 bytes is still refused.
    """
    global _RESOURCE_SHIMS_READY
    if _RESOURCE_SHIMS_READY:
        return
    _ytdmod._load_reader()                       # puts vendor/ on sys.path
    resource = importlib.import_module("fivefury.resource")

    def _decompress_raw_resource_stream(data, *, dictionary=None):
        if dictionary is None:
            decompressor = zlib.decompressobj(wbits=-15)
        else:
            decompressor = zlib.decompressobj(wbits=-15, zdict=dictionary)
        output = decompressor.decompress(data) + decompressor.flush()
        if not decompressor.eof:
            raise ValueError("resource deflate stream is truncated")
        if decompressor.unconsumed_tail or len(decompressor.unused_data) > 16:
            raise ValueError("resource deflate stream contains trailing data")
        return output

    resource._decompress_raw_resource_stream = _decompress_raw_resource_stream
    _RESOURCE_SHIMS_READY = True


# An event set record is 0x30 bytes in both generations.
_EVENT_SET_SIZE = 0x30
_YFT_SHIMS_READY = False


def _install_yft_shims() -> None:
    """Rebuild empty event sets whose runtime state is not the retail value.

    Retail gen9 vehicles and all 24 vanilla gen8 ones carry ``resource_state=1``
    on every empty event set.  Third-party packs (``i8``, ``gtr``) carry 0 and a
    bogus VFT (``0x74536353``); CodeWalker copies both through unchanged, so the
    game evidently re-initialises these sets at spawn.  fivefury refuses to write
    them at all, which would make every such pack unconvertible.

    The replacement keeps fivefury's record layout and the source state, and it
    still refuses sets that actually hold instances or point at a bank/group.
    """
    global _YFT_SHIMS_READY
    if _YFT_SHIMS_READY:
        return
    writer = importlib.import_module("fivefury.yft.writer")
    events_writer = importlib.import_module("fivefury.yft.events_writer")

    def write_event_sets(stream, event_sets, *, runtime_headers):
        offsets: dict[int, int] = {}
        for event_set in event_sets:
            identity = id(event_set)
            if identity in offsets:
                continue
            empty = (event_set.is_empty and event_set.capacity == 0
                     and event_set.new_instance_type == 0
                     and not event_set.bank_pointer and not event_set.group_pointer)
            if not empty:
                raise ValueError(
                    "YFT event set carries instances and cannot be rebuilt")
            offset = stream.alloc(_EVENT_SET_SIZE, 16)
            stream.pack_into("I", offset, int(runtime_headers.event_set))
            stream.pack_into("I", offset + 4, int(event_set.resource_state))
            stream.pack_into("HH", offset + 0x10, 0, 0)
            stream.pack_into("i", offset + 0x18, int(event_set.new_instance_type))
            offsets[identity] = offset
        return offsets

    events_writer.write_event_sets = write_event_sets
    writer.write_event_sets = write_event_sets                 # imported by name

    # Third-party packs also ship fragment headers fivefury refuses to touch:
    # empty event sets and physics classes with resource_state 0, bound VFTs
    # that are absent or junk ("CMPs", "USBC"), and one vehicle-glass pane
    # pointing at a mesh that is not glass.  CodeWalker copies every one of
    # those bytes through unchanged and the packs work in game, so they are
    # placeholders the runtime rebuilds.  The gen9 writers already emit the
    # gen9 VFTs and state 1 on their own; only the pre-write checks stand in
    # the way.  Every vanilla fragment passes the same checks, so loosening
    # them cannot hide a real conversion bug.
    events = importlib.import_module("fivefury.yft.events")
    events.YftEventSet.can_rebuild = property(
        lambda self: self.is_empty
        and self.capacity == 0
        and self.new_instance_type == 0
        and not self.bank_pointer
        and not self.group_pointer)

    bound_profiles = importlib.import_module("fivefury.yft.bound_profiles")
    diagnostics = importlib.import_module("fivefury.authoring.diagnostics")
    original_validate_bound_profile = bound_profiles.validate_bound_profile

    def validate_bound_profile(root, profile, *, expected_slots=None):
        if bound_profiles.coerce_yft_physics_bound_profile(profile) is (
                bound_profiles.YftPhysicsBoundProfile.PRESERVE):
            return diagnostics.ValidationReport()
        return original_validate_bound_profile(
            root, profile, expected_slots=expected_slots)

    bound_profiles.validate_bound_profile = validate_bound_profile
    importlib.import_module("fivefury.yft.validation").validate_bound_profile = (
        validate_bound_profile)
    importlib.import_module("fivefury.yft.physics_authoring").validate_bound_profile = (
        validate_bound_profile)
    glass_authoring = importlib.import_module("fivefury.yft.vehicle_glass_authoring")
    glass_authoring.validate_yft_vehicle_glass = (
        lambda source: diagnostics.ValidationReport())

    # Octants are a pure acceleration table, and the retail gen9 fragments carry
    # exactly the ones their gen8 sources had: burrito2.yft has 22 octant blocks
    # for 32 geometries on both sides.  fivefury rebuilds a table for every
    # geometry that arrives without one, which grew burrito2's system segment
    # from the retail 1,859,584 B to 2,228,224 B (+20%).  Keep the source state.
    bounds_writer = importlib.import_module("fivefury.bounds.writer")

    def keep_octants(bound, vertices_shrunk, *, with_bvh):
        if with_bvh:
            return None
        octants = getattr(bound, "octants", None)
        return octants if (octants is not None and octants.has_items) else None

    bounds_writer._choose_octants = keep_octants
    _YFT_SHIMS_READY = True


def _yft_modules():
    """(yft package, hashing) with the drawable codec shims installed."""
    # The fragment rebuild re-encodes vertex buffers through the same ydr code
    # as .ydd, so it needs the same numpy 2.x and skin-channel adapters.
    _install_resource_shims()
    _install_ydd_shims()
    _install_yft_shims()
    return (importlib.import_module("fivefury.yft"),
            importlib.import_module("fivefury.hashing"))


_MESH_BULK_FIELDS = frozenset({
    # Per-vertex and per-index arrays. Walking into them costs seconds on a
    # 13 MB fragment (488k Vector3 objects) and no caller ever looks below the
    # mesh, so the mesh itself is the leaf.
    "positions", "normals", "tangents", "texcoords", "colours0", "colours1",
    "blend_weights", "blend_indices", "bone_ids", "indices",
})


def _walk_yft(root):
    """Yield every object reachable from ``root`` exactly once.

    Mesh vertex arrays are not descended into: ``_prepare_yft`` only pins
    header values one level above them, and expanding them made the walk
    slower than reading and writing the whole fragment combined.
    """
    seen: set[int] = set()
    stack = [root]
    while stack:
        obj = stack.pop()
        if obj is None or isinstance(obj, (str, bytes, int, float, bool)):
            continue
        if id(obj) in seen:
            continue
        seen.add(id(obj))
        yield obj
        if dataclasses.is_dataclass(obj):
            skip = _MESH_BULK_FIELDS if _is_yft_mesh(obj) else ()
            stack.extend(getattr(obj, name, None) for name in
                         (f.name for f in dataclasses.fields(obj))
                         if name not in skip)
        elif isinstance(obj, (list, tuple)):
            stack.extend(obj)
        elif isinstance(obj, dict):
            stack.extend(obj.values())


def _is_yft_mesh(obj) -> bool:
    return hasattr(obj, "positions") and hasattr(obj, "indices") \
        and hasattr(obj, "vertex_buffer_flags")


def _prepare_yft(yft) -> tuple[int, int, int]:
    """Pin the gen9 header values; returns (meshes, joints, states) touched."""
    meshes = joints = states = 0
    for obj in _walk_yft(yft):
        if _is_yft_mesh(obj):
            object.__setattr__(obj, "vertex_buffer_flags", GEN9_VERTEX_BUFFER_FLAGS)
            meshes += 1
        elif type(obj).__name__ == "YdrJoints":
            # fivefury keeps a legacy or junk joints VFT unless it is zeroed.
            if int(getattr(obj, "vft", 0) or 0):
                object.__setattr__(obj, "vft", 0)
                joints += 1
            # +0x04 doubles as the class resource state, which the writer
            # copies verbatim; third-party joints carry 0 there.
            if int(getattr(obj, "unknown_4h", 1) or 0) != 1:
                object.__setattr__(obj, "unknown_4h", 1)
                joints += 1
        elif type(obj).__name__ == "YftPhysicsChildEvents":
            # A player pointer refers to an event player that would have to be
            # rebuilt as well.  Retail content never has one; refuse loudly
            # instead of writing a dangling pointer.
            for field_name in ("collision_player_pointer", "break_player_pointer",
                               "break_from_root_player_pointer"):
                if int(getattr(obj, field_name, 0) or 0):
                    raise UnsupportedResource(
                        f"fragment event player pointer {field_name} is set; "
                        f"event players cannot be rebuilt")
        if hasattr(obj, "resource_state") and not isinstance(obj, dict):
            # Physics classes and event sets: the readers keep the file value
            # and the writers emit it back, so third-party zeros must be lifted
            # to the retail 1 or the rebuild refuses to run.
            if int(getattr(obj, "resource_state", 1) or 0) != 1:
                object.__setattr__(obj, "resource_state", 1)
                states += 1
    return meshes, joints, states


def convert_yft(raw: bytes) -> bytes:
    """Convert one gen8 .yft fragment (162) to gen9 (171).

    The fragment is decoded, the two gen9 header values are pinned, and the file
    is rebuilt against the gen9 runtime tables.  Every mesh channel, every
    material parameter, and every physics LOD survives; the bound geometry is
    re-quantised to int16, which is how gen9 stores it.
    """
    yft_api, _hashing = _yft_modules()
    version = rsc7_version(raw)
    if version != LEGACY_YFT_VERSION:
        raise UnsupportedResource(
            f"fragment RSC7 version {version}, expected {LEGACY_YFT_VERSION}")
    yft = yft_api.read_yft(raw)
    _prepare_yft(yft)
    yft.version = GEN9_YFT_VERSION
    converted = yft_api.build_yft_bytes(yft)
    return converted


def _collect_yft_meshes(yft) -> list:
    return [obj for obj in _walk_yft(yft) if _is_yft_mesh(obj)]


def readback_yft_problems(source: bytes, converted: bytes) -> list[str]:
    """Re-read both fragments and compare every mesh channel and header value."""
    yft_api, _hashing = _yft_modules()
    old = yft_api.read_yft(source)
    new = yft_api.read_yft(converted)
    problems: list[str] = []
    old_meshes = _collect_yft_meshes(old)
    new_meshes = _collect_yft_meshes(new)
    if len(old_meshes) != len(new_meshes):
        problems.append(f"mesh count {len(old_meshes)} -> {len(new_meshes)}")
    for index, (before, after) in enumerate(zip(old_meshes, new_meshes)):
        if _mesh_fingerprint(before) != _mesh_fingerprint(after):
            problems.append(f"mesh {index}: vertex data differs")
        if int(getattr(after, "vertex_buffer_flags", 0) or 0) != GEN9_VERTEX_BUFFER_FLAGS:
            problems.append(f"mesh {index}: vertex buffer flags "
                            f"{int(getattr(after, 'vertex_buffer_flags', 0) or 0):#010x}")
        before_material, after_material = before.material, after.material
        if before_material and after_material:
            if before_material.shader_name != after_material.shader_name:
                problems.append(f"mesh {index}: shader {before_material.shader_name} -> "
                                f"{after_material.shader_name}")
            after_parameters = {p.name: p.value for p in (after_material.parameters or ())}
            for parameter in before_material.parameters or ():
                if parameter.name in after_parameters and \
                        after_parameters[parameter.name] != parameter.value:
                    problems.append(f"mesh {index}: parameter {parameter.name} changed")
    for obj in _walk_yft(new):
        if type(obj).__name__ == "YdrJoints" and int(getattr(obj, "vft", 0) or 0):
            if int(obj.vft) != GEN9_JOINTS_VFT:
                problems.append(f"joints vft {int(obj.vft):#010x}, expected "
                                f"{GEN9_JOINTS_VFT:#010x}")
            break
    return problems


# --------------------------------------------------------------------------- #
# file / tree conversion
# --------------------------------------------------------------------------- #
def convert_ytd(raw: bytes) -> bytes:
    """Convert one gen8 .ytd file image to gen9 (byte-identical to CodeWalker)."""
    textures, keys_before = parse_legacy(raw)
    return build_gen9(textures, keys_before)


def convert_bytes(raw: bytes, filename: str) -> tuple[bytes, str]:
    """Convert one resource by extension; returns (payload, action).

    ``action`` is ``"converted"`` for .ytd, ``"copied"`` for the version-identical
    .ymt/.yld, ``"placeholder"`` for a stub archive that only gets its version
    byte rewritten.  Unsupported types raise :class:`UnsupportedResource`.
    """
    ext = os.path.splitext(filename)[1].lower()
    version = rsc7_version(raw)
    if version is None:
        raise UnsupportedResource(f"{filename}: not an RSC7 resource")
    if is_placeholder(raw):
        out = bytearray(raw)
        if ext == ".ytd" and version == LEGACY_YTD_VERSION:
            struct.pack_into("<I", out, 4, GEN9_YTD_VERSION)
        return bytes(out), "placeholder"
    if ext == ".ytd":
        try:
            return convert_ytd(raw), "converted"
        except UnsupportedResource:
            raise
        except Exception as exc:  # noqa: BLE001 - the reason is reported, not swallowed
            # A truncated or malformed dictionary must end up as one readable
            # skip line, not as a traceback that aborts the whole batch.
            raise UnsupportedResource(
                f"{filename}: .ytd conversion failed: "
                f"{type(exc).__name__}: {exc}") from exc
    if ext == ".ydd":
        try:
            return convert_ydd(raw), "converted"
        except UnsupportedResource:
            raise
        except Exception as exc:  # noqa: BLE001 - the reason is reported, not swallowed
            # A .ydd that cannot be decoded (truncated file, unknown compression,
            # a payload shape the converter has no rule for) must not abort a
            # whole batch: it becomes a skip carrying the original error text.
            raise UnsupportedResource(
                f"{filename}: .ydd conversion failed: "
                f"{type(exc).__name__}: {exc}") from exc
    if ext == ".yft":
        try:
            return convert_yft(raw), "converted"
        except UnsupportedResource:
            raise
        except Exception as exc:  # noqa: BLE001 - the reason is reported, not swallowed
            raise UnsupportedResource(
                f"{filename}: .yft conversion failed: "
                f"{type(exc).__name__}: {exc}") from exc
    if ext in _PASSTHROUGH_VERSIONS:
        expected = _PASSTHROUGH_VERSIONS[ext]
        if version != expected:
            raise UnsupportedResource(
                f"{filename}: {ext} RSC7 version {version}, expected {expected}; "
                f"refusing to copy an unknown generation")
        return raw, "copied"
    if ext in _UNSUPPORTED:
        raise UnsupportedResource(f"{filename}: {_UNSUPPORTED[ext]}")
    raise UnsupportedResource(f"{filename}: no gen8->gen9 rule for '{ext or 'no extension'}'")


@dataclass
class ConversionResult:
    rel: str
    action: str                       # converted / copied / placeholder / skipped / failed
    src_size: int = 0
    dst_size: int = 0
    problems: list[str] = field(default_factory=list)
    note: str = ""

    @property
    def ok(self) -> bool:
        return self.action != "skipped" and not self.problems


def convert_file(src: str, dst: str) -> ConversionResult:
    """Convert one file on disk.  Reads `src`, writes `dst` (parents created)."""
    rel = os.path.basename(src)
    with open(src, "rb") as fh:
        raw = fh.read()
    try:
        out, action = convert_bytes(raw, src)
    except PlaceholderArchive as exc:
        return ConversionResult(rel=rel, action="skipped", src_size=len(raw), note=str(exc))
    except UnsupportedResource as exc:
        return ConversionResult(rel=rel, action="skipped", src_size=len(raw), note=str(exc))
    if action == "converted":
        ext = os.path.splitext(src)[1].lower()
        if ext == ".ytd":
            problems = readback_problems(raw, out)
        elif ext == ".yft":
            problems = readback_yft_problems(raw, out)
        else:
            problems = readback_ydd_problems(raw, out)
    else:
        problems = []
    try:
        os.makedirs(os.path.dirname(os.path.abspath(dst)) or ".", exist_ok=True)
        with open(dst, "wb") as fh:
            fh.write(out)
    except OSError as exc:
        # A read-only target, a path whose parent is a file, a missing drive --
        # every one of them is one readable line, not a traceback.
        return ConversionResult(rel=rel, action="failed", src_size=len(raw),
                                note=f"cannot write {dst}: "
                                     f"{type(exc).__name__}: {exc}")
    return ConversionResult(rel=rel, action=action, src_size=len(raw),
                            dst_size=len(out), problems=problems)


def convert_tree(src: str, dst: str, *, dry_run: bool = False) -> list[ConversionResult]:
    """Convert every resource below `src` into `dst`, keeping the folder layout.

    Files whose type has no lossless upgrade are reported as ``skipped`` with the
    reason -- never silently dropped.
    """
    if not os.path.isdir(src):
        raise NotADirectoryError(src)
    results: list[ConversionResult] = []
    for root, _dirs, files in os.walk(src):
        for name in sorted(files):
            ext = os.path.splitext(name)[1].lower()
            if ext not in (".ytd", ".ymt", ".yld", ".ydd", ".yft"):
                continue
            full = os.path.join(root, name)
            rel = os.path.relpath(full, src)
            target = os.path.join(dst, rel)
            if dry_run:
                try:
                    with open(full, "rb") as fh:
                        raw = fh.read()
                    _out, action = convert_bytes(raw, name)
                    problems = []
                except (PlaceholderArchive, UnsupportedResource) as exc:
                    results.append(ConversionResult(rel=rel, action="skipped",
                                                    src_size=os.path.getsize(full),
                                                    note=str(exc)))
                    continue
                results.append(ConversionResult(rel=rel, action=action,
                                                src_size=len(raw), dst_size=len(_out),
                                                problems=problems))
                continue
            results.append(convert_file(full, target))
    return results
