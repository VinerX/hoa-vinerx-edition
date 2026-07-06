#!/usr/bin/env python3
"""
convert.py - resize arbitrary PNG/JPG images into HOI4-ready .dds sprites.

No external binaries required: uses Pillow's built-in DXT (BC1/BC3) encoder.

Presets carry the exact canvas sizes used by Hearts of Azeroth:
    focus    88 x 88    -> gfx/interface/focus_tree/
    leader   156 x 210  -> gfx/leaders/<TAG>/
    idea      64 x 64   -> gfx/interface/ideas/
    advisor   65 x 67   -> gfx/interface/advisors/

Usage:
    python convert.py <preset> <input> [--out DIR] [--fit cover|contain]
                      [--format DXT5|DXT1] [--suffix STR]

    <input> can be a single file, a directory, or a glob (e.g. "raw/*.png").

Examples:
    python convert.py leader raw_portraits/ --out out/leaders
    python convert.py focus "raw/*.png" --out out/focus --fit contain
    python convert.py idea raw/alliance.png --out out/ideas --icon-safe

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
    "focus": (88, 88),
    "leader": (156, 210),
    "idea": (64, 64),
    "advisor": (65, 67),
}

SAFE_PADDING = {
    "focus": 6,
    "leader": 0,
    "idea": 8,
    "advisor": 6,
}

EXTS = (".png", ".jpg", ".jpeg", ".webp", ".bmp", ".dds", ".tga")


def collect_inputs(arg):
    if os.path.isdir(arg):
        files = []
        for ext in EXTS:
            files += glob.glob(os.path.join(arg, "*" + ext))
            files += glob.glob(os.path.join(arg, "*" + ext.upper()))
        return sorted(set(files))
    if any(ch in arg for ch in "*?[]"):
        return sorted(glob.glob(arg))
    return [arg] if os.path.isfile(arg) else []


def fit_cover(im, size, vbias=0.5):
    """vbias: 0.0 = keep top, 0.5 = center, 1.0 = bottom."""
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


def add_safe_padding(im, pad):
    if pad <= 0:
        return im
    tw, th = im.size
    inner_w = max(1, tw - pad * 2)
    inner_h = max(1, th - pad * 2)
    inner = fit_contain(im, (inner_w, inner_h))
    canvas = Image.new("RGBA", (tw, th), (0, 0, 0, 0))
    canvas.paste(inner, (pad, pad), inner)
    return canvas


def parse_anchor(anchor_value, focus_top):
    anchor_words = {"top": 0.0, "center": 0.5, "bottom": 1.0}
    if focus_top:
        return 0.25
    if anchor_value in anchor_words:
        return anchor_words[anchor_value]
    try:
        return max(0.0, min(1.0, float(anchor_value)))
    except ValueError:
        sys.exit("--anchor must be top|center|bottom or a 0.0-1.0 number")


def target_size(args):
    if args.preset == "custom":
        if not args.size:
            sys.exit("custom preset needs --size WxH")
        width, height = args.size.lower().split("x")
        return int(width), int(height)
    return PRESETS[args.preset]


def main():
    ap = argparse.ArgumentParser(description="Convert images to HOI4 .dds sprites.")
    ap.add_argument("preset", choices=list(PRESETS) + ["custom"])
    ap.add_argument("input", help="file, directory, or glob")
    ap.add_argument("--out", default="out", help="output directory (default: out)")
    ap.add_argument("--fit", choices=["cover", "contain"], default="cover")
    ap.add_argument(
        "--format",
        dest="fmt",
        choices=["DXT5", "DXT1"],
        default="DXT5",
        help="DXT5 keeps alpha (default); DXT1 = smaller, 1-bit alpha",
    )
    ap.add_argument("--size", help="WxH for --preset custom, e.g. 120x120")
    ap.add_argument("--suffix", default="", help="append to output filename stem")
    ap.add_argument(
        "--anchor",
        default="center",
        help="vertical crop anchor for --fit cover: top|center|bottom or a 0.0-1.0 fraction",
    )
    ap.add_argument(
        "--focus-top",
        dest="focus_top",
        action="store_true",
        help="shortcut for --anchor 0.25 so portraits do not lose the top of the skull",
    )
    ap.add_argument(
        "--safe-pad",
        type=int,
        default=None,
        help="keep transparent inner padding on all sides after resize",
    )
    ap.add_argument(
        "--icon-safe",
        action="store_true",
        help="recommended safe mode for UI icons: contain + preset padding",
    )
    ap.add_argument(
        "--preview-png",
        action="store_true",
        help="also save a PNG preview next to the DDS output",
    )
    args = ap.parse_args()

    size = target_size(args)
    vbias = parse_anchor(args.anchor, args.focus_top)

    if args.icon_safe:
        if args.preset == "leader":
            sys.exit("--icon-safe is meant for focus/idea/advisor icons, not leader portraits")
        args.fit = "contain"
        if args.safe_pad is None:
            args.safe_pad = SAFE_PADDING.get(args.preset, 0)

    if args.safe_pad is not None and args.safe_pad * 2 >= min(size):
        sys.exit("--safe-pad is too large for the target canvas")

    files = collect_inputs(args.input)
    if not files:
        sys.exit(f"no input images matched: {args.input}")

    os.makedirs(args.out, exist_ok=True)
    fit = fit_cover if args.fit == "cover" else fit_contain

    ok = 0
    for src in files:
        try:
            im = Image.open(src).convert("RGBA")
            im = fit(im, size, vbias) if fit is fit_cover else fit(im, size)
            if args.safe_pad:
                im = add_safe_padding(im, args.safe_pad)

            stem = os.path.splitext(os.path.basename(src))[0] + args.suffix
            dds_path = os.path.join(args.out, stem + ".dds")
            im.save(dds_path, pixel_format=args.fmt)
            if args.preview_png:
                im.save(os.path.join(args.out, stem + ".png"))

            print(
                f"  {os.path.basename(src)}  ->  {stem}.dds  "
                f"{size[0]}x{size[1]} {args.fmt} fit={args.fit} pad={args.safe_pad or 0}"
            )
            ok += 1
        except Exception as exc:
            print(f"  !! {os.path.basename(src)}: {exc}", file=sys.stderr)

    print(f"\nDone: {ok}/{len(files)} -> {args.out}")


if __name__ == "__main__":
    main()
