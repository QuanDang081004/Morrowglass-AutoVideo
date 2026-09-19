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
OPENVERSE_API = "https://api.openverse.org/v1/images/"
MET_COLLECTION_API = (
    "https://collectionapi.metmuseum.org/public/collection"
)
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
    provider: str = "wikimedia"
    fallback_url: str = ""


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


_OPENVERSE_COMMERCIAL_LICENSES = {
    "cc0",
    "pdm",
    "by",
    "by-sa",
}


def _openverse_description(
    item: dict[str, Any],
) -> str:
    parts: list[str] = []
    meta = item.get(
        "meta_data"
    )
    if isinstance(meta, dict):
        description = meta.get(
            "description"
        )
        if description:
            parts.append(
                str(description)
            )

    tags = item.get("tags")
    if isinstance(tags, list):
        tag_names = []
        for tag in tags[:20]:
            if isinstance(tag, dict):
                name = str(
                    tag.get("name")
                    or ""
                ).strip()
                if name:
                    tag_names.append(
                        name
                    )
        if tag_names:
            parts.append(
                " ".join(tag_names)
            )
    return _plain_text(
        " ".join(parts)
    )


def search_openverse_images(
    query: str,
    *,
    limit: int = 20,
    timeout: float = 30.0,
) -> list[ArchiveAsset]:
    query = re.sub(
        r"\s+",
        " ",
        query or "",
    ).strip()
    if not query:
        return []

    response = requests.get(
        OPENVERSE_API,
        params={
            "q": query,
            "page_size": str(
                max(
                    1,
                    min(
                        int(limit),
                        50,
                    ),
                )
            ),
        },
        headers={
            "User-Agent": _USER_AGENT,
        },
        timeout=timeout,
    )
    response.raise_for_status()
    payload = response.json()
    raw_results = payload.get(
        "results",
        [],
    )
    if not isinstance(
        raw_results,
        list,
    ):
        return []

    results: list[ArchiveAsset] = []
    for item in raw_results:
        if not isinstance(
            item,
            dict,
        ):
            continue
        if bool(
            item.get("watermarked")
        ):
            continue

        license_slug = str(
            item.get("license")
            or ""
        ).strip().lower()
        if (
            license_slug
            not in _OPENVERSE_COMMERCIAL_LICENSES
        ):
            continue

        image_url = str(
            item.get("url")
            or ""
        ).strip()
        thumbnail = str(
            item.get("thumbnail")
            or ""
        ).strip()
        if not image_url.startswith(
            ("http://", "https://")
        ):
            image_url = thumbnail
            thumbnail = ""
        if not image_url.startswith(
            ("http://", "https://")
        ):
            continue

        source_page = str(
            item.get(
                "foreign_landing_url"
            )
            or ""
        ).strip()
        if not source_page:
            identifier = str(
                item.get("id")
                or ""
            ).strip()
            if identifier:
                source_page = (
                    "https://openverse.org/image/"
                    + identifier
                )

        license_version = str(
            item.get(
                "license_version"
            )
            or ""
        ).strip()
        license_name = (
            license_slug.upper()
            if not license_version
            else (
                license_slug.upper()
                + " "
                + license_version
            )
        )

        results.append(
            ArchiveAsset(
                title=str(
                    item.get("title")
                    or ""
                ).strip(),
                image_url=image_url,
                source_page=source_page,
                license_name=license_name,
                license_url=str(
                    item.get(
                        "license_url"
                    )
                    or ""
                ).strip(),
                artist=str(
                    item.get("creator")
                    or ""
                ).strip(),
                description=(
                    _openverse_description(
                        item
                    )
                ),
                provider="openverse",
                fallback_url=(
                    thumbnail
                    if thumbnail.startswith(
                        (
                            "http://",
                            "https://",
                        )
                    )
                    else ""
                ),
            )
        )
    return results


def _met_description(
    item: dict[str, Any],
) -> str:
    parts: list[str] = []
    for key in (
        "title",
        "objectName",
        "culture",
        "period",
        "dynasty",
        "reign",
        "objectDate",
        "medium",
        "classification",
        "country",
        "region",
        "city",
        "excavation",
    ):
        value = str(
            item.get(key)
            or ""
        ).strip()
        if value:
            parts.append(value)

    tags = item.get("tags")
    if isinstance(tags, list):
        for tag in tags[:20]:
            if isinstance(tag, dict):
                term = str(
                    tag.get("term")
                    or ""
                ).strip()
                if term:
                    parts.append(term)

    return _plain_text(
        " ".join(parts)
    )


def search_met_images(
    query: str,
    *,
    limit: int = 12,
    timeout: float = 30.0,
) -> list[ArchiveAsset]:
    query = re.sub(
        r"\s+",
        " ",
        query or "",
    ).strip()
    if not query:
        return []

    page_limit = max(
        1,
        min(
            int(limit),
            30,
        ),
    )
    search_response = requests.get(
        (
            MET_COLLECTION_API
            + "/v1.1/search"
        ),
        params={
            "q": query,
            "hasImages": "true",
            "offset": "0",
            "limit": str(
                page_limit
            ),
        },
        headers={
            "User-Agent": _USER_AGENT,
        },
        timeout=timeout,
    )
    search_response.raise_for_status()
    payload = search_response.json()
    object_ids = payload.get(
        "objectIDs",
        [],
    )
    if not isinstance(
        object_ids,
        list,
    ):
        return []

    results: list[ArchiveAsset] = []
    for object_id in object_ids[
        :page_limit
    ]:
        try:
            response = requests.get(
                (
                    MET_COLLECTION_API
                    + "/v1/objects/"
                    + str(
                        int(object_id)
                    )
                ),
                headers={
                    "User-Agent": (
                        _USER_AGENT
                    ),
                },
                timeout=timeout,
            )
            response.raise_for_status()
            item = response.json()
        except Exception:
            continue

        if not isinstance(
            item,
            dict,
        ):
            continue
        if not bool(
            item.get(
                "isPublicDomain"
            )
        ):
            continue

        image_url = str(
            item.get(
                "primaryImage"
            )
            or item.get(
                "primaryImageSmall"
            )
            or ""
        ).strip()
        fallback = str(
            item.get(
                "primaryImageSmall"
            )
            or ""
        ).strip()
        if not image_url.startswith(
            (
                "http://",
                "https://",
            )
        ):
            continue

        source_page = str(
            item.get("objectURL")
            or ""
        ).strip()
        if not source_page:
            source_page = (
                "https://www.metmuseum.org/art/collection/search/"
                + str(object_id)
            )

        artist = str(
            item.get(
                "artistDisplayName"
            )
            or item.get(
                "artistAlphaSort"
            )
            or ""
        ).strip()

        results.append(
            ArchiveAsset(
                title=str(
                    item.get("title")
                    or item.get(
                        "objectName"
                    )
                    or ""
                ).strip(),
                image_url=image_url,
                source_page=source_page,
                license_name=(
                    "Public Domain"
                ),
                license_url=(
                    "https://www.metmuseum.org/"
                    "about-the-met/policies-and-documents/"
                    "open-access"
                ),
                artist=artist,
                description=(
                    _met_description(
                        item
                    )
                ),
                provider="metmuseum",
                fallback_url=(
                    fallback
                    if fallback.startswith(
                        (
                            "http://",
                            "https://",
                        )
                    )
                    else ""
                ),
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
    urls = [
        value
        for value in (
            asset.image_url,
            asset.fallback_url,
        )
        if value
    ]
    if not urls:
        raise RuntimeError(
            "archive asset has no downloadable URL"
        )

    content: bytes | None = None
    last_error: Exception | None = None
    for url in urls:
        try:
            response = requests.get(
                url,
                headers={
                    "User-Agent": _USER_AGENT,
                },
                timeout=timeout,
            )
            response.raise_for_status()
            content = response.content
            if content:
                break
        except Exception as exc:
            last_error = exc

    if not content:
        raise RuntimeError(
            "archive image download failed"
        ) from last_error

    temp = target.with_suffix(
        ".download"
    )
    temp.write_bytes(
        content
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
        "provider": asset.provider,
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
