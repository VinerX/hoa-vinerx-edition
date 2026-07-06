#!/usr/bin/env python3
"""
convert.py — resize arbitrary PNG/JPG images into HOI4-ready .dds sprites.

No external binaries required: uses Pillow's built-in DXT (BC1/BC3) encoder.

Presets carry the exact canvas sizes used by Hearts of Azeroth:
    focus    88 x 88    -> gfx/interface/focus_tree/
    leader   156 x 210  -> gfx/leaders/<TAG>/
    idea     64 x 64     -> gfx/interface/ideas/
    advisor  65 x 67     -> gfx/interface/advisors/

Usage:
    python convert.py <preset> <input> [--out DIR] [--fit cover|contain]
                      [--format DXT5|DXT1] [--suffix STR]

    <input> can be a single file, a directory, or a glob (e.g. "raw/*.png").

Examples:
    python convert.py leader raw_portraits/ --out out/leaders
    python convert.py focus "raw/*.png" --out out/focus --fit contain
    python convert.py idea raw/alliance.png --out out/ideas

Fit modes:
    cover   (default) scale to fill the canvas, center-crop overflow.
            Best for portraits where you want the whole frame filled.
    contain scale to fit inside the canvas, pad the rest with transparency.
            Best for icons/logos that must not be cropped.
"""
import argparse
import glob
import os
import sys

from PIL import Image

PRESETS = {
    "focus":   (88, 88),
    "leader":  (156, 210),
    "idea":    (64, 64),
    "advisor": (65, 67),
}

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".dds", ".tga")


def collect_inputs(arg):
    if os.path.isdir(arg):
        files = []
        for e in EXTS:
            files += glob.glob(os.path.join(arg, "*" + e))
            files += glob.glob(os.path.join(arg, "*" + e.upper()))
        return sorted(set(files))
    if any(ch in arg for ch in "*?[]"):
        return sorted(glob.glob(arg))
    return [arg] if os.path.isfile(arg) else []


def fit_cover(im, size, vbias=0.5):
    """vbias: vertical crop anchor, 0.0 = keep top, 0.5 = center, 1.0 = bottom.
    Use a low value (e.g. 0.25) for portraits so faces/heads aren't cut off."""
    tw, th = size
    sw, sh = im.size
    scale = max(tw / sw, th / sh)
    nw, nh = round(sw * scale), round(sh * scale)
    im = im.resize((nw, nh), Image.LANCZOS)
    left = (nw - tw) // 2
    top = round((nh - th) * vbias)
    return im.crop((left, top, left + tw, top + th))


def fit_contain(im, size):
    tw, th = size
    sw, sh = im.size
    scale = min(tw / sw, th / sh)
    nw, nh = max(1, round(sw * scale)), max(1, round(sh * scale))
    im = im.resize((nw, nh), Image.LANCZOS)
    canvas = Image.new("RGBA", size, (0, 0, 0, 0))
    canvas.paste(im, ((tw - nw) // 2, (th - nh) // 2), im)
    return canvas


def main():
    ap = argparse.ArgumentParser(description="Convert images to HOI4 .dds sprites.")
    ap.add_argument("preset", choices=list(PRESETS) + ["custom"])
    ap.add_argument("input", help="file, directory, or glob")
    ap.add_argument("--out", default="out", help="output directory (default: out)")
    ap.add_argument("--fit", choices=["cover", "contain"], default="cover")
    ap.add_argument("--format", dest="fmt", choices=["DXT5", "DXT1"], default="DXT5",
                    help="DXT5 keeps alpha (default); DXT1 = smaller, 1-bit alpha")
    ap.add_argument("--size", help="WxH for --preset custom, e.g. 120x120")
    ap.add_argument("--suffix", default="", help="append to output filename stem")
    ap.add_argument("--anchor", default="center",
                    help="vertical crop anchor for --fit cover: top|center|bottom "
                         "or a 0.0-1.0 fraction (default: center)")
    ap.add_argument("--focus-top", dest="focus_top", action="store_true",
                    help="shortcut for --anchor 0.25: bias crop toward the head "
                         "so portraits don't lose the top of the skull")
    args = ap.parse_args()

    anchor_words = {"top": 0.0, "center": 0.5, "bottom": 1.0}
    if args.focus_top:
        vbias = 0.25
    elif args.anchor in anchor_words:
        vbias = anchor_words[args.anchor]
    else:
        try:
            vbias = max(0.0, min(1.0, float(args.anchor)))
        except ValueError:
            sys.exit("--anchor must be top|center|bottom or a 0.0-1.0 number")

    if args.preset == "custom":
        if not args.size:
            sys.exit("custom preset needs --size WxH")
        w, h = args.size.lower().split("x")
        size = (int(w), int(h))
    else:
        size = PRESETS[args.preset]

    files = collect_inputs(args.input)
    if not files:
        sys.exit(f"no input images matched: {args.input}")

    os.makedirs(args.out, exist_ok=True)
    fit = fit_cover if args.fit == "cover" else fit_contain

    ok = 0
    for f in files:
        try:
            im = Image.open(f).convert("RGBA")
            im = fit(im, size, vbias) if fit is fit_cover else fit(im, size)
            stem = os.path.splitext(os.path.basename(f))[0] + args.suffix
            dst = os.path.join(args.out, stem + ".dds")
            im.save(dst, pixel_format=args.fmt)
            print(f"  {os.path.basename(f)}  ->  {stem}.dds  {size[0]}x{size[1]} {args.fmt}")
            ok += 1
        except Exception as e:
            print(f"  !! {os.path.basename(f)}: {e}", file=sys.stderr)

    print(f"\nDone: {ok}/{len(files)} -> {args.out}")


if __name__ == "__main__":
    main()
