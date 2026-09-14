"""Catalog publication must reach the already-running forecast registry."""
import unittest
from unittest.mock import patch

from ai_server.ml import region_registry as registry


class RegionRegistryRefreshTest(unittest.TestCase):
    def test_published_catalog_refreshes_without_training_or_restart(self):
        old = {'old': object()}
        new = {'new': object()}
        with patch.object(registry, '_PIPELINES', old), patch.object(registry, '_CATALOG_SIGNATURE', (1, 2)), patch.object(registry, '_catalog_signature', return_value=(3, 4)), patch.object(registry, '_build_region_pipelines', return_value=new) as build:
            self.assertIs(registry.get_region_pipeline('new'), new['new'])
            self.assertEqual(registry.list_region_pipelines(), (new['new'],))
            build.assert_called_once()
            with self.assertRaises(ValueError):
                registry.get_region_pipeline('old')

    def test_invalid_catalog_does_not_publish_partial_registry(self):
        old = {'old': object()}
        with patch.object(registry, '_PIPELINES', old), patch.object(registry, '_CATALOG_SIGNATURE', (1, 2)), patch.object(registry, '_catalog_signature', return_value=(3, 4)), patch.object(registry, '_build_region_pipelines', side_effect=ValueError('invalid catalog')):
            with self.assertRaises(ValueError):
                registry.list_region_pipelines()
            self.assertIs(registry._PIPELINES, old)
            self.assertEqual(registry._CATALOG_SIGNATURE, (1, 2))


if __name__ == '__main__':
    unittest.main()
