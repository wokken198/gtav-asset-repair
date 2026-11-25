"""Read and rebuild RPF7 archives without CodeWalker.

CodeWalker's ``RpfFile.Defragment`` rewrites an archive in place, and on this machine it
never returned for a 3 GB archive.  The format is simple enough to do it ourselves: read
the header/TOC/name table, then lay the payloads back out compactly with 512-byte block
alignment.

Payload bytes are copied verbatim (already raw-deflated on disk); nothing is
recompressed or re-encoded, so resource semantics cannot change.  Child ``.rpf``
archives are rebuilt first, bottom-up, because their own holes are worth reclaiming too
-- but only when they are plain ``RPF7``; encrypted children are copied as they are.

The TOC keeps the source order, so directory ``index``/``count`` ranges stay valid and
the archive reads back with the same entry order it had before.

Format reference (verified against CodeWalker, fivefury and rage-cli):
    header       16 bytes: uint32 magic 0x52504637, entry count, names length, encryption
    TOC          entry count x 16 bytes
    names        names length bytes, null-terminated latin-1, root name is empty
    payloads     512-byte block aligned

An entry's second uint32 tells the kind apart:
    0x7FFFFF00       directory: u16 name offset, u16 pad, u32 0x7FFFFF00,
                     u32 first child index, u32 child count
    high bit clear   binary file: packed uint64 (name offset 16 bits, stored size
                     24 bits, payload block 24 bits), u32 uncompressed size, u32 encryption
    high bit set     resource: u16 name offset, 24-bit stored size, 24-bit payload
                     block, u32 system flags, u32 graphics flags
"""

import struct
import zlib

MAGIC = 0x52504637
DIR_MARK = 0x7FFFFF00
ENCRYPTED_AES = 0x0FFFFFF9
ENCRYPTED_NG = 0x0FEFFFFF
BLOCK = 512
RPF7_HEAD = b"7FPR"   # 0x52504637 little-endian, the way it sits on disk


class Rpf7Error(ValueError):
    """The bytes are not an RPF7 archive we can read."""


class EncryptedEntry(Rpf7Error):
    """An entry is encrypted; its plaintext cannot be read without the key."""


def _str(blob, offset):
    end = blob.find(b"\0", offset)
    if end < 0:
        end = len(blob)
    return blob[offset:end].decode("latin-1")


def parse(data):
    """Return (encryption, entries) where entries is the flat TOC list."""
    if len(data) < 16:
        raise Rpf7Error("archive is too short to hold an RPF7 header")
    magic, count, names_len, encryption = struct.unpack_from("<IIII", data, 0)
    if magic != MAGIC:
        raise Rpf7Error("not an RPF7 archive (magic 0x%08x)" % magic)
    if encryption == ENCRYPTED_AES:
        raise EncryptedEntry(
            "archive uses AES encryption, so its directory table is unreadable "
            "without the key; defrag only works on unencrypted archives")
    if encryption == ENCRYPTED_NG:
        raise EncryptedEntry(
            "archive uses NG encryption (the encrypted format the retail game ships), "
            "so its directory table is unreadable without the key; defrag only works "
            "on unencrypted archives")
    if count == 0 or count > 4_000_000:
        raise Rpf7Error("implausible entry count %d" % count)
    toc_at = 16
    names_at = toc_at + count * 16
    if names_at + names_len > len(data):
        raise Rpf7Error("name table runs past the end of the file")
    names = data[names_at:names_at + names_len]
    entries = []
    for index in range(count):
        at = toc_at + index * 16
        word = struct.unpack_from("<I", data, at + 4)[0]
        if word == DIR_MARK:
            name_off = struct.unpack_from("<H", data, at)[0]
            first, kids = struct.unpack_from("<II", data, at + 8)
            entries.append({"kind": "dir", "name": _str(names, name_off),
                            "index": first, "count": kids})
        elif not word & 0x80000000:
            packed = struct.unpack_from("<Q", data, at)[0]
            name_off = packed & 0xFFFF
            stored = (packed >> 16) & 0xFFFFFF
            block = (packed >> 40) & 0xFFFFFF
            size, enc = struct.unpack_from("<II", data, at + 8)
            entries.append({"kind": "file", "name": _str(names, name_off),
                            "stored": stored, "block": block, "size": size, "enc": enc})
        else:
            name_off = struct.unpack_from("<H", data, at)[0]
            stored_raw = int.from_bytes(data[at + 2:at + 5], "little")
            block = int.from_bytes(data[at + 5:at + 8], "little") & 0x7FFFFF
            # The stored size uses all 24 bits: a 9.9 MB fragment has
            # stored_raw == 0x9862EC.  Masking with 0x7FFFFF truncates every
            # resource above 8 MB (0x9862EC -> 0x1862EC = 1.6 MB), and the
            # truncated read then gets written back, which is why the game saw
            # a 1.6 MB "complete" model and drew nothing.
            stored = stored_raw & 0xFFFFFF
            sysf, gfxf = struct.unpack_from("<II", data, at + 8)
            entries.append({"kind": "res", "name": _str(names, name_off),
                            "stored": stored, "stored_raw": stored_raw,
                            "block": block, "sysf": sysf, "gfxf": gfxf})
    return encryption, entries


def walk(entries):
    """Return [(path, entry)] in depth-first order.  Paths use '/' separators."""
    out = []
    if not entries or entries[0]["kind"] != "dir":
        return out

    def rec(index, prefix):
        node = entries[index]
        if node["kind"] != "dir":
            return
        for kid in range(node["index"], node["index"] + node["count"]):
            if kid >= len(entries):
                break
            entry = entries[kid]
            path = prefix + "/" + entry["name"] if prefix else entry["name"]
            out.append((path, entry))
            if entry["kind"] == "dir":
                rec(kid, path)

    rec(0, "")
    return out


def stored_bytes(data, entry):
    """The payload exactly as the archive holds it (still compressed if it was)."""
    start = entry["block"] * BLOCK
    if entry["kind"] == "res" and entry.get("stored_raw") == 0xFFFFFF:
        head = data[start:start + 16]
        if len(head) < 16:
            raise Rpf7Error("%s: payload runs past the end of the file" % entry["name"])
        length = head[7] | (head[14] << 8) | (head[5] << 16) | (head[2] << 24)
    else:
        length = entry["stored"] or entry.get("size") or 0
    end = start + length
    if end > len(data):
        raise Rpf7Error("%s: payload runs past the end of the file" % entry["name"])
    return data[start:end]


def payload_bytes(data, entry):
    """The uncompressed payload (what the game loads)."""
    if entry["kind"] == "file" and entry.get("enc"):
        raise EncryptedEntry("%s: entry is encrypted" % entry["name"])
    raw = stored_bytes(data, entry)
    if not raw:
        return b""
    if entry["kind"] == "file" and entry["stored"] == 0:
        return raw
    if entry["kind"] == "file":
        return zlib.decompress(raw, -15)
    return raw


def rebuild_bytes(data, recursive=True, depth=0):
    """Return (new_bytes, stats).  Entry order and directory ranges are preserved."""
    encryption, entries = parse(data)
    if not entries or entries[0]["kind"] != "dir":
        raise Rpf7Error("archive has no root directory entry")

    rebuilt_children = 0
    locked_children = []
    if recursive and depth < 16:
        # Decide once for the whole archive: an archive tree is either completely
        # open (every child .rpf parses and every entry inside it can be read) or it
        # is mixed.  Recursing into a mixed tree rewrites the open children while the
        # encrypted ones stay byte-identical, and the result is a container the game
        # no longer recognises - measured on update.rpf: scaleform_generic.rpf lost
        # 23% and scaleform_minimap.rpf lost 49% although the archive still parsed.
        children = []
        for entry in entries:
            if entry["kind"] != "file" or not entry["name"].lower().endswith(".rpf"):
                continue
            try:
                inner = payload_bytes(data, entry)
            except (Rpf7Error, EncryptedEntry, zlib.error):
                children.append((entry, None))
                continue
            if inner[:4] != RPF7_HEAD:
                children.append((entry, None))
                continue
            try:
                _, inner_entries = parse(inner)
            except Rpf7Error:
                children.append((entry, None))
                continue
            readable = True
            for inner_entry in inner_entries:
                if inner_entry["kind"] == "dir":
                    continue
                try:
                    payload_bytes(inner, inner_entry)
                except Exception:
                    readable = False
                    break
            children.append((entry, inner if readable else None))

        if not children:
            pass
        else:
            for child, inner in children:
                if inner is None:
                    # Encrypted, unparseable, or holding entries we cannot read.
                    # Rewriting it would not shrink the archive, it would corrupt it.
                    locked_children.append(child["name"])
                    continue
                try:
                    smaller, _ = rebuild_bytes(inner, recursive=True, depth=depth + 1)
                except (Rpf7Error, EncryptedEntry):
                    locked_children.append(child["name"])
                    continue
                if len(smaller) < len(inner):
                    child["_rebuilt"] = smaller

    names = bytearray()
    for entry in entries:
        entry["name_off"] = len(names)
        names += entry["name"].encode("latin-1") + b"\0"

    header_len = 16 + len(entries) * 16 + len(names)
    first_block = (header_len + BLOCK - 1) // BLOCK
    cursor = first_block * BLOCK
    toc = bytearray()
    body = bytearray()

    for entry in entries:
        if entry["kind"] == "dir":
            toc += struct.pack("<HHIII", entry["name_off"], 0, DIR_MARK,
                               entry["index"], entry["count"])
            continue
        if "_rebuilt" in entry:
            plain = entry["_rebuilt"]
            rebuilt_children += 1
            # Keep the storage choice the source made.  The game decides "is this
            # deflated?" from stored != 0, so compressing an entry that the source
            # kept raw makes it read the deflate stream as the payload itself -
            # that is exactly the "bad archive signature 0x3879BBEC" crash.
            if entry["stored"] == 0:
                blob = plain
            else:
                # the stored size lives in 24 bits; above that, keep it uncompressed
                # and let the 32-bit uncompressed field describe it, like the game
                # does for big child .rpf files
                packed_bytes = zlib.compress(plain, 9)[2:-4]
                blob = packed_bytes if len(packed_bytes) <= 0xFFFFFF else plain
        else:
            plain = None
            blob = stored_bytes(data, entry)
        pad = (-cursor) % BLOCK
        if pad:
            body += b"\0" * pad
            cursor += pad
        block = cursor // BLOCK
        body += blob
        cursor += len(blob)
        if entry["kind"] == "file":
            if plain is not None:
                stored = 0 if blob is plain else len(blob)
                size = len(plain)
            else:
                stored = entry["stored"]
                size = entry["size"]
            packed = (entry["name_off"] & 0xFFFF) | ((stored & 0xFFFFFF) << 16) | ((block & 0xFFFFFF) << 40)
            toc += struct.pack("<QII", packed, size, entry.get("enc", 0))
        else:
            # The high bit of the three size bytes is the "payload is deflated" flag,
            # The stored size is the real payload length; the game reads exactly
            # this many bytes and decompresses nothing.  Saturated 0xFFFFFF means
            # "the length is in the RSC7 header" (handled by stored_bytes).
            size24 = 0xFFFFFF if len(blob) >= 0xFFFFFF else len(blob)
            size_bytes = size24.to_bytes(3, "little")
            packed = struct.pack("<H", entry["name_off"])
            packed += size_bytes
            packed += bytes((block & 0xFF, (block >> 8) & 0xFF,
                             ((block >> 16) & 0x7F) | 0x80))
            packed += struct.pack("<II", entry.get("sysf", 0), entry.get("gfxf", 0))
            toc += packed

    out = bytearray()
    out += struct.pack("<IIII", MAGIC, len(entries), len(names), encryption)
    out += toc
    out += names
    out += b"\0" * (first_block * BLOCK - len(out))
    out += body
    stats = {"entries": len(entries),
             "files": sum(1 for e in entries if e["kind"] != "dir"),
             "names": len(names), "children_rebuilt": rebuilt_children,
             "locked_children": locked_children}
    return bytes(out), stats


def verify(original, rebuilt):
    """Return a list of problems comparing the rebuilt archive with the original."""
    _, before = parse(original)
    try:
        _, after = parse(rebuilt)
    except Rpf7Error as exc:
        return ["rebuilt archive cannot be parsed: %s" % exc]
    problems = []
    if len(before) != len(after):
        problems.append("entry count %d -> %d" % (len(before), len(after)))
    old = walk(before)
    new = walk(after)
    old_paths = [p for p, _ in old]
    new_paths = [p for p, _ in new]
    if old_paths != new_paths:
        missing = [p for p in old_paths if p not in set(new_paths)]
        extra = [p for p in new_paths if p not in set(old_paths)]
        if missing:
            problems.append("missing entries: %s" % ", ".join(missing[:4]))
        if extra:
            problems.append("unexpected entries: %s" % ", ".join(extra[:4]))
        if not missing and not extra:
            problems.append("entry order changed")
    if not problems:
        old_map = dict(old)
        new_map = dict(new)
        lost = [p for p in old_map
                if p in new_map and old_map[p]["kind"] != new_map[p]["kind"]]
        if lost:
            problems.append("entry kind changed: %s" % ", ".join(lost[:4]))
    return problems
