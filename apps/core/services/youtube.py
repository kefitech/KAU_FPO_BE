"""
YouTube playlist feed helper.

Uses the YouTube Data API v3 when an active key is configured in
ExternalAPISettings (service='youtube_api'), managed from the admin portal's
External APIs page, the same way as the weather key. Requests go to the
entry's API URL, or API_BASE_URL when that is blank. The API returns up to
50 videos per playlist and costs 2 quota units per lookup.

Falls back to the public Atom feed
(https://www.youtube.com/feeds/videos.xml?playlist_id=...) when no key is
configured or the API call fails. The feed needs no key but lists at most 15
videos and is not an officially supported endpoint.

Results are cached in Redis because the landing page reads them on every visit.
"""
import logging
import re
import xml.etree.ElementTree as ET
from urllib.parse import parse_qs, urlparse

import httpx
from django.core.cache import cache

logger = logging.getLogger(__name__)

FEED_URL        = 'https://www.youtube.com/feeds/videos.xml'
API_BASE_URL    = 'https://www.googleapis.com/youtube/v3'  # used when the entry's API URL is blank
API_MAX_RESULTS = 50            # playlistItems.list page size limit
FEED_CACHE_TTL  = 60 * 60 * 6   # 6 hours
FAIL_CACHE_TTL  = 60 * 10       # retry a failed feed after 10 minutes
_FAILED         = '__failed__'

YOUTUBE_CHANNEL_BLOCK   = 'youtube_channel_url'   # SiteBlock key holding the channel link
DEFAULT_YOUTUBE_CHANNEL = 'https://www.youtube.com/@KauIndia'

_PLAYLIST_ID_RE = re.compile(r'^[A-Za-z0-9_-]{10,64}$')

# Google error reasons (from error.errors[].reason and error.details[].reason)
# mapped to messages an admin can act on. Anything else shows Google's message.
_API_ERROR_HINTS = [
    ({'API_KEY_INVALID', 'keyInvalid'},
     'The YouTube API key is not valid. Update it under External APIs.'),
    ({'SERVICE_DISABLED', 'accessNotConfigured'},
     'YouTube Data API v3 is not enabled for this API key. Enable it in the Google Cloud Console '
     '(APIs & Services → Library).'),
    ({'API_KEY_SERVICE_BLOCKED'},
     "This API key is not allowed to call YouTube Data API v3. Allow it in the key's API restrictions "
     'in the Google Cloud Console.'),
    ({'API_KEY_HTTP_REFERRER_BLOCKED', 'API_KEY_IP_ADDRESS_BLOCKED', 'ipRefererBlocked'},
     "This API key's application restrictions block requests from this server. Allow the server's "
     'IP address, or remove the website restriction.'),
    ({'quotaExceeded', 'dailyLimitExceeded'},
     'The YouTube API daily quota is used up. It resets at midnight Pacific Time.'),
]
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


def _get_youtube_api_settings():
    """
    Return (api_key, base_url) from the active youtube_api entry, base_url
    being its API URL or API_BASE_URL when that is blank. None without a key.
    """
    from apps.database.models import ExternalAPISettings
    from apps.notifications.utils import decrypt_config

    settings_obj = ExternalAPISettings.objects.filter(
        service=ExternalAPISettings.SERVICE_YOUTUBE, is_active=True
    ).first()
    if not settings_obj or not settings_obj.config:
        return None
    api_key = decrypt_config(settings_obj.config).get('api_key')
    if not api_key:
        return None
    return api_key, (settings_obj.api_url or '').strip().rstrip('/') or API_BASE_URL


class YouTubeLookupError(Exception):
    """A playlist lookup failure carrying a message an admin can act on."""


def _not_youtube_message(base_url, status_code):
    return (
        f'{base_url} did not respond like the YouTube Data API (HTTP {status_code}). Check the API URL '
        f'under External APIs, or leave it blank to use {API_BASE_URL}.'
    )


def _api_error_message(response, base_url):
    try:
        body = response.json()
    except ValueError:
        body = None
    error = body.get('error') if isinstance(body, dict) else None
    if not isinstance(error, dict):
        return _not_youtube_message(base_url, response.status_code)
    reasons = {e.get('reason') for e in error.get('errors') or []}
    reasons |= {d.get('reason') for d in error.get('details') or []}
    for codes, hint in _API_ERROR_HINTS:
        if reasons & codes:
            return hint
    return f'YouTube API error (HTTP {response.status_code}): {error.get("message") or response.reason_phrase}'


def _api_get(base_url, path, params, api_key):
    # Key goes in a header, not the query string, so it never appears in
    # logged request URLs or exception messages.
    try:
        response = httpx.get(
            f'{base_url}/{path}', params=params, headers={'X-Goog-Api-Key': api_key}, timeout=5.0,
        )
    except (httpx.RequestError, httpx.InvalidURL) as exc:
        raise YouTubeLookupError(
            f'Could not reach the YouTube API at {base_url}. Check the API URL under External APIs '
            f"(leave it blank to use {API_BASE_URL}) and the server's internet connection."
        ) from exc
    if response.is_error:
        raise YouTubeLookupError(_api_error_message(response, base_url))
    try:
        body = response.json()
    except ValueError:
        body = None
    # Every Data API response carries kind 'youtube#...'; anything else means a wrong URL
    if not isinstance(body, dict) or not str(body.get('kind', '')).startswith('youtube#'):
        raise YouTubeLookupError(_not_youtube_message(base_url, response.status_code))
    return body


def _fetch_from_api(playlist_id, api_key, base_url):
    items = _api_get(base_url, 'playlists', {'part': 'snippet', 'id': playlist_id}, api_key).get('items') or []
    if not items:
        return None  # missing or private playlist
    snippet = items[0]['snippet']

    playlist_items = _api_get(base_url, 'playlistItems', {
        'part':       'snippet,contentDetails,status',
        'playlistId': playlist_id,
        'maxResults': API_MAX_RESULTS,
    }, api_key)

    videos = []
    for item in playlist_items.get('items') or []:
        # Private and deleted videos stay in playlists as placeholders
        if item.get('status', {}).get('privacyStatus') not in ('public', 'unlisted'):
            continue
        video_id = item.get('contentDetails', {}).get('videoId')
        if not video_id:
            continue
        thumbs = item['snippet'].get('thumbnails') or {}
        thumb  = thumbs.get('high') or thumbs.get('medium') or thumbs.get('default') or {}
        videos.append({
            'video_id':  video_id,
            'title':     item['snippet'].get('title', ''),
            'thumbnail': thumb.get('url') or f'https://i.ytimg.com/vi/{video_id}/hqdefault.jpg',
            'published': item['contentDetails'].get('videoPublishedAt', ''),
        })

    channel_id = snippet.get('channelId')
    return {
        'title':       snippet.get('title', ''),
        'channel_url': f'https://www.youtube.com/channel/{channel_id}' if channel_id else '',
        'videos':      videos,
    }


def _fetch_from_feed(playlist_id):
    response = httpx.get(FEED_URL, params={'playlist_id': playlist_id}, timeout=5.0)
    response.raise_for_status()
    return _parse_feed(response.text)


def fetch_playlist_feed(playlist_id, use_cache=True, strict=False):
    """
    Return {title, channel_url, videos: [{video_id, title, thumbnail, published}]}
    for a playlist, or None when the playlist is missing, private or YouTube
    is unreachable. Tries the Data API first when a key is configured, then
    the public feed. Best-effort: never raises, unless strict=True (admin
    validation), where a failing API key or a failed keyless lookup raises
    YouTubeLookupError with the reason instead of falling back silently.
    """
    cache_key = f'youtube:feed:{playlist_id}'
    if use_cache:
        try:
            cached = cache.get(cache_key)
            if cached is not None:
                return None if cached == _FAILED else cached
        except Exception:  # noqa: BLE001 -- a cache outage must not block the lookup
            pass

    data = None
    try:
        api = _get_youtube_api_settings()
    except Exception:  # noqa: BLE001 -- a settings lookup failure falls back to the feed
        logger.warning('fetch_playlist_feed: could not read youtube_api settings', exc_info=True)
        api = None

    if api:
        try:
            data = _fetch_from_api(playlist_id, *api)
        except Exception as exc:  # noqa: BLE001 -- best-effort, see docstring
            if strict and isinstance(exc, YouTubeLookupError):
                raise
            logger.warning('fetch_playlist_feed: YouTube API failed for playlist %s', playlist_id, exc_info=True)

    if data is None:
        try:
            data = _fetch_from_feed(playlist_id)
        except Exception as exc:  # noqa: BLE001 -- best-effort, see docstring
            logger.warning('fetch_playlist_feed: could not load feed for playlist %s', playlist_id, exc_info=True)
            # Without a key the feed is the only source, and it 404s for many public playlists
            if strict and not api:
                raise YouTubeLookupError(
                    'Could not load this playlist from YouTube without an API key. Make sure the playlist '
                    'is public, then add and activate a YouTube Data API key under External APIs.'
                ) from exc

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
