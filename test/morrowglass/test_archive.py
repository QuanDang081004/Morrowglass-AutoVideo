import unittest
from unittest.mock import Mock, patch

from app.morrowglass.archive import (
    ArchiveAsset,
    archive_asset_keys,
    rank_archive_assets,
    relevance_score,
    search_openverse_images,
)


class ArchiveTests(unittest.TestCase):
    def test_ranking_skips_used_asset_identity(self):
        first = ArchiveAsset(
            title="Roman wax mask A",
            image_url="https://example.com/a.jpg",
            source_page="https://example.com/a",
            license_name="Public domain",
            license_url="",
            artist="",
            description="Roman wax mask ancestor portrait",
        )
        second = ArchiveAsset(
            title="Roman wax mask B",
            image_url="https://example.com/b.jpg",
            source_page="https://example.com/b",
            license_name="Public domain",
            license_url="",
            artist="",
            description="Roman wax mask ancestor portrait",
        )
        ranked = rank_archive_assets(
            [first, second],
            query="Ancient Rome wax mask ancestors",
            excluded_keys=archive_asset_keys(
                first
            ),
            required_terms={
                "wax",
                "mask",
                "ancestor",
            },
        )
        self.assertEqual(
            ranked,
            [second],
        )

    def test_scene_specific_terms_filter_generic_roman_coin(self):
        coin = ArchiveAsset(
            title="Roman coins",
            image_url="https://example.com/coin.jpg",
            source_page="https://example.com/coin",
            license_name="Public domain",
            license_url="",
            artist="",
            description="Ancient Roman coin collection",
        )
        mask = ArchiveAsset(
            title="Roman funerary wax mask",
            image_url="https://example.com/mask.jpg",
            source_page="https://example.com/mask",
            license_name="Public domain",
            license_url="",
            artist="",
            description="ancestor wax mask in a Roman family",
        )
        ranked = rank_archive_assets(
            [coin, mask],
            query="Ancient Rome wax mask ancestors wealthy family",
            required_terms={
                "wax",
                "mask",
                "ancestor",
                "family",
            },
        )
        self.assertEqual(
            ranked,
            [mask],
        )

    def test_openverse_keeps_only_commercially_usable_licenses(self):
        response = Mock()
        response.raise_for_status.return_value = None
        response.json.return_value = {
            "results": [
                {
                    "id": "good",
                    "title": "Roman funeral mask",
                    "url": "https://example.com/good.jpg",
                    "thumbnail": "https://example.com/good-thumb.jpg",
                    "foreign_landing_url": "https://example.com/good",
                    "license": "by",
                    "license_version": "4.0",
                    "license_url": "https://creativecommons.org/licenses/by/4.0/",
                    "creator": "Museum",
                    "watermarked": False,
                    "meta_data": {
                        "description": "Roman ancestor funerary mask",
                    },
                    "tags": [
                        {"name": "Roman"},
                        {"name": "mask"},
                    ],
                },
                {
                    "id": "blocked",
                    "title": "NC image",
                    "url": "https://example.com/nc.jpg",
                    "foreign_landing_url": "https://example.com/nc",
                    "license": "by-nc",
                    "license_version": "4.0",
                    "creator": "Someone",
                    "watermarked": False,
                },
            ]
        }

        with patch(
            "app.morrowglass.archive.requests.get",
            return_value=response,
        ):
            results = search_openverse_images(
                "Roman funeral mask",
            )

        self.assertEqual(
            len(results),
            1,
        )
        self.assertEqual(
            results[0].provider,
            "openverse",
        )
        self.assertEqual(
            results[0].source_page,
            "https://example.com/good",
        )
        self.assertIn(
            "Roman ancestor funerary mask",
            results[0].description,
        )

    def test_ranking_prefers_scene_relevant_metadata(self):
        relevant = ArchiveAsset(
            title="Stone chamber entrance",
            image_url="https://example.com/a.jpg",
            source_page="https://example.com/a",
            license_name="Public domain",
            license_url="",
            artist="",
            description=(
                "historic stone chamber with brick entrance"
            ),
        )
        generic = ArchiveAsset(
            title="Mountain landscape",
            image_url="https://example.com/b.jpg",
            source_page="https://example.com/b",
            license_name="CC BY 4.0",
            license_url="",
            artist="",
            description="mountain valley and trees",
        )

        ranked = rank_archive_assets(
            [generic, relevant],
            query="stone chamber brick entrance",
            visual_description=(
                "a child places a brick at a stone chamber entrance"
            ),
        )
        self.assertIs(
            ranked[0],
            relevant,
        )
        self.assertGreater(
            relevance_score(
                relevant,
                "stone chamber entrance",
            ),
            relevance_score(
                generic,
                "stone chamber entrance",
            ),
        )


if __name__ == "__main__":
    unittest.main()
