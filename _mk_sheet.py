import os, sys
sys.path.insert(0, "src")
from PIL import Image, ImageDraw, ImageFont
from gtav_asset_repair import normals

SRC = "docs/sample"
OUT = "docs/images/sample-compare.png"
NAMES = ["sample_emblem_a", "sample_emblem_b", "sample_emblem_c"]
CELL_W, CELL_H = 320, 200
PAD = 6
HEAD = 26

def font(sz):
    for n in ("segoeui.ttf", "arial.ttf"):
        try:
            return ImageFont.truetype(n, sz)
        except Exception:
            pass
    return ImageFont.load_default()

f_head = font(14)
f_tag = font(13)

rows = []
for name in NAMES:
    p = os.path.join(SRC, name + ".dds")
    tmp = os.path.join("_sheet_tmp", name + ".png")
    os.makedirs("_sheet_tmp", exist_ok=True)
    from gtav_asset_repair import dds as ddsmod
    ddsmod.decode("_sheet_tmp", [p], "texconv.exe")
    rgba = normals.load_rgba(tmp)
    h = normals.height_field(rgba, blur=1.2)
    n = normals.normal_from_height(h, strength=6.5)
    bg = Image.new("RGBA", Image.open(tmp).size, (255, 255, 255, 255))
    bg.alpha_composite(Image.open(tmp).convert("RGBA"))
    lit = (normals.shade_preview(rgba, n) * 255).astype("uint8")
    rows.append((name, bg.convert("RGB"), Image.fromarray(n), Image.fromarray(lit)))

W = PAD + 3 * (CELL_W + PAD)
H = HEAD + len(rows) * (CELL_H + 24 + PAD)
sheet = Image.new("RGB", (W, H), (26, 26, 26))
d = ImageDraw.Draw(sheet)
titles = ["diffuse", "generated normal", "diffuse + normal"]
for i, t in enumerate(titles):
    d.text((PAD + i * (CELL_W + PAD) + 4, 7), t, font=f_head, fill=(200, 200, 200))

y = HEAD
for name, diff, nrm, lit in rows:
    for i, im in enumerate((diff, nrm, lit)):
        box = (PAD + i * (CELL_W + PAD), y)
        sheet.paste(im.resize((CELL_W, CELL_H), Image.LANCZOS), box)
    d.text((PAD + 4, y + CELL_H + 4), name, font=f_tag, fill=(150, 150, 150))
    y += CELL_H + 24 + PAD

sheet.save(OUT)
print("saved", OUT, sheet.size)
