#!/usr/bin/env python3
"""Select and extract one Vantrend Beauty product into an auditable run directory."""

from __future__ import annotations

import argparse
import html
import json
import random
import re
import sys
from collections import deque
from datetime import datetime, timezone
from html.parser import HTMLParser
from pathlib import Path
from typing import Any
from urllib.error import HTTPError, URLError
from urllib.parse import quote, urljoin, urlparse, urlunparse
from urllib.request import Request, urlopen
from uuid import uuid4

from content_plan import build_content_plan
from PIL import Image
from io import BytesIO
from zoneinfo import ZoneInfo
from update_manifest import load_manifest, update_manifest, write_manifest


BASE_URL = "https://www.vantrendtools.com"
PRODUCTS_URL = f"{BASE_URL}/products/"
ALLOWED_HOSTS = {"vantrendtools.com", "www.vantrendtools.com"}
USER_AGENT = "Mozilla/5.0 (compatible; VantrendProductPublisher/1.0)"
MAX_CANDIDATES = 10
SPACE_RE = re.compile(r"\s+")
MODEL_RE = re.compile(r"\bVC-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", re.I)
VOID_TAGS = {
    "area",
    "base",
    "br",
    "col",
    "embed",
    "hr",
    "img",
    "input",
    "link",
    "meta",
    "param",
    "source",
    "track",
    "wbr",
}


def clean_text(value: str) -> str:
    return SPACE_RE.sub(" ", html.unescape(value or "")).strip()


class VantrendHTMLParser(HTMLParser):
    """Collect listing links and product-specific fields from Vantrend Beauty pages."""

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.anchors: list[dict[str, Any]] = []
        self.canonical_url = ""
        self.raw_html = ""
        self.meta_description = ""
        self.h1 = ""
        self.summary = ""
        self.quick_specs: list[tuple[str, str]] = []
        self.spec_rows: list[list[tuple[str, str]]] = []
        self.applications: list[str] = []
        self.breadcrumbs: list[dict[str, str]] = []
        self.gallery_images: list[str] = []
        self.detail_text = ""
        self._stack: list[dict[str, Any]] = []

    def _ancestor_has_class(self, class_name: str) -> bool:
        return any(class_name in node["classes"] for node in self._stack)

    def _nearest(self, tag: str | None = None) -> dict[str, Any] | None:
        for node in reversed(self._stack):
            if tag is None or node["tag"] == tag:
                return node
        return None

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        tag = tag.lower()
        values = {key.lower(): (value or "") for key, value in attrs}
        classes = set(values.get("class", "").split())

        if tag == "link":
            if "canonical" in values.get("rel", "").lower().split():
                self.canonical_url = values.get("href", "")
            return
        if tag == "meta":
            if values.get("name", "").lower() == "description":
                self.meta_description = clean_text(values.get("content", ""))
            return
        if tag == "img":
            if self._ancestor_has_class("product_gallery_main"):
                source = values.get("src", "")
                if source and source not in self.gallery_images:
                    self.gallery_images.append(source)
            return
        if tag in VOID_TAGS:
            return

        node: dict[str, Any] = {
            "tag": tag,
            "attrs": values,
            "classes": classes,
            "parts": [],
        }
        if tag == "tr":
            node["cells"] = []
        self._stack.append(node)

    def handle_data(self, data: str) -> None:
        if any(node["tag"] in {"script", "style", "noscript"} for node in self._stack):
            return
        if any(node["attrs"].get("id", "").lower() in {"reviews", "faq"} or node["classes"] & {"product_reviews", "product_faq", "product_packing_shipping"} for node in self._stack):
            return
        value = clean_text(data)
        if not value:
            return
        for node in self._stack:
            node["parts"].append(value)

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        match_index = -1
        for index in range(len(self._stack) - 1, -1, -1):
            if self._stack[index]["tag"] == tag:
                match_index = index
                break
        if match_index < 0:
            return
        while len(self._stack) - 1 > match_index:
            self._finish_node(self._stack.pop())
        self._finish_node(self._stack.pop())

    def _finish_node(self, node: dict[str, Any]) -> None:
        tag = node["tag"]
        classes: set[str] = node["classes"]
        text = clean_text(" ".join(node["parts"]))

        if tag == "a":
            anchor = {
                "href": node["attrs"].get("href", ""),
                "title": clean_text(node["attrs"].get("title", "")),
                "text": text,
                "classes": sorted(classes),
                "product_card": self._ancestor_has_class("item_box") and self._ancestor_has_class("page_content_box"),
            }
            self.anchors.append(anchor)
            if self._ancestor_has_class("page_inside") and text:
                self.breadcrumbs.append({"label": text, "href": anchor["href"]})
        elif tag == "h1" and (self._ancestor_has_class("product_info") or not self.h1):
            if text:
                self.h1 = text
        elif tag == "p" and "product_info_description" in classes:
            self.summary = text
        elif tag == "li" and self._ancestor_has_class("product_attributes"):
            if ":" in text:
                key, value = text.split(":", 1)
                self.quick_specs.append((clean_text(key), clean_text(value)))
        elif tag in {"th", "td"} and self._ancestor_has_class("product_specifications"):
            row = self._nearest(tag="tr")
            if row is not None and text:
                row["cells"].append((tag, text))
        elif tag == "tr" and self._ancestor_has_class("product_specifications"):
            if node.get("cells"):
                self.spec_rows.append(node["cells"])

        if "show_item_box7" in classes:
            self.detail_text = clean_text(self.detail_text + " " + text)

    def close(self) -> None:
        super().close()
        while self._stack:
            self._finish_node(self._stack.pop())


def normalize_url(value: str, base: str = BASE_URL) -> str:
    absolute = urljoin(base, value)
    parsed = urlparse(absolute)
    scheme = parsed.scheme.lower()
    host = (parsed.hostname or "").lower()
    if scheme not in {"http", "https"} or host not in ALLOWED_HOSTS:
        raise ValueError(f"Unsupported URL: {value}")
    path = re.sub(r"/{2,}", "/", parsed.path or "/")
    path = quote(path, safe="/%:@!$&'()*+,;=-._~")
    return urlunparse(("https", "www.vantrendtools.com", path, "", parsed.query, ""))


def fetch_bytes(url: str, timeout: int = 25) -> tuple[bytes, str]:
    request = Request(url, headers={"User-Agent": USER_AGENT, "Accept": "*/*"})
    try:
        with urlopen(request, timeout=timeout) as response:
            normalize_url(response.url)
            return response.read(), response.headers.get("Content-Type", "")
    except (HTTPError, URLError, TimeoutError) as exc:
        raise RuntimeError(f"Failed to fetch {url}: {exc}") from exc


def fetch_html(url: str) -> VantrendHTMLParser:
    body, content_type = fetch_bytes(url)
    charset_match = re.search(r"charset=([\w-]+)", content_type, re.I)
    charset = charset_match.group(1) if charset_match else "utf-8"
    text = body.decode(charset, errors="replace")
    parser = VantrendHTMLParser()
    parser.raw_html = text
    parser.feed(text)
    parser.close()
    return parser


def is_listing_path(path: str) -> bool:
    return bool(
        path.rstrip("/") == "/products"
        or re.fullmatch(r"/products/(?:index|\d+)\.html", path, re.I)
    )


def is_product_path(path: str) -> bool:
    return bool(
        path.lower().endswith(".html")
        and not path.lower().startswith("/products/")
        and not is_listing_path(path)
    )


def normalize_listing_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.path.lower().rstrip("/") in {"/products", "/products/index.html", "/products/1.html"}:
        return urlunparse(parsed._replace(path="/products/"))
    return url


def discover_candidates(audit: dict[str, Any] | None = None) -> list[dict[str, Any]]:
    """Collect every linked product-list page before sampling any product."""
    if audit is None:
        audit = {}
    audit.update(version=1, catalog_url=PRODUCTS_URL, status="scanning",
                 started_at=datetime.now(timezone.utc).isoformat(), pages=[])
    listing_queue = deque([PRODUCTS_URL])
    queued_listings = {PRODUCTS_URL}
    by_url: dict[str, dict[str, Any]] = {}

    while listing_queue:
        listing_url = listing_queue.popleft()
        page: dict[str, Any] = {"url": listing_url, "status": "checking"}
        audit["pages"].append(page)
        try:
            parser = fetch_html(listing_url)
        except RuntimeError as exc:
            cause = exc.__cause__
            if listing_url != PRODUCTS_URL and isinstance(cause, HTTPError) and cause.code in {404, 410}:
                # A stale pager link is evidence of a missing page, not an unread page.
                page.update(status="not_found", http_status=cause.code)
                continue
            page.update(status="failed", error=str(exc))
            audit.update(status="blocked", error=f"Cannot read catalog page: {listing_url}")
            raise RuntimeError(audit["error"]) from exc
        page_products: set[str] = set()
        page_links: set[str] = set()
        for anchor in parser.anchors:
            href = anchor.get("href", "")
            if not href:
                continue
            try:
                url = normalize_url(href, listing_url)
            except ValueError:
                continue
            path = urlparse(url).path
            classes = set(anchor.get("classes", []))
            title = clean_text(anchor.get("title", "") or anchor.get("text", ""))
            if is_listing_path(path):
                url = normalize_listing_url(url)
                page_links.add(url)
                if url not in queued_listings:
                    queued_listings.add(url)
                    listing_queue.append(url)
            elif anchor.get("product_card") and is_product_path(path):
                page_products.add(url)
                existing = by_url.get(url)
                if existing is None:
                    existing = {"url": url, "title": title, "listing_pages": []}
                    by_url[url] = existing
                elif not existing["title"] and title:
                    existing["title"] = title
                if listing_url not in existing["listing_pages"]:
                    existing["listing_pages"].append(listing_url)
        page.update(product_count=len(page_products), product_urls=sorted(page_products),
                    pagination_urls=sorted(page_links))
        if not page_products:
            page.update(status="failed", error="No product cards found")
            audit.update(status="blocked", error=f"No product cards found on catalog page: {listing_url}")
            raise RuntimeError(audit["error"])
        page["status"] = "fetched"

    candidates = list(by_url.values())
    audit.update(status="complete", completed_at=datetime.now(timezone.utc).isoformat(),
                 page_count=sum(p["status"] == "fetched" for p in audit["pages"]),
                 missing_page_count=sum(p["status"] == "not_found" for p in audit["pages"]),
                 candidate_count=len(candidates), candidates=candidates)
    return candidates


def discover_selection_catalog(log_path: Path, log: dict[str, Any]) -> list[dict[str, Any]]:
    audit: dict[str, Any] = {}
    catalog_path = log_path.parent / "catalog.json"
    try:
        return discover_candidates(audit)
    except Exception as exc:
        log.update(status="blocked", reason=f"Catalog discovery failed: {exc}")
        raise
    finally:
        write_manifest(catalog_path, audit)
        log["catalog"] = {"path": str(catalog_path), "status": audit.get("status", "blocked"),
                          "page_count": audit.get("page_count"),
                          "candidate_count": audit.get("candidate_count")}
        write_manifest(log_path, log)


KEY_ALIASES = {"model number": "model", "model no": "model", "product model": "model",
               "product size": "dimensions", "battery capacity": "battery", "plugs type": "charging_port"}


def canonical_key(raw: str) -> str:
    value = re.sub(r"[^a-z0-9]+", " ", raw.lower()).strip()
    return KEY_ALIASES.get(value, value.replace(" ", "_"))


def normalize_fact_value(value: str) -> str:
    return re.sub(r"\s+", "", value.lower().replace("×", "x").replace("*", "x").replace("&", "and"))


def compatible_fact_value(key: str, values: list[str]) -> str | None:
    if key == "battery":
        # Remove only the explicit generic suffix; keep voltage, chemistry and capacities intact.
        reduced = [normalize_fact_value(re.sub(r"\b(?:rechargeable|battery)\b", "", x, flags=re.I)) for x in values]
        if len(set(reduced)) == 1:
            return min(values, key=len)
    if key in {"application", "suitable_for"} and not any(re.search(r"\b(?:not|except|exclude|only)\b", x, re.I) for x in values):
        # Independent application lists remain separate, attributable evidence, not a merged scope.
        return values[0]
    return None


def pairs_from_spec_rows(rows: list[list[tuple[str, str]]]) -> list[tuple[str, str]]:
    pairs: list[tuple[str, str]] = []
    for row in rows:
        index = 0
        while index + 1 < len(row):
            key_tag, key = row[index]
            value_tag, value = row[index + 1]
            if key_tag == "th" and value_tag == "td" and key and value:
                pairs.append((key, value))
                index += 2
            else:
                index += 1
    return pairs


def extract_facts(
    quick_pairs: list[tuple[str, str]],
    detailed_pairs: list[tuple[str, str]],
    evidence_text: str,
    variations: dict[str, Any] | None = None,
) -> tuple[dict[str, str], dict[str, str], dict[str, list[str]]]:
    records: dict[str, list[tuple[str, str]]] = {}
    for source, pairs in (("quick", quick_pairs), ("detail", detailed_pairs)):
        for raw_key, raw_value in pairs:
            key = canonical_key(raw_key)
            value = clean_text(raw_value).strip(" :：")
            if not key or not value:
                continue
            records.setdefault(key, []).append((source, value))

    declared: dict[str, str] = {}
    corroborated: dict[str, str] = {}
    conflicts: dict[str, list[str]] = {}
    normalized_evidence = normalize_fact_value(evidence_text)

    for key, items in records.items():
        unique: dict[str, str] = {}
        sources_by_value: dict[str, set[str]] = {}
        for source, value in items:
            normalized = normalize_fact_value(value)
            if not normalized:
                continue
            unique.setdefault(normalized, value)
            sources_by_value.setdefault(normalized, set()).add(source)
        if len(unique) == 1:
            normalized, value = next(iter(unique.items()))
            declared[key] = value
            if len(sources_by_value[normalized]) >= 2 or (
                len(normalized) >= 4 and normalized in normalized_evidence
            ):
                corroborated[key] = value
        elif len(unique) > 1:
            values = list(unique.values())
            compatible = compatible_fact_value(key, values)
            if compatible is None:
                conflicts[key] = values
            else:
                declared[key] = compatible
                if variations is not None:
                    variations[key] = {
                        "status": "compatible", "selected_value": compatible,
                        "evidence": [{"source": source, "value": value} for source, value in items],
                    }
    return declared, corroborated, conflicts


USE_CASES = {
    "nail salon supply": ("nail salon", "beauty studio"),
    "nail technician use": ("nail technician",),
    "home nail care": ("home use", "home users"),
    "nail filing": ("nail filing",),
    "gel removal": ("gel removal", "gel polish removal"),
    "wholesale distribution": ("wholesale", "distributor"),
    "private label supply": ("private label", "private-label"),
    "OEM supply": ("oem",),
    "ODM supply": ("odm",),
}

def extract_use_cases(text: str) -> list[str]:
    def mentioned(needle: str) -> bool:
        pattern = r"[ -]+".join(map(re.escape, needle.split()))
        return bool(re.search(rf"\b{pattern}(?:s|es)?\b", text, re.I))

    cases = [label for label, needles in USE_CASES.items() if any(map(mentioned, needles))]
    if "OEM supply" in cases and "ODM supply" in cases:
        cases = [label for label in cases if label not in {"OEM supply", "ODM supply"}]
        cases.append("OEM ODM supply")
    return cases


def extract_product(url: str) -> dict[str, Any]:
    url = normalize_url(url)
    if not is_product_path(urlparse(url).path):
        raise ValueError("Target must be a product detail URL, not a category")
    try:
        parser = fetch_html(url)
    except RuntimeError as exc:
        if isinstance(exc.__cause__, HTTPError) and exc.__cause__.code in {404, 410}:
            raise ValueError("Product page no longer exists") from exc
        raise
    title = clean_text(parser.h1)
    if not title:
        raise ValueError("Product page has no usable product H1 title")
    summary = clean_text(parser.summary)
    detail_pairs = pairs_from_spec_rows(parser.spec_rows)
    evidence_text = clean_text(f"{title} {summary} {parser.detail_text}")
    variations: dict[str, Any] = {}
    declared, corroborated, conflicts = extract_facts(
        parser.quick_specs,
        detail_pairs,
        evidence_text,
        variations,
    )

    model = declared.get("item_number", "") or declared.get("model", "")
    if not model:
        model_matches = MODEL_RE.findall(f"{title} {summary}")
        model = model_matches[0] if model_matches else "product"

    gallery: list[str] = []
    for source in parser.gallery_images:
        try:
            image_url = normalize_url(source, url)
        except ValueError:
            continue
        if image_url not in gallery:
            gallery.append(image_url)
    hero = gallery[0] if gallery else ""

    use_case_source = clean_text(
        f"{summary} {parser.detail_text} {' '.join(value for key, value in detail_pairs if canonical_key(key) in {'application', 'suitable_for'})}"
    ).lower()
    use_cases = extract_use_cases(use_case_source)

    breadcrumbs: list[dict[str, str]] = []
    for item in parser.breadcrumbs:
        try:
            breadcrumb_url = normalize_url(item.get("href", ""), url)
        except ValueError:
            continue
        label = clean_text(item.get("label", ""))
        if label and not any(existing["url"] == breadcrumb_url for existing in breadcrumbs):
            breadcrumbs.append({"label": label, "url": breadcrumb_url})

    canonical = normalize_url(parser.canonical_url or url, url)
    product = {
        "source_url": url,
        "canonical_url": canonical,
        "title": title,
        "model": model,
        "summary": summary,
        "facts": {
            "corroborated": corroborated,
            "declared": declared,
            "conflicts": conflicts,
            "variations": variations,
        },
        "use_cases": use_cases,
        "application_labels": parser.applications,
        "breadcrumbs": breadcrumbs,
        "product_detail_text": parser.detail_text,
        "source_sections": {"summary": parser.summary, "quick_specs": parser.quick_specs, "specifications": detail_pairs, "detail": parser.detail_text},
        "fetched_at": datetime.now(timezone.utc).isoformat(),
        "raw_html": parser.raw_html,
        "hero_image_url": hero,
        "gallery_image_urls": gallery,
    }
    usable_facts = {**declared, **corroborated}
    if not hero or len(usable_facts) < 3:
        raise ValueError("Product page lacks a hero image or three usable specifications")
    return product


def slugify(value: str) -> str:
    value = re.sub(r"[^a-zA-Z0-9]+", "-", value).strip("-").lower()
    return value[:60] or "product"


def resolve_output_root(requested: str | None) -> Path:
    if requested:
        root = Path(requested).expanduser().resolve()
    else:
        root = Path.cwd() / "campaign-runs"
    try:
        root.mkdir(parents=True, exist_ok=True)
        probe = root / ".write-test"
        probe.touch(exist_ok=False)
        probe.unlink()
        return root
    except OSError:
        if requested:
            raise
        fallback = Path.home() / ".codex" / "outputs" / "wanchuan-social-publisher"
        fallback.mkdir(parents=True, exist_ok=True)
        return fallback


def image_suffix(url: str, content_type: str) -> str:
    suffix = Path(urlparse(url).path).suffix.lower()
    if suffix in {".jpg", ".jpeg", ".png", ".webp"}:
        return suffix
    if "png" in content_type:
        return ".png"
    if "webp" in content_type:
        return ".webp"
    return ".jpg"


def create_run(product: dict[str, Any], output_root: Path, plan: dict[str, Any], mode: str) -> Path:
    try:
        image_body, content_type = fetch_bytes(product["hero_image_url"])
    except RuntimeError as exc:
        if isinstance(exc.__cause__, HTTPError) and exc.__cause__.code in {404, 410}:
            raise ValueError("Product hero no longer exists") from exc
        raise
    try:
        with Image.open(BytesIO(image_body)) as im:
            if min(im.size) < 300:
                raise ValueError("Hero is below 300 pixels on its shorter side")
            im.verify()
    except (OSError, SyntaxError) as exc:
        raise ValueError("Hero is not a decodable image") from exc
    timestamp = datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S")
    run_dir = output_root / f"{timestamp}-{slugify(product['model'])}-{uuid4().hex[:6]}"
    source_dir = run_dir / "source"
    source_dir.mkdir(parents=True)
    (run_dir / "evidence").mkdir()
    hero_path = source_dir / f"hero{image_suffix(product['hero_image_url'], content_type)}"
    hero_path.write_bytes(image_body)
    (source_dir / "product.html").write_text(product.pop("raw_html", ""), encoding="utf-8")
    write_manifest(run_dir / "product.json", product)
    write_manifest(run_dir / "content-plan.json", plan)
    now = datetime.now(timezone.utc).isoformat()
    manifest = {
        "version": 1, "skill": "wanchuan-social-publisher", "mode": mode,
        "run_id": run_dir.name, "created_at": now, "updated_at": now, "status": "prepared",
        "product": {k: product[k] for k in ("title", "model", "source_url", "canonical_url")},
        "artifacts": {
            "product_json": str(run_dir / "product.json"), "content_plan": str(run_dir / "content-plan.json"),
            "source_hero": str(hero_path), "facebook_copy": str(run_dir / "facebook.txt"),
            "linkedin_copy": str(run_dir / "linkedin.txt"), "social_image": str(run_dir / "social.webp"),
            "social_upload": str(run_dir / "social-upload.jpg"), "review": str(run_dir / "evidence/review.json"),
        },
        "channels": {"facebook": {"status": "pending", "identity_id": "61575467138674"},
                     "linkedin": {"status": "pending", "identity_id": "146727123"}},
        "reporting": {"google_sheet": {"status": "pending", "spreadsheet_id": "18iLpJ7bpDbJzxYtg0vsSOQxOR2e0KBuMI9C7LK0MhAw",
                       "sheet_name": "工作表1", "domain": "vantrendtools.com", "website_value": "不适用（仅社媒）"}},
        "history": [],
    }
    write_manifest(run_dir / "manifest.json", manifest)
    return run_dir


def source_quality_issues(product: dict[str, Any]) -> list[str]:
    """Conservative screening; a passing result still requires editorial source review."""
    facts = product.get("facts", {})
    issues = [f"Conflicting or unresolved {key}: {values}" for key, values in facts.get("conflicts", {}).items()]
    usable = {**facts.get("declared", {}), **facts.get("corroborated", {})}
    if len(usable) < 3 or not product.get("hero_image_url"):
        issues.append("Missing hero image or fewer than three usable specifications")
    expected = str(usable.get("model", product.get("model", ""))).upper()
    detail = " ".join(str(product.get(k, "")) for k in ("title", "summary", "product_detail_text"))
    models = set(re.findall(r"\bVC-[A-Z0-9]+(?:-[A-Z0-9]+)*\b", detail.upper()))
    if expected and any(model != expected for model in models):
        issues.append("Mixed model evidence requires review: " + ", ".join(sorted(models)))
    return issues


def ensure_unsubmitted(manifest: dict[str, Any]) -> None:
    records = list(manifest.get("channels", {}).values()) + manifest.get("history", [])
    if manifest.get("publishing_started_at") or any(
        item.get("submission_started_at") or item.get("status") in {"published", "failed"}
        for item in records
    ):
        raise ValueError("Cannot reselect after a publishing attempt, including an uncertain result")
    if any(item.get("status") not in {"pending", "blocked"}
           for item in manifest.get("channels", {}).values()):
        raise ValueError("Cannot reselect with an unknown channel state")


def new_selection(output_root: Path, *, targeted: bool) -> tuple[Path, dict[str, Any]]:
    log_dir = output_root / ("selection-" + datetime.now(ZoneInfo("Asia/Shanghai")).strftime("%Y%m%d-%H%M%S") + "-" + uuid4().hex[:8])
    log_dir.mkdir()
    log_path = log_dir / "selection.json"
    log = {"version": 1, "created_at": datetime.now(timezone.utc).isoformat(),
           "output_root": str(output_root), "max_candidates": 1 if targeted else MAX_CANDIDATES,
           "targeted": targeted, "status": "selecting", "attempts": []}
    write_manifest(log_path, log)
    return log_path, log


def retry_selection(manifest_path: Path, reason: str,
                    requested_root: str | None = None) -> tuple[Path, dict[str, Any]]:
    old = load_manifest(manifest_path)
    ensure_unsubmitted(old)
    selection = old.get("selection", {})
    if not selection.get("log_path"):
        raise ValueError("Run has no selection ledger; do not silently resume a legacy run")
    log_path = Path(selection["log_path"])
    log = json.loads(log_path.read_text(encoding="utf-8"))
    if requested_root and Path(requested_root).expanduser().resolve() != Path(log["output_root"]):
        raise ValueError("Reselection must keep the same output root")
    if log.get("targeted"):
        raise ValueError("An explicitly targeted run cannot change products without authorization")
    attempts = log.get("attempts", [])
    if not attempts or attempts[-1].get("status") != "selected" or (
        Path(attempts[-1].get("manifest", "")).resolve() != manifest_path.resolve()
    ):
        raise ValueError("Only the current selected candidate can be rejected once")
    for channel in ("facebook", "linkedin"):
        update_manifest(manifest_path, channel, "blocked", error="Product rejected before submission: " + reason)
    attempts[-1].update(status="rejected", reason=reason)
    log["status"] = "selecting"
    write_manifest(log_path, log)
    return log_path, log


def select_candidate(candidates: list[dict[str, Any]], output_root: Path,
                     log_path: Path, log: dict[str, Any]) -> dict[str, Any]:
    tried = {normalize_url(item["url"]) for item in log["attempts"]}
    tried.update(item["canonical_url"] for item in log["attempts"] if item.get("canonical_url"))
    for candidate in candidates:
        if len(log["attempts"]) >= log["max_candidates"]:
            break
        url = normalize_url(candidate["url"])
        if url in tried:
            continue
        tried.add(url)
        record = {"url": url, "title": candidate.get("title", ""), "status": "checking"}
        if candidate.get("listing_pages"):
            record["listing_pages"] = candidate["listing_pages"]
        log["attempts"].append(record)
        write_manifest(log_path, log)
        try:
            product = extract_product(url)
            record["title"] = product["title"]
            canonical = normalize_url(product["canonical_url"])
            record["canonical_url"] = canonical
            if canonical != url and canonical in tried:
                raise ValueError("Canonical URL already evaluated in this selection")
            tried.add(canonical)
            product_path = log_path.parent / f"candidate-{len(log['attempts']):02d}.json"
            write_manifest(product_path, {k: v for k, v in product.items() if k != "raw_html"})
            record["product_json"] = str(product_path)
            issues = source_quality_issues(product)
            if issues:
                raise ValueError("; ".join(issues))
            # Content-plan evidence failures reject only this candidate.
            plan = build_content_plan(product)
            run_dir = create_run(product, output_root, plan, log["mode"])
        except ValueError as exc:
            record.update(status="rejected", reason=str(exc))
            write_manifest(log_path, log)
            continue
        except (RuntimeError, OSError) as exc:
            record.update(status="blocked", reason=str(exc))
            log.update(status="blocked", reason="Tool, network or filesystem failure")
            write_manifest(log_path, log)
            raise
        manifest_path = run_dir / "manifest.json"
        record.update(status="selected", manifest=str(manifest_path))
        log["status"] = "selected"
        write_manifest(log_path, log)
        manifest = load_manifest(manifest_path)
        manifest["selection"] = {"log_path": str(log_path), "attempt": len(log["attempts"]),
                                 "max_candidates": log["max_candidates"],
                                 "editorial_review": "required"}
        manifest["artifacts"]["selection_log"] = str(log_path)
        if log.get("catalog", {}).get("path"):
            manifest["artifacts"]["catalog_snapshot"] = log["catalog"]["path"]
        write_manifest(manifest_path, manifest)
        return {"run_dir": str(run_dir), "manifest": str(manifest_path),
                "product_json": str(run_dir / "product.json"),
                "content_plan": str(run_dir / "content-plan.json"),
                "core_keyword": plan["core_keyword"], "selected_product": product["title"],
                "source_url": product["source_url"], "selection_log": str(log_path),
                "skipped_candidates": len(log["attempts"]) - 1}
    log["status"] = "blocked"
    log["reason"] = "Candidate limit reached" if len(log["attempts"]) >= log["max_candidates"] else "No untried candidates remain"
    write_manifest(log_path, log)
    raise RuntimeError(f"No qualified product: {log['reason']}. Selection log: {log_path}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--product-url",
        help="Select this exact Vantrend Beauty product instead of random selection",
    )
    parser.add_argument("--output-root", help="Root directory for timestamped runs")
    parser.add_argument("--allow-reselect", action="store_true",
                        help="Allow replacing an explicitly targeted product when authorized")
    parser.add_argument("--retry-from", type=Path,
                        help="Reject this invocation's unsubmitted candidate and use its remaining budget")
    parser.add_argument("--reason", help="Product-specific evidence reason for --retry-from")
    parser.add_argument("--mode", choices=("dry-run", "live"), default="dry-run")
    parser.add_argument("--seed", type=int, help="Deterministic random seed for tests only")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    rng: random.Random = random.Random(args.seed) if args.seed is not None else random.SystemRandom()
    if args.retry_from:
        if args.product_url or args.allow_reselect or not args.reason or not args.reason.strip():
            raise ValueError("--retry-from requires --reason and cannot be combined with a target override")
        log_path, log = retry_selection(args.retry_from, args.reason.strip(), args.output_root)
        output_root = Path(log["output_root"])
        if len(log["attempts"]) >= log["max_candidates"]:
            select_candidate([], output_root, log_path, log)
    else:
        if args.reason:
            raise ValueError("--reason requires --retry-from")
        output_root = resolve_output_root(args.output_root)
        log_path, log = new_selection(output_root, targeted=bool(args.product_url and not args.allow_reselect))
    if not args.retry_from:
        log["mode"] = args.mode
        write_manifest(log_path, log)
    candidates = []
    if not log["targeted"]:
        candidates = discover_selection_catalog(log_path, log)
        rng.shuffle(candidates)
    if args.product_url:
        candidates.insert(0, {"url": normalize_url(args.product_url), "title": ""})
    result = select_candidate(candidates, output_root, log_path, log)
    print(json.dumps(result, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except Exception as exc:
        print(f"error: {exc}", file=sys.stderr)
        raise SystemExit(1)
