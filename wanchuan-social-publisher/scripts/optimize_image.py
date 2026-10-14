#!/usr/bin/env python3
"""Crop, strip metadata from, compress, and validate an Vantrend Beauty WebP image."""

from __future__ import annotations

import argparse
import io
import json
import math
import sys
from pathlib import Path

from PIL import Image, ImageOps


TARGETS = {
    "social": {"ratio": 1.0, "max_size": (1600, 1600), "min_size": (960, 960), "max_bytes": 750 * 1024},
}
METADATA_CHUNKS = {b"EXIF", b"XMP ", b"ICCP"}
TRANSPORT_MAX_BYTES = 750 * 1024


def flatten_to_rgb(image: Image.Image) -> Image.Image:
    if image.mode == "RGB":
        return image.copy()
    if image.mode in {"RGBA", "LA"} or "transparency" in image.info:
        rgba = image.convert("RGBA")
        background = Image.new("RGB", rgba.size, "white")
        background.paste(rgba, mask=rgba.getchannel("A"))
        return background
    return image.convert("RGB")


def crop_to_ratio(image: Image.Image, ratio: float) -> Image.Image:
    width, height = image.size
    current = width / height
    if math.isclose(current, ratio, rel_tol=0.002):
        return image
    if current > ratio:
        crop_width = max(1, round(height * ratio))
        left = (width - crop_width) // 2
        return image.crop((left, 0, left + crop_width, height))
    crop_height = max(1, round(width / ratio))
    top = (height - crop_height) // 2
    return image.crop((0, top, width, top + crop_height))


def downscale(image: Image.Image, max_size: tuple[int, int]) -> Image.Image:
    if image.width <= max_size[0] and image.height <= max_size[1]:
        return image
    result = image.copy()
    result.thumbnail(max_size, Image.Resampling.LANCZOS)
    return result


def strip_metadata(image: Image.Image) -> Image.Image:
    """Rebuild from pixels so EXIF, XMP, ICC and source container data cannot survive."""
    rgb = flatten_to_rgb(image)
    return Image.frombytes("RGB", rgb.size, rgb.tobytes())


def encode_webp(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(
        buffer,
        format="WEBP",
        quality=quality,
        method=6,
        lossless=False,
    )
    return buffer.getvalue()


def encode_jpeg(image: Image.Image, quality: int) -> bytes:
    buffer = io.BytesIO()
    image.save(buffer, format="JPEG", quality=quality, optimize=True, progressive=True, subsampling="4:2:0")
    return buffer.getvalue()


def create_transport_jpeg(image: Image.Image, path: Path) -> dict[str, object]:
    for quality in range(90, 71, -2):
        encoded = encode_jpeg(image, quality)
        if len(encoded) <= TRANSPORT_MAX_BYTES:
            path.parent.mkdir(parents=True, exist_ok=True)
            path.write_bytes(encoded)
            with Image.open(path) as check:
                check.verify()
            with Image.open(path) as check:
                if check.format != "JPEG" or check.getexif() or any(key in check.info for key in ("exif", "icc_profile", "xmp")):
                    raise RuntimeError("Transport derivative must be metadata-free JPEG")
                width, height = check.size
            return {"path": str(path), "format": "JPEG", "quality": quality, "bytes": len(encoded), "width": width, "height": height, "metadata_removed": True}
    raise RuntimeError("Unable to create the temporary social-upload JPEG below 750 KiB")


def compress(image: Image.Image, max_bytes: int, min_size: tuple[int, int]) -> tuple[bytes, Image.Image, int]:
    if image.width < min_size[0] or image.height < min_size[1]:
        raise ValueError("Source is below minimum dimensions; do not upscale")
    working = image
    while True:
        for quality in range(88, 67, -2):
            encoded = encode_webp(working, quality)
            if len(encoded) <= max_bytes:
                return encoded, working, quality
        if working.width <= min_size[0] or working.height <= min_size[1]:
            break
        next_size = (max(min_size[0], round(working.width * 0.9)), max(min_size[1], round(working.height * 0.9)))
        if next_size == working.size:
            break
        working = working.resize(next_size, Image.Resampling.LANCZOS)
    raise RuntimeError(f"Unable to compress image below {max_bytes} bytes at WebP quality >= 68 without shrinking below {min_size[0]}x{min_size[1]}")


def metadata_chunks(data: bytes) -> list[str]:
    if len(data) < 12 or data[:4] != b"RIFF" or data[8:12] != b"WEBP":
        return []
    chunks: list[str] = []
    offset = 12
    while offset + 8 <= len(data):
        name = data[offset : offset + 4]
        size = int.from_bytes(data[offset + 4 : offset + 8], "little")
        if name in METADATA_CHUNKS:
            chunks.append(name.decode("ascii").strip())
        offset += 8 + size + (size % 2)
    return chunks


def validate(path: Path, kind: str, max_bytes: int) -> dict[str, object]:
    if path.suffix.lower() != ".webp":
        raise RuntimeError("Output path must use the .webp extension")
    size = path.stat().st_size
    if size > max_bytes:
        raise RuntimeError(f"Output is {size} bytes, above the {max_bytes}-byte limit")
    with Image.open(path) as image:
        image.verify()
    with Image.open(path) as image:
        if image.format != "WEBP":
            raise RuntimeError(f"Output format is {image.format}, expected WEBP")
        width, height = image.size
    if min(width, height) < 960:
        raise ValueError("Social image must be at least 960 x 960 pixels")
    embedded_metadata = metadata_chunks(path.read_bytes())
    if embedded_metadata:
        raise RuntimeError(f"Output still contains metadata chunks: {', '.join(embedded_metadata)}")
    ratio = width / height
    expected = TARGETS[kind]["ratio"]
    if abs(ratio - expected) > 0.01:
        raise RuntimeError(f"Output ratio {ratio:.4f} does not match {expected:.4f}")
    return {
        "path": str(path),
        "kind": kind,
        "format": "WEBP",
        "width": width,
        "height": height,
        "bytes": size,
        "max_bytes": max_bytes,
        "metadata_removed": True,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("input", type=Path)
    parser.add_argument("output", type=Path)
    parser.add_argument("--kind", choices=sorted(TARGETS), required=True)
    parser.add_argument("--max-bytes", type=int, help="Override the clarity-preserving per-kind byte ceiling")
    parser.add_argument("--transport-jpeg", type=Path, help="For social images only, create a temporary metadata-free desktop upload derivative")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    target = TARGETS[args.kind]
    max_bytes = args.max_bytes or target["max_bytes"]
    if max_bytes <= 0:
        raise ValueError("--max-bytes must be positive")
    if not args.input.is_file():
        raise FileNotFoundError(args.input)
    args.output.parent.mkdir(parents=True, exist_ok=True)
    if args.transport_jpeg and args.kind != "social":
        raise ValueError("--transport-jpeg is valid only with --kind social")

    with Image.open(args.input) as source:
        source = ImageOps.exif_transpose(source)
        image = strip_metadata(source)
    image = crop_to_ratio(image, target["ratio"])
    image = downscale(image, target["max_size"])
    encoded, final_image, quality = compress(image, max_bytes, target["min_size"])
    args.output.write_bytes(encoded)

    result = validate(args.output, args.kind, max_bytes)
    result["quality"] = quality
    result["input"] = str(args.input)
    result["cropped_size"] = list(final_image.size)
    if args.transport_jpeg:
        result["transport_jpeg"] = create_transport_jpeg(final_image, args.transport_jpeg)
    print(json.dumps(result, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
