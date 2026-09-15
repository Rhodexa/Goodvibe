"""Repack scratch_src/ back into ../project.sb3 (asset files + project.json only)."""
import os
import zipfile

EXCLUDE_EXT = {".py"}
EXCLUDE_NAMES = {"project.json.orig", "__pycache__"}

here = os.path.dirname(os.path.abspath(__file__))
out = os.path.join(here, "..", "project.sb3")

files = []
for name in sorted(os.listdir(here)):
    if name in EXCLUDE_NAMES:
        continue
    if os.path.splitext(name)[1] in EXCLUDE_EXT:
        continue
    path = os.path.join(here, name)
    if os.path.isfile(path):
        files.append(name)

assert "project.json" in files

with zipfile.ZipFile(out, "w", zipfile.ZIP_DEFLATED) as zf:
    for name in files:
        zf.write(os.path.join(here, name), name)

print(f"wrote {out} with {len(files)} files")
