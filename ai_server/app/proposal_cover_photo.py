"""Choose a distinct local landmark from verified report photo metadata."""
from hashlib import sha256
from io import BytesIO
import json
from pathlib import Path
from PIL import Image

from .presentation_theme import download_images, _valid_image_url

CACHE = Path(__file__).resolve().parents[2] / 'storage' / 'region_cover_images'


def candidates(report, excluded_title=''):
    region = str(report.get('region_name') or '').strip()
    if not region:
        return []
    found = []
    for source in report.get('evidence_sources') or []:
        if source.get('source_type') not in ('open_api', 'tourism_open_api'):
            continue
        # The administrative address must identify the requested region.
        address = str(source.get('address') or '')
        if not (address == region or address.startswith(region+' ')):
            continue
        if str(source.get('content_type_id')) not in ('12','14'):
            continue
        title = str(source.get('title') or '')
        if not title or title in excluded_title or not _valid_image_url(source.get('image_url')):
            continue
        found.append(dict(source))
    def priority(source):
        title=source['title']
        # Photo subject preference, not a learned popularity/recommendation rank.
        groups=(('해수욕장','해변','호수','폭포'),('궁','성곽','산성','공원','박물관'),('포구','항구'),('산','오름'))
        return next((i for i, words in enumerate(groups) if any(w in title for w in words)),len(groups))
    return sorted(found,key=priority)


def choose_cover_photo(report, excluded_blob=None, excluded_title='', *, excluded_blobs=()):
    excluded_hashes={sha256(blob).digest() for blob in excluded_blobs if blob}
    if excluded_blob:excluded_hashes.add(sha256(excluded_blob).digest())
    for source in candidates(report,excluded_title)[:3]:
        key=sha256(source['image_url'].encode()).hexdigest()
        path=CACHE/(key+'.img')
        blob=None
        try:
            if path.is_file():
                blob=path.read_bytes()
                Image.open(BytesIO(blob)).verify()
        except (OSError,ValueError):
            blob=None
        if blob is None:
            images=download_images([source])
            if not images:continue
            blob=images[0][1].getvalue()
            try:
                CACHE.mkdir(parents=True,exist_ok=True)
                path.write_bytes(blob)
                (CACHE/(key+'.json')).write_text(json.dumps(source,ensure_ascii=False,indent=2),encoding='utf-8')
            except OSError:
                pass  # The validated in-memory photo can still be exported.
        if sha256(blob).digest() in excluded_hashes:
            continue
        return source,blob
    return None
