# -*- coding: utf-8 -*-
"""
    flask_cache_backends
    ~~~~~~~~~~~~~~

    This module implements a flask-cache wrapper for:
        * python-binary-memcached

    Usage:
        cache_config['CACHE_TYPE'] = 'bmemcached_backend.bmemcached'
        cache = Cache(app, config=cache_config)
"""
from werkzeug.contrib.cache import BaseCache, MemcachedCache


# http://pythonhosted.org/Flask-Cache/#configuring-flask-cache
# http://werkzeug.pocoo.org/docs/utils/#werkzeug.utils.import_string
# https://github.com/mitsuhiko/werkzeug/blob/master/werkzeug/utils.py#L383

class BMemcachedCache(MemcachedCache):

    def __init__(self, servers=None, default_timeout=300, key_prefix=None,
                 username=None, password=None):
        BaseCache.__init__(self, default_timeout)

        if servers is None:
            servers = ['127.0.0.1:11211']

        import bmemcached
        self._client = bmemcached.Client(servers,
                                      username=username,
                                      password=password)

        self.key_prefix = key_prefix
def bmemcached(app, config, args, kwargs):
    args.append(config['CACHE_MEMCACHED_SERVERS'])
    kwargs.update(dict(username=config['CACHE_MEMCACHED_USERNAME'],
                       password=config['CACHE_MEMCACHED_PASSWORD'],
                       key_prefix=config['CACHE_KEY_PREFIX']))
    return BMemcachedCache(*args, **kwargs)
