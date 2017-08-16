from flask.ext.cache import Cache
from werkzeug.contrib.cache import MemcachedCache
from .server import application
import os

# Constants
USE_MEMCACHE = True

## Cache
cache_config = {}
cache_config['CACHE_TYPE'] = 'simple'

### Memcache

if USE_MEMCACHE:
    username = os.environ.get('MEMCACHIER_USERNAME') or os.environ.get('MEMCACHE_USERNAME')
    password = os.environ.get('MEMCACHIER_PASSWORD') or os.environ.get('MEMCACHE_PASSWORD')
    servers = os.environ.get('MEMCACHIER_SERVERS') or os.environ.get('MEMCACHE_SERVERS')
    if username and password and servers:
        servers = servers.split(';')
        cache_config['CACHE_TYPE'] = 'flask_cache_backends.bmemcached'
        cache_config['CACHE_MEMCACHED_USERNAME'] = username
        cache_config['CACHE_MEMCACHED_PASSWORD'] = password
        cache_config['CACHE_MEMCACHED_SERVERS'] = servers
cache = Cache(application, config=cache_config)
