#!/usr/bin/python

from __future__ import absolute_import
import os
import re
import sys
import shutil
import tempfile

import py.path
import pytest
from django.core.cache import cache
from django.conf import settings

import startup

class AmaraPyTest(object):
    """
    Pytest plugin used by amara
    """
    IGNORE_DIRS = set([
        'amara-assets',
        'libs',
        'media',
        'locale',
        'docs',
        'templates',
        'pykss',
    ])

    def pytest_ignore_collect(self, path, config):
        if path.isdir():
            return path.relto(settings.PROJECT_ROOT) in self.IGNORE_DIRS
        return False

    @pytest.mark.trylast
    def pytest_configure(self, config):
        # Import inside the functions to avoid bootstrapping errors, since
        # this module runs before startup.startup() is called.
        from utils.test_utils import monkeypatch, before_tests

        self.patcher = monkeypatch.MonkeyPatcher()
        self.patcher.patch_functions()
        self.patch_for_rest_framework()

        settings.MEDIA_ROOT = tempfile.mkdtemp(prefix='amara-test-media-root')

        reporter = config.pluginmanager.getplugin('terminalreporter')
        reporter.startdir = py.path.local('/run/pytest/amara/')

        before_tests.send(config)

    def patch_for_rest_framework(self):
        # patch some of old django code to be compatible with the rest
        # framework testing tools
        # restframeworkcompat is the compat module from django-rest-framework
        # 3.0.3
        from utils.test_utils import restframeworkcompat
        import django.test.client
        import django.utils.encoding
        django.test.client.RequestFactory = restframeworkcompat.RequestFactory
        django.utils.encoding.force_bytes = restframeworkcompat.force_bytes_or_smart_bytes

    def pytest_unconfigure(self, config):
        self.patcher.unpatch_functions()
        shutil.rmtree(settings.MEDIA_ROOT)

    def pytest_runtest_teardown(self, item, nextitem):
        self.patcher.reset_mocks()
        cache.clear()

    @pytest.fixture(autouse=True)
    def global_fixture(self, db):
        from auth.models import CustomUser
        CustomUser.get_amara_anonymous()

if __name__ == '__main__':
    startup.startup()
    sys.argv[0] = re.sub(r'(-script\.pyw?|\.exe)?$', '', sys.argv[0])
    sys.exit(pytest.main(plugins=[AmaraPyTest()]))

