from __future__ import absolute_import

import shutil
import tempfile

from django.conf import settings
from django.core.cache import cache
import django.test.client
import django.utils.encoding
from django_redis import get_redis_connection
import py.path
import pytest

from auth.models import CustomUser
from utils.test_utils import monkeypatch, before_tests, restframeworkcompat

patcher = None

def pytest_configure(config):
    global patcher
    patcher = monkeypatch.MonkeyPatcher()
    patcher.patch_functions()
    patch_for_rest_framework()
    patch_mockredis()

    settings.MEDIA_ROOT = tempfile.mkdtemp(prefix='amara-test-media-root')

    reporter = config.pluginmanager.getplugin('terminalreporter')
    reporter.startdir = py.path.local('/run/pytest/')

    before_tests.send(config)

def patch_for_rest_framework():
    # patch some of old django code to be compatible with the rest
    # framework testing tools
    # restframeworkcompat is the compat module from django-rest-framework
    # 3.0.3
    django.test.client.RequestFactory = restframeworkcompat.RequestFactory
    django.utils.encoding.force_bytes = restframeworkcompat.force_bytes_or_smart_bytes

def patch_mockredis():
    from mockredis.client import MockRedis
    # Patch for mockredis returning a boolean when it should return 1 or 0.
    # (See https://github.com/locationlabs/mockredis/issues/147)
    def exists(self, key):
        if self._encode(key) in self.redis:
            return 1
        else:
            return 0

    MockRedis.exists = exists

def pytest_unconfigure(config):
    patcher.unpatch_functions()
    shutil.rmtree(settings.MEDIA_ROOT)

def pytest_runtest_teardown(item, nextitem):
    from django_redis import get_redis_connection
    patcher.reset_mocks()
    get_redis_connection("default").flushdb()

@pytest.fixture(autouse=True)
def setup_amara_db(db):
    CustomUser.get_amara_anonymous()

@pytest.fixture
def redis_connection():
    return get_redis_connection('default')
