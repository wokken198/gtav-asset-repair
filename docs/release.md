# Release checklist

Text-only steps first, build last: the build is the only part that pins the CPU for a couple of
minutes, so everything that can fail early is checked before it starts.

## 1. Before building

```bash
python -m unittest discover -s tests -q      # expect: Ran 45 tests, OK
node --check dsh-plugin/index.js             # syntax only; use the bundled node if PATH has none
python -m json.tool dsh-plugin/package.json > /dev/null
python -m json.tool dsh-plugin/locale/en.json > /dev/null
python -m json.tool dsh-plugin/locale/zh.json > /dev/null
```

- `gui.VERSION`, `pyproject.toml` and `dsh-plugin/package.json` must carry the same version.
- `CHANGELOG.md` has a section for that version.
- `dsh-plugin/vendor/gtatools/*.py` is byte-identical to `src/gtatools/*.py`
  (`diff -r src/gtatools dsh-plugin/vendor/gtatools`).
- `tests/_tmp` does not exist any more; the test run recreates it, so delete it last.

## 2. Build

```bash
pyinstaller --noconfirm --clean --onedir --windowed --name gtatools \
  --icon resources/gtatools.ico \
  --add-binary "texconv.exe;." \
  --add-data "resources;resources" \
  --paths src --hidden-import PIL.ImageTk packaging/gui_entry.py
```

Then zip `dist/gtatools` (the folder, not just the exe) as `gtatools-portable.zip`.

The one-file variant is optional and only useful for people who keep it somewhere writable:

```bash
pyinstaller --noconfirm --clean --onefile --windowed --name gtatools --runtime-tmpdir . \
  --icon resources/gtatools.ico --add-binary "texconv.exe;." \
  --add-data "resources;resources" --paths src --hidden-import PIL.ImageTk packaging/gui_entry.py
```

## 3. Smoke test the packaged build

- start it, check the window title carries the version
- switch to English and back: navigation width must not move, both switches must stay visible
- open each of the four pages once
- compress one `.ytd` with a copy on hand and confirm `*.ytd.bak` appears
- `ped check` on a folder of pairs: rows either green or red, never blank

## 4. Publish

Only after the smoke test, and only when asked: push the tree, re-pin `market/index.json` to the new
commit, tag `vX.Y.Z`, create the release, then verify the badge on CI.
