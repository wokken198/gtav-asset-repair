"""Compact an .rpf container so the space freed by texture compression reaches disk.

Compression only shrinks what the game loads into memory; the archive keeps its old
size until something rewrites its page layout.  OpenIV calls that "Defrag", and this
is the same thing: no entry content changes, only the container is repacked tight.

The write path is a pure-Python RPF7 reader/writer (``rpf7.py``), verified byte for
byte against rage-cli and CodeWalker's ``Defragment`` on three archives.  CodeWalker is
not needed.
"""
import os
import shutil
import time

from . import rpf7, settings

BACKUP_LIMIT = 500 * 1024 * 1024


class Report:
    """What one defrag pass did, kept as fields so callers can lay it out."""

    __slots__ = ("leaf", "before", "after", "pct", "ms", "entries", "children",
                 "locked", "recursive", "raw")

    def __init__(self, leaf, before, after, pct, ms, entries, children, recursive,
                 raw="", locked=0):
        self.leaf = leaf
        self.before = before
        self.after = after
        self.pct = pct
        self.ms = ms
        self.entries = entries
        self.children = children
        self.locked = locked
        self.recursive = recursive
        self.raw = raw

    @property
    def saved(self):
        return self.before - self.after

    def __str__(self):
        if self.raw:
            return self.raw
        tail = ", children %d" % self.children
        if self.locked:
            # A mixed tree keeps every child exactly as it was; without this note the
            # 0.0% result reads like a bug instead of the safety rule doing its job.
            tail += " (%d child archive(s) left untouched: the tree contains encrypted or unreadable children)" % self.locked
        return ("%s: %d -> %d bytes (%.1f%%) in %d ms, entries %d%s, "
                "recursive %s" % (self.leaf, self.before, self.after, self.pct, self.ms,
                                  self.entries, tail, self.recursive))


def defrag(path, out="", dry_run=False, recursive=True):
    """Rewrite the archive compactly; returns a Report.  ``dry_run`` only measures.

    Child .rpf archives are rebuilt first so their own holes go away too.  The new
    bytes are verified against the source before they replace it, and the write goes
    through a ``.new`` sibling so an interrupted run never leaves a half archive.
    """
    path = os.path.abspath(path)
    if not os.path.isfile(path):
        raise RuntimeError("%s: no such file" % path)
    if not (os.stat(path).st_mode & 0o200):
        raise RuntimeError("%s is read-only; clear the attribute before defragmenting"
                           % os.path.basename(path))
    with open(path, "rb") as fh:
        data = fh.read()
    before = len(data)
    name = os.path.basename(path)
    if dry_run:
        encryption, entries = rpf7.parse(data)
        items = rpf7.walk(entries)
        files = sum(1 for _, entry in items if entry["kind"] != "dir")
        raw = "%s: %d entries, %d file(s), %s; a defrag compacts the payload" % (
            name, len(entries), files, "recurse" if recursive else "no recursion")
        return Report(name, before, before, 0.0, 0, len(entries), files, recursive, raw)
    start = time.time()
    new, stats = rpf7.rebuild_bytes(data, recursive=recursive)
    problems = rpf7.verify(data, new)
    if problems:
        raise RuntimeError("the rebuilt archive does not match the source: "
                           + "; ".join(problems))
    target = out or path
    tmp = target + ".new"
    try:
        with open(tmp, "wb") as fh:
            fh.write(new)
        os.replace(tmp, target)
    except BaseException:
        if os.path.exists(tmp):
            os.remove(tmp)
        raise
    pct = (len(new) - before) * 100.0 / before if before else 0.0
    return Report(name, before, len(new), pct, int((time.time() - start) * 1000),
                  stats["entries"], stats["children_rebuilt"], recursive,
                  locked=len(stats["locked_children"]))


def backup(path, limit=BACKUP_LIMIT):
    """Keep a copy next to the archive; returns its path, or '' when it is too big."""
    size = os.path.getsize(path)
    if size > limit:
        return ""
    if not settings.keep_bak():
        return ""
    dst = path + ".bak"
    if not os.path.exists(dst):
        shutil.copy2(path, dst)
    return dst
