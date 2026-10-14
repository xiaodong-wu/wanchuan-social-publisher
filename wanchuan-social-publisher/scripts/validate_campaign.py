#!/usr/bin/env python3
"""Validate a complete Vantrend Beauty campaign directory before any publishing."""

from __future__ import annotations

import argparse
import json
import re
import sys
from pathlib import Path
from typing import Any

import hashlib
from PIL import Image
from optimize_image import validate as validate_webp
from update_manifest import IDENTITIES, load_manifest
from scrape_product import normalize_url, is_product_path
from urllib.parse import urlparse


WORD_RE = re.compile(r"[A-Za-z]+(?:[-'][A-Za-z]+)*")
HASHTAG_RE = re.compile(r"(?<!\w)#[A-Za-z][A-Za-z0-9_]*")


def word_count(value: str) -> int:
    return len(WORD_RE.findall(value))


def hashtag_count(value: str) -> int:
    return len(set(HASHTAG_RE.findall(value)))


def is_feature_line(line: str) -> bool:
    stripped = line.strip()
    if len(stripped) < 5:
        return False
    first = stripped[0]
    return first in {
        "💅",
        "🔋",
        "🏭",
        "📦",
        "🛠",
        "⚙",
        "🔧",
        "✅",
        "💡",
        "📏",
    }


def is_linkedin_bullet(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith(("-", "•", "▪", "‣", "✅", "🚗", "🛞", "🏭", "📦", "⚙", "🛠", "🔧"))


def validate_facebook(value: str, product_url: str) -> dict[str, int]:
    count = word_count(value)
    if not 80 <= count <= 150:
        raise ValueError(f"Facebook copy must be 80–150 English words; received {count}")
    lines = [line for line in value.splitlines() if line.strip()]
    features = sum(is_feature_line(line) for line in lines[:4])
    if features != 4:
        raise ValueError(f"Facebook copy must begin with four emoji feature lines; received {features}")
    hashtags = hashtag_count(value)
    if not 8 <= hashtags <= 12:
        raise ValueError(f"Facebook copy must contain 8–12 unique hashtags; received {hashtags}")
    if product_url not in value:
        raise ValueError("Facebook copy does not contain the selected product URL")
    return {"words": count, "feature_lines": features, "hashtags": hashtags}


def validate_linkedin(value: str, product_url: str) -> dict[str, int]:
    count = word_count(value)
    if not 150 <= count <= 250:
        raise ValueError(f"LinkedIn copy must be 150–250 English words; received {count}")
    lines = [line for line in value.splitlines() if line.strip()]
    bullets = sum(is_linkedin_bullet(line) for line in lines)
    if not 3 <= bullets <= 5:
        raise ValueError(f"LinkedIn copy must contain 3–5 feature bullets; received {bullets}")
    hashtags = hashtag_count(value)
    if not 3 <= hashtags <= 5:
        raise ValueError(f"LinkedIn copy must contain 3–5 unique hashtags; received {hashtags}")
    if product_url not in value:
        raise ValueError("LinkedIn copy does not contain the selected product URL")
    return {"words": count, "feature_bullets": bullets, "hashtags": hashtags}


def artifact_path(manifest: dict[str, Any], key: str) -> Path:
    value = manifest.get("artifacts", {}).get(key)
    if not value:
        raise ValueError(f"Manifest artifact is missing: {key}")
    return Path(value)


def digest(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def validate_transport(path):
    if path.stat().st_size > 750 * 1024:
        raise ValueError("Transport image exceeds 750 KiB")
    with Image.open(path) as im:
        im.verify()
    with Image.open(path) as im:
        if im.format != "JPEG" or im.width != im.height or im.width < 960:
            raise ValueError("Transport must be square JPEG, at least 960 x 960")
        if im.getexif() or any(k in im.info for k in ("exif", "icc_profile", "xmp", "comment")):
            raise ValueError("Transport still has embedded metadata")
        return {"format":"JPEG", "size":list(im.size), "bytes":path.stat().st_size}


def validate_campaign(manifest):
    for c,identity in IDENTITIES.items():
        if manifest['channels'][c].get('identity_id') != identity:
            raise ValueError('Target identity mismatch')
    product_url = manifest['product']['canonical_url']
    if normalize_url(product_url) != product_url or not is_product_path(urlparse(product_url).path):
        raise ValueError('Expected a canonical Vantrend product URL')
    product = json.loads(artifact_path(manifest,'product_json').read_text())
    if product['canonical_url'] != product_url or product['facts']['conflicts']:
        raise ValueError('Product source mismatch or unresolved source conflicts')
    fb = artifact_path(manifest,'facebook_copy').read_text(encoding='utf-8').strip()
    li = artifact_path(manifest,'linkedin_copy').read_text(encoding='utf-8').strip()
    for value in (fb,li):
        if re.search(r'[\u3400-\u9fff]',value): raise ValueError('Social copy must be English')
        if re.findall(r'https?://[^\s]+',value) != [product_url]:
            raise ValueError('Each post must contain only the full canonical product URL, exactly once')
        if product_url not in value.splitlines(): raise ValueError('Product URL needs its own line')
    if fb==li: raise ValueError('Write platform-specific copy')
    plan=json.loads(artifact_path(manifest,'content_plan').read_text())
    if plan.get('source_url')!=product_url or not plan.get('core_keyword'):
        raise ValueError('Content plan belongs to a different product or is empty')
    review=json.loads(artifact_path(manifest,'review').read_text())
    if review.get('product_url')!=product_url or any(review.get(k)!='passed' for k in ('source_review','copy_review','image_review')):
        raise ValueError('Record source, claim, and image editorial review before publication')
    claims=review.get('claims',[])
    if len(claims)<4: raise ValueError('Trace at least four feature claims to source quotations')
    evidence=json.dumps(product['source_sections'],ensure_ascii=False)
    for claim in claims:
        if not claim.get('claim') or not claim.get('quote') or claim['quote'] not in evidence:
            raise ValueError('Claim quotation is absent from product-specific source evidence')
    for key in ('product_json','source_hero','facebook_copy','linkedin_copy','social_image','social_upload'):
        if review.get('sha256',{}).get(key)!=digest(artifact_path(manifest,key)):
            raise ValueError(f'Review is missing or stale for {key}; inspect final artifacts again')
    social=artifact_path(manifest,'social_image')
    return {'status':'validated', 'mode':manifest['mode'],
            'facebook':validate_facebook(fb,product_url), 'linkedin':validate_linkedin(li,product_url),
            'social':validate_webp(social,'social',750*1024),
            'transport':validate_transport(artifact_path(manifest,'social_upload')),
            'editorial_review':'recorded; source and image judgment remains the agent responsibility'}


def main():
    p=argparse.ArgumentParser(description=__doc__);p.add_argument('manifest',type=Path)
    a=p.parse_args()
    print(json.dumps(validate_campaign(load_manifest(a.manifest)),ensure_ascii=False,indent=2))

if __name__=='__main__':
    try: main()
    except (ValueError,OSError,KeyError) as e:
        print(f'error: {e}',file=sys.stderr);sys.exit(1)
