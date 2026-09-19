from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from pathlib import Path
import re
from typing import Any
from urllib.parse import urlsplit, urlunsplit

import requests
from PIL import Image


WIKIMEDIA_API = "https://commons.wikimedia.org/w/api.php"
_USER_AGENT = (
    "MorrowglassAutoVideo/1.0 "
    "(historical documentary asset fetcher)"
)

_ALLOWED_LICENSE_MARKERS = (
    "public domain",
    "cc0",
    "cc by",
    "cc-by",
    "cc by-sa",
    "cc-by-sa",
)


@dataclass(slots=True)
class ArchiveAsset:
    title: str
    image_url: str
    source_page: str
    license_name: str
    license_url: str
    artist: str
    description: str = ""


def _metadata_value(
    extmetadata: dict[str, Any],
    key: str,
) -> str:
    raw = extmetadata.get(key)
    if not isinstance(raw, dict):
        return ""
    return str(raw.get("value") or "").strip()


def _plain_text(value: str) -> str:
    value = re.sub(
        r"<[^>]+>",
        " ",
        value or "",
    )
    value = unescape(value)
    return re.sub(
        r"\s+",
        " ",
        value,
    ).strip()


def _license_is_reusable(
    license_name: str,
) -> bool:
    value = (
        license_name or ""
    ).strip().lower()
    return any(
        marker in value
        for marker in _ALLOWED_LICENSE_MARKERS
    )


_TOKEN_ALIASES = {
    "rome": "roman",
    "romans": "roman",
    "funerary": "funeral",
    "funerals": "funeral",
    "masks": "mask",
    "ancestors": "ancestor",
    "actors": "actor",
    "families": "family",
    "soldiers": "soldier",
    "warriors": "warrior",
    "tombs": "tomb",
    "temples": "temple",
    "statues": "statue",
}


def _tokens(value: str) -> set[str]:
    tokens = set()
    for token in re.findall(
        r"[^\W_][\w'-]*",
        (value or "").lower(),
        flags=re.UNICODE,
    ):
        if len(token) < 3:
            continue
        canonical = _TOKEN_ALIASES.get(
            token,
            token,
        )
        tokens.add(canonical)
    return tokens


def archive_text_tokens(
    value: str,
) -> set[str]:
    return _tokens(value)


def _normalized_title(
    value: str,
) -> str:
    return re.sub(
        r"[^a-z0-9]+",
        " ",
        (value or "").lower(),
    ).strip()


def _normalized_url(
    value: str,
) -> str:
    raw = (value or "").strip()
    if not raw:
        return ""
    try:
        parts = urlsplit(raw)
        return urlunsplit(
            (
                parts.scheme.lower(),
                parts.netloc.lower(),
                parts.path,
                "",
                "",
            )
        )
    except Exception:
        return raw.lower()


def archive_asset_keys(
    asset: ArchiveAsset,
) -> set[str]:
    keys: set[str] = set()
    source = _normalized_url(
        asset.source_page
    )
    image = _normalized_url(
        asset.image_url
    )
    title = _normalized_title(
        asset.title
    )
    if source:
        keys.add(
            f"source:{source}"
        )
    if image:
        keys.add(
            f"image:{image}"
        )
    if title:
        keys.add(
            f"title:{title}"
        )
    return keys


def archive_record_keys(
    record: dict[str, str],
) -> set[str]:
    keys: set[str] = set()
    source = _normalized_url(
        str(
            record.get(
                "source_page",
                "",
            )
        )
    )
    image = _normalized_url(
        str(
            record.get(
                "image_url",
                "",
            )
        )
    )
    title = _normalized_title(
        str(
            record.get(
                "title",
                "",
            )
        )
    )
    if source:
        keys.add(
            f"source:{source}"
        )
    if image:
        keys.add(
            f"image:{image}"
        )
    if title:
        keys.add(
            f"title:{title}"
        )
    return keys


def archive_metadata_tokens(
    asset: ArchiveAsset,
) -> set[str]:
    return _tokens(
        " ".join(
            value
            for value in (
                asset.title,
                asset.description,
            )
            if value
        )
    )


def relevance_score(
    asset: ArchiveAsset,
    query: str,
    visual_description: str = "",
) -> float:
    target = _tokens(
        " ".join(
            value
            for value in (
                query,
                visual_description,
            )
            if value
        )
    )
    if not target:
        return 0.0

    title_tokens = _tokens(
        asset.title
    )
    desc_tokens = _tokens(
        asset.description
    )

    title_overlap = len(
        target & title_tokens
    )
    desc_overlap = len(
        target & desc_tokens
    )
    coverage = len(
        target
        & (
            title_tokens
            | desc_tokens
        )
    ) / max(1, len(target))

    return (
        title_overlap * 3.0
        + desc_overlap * 1.5
        + coverage * 5.0
    )


def rank_archive_assets(
    assets: list[ArchiveAsset],
    *,
    query: str,
    visual_description: str = "",
    excluded_keys: set[str] | None = None,
    required_terms: set[str] | None = None,
) -> list[ArchiveAsset]:
    excluded_keys = (
        excluded_keys
        or set()
    )
    required_terms = (
        required_terms
        or set()
    )

    eligible: list[
        ArchiveAsset
    ] = []
    for asset in assets:
        if (
            archive_asset_keys(
                asset
            )
            & excluded_keys
        ):
            continue

        if required_terms:
            metadata_terms = (
                archive_metadata_tokens(
                    asset
                )
            )
            if not (
                metadata_terms
                & required_terms
            ):
                continue

        eligible.append(
            asset
        )

    return sorted(
        eligible,
        key=lambda asset: (
            relevance_score(
                asset,
                query,
                visual_description,
            ),
            len(asset.description),
        ),
        reverse=True,
    )


def search_wikimedia_images(
    query: str,
    *,
    limit: int = 12,
    thumb_width: int = 1920,
    timeout: float = 30.0,
) -> list[ArchiveAsset]:
    query = re.sub(
        r"\s+",
        " ",
        query or "",
    ).strip()
    if not query:
        return []

    params = {
        "action": "query",
        "format": "json",
        "formatversion": "2",
        "generator": "search",
        "gsrsearch": query,
        "gsrnamespace": "6",
        "gsrlimit": str(
            max(1, min(int(limit), 30))
        ),
        "prop": "imageinfo",
        "iiprop": "url|extmetadata|mime",
        "iiurlwidth": str(
            max(640, int(thumb_width))
        ),
    }
    response = requests.get(
        WIKIMEDIA_API,
        params=params,
        headers={
            "User-Agent": _USER_AGENT,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    pages = (
        payload.get("query", {})
        .get("pages", [])
    )
    if not isinstance(pages, list):
        return []

    results: list[ArchiveAsset] = []
    for page in pages:
        if not isinstance(page, dict):
            continue
        imageinfo = page.get("imageinfo") or []
        if not imageinfo:
            continue
        info = imageinfo[0]
        if not isinstance(info, dict):
            continue

        mime = str(
            info.get("mime") or ""
        ).lower()
        if not mime.startswith("image/"):
            continue
        if mime in {
            "image/svg+xml",
            "image/tiff",
        }:
            continue

        extmetadata = (
            info.get("extmetadata")
            if isinstance(
                info.get("extmetadata"),
                dict,
            )
            else {}
        )
        license_name = _plain_text(
            _metadata_value(
                extmetadata,
                "LicenseShortName",
            )
        )
        if not _license_is_reusable(
            license_name
        ):
            continue

        image_url = str(
            info.get("thumburl")
            or info.get("url")
            or ""
        ).strip()
        if not image_url.startswith(
            ("http://", "https://")
        ):
            continue

        source_page = str(
            info.get("descriptionurl")
            or ""
        ).strip()
        license_url = _plain_text(
            _metadata_value(
                extmetadata,
                "LicenseUrl",
            )
        )
        artist = _plain_text(
            _metadata_value(
                extmetadata,
                "Artist",
            )
        )
        description = _plain_text(
            _metadata_value(
                extmetadata,
                "ImageDescription",
            )
            or _metadata_value(
                extmetadata,
                "ObjectName",
            )
        )
        title = str(
            page.get("title") or ""
        ).removeprefix("File:")

        results.append(
            ArchiveAsset(
                title=title,
                image_url=image_url,
                source_page=source_page,
                license_name=license_name,
                license_url=license_url,
                artist=artist,
                description=description,
            )
        )
    return results


def download_archive_image(
    asset: ArchiveAsset,
    target: str | Path,
    *,
    timeout: float = 120.0,
) -> Path:
    target = Path(target)
    target.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    response = requests.get(
        asset.image_url,
        headers={
            "User-Agent": _USER_AGENT,
        },
        timeout=timeout,
    )
    response.raise_for_status()

    temp = target.with_suffix(
        ".download"
    )
    temp.write_bytes(
        response.content
    )

    try:
        with Image.open(temp) as image:
            image.load()
            if image.mode not in (
                "RGB",
                "RGBA",
            ):
                image = image.convert("RGB")
            if (
                target.suffix.lower()
                in {".jpg", ".jpeg"}
                and image.mode == "RGBA"
            ):
                background = Image.new(
                    "RGB",
                    image.size,
                    "white",
                )
                background.paste(
                    image,
                    mask=image.getchannel("A"),
                )
                image = background
            image.save(
                target,
                quality=92,
            )
    finally:
        if temp.exists():
            temp.unlink()

    if (
        not target.is_file()
        or target.stat().st_size == 0
    ):
        raise RuntimeError(
            f"archive image is empty: {target}"
        )
    return target


def attribution_record(
    asset: ArchiveAsset,
) -> dict[str, str]:
    return {
        "provider": "wikimedia",
        "title": asset.title,
        "image_url": asset.image_url,
        "source_page": asset.source_page,
        "license": asset.license_name,
        "license_url": asset.license_url,
        "artist": asset.artist,
    }


def write_attribution_file(
    records: dict[str, dict[str, str]],
    path: str | Path,
) -> Path:
    path = Path(path)
    path.parent.mkdir(
        parents=True,
        exist_ok=True,
    )
    lines = [
        "# Asset attribution",
        "",
        (
            "Automatically generated by Morrowglass. "
            "Verify licensing requirements before publication."
        ),
        "",
    ]
    for scene_id in sorted(records):
        record = records[scene_id]
        lines.extend(
            [
                f"## {scene_id}",
                f"- Provider: {record.get('provider', '')}",
                f"- Title: {record.get('title', '')}",
                f"- Artist: {record.get('artist', '')}",
                f"- License: {record.get('license', '')}",
                f"- License URL: {record.get('license_url', '')}",
                f"- Source: {record.get('source_page', '')}",
                "",
            ]
        )
    path.write_text(
        "\n".join(lines),
        encoding="utf-8",
    )
    return path
