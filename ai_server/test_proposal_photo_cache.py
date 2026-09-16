"""A saved verified photo survives network loss; attribution stays bound."""
from hashlib import sha256
from io import BytesIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest import TestCase
from unittest.mock import patch

import httpx
from PIL import Image

from ai_server.app.presentation_theme import download_images
from ai_server.app.case_images import case_image


class PhotoCacheTest(TestCase):
    def test_verified_download_then_offline_reuse(self):
        blob=BytesIO(); Image.new('RGB',(8,8),'blue').save(blob,format='PNG')
        source={'image_url':'https://example.go.kr/photo.png','title':'원자료 장소'}
        response=httpx.Response(200,headers={'content-type':'image/png'},content=blob.getvalue(),
                                request=httpx.Request('GET',source['image_url']))
        with TemporaryDirectory() as folder, patch('ai_server.app.presentation_theme.IMAGE_CACHE',Path(folder)), \
             patch('ai_server.app.presentation_theme.httpx.Client') as client:
            get=client.return_value.__enter__.return_value.get
            get.return_value=response
            self.assertEqual(download_images([source])[0][1].getvalue(),blob.getvalue())
            get.side_effect=httpx.ConnectError('offline')
            cached=download_images([source])
            self.assertEqual(get.call_count,1)
            self.assertIs(cached[0][0],source)
            self.assertEqual(cached[0][1].getvalue(),blob.getvalue())
            key=sha256(source['image_url'].encode()).hexdigest()
            (Path(folder)/(key+'.img')).write_bytes(b'corrupt')
            self.assertEqual(download_images([source]),[])

    def test_festival_fallback_names_actual_other_event(self):
        photo=case_image({'source_id':'case:festival:example','evidence_kind':'festival_statistics'})
        self.assertIsNotNone(photo)
        self.assertEqual(photo['match_kind'],'similar_operation')
        self.assertIn('서울 중구 정동야행',photo['caption'])
        self.assertIn('참고',photo['caption'])
        self.assertNotIn('인천 섬',photo['caption'])
