#!/usr/bin/env python3
"""
batch_icons.py - cut generated icon sheets into named HOI4 UI sprites.

Supports any preset from convert.py (focus, idea, advisor, leader, custom).
Useful when an image model returns a contact sheet and you want reproducible
slot-based slicing into final DDS files.
"""
import argparse
import json
import sys
from pathlib import Path

from PIL import Image

import convert


def load_manifest(path):
    with open(path, "r", encoding="utf-8-sig") as fh:
        return json.load(fh)


def normalize_slot(slot, cols):
    if isinstance(slot, int):
        if slot < 1:
            raise ValueError("slot numbers are 1-based")
        idx = slot - 1
        return idx // cols, idx % cols
    if isinstance(slot, str) and "," in slot:
        row_text, col_text = slot.split(",", 1)
        return int(row_text.strip()), int(col_text.strip())
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


def resolve_size(manifest):
    preset = manifest["preset"]
    if preset == "custom":
        size = manifest.get("size")
        if not size:
            sys.exit("custom preset requires size in manifest")
        width, height = size.lower().split("x")
        return preset, (int(width), int(height))
    return preset, convert.PRESETS[preset]


def render_icon(crop, preset, size, fit, vbias, safe_pad, focus_mask, mask_feather):
    if fit == "cover":
        out = convert.fit_cover(crop, size, vbias)
    else:
        out = convert.fit_contain(crop, size)
    if safe_pad:
        out = convert.add_safe_padding(out, safe_pad)
    if preset == "focus" and focus_mask != "none":
        out = convert.apply_focus_mask(out, focus_mask, mask_feather)
    return out


def process_manifest(manifest_path, out_dir):
    manifest = load_manifest(manifest_path)
    preset, size = resolve_size(manifest)
    fit = manifest.get("fit", "contain")
    safe_pad = int(manifest.get("safe_pad", convert.SAFE_PADDING.get(preset, 0)))
    fmt = manifest.get("format", "DXT5")
    preview_png = bool(manifest.get("preview_png", True))
    prefix = manifest.get("prefix", "")
    vbias = convert.parse_anchor(manifest.get("anchor", "center"), False)
    focus_mask = manifest.get("focus_mask", "none")
    mask_feather = float(manifest.get("mask_feather", 1.5))
    use_texconv = bool(manifest.get("texconv", False))
    texconv_path = manifest.get("texconv_path", convert.TEXCONV_DEFAULT)
    texconv_format = manifest.get("texconv_format", fmt)
    mip_levels = int(manifest.get("mip_levels", 1))
    chroma_key = manifest.get("chroma_key")
    chroma_threshold = float(manifest.get("chroma_threshold", 0.10))
    chroma_softness = float(manifest.get("chroma_softness", 0.03))
    despill = float(manifest.get("despill", 0.75))
    chroma_rgb = convert.parse_hex_color(chroma_key) if chroma_key else None

    sheet_path = Path(manifest["sheet"])
    if not sheet_path.is_file():
        sys.exit(f"sheet not found: {sheet_path}")

    rows = int(manifest["grid"]["rows"])
    cols = int(manifest["grid"]["cols"])
    out_dir.mkdir(parents=True, exist_ok=True)
    tmp_dir = out_dir / "_tmp_crops"
    tmp_dir.mkdir(parents=True, exist_ok=True)

    sheet = Image.open(sheet_path).convert("RGBA")
    written = []

    for item in manifest["items"]:
        row, col = normalize_slot(item["slot"], cols)
        crop = crop_slot(sheet, row, col, rows, cols)
        if chroma_rgb:
            crop = convert.apply_chroma_key(
                crop,
                chroma_rgb,
                chroma_threshold,
                chroma_softness,
                despill,
            )
        stem = prefix + item["name"]
        crop_path = tmp_dir / f"{stem}__crop.png"
        crop.save(crop_path)

        final = render_icon(crop, preset, size, fit, vbias, safe_pad, focus_mask, mask_feather)
        dds_path = out_dir / f"{stem}.dds"
        if use_texconv:
            convert.save_with_texconv(final, str(dds_path), texconv_path, texconv_format, mip_levels)
        else:
            final.save(dds_path, pixel_format=fmt)
        if preview_png:
            final.save(out_dir / f"{stem}.png")
        written.append((item["slot"], stem, dds_path.name))

    return written


def write_template(path):
    template = {
        "sheet": "C:/path/to/generated_sheet.png",
        "preset": "focus",
        "grid": {"rows": 2, "cols": 4},
        "fit": "contain",
        "safe_pad": 8,
        "focus_mask": "medallion",
        "mask_feather": 1.5,
        "format": "DXT5",
        "texconv": True,
        "texconv_format": "DXT1",
        "mip_levels": 1,
        "chroma_key": "#00FFF0",
        "chroma_threshold": 0.10,
        "chroma_softness": 0.03,
        "despill": 0.75,
        "preview_png": True,
        "prefix": "GNO_",
        "items": [
            {"slot": 1, "name": "sw_mekkatorque_workshop"},
            {"slot": 2, "name": "sw_iron_gate_preparations"},
            {"slot": 3, "name": "sw_mechanical_defenses"},
            {"slot": 4, "name": "sw_gnomish_ingenuity"},
        ],
    }
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(template, fh, ensure_ascii=False, indent=2)
        fh.write("\n")


def main():
    ap = argparse.ArgumentParser(description="Batch cut contact sheets into HOI4 UI icons.")
    ap.add_argument("manifest", nargs="?", help="path to manifest JSON")
    ap.add_argument("--out", default="out_batch_icons", help="output directory")
    ap.add_argument("--write-template", help="write a manifest template JSON and exit")
    args = ap.parse_args()

    if args.write_template:
        write_template(args.write_template)
        print(f"Template written: {args.write_template}")
        return
    if not args.manifest:
        sys.exit("manifest path is required unless --write-template is used")

    written = process_manifest(Path(args.manifest), Path(args.out))
    for slot, stem, dds_name in written:
        print(f"slot {slot} -> {stem} ({dds_name})")
    print(f"\nDone: {len(written)} icons -> {args.out}")


if __name__ == "__main__":
    main()
