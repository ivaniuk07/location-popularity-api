import hashlib
import json
import logging

from django.db import transaction
from django_redis import get_redis_connection
from redis.exceptions import RedisError
from rest_framework.utils.encoders import JSONEncoder


logger = logging.getLogger(__name__)
LOCATION_LIST_CACHE_TTL = 60
LOCATION_LIST_VERSION_KEY = "location:list:version"


def _cache_key(request, version):
    selection = {
        "path": request.path,
        "scheme": request.scheme,
        "host": request.get_host(),
        "params": sorted(request.query_params.lists()),
    }
    encoded = json.dumps(selection, ensure_ascii=False, separators=(",", ":"))
    digest = hashlib.sha256(encoded.encode("utf-8")).hexdigest()
    version_text = (
        version.decode("ascii") if isinstance(version, bytes) else str(version)
    )
    return f"location:list:v{version_text}:{digest}"


def get_cached_location_list(request):
    try:
        redis = get_redis_connection("default")
        version = redis.get(LOCATION_LIST_VERSION_KEY) or b"0"
        key = _cache_key(request, version)
        payload = redis.get(key)
        if payload is not None:
            return redis, key, json.loads(payload)
        return redis, key, None
    except (RedisError, TypeError, ValueError, UnicodeDecodeError):
        logger.exception("Не вдалося прочитати кеш списку локацій")
        return None, None, None


def cache_location_list(redis, key, data):
    if redis is None or key is None:
        return
    try:
        payload = json.dumps(data, cls=JSONEncoder, ensure_ascii=False)
        redis.set(key, payload, ex=LOCATION_LIST_CACHE_TTL)
    except (RedisError, TypeError, ValueError):
        logger.exception("Не вдалося записати кеш списку локацій")


def invalidate_location_list_cache():
    try:
        get_redis_connection("default").incr(LOCATION_LIST_VERSION_KEY)
    except RedisError:
        logger.exception("Не вдалося оновити версію кешу локацій")


def invalidate_location_list_after_commit(using=None):
    transaction.on_commit(invalidate_location_list_cache, using=using)
