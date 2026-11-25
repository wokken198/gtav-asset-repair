"""Copy src/gtav_asset_repair into dsh-plugin/vendor/gtav_asset_repair.

The DSH plugin is a standalone npm package, so it has to ship its own copy of
the Python package (index.js runs `python -m gtav_asset_repair.cli` with
PYTHONPATH pointing at the vendored tree).  That copy includes the 470-file
fivefury build, and keeping both trees in git means every release uploads the
same bytes twice.

Only `src/` is under version control for that reason; run this script before
`npm pack` / before creating the release zip, so the plugin bundle is complete.

    python packaging/sync_plugin.py
"""

import os
import shutil

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
SRC = os.path.join(ROOT, "src", "gtav_asset_repair")
DST = os.path.join(ROOT, "dsh-plugin", "vendor", "gtav_asset_repair")


def main():
    if not os.path.isdir(SRC):
        raise SystemExit("source package not found: %s" % SRC)
    if os.path.isdir(DST):
        shutil.rmtree(DST)
    shutil.copytree(SRC, DST, ignore=shutil.ignore_patterns("__pycache__", "*.pyc"))
    total = sum(len(files) for _, _, files in os.walk(DST))
    print("synced %d file(s) -> %s" % (total, DST))


if __name__ == "__main__":
    main()
