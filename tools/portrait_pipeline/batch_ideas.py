#!/usr/bin/env python3
"""
batch_ideas.py - cut generated icon sheets into named HOI4 idea icons.

Workflow:
1. Prepare a manifest JSON with sheet path, grid size, and slot mapping.
2. Generate one or more contact sheets with icons arranged by slots.
3. Run this script to crop each slot, convert to final 64x64-safe idea icons,
   and emit named DDS + PNG preview files.
"""
import argparse
import json
import os
import sys
from pathlib import Path

from PIL import Image

import convert


def load_manifest(path):
    with open(path, "r", encoding="utf-8") as fh:
        return json.load(fh)


def normalize_slot(slot, cols):
    if isinstance(slot, int):
        if slot < 1:
            raise ValueError("slot numbers are 1-based")
        slot -= 1
        return slot // cols, slot % cols
    if isinstance(slot, str):
        text = slot.strip()
        if "," in text:
            row_text, col_text = text.split(",", 1)
            return int(row_text), int(col_text)
    if isinstance(slot, (list, tuple)) and len(slot) == 2:
        return int(slot[0]), int(slot[1])
    raise ValueError(f"unsupported slot format: {slot!r}")


def crop_slot(sheet, row, col, rows, cols):
    width, height = sheet.size
    cell_w = width // cols
    cell_h = height // rows
    left = col * cell_w
    top = row * cell_h
    return sheet.crop((left, top, left + cell_w, top + cell_h))


def convert_idea_icon(src_path, out_dir, stem, safe_pad):
    im = Image.open(src_path).convert("RGBA")
    im = convert.fit_contain(im, convert.PRESETS["idea"])
    if safe_pad:
        im = convert.add_safe_padding(im, safe_pad)

    dds_path = out_dir / f"{stem}.dds"
    png_path = out_dir / f"{stem}.png"
    crop_path = out_dir / f"{stem}__crop.png"

    im.save(dds_path, pixel_format="DXT5")
    im.save(png_path)
    return crop_path, png_path, dds_path


def process_batch(manifest_path, out_dir):
    manifest = load_manifest(manifest_path)
    sheet_path = Path(manifest["sheet"])
    rows = int(manifest["grid"]["rows"])
    cols = int(manifest["grid"]["cols"])
    safe_pad = int(manifest.get("safe_pad", convert.SAFE_PADDING["idea"]))
    prefix = manifest.get("prefix", "")

    if not sheet_path.is_file():
        sys.exit(f"sheet not found: {sheet_path}")

    out_dir.mkdir(parents=True, exist_ok=True)
    temp_dir = out_dir / "_tmp_crops"
    temp_dir.mkdir(parents=True, exist_ok=True)

    sheet = Image.open(sheet_path).convert("RGBA")
    written = []

    for item in manifest["items"]:
        row, col = normalize_slot(item["slot"], cols)
        crop = crop_slot(sheet, row, col, rows, cols)
        stem = prefix + item["name"]
        crop_path = temp_dir / f"{stem}__crop.png"
        crop.save(crop_path)
        _, png_path, dds_path = convert_idea_icon(crop_path, out_dir, stem, safe_pad)
        written.append((item["slot"], stem, png_path.name, dds_path.name))

    return written


def write_template(path):
    template = {
        "sheet": "C:/path/to/generated_sheet.png",
        "grid": {"rows": 2, "cols": 3},
        "safe_pad": 8,
        "prefix": "AMA_",
        "items": [
            {"slot": 1, "name": "sw_loa_blessings_idea"},
            {"slot": 2, "name": "sw_spirit_guardians_idea"},
            {"slot": 3, "name": "sw_rangers_nightmare_idea"},
            {"slot": 4, "name": "sw_hex_warfare_idea"},
            {"slot": 5, "name": "sw_blessed_axes_idea"},
            {"slot": 6, "name": "sw_eternal_hatred_idea"},
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(template, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser(description="Batch cut contact sheets into HOI4 idea icons.")
    ap.add_argument("manifest", nargs="?", help="path to manifest JSON")
    ap.add_argument("--out", default="out_batch_ideas", help="output directory")
    ap.add_argument("--write-template", help="write a manifest template JSON and exit")
    args = ap.parse_args()

    if args.write_template:
        write_template(args.write_template)
        print(f"Template written: {args.write_template}")
        return

    if not args.manifest:
        sys.exit("manifest path is required unless --write-template is used")

    written = process_batch(Path(args.manifest), Path(args.out))
    for slot, stem, png_name, dds_name in written:
        print(f"slot {slot} -> {stem} ({png_name}, {dds_name})")
    print(f"\nDone: {len(written)} idea icons -> {args.out}")


if __name__ == "__main__":
    main()
