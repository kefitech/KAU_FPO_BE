"""
YouTube playlist feed helper.

Reads the public Atom feed YouTube publishes for every playlist
(https://www.youtube.com/feeds/videos.xml?playlist_id=...), so no API key is
needed. The feed lists at most 15 videos. Results are cached in Redis because
the landing page reads them on every visit.
"""
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

import httpx
from django.core.cache import cache

logger = logging.getLogger(__name__)

FEED_URL        = 'https://www.youtube.com/feeds/videos.xml'
FEED_CACHE_TTL  = 60 * 60 * 6   # 6 hours
FAIL_CACHE_TTL  = 60 * 10       # retry a failed feed after 10 minutes
_FAILED         = '__failed__'

YOUTUBE_CHANNEL_BLOCK   = 'youtube_channel_url'   # SiteBlock key holding the channel link
DEFAULT_YOUTUBE_CHANNEL = 'https://www.youtube.com/@KauIndia'

_PLAYLIST_ID_RE = re.compile(r'^[A-Za-z0-9_-]{10,64}$')
_NS = {
    'atom':  'http://www.w3.org/2005/Atom',
    'yt':    'http://www.youtube.com/xml/schemas/2015',
    'media': 'http://search.yahoo.com/mrss/',
}


def extract_playlist_id(value):
    """
    Return the playlist id from a playlist URL, a watch URL with `list=`,
    or a bare id. Returns None when nothing valid is found.
    """
    value = (value or '').strip()
    if not value:
        return None
    if _PLAYLIST_ID_RE.match(value):
        return value
    parsed = urlparse(value)
    host = (parsed.hostname or '').lower()
    if not (host == 'youtu.be' or host == 'youtube.com' or host.endswith('.youtube.com')):
        return None
    playlist_id = parse_qs(parsed.query).get('list', [None])[0]
    if playlist_id and _PLAYLIST_ID_RE.match(playlist_id):
        return playlist_id
    return None


def _parse_feed(xml_text):
    root = ET.fromstring(xml_text)
    channel_uri = root.find('atom:author/atom:uri', _NS)
    videos = []
    for entry in root.findall('atom:entry', _NS):
        video_id = entry.findtext('yt:videoId', default='', namespaces=_NS)
        if not video_id:
            continue
        thumb = entry.find('media:group/media:thumbnail', _NS)
        videos.append({
            'video_id':  video_id,
            'title':     entry.findtext('atom:title', default='', namespaces=_NS),
            'thumbnail': thumb.get('url') if thumb is not None else f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
            'published': entry.findtext('atom:published', default='', namespaces=_NS),
        })
    return {
        'title':       root.findtext('atom:title', default='', namespaces=_NS),
        'channel_url': channel_uri.text if channel_uri is not None else '',
        'videos':      videos,
    }


def fetch_playlist_feed(playlist_id, use_cache=True):
    """
    Return {title, channel_url, videos: [{video_id, title, thumbnail, published}]}
    for a playlist, or None when the playlist is missing, private or YouTube
    is unreachable. Best-effort: never raises.
    """
    cache_key = f'youtube:feed:{playlist_id}'
    if use_cache:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return None if cached == _FAILED else cached
        except Exception:  # noqa: BLE001 -- a cache outage must not block the lookup
            pass

    try:
        response = httpx.get(FEED_URL, params={'playlist_id': playlist_id}, timeout=5.0)
        response.raise_for_status()
        data = _parse_feed(response.text)
    except Exception:  # noqa: BLE001 -- best-effort, see docstring
        logger.warning('fetch_playlist_feed: could not load playlist %s', playlist_id, exc_info=True)
        data = None

    try:
        if data is None:
            cache.set(cache_key, _FAILED, timeout=FAIL_CACHE_TTL)
        else:
            cache.set(cache_key, data, timeout=FEED_CACHE_TTL)
    except Exception:  # noqa: BLE001
        pass
    return data


def get_youtube_channel_url():
    from apps.database.models.cms import SiteBlock

    block = SiteBlock.objects.filter(block_key=YOUTUBE_CHANNEL_BLOCK).first()
    return (block.get_content('en') if block else '') or DEFAULT_YOUTUBE_CHANNEL
