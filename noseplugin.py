# Amara, universalsubtitles.org
#
# Copyright (C) 2015 Participatory Culture Foundation
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE. See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program. If not, see
# http://www.gnu.org/licenses/agpl-3.0.html.

"""utils.test_utils.plugin -- Amara nose Plugin
"""
from __future__ import absolute_import
import os
import shutil
import tempfile

from django.dispatch import Signal
from django.conf import settings
from django.core.cache import cache
from nose.plugins import Plugin

import optionalapps

before_tests = Signal()

class UnisubsTestPlugin(Plugin):
    name = 'Amara Test Plugin'

    def __init__(self):
        Plugin.__init__(self)
        self.directories_to_skip = set([
            os.path.join(settings.PROJECT_ROOT, 'libs'),
        ])
        self.vdisplay = None
        self.include_webdriver_tests = False

    def options(self, parser, env=os.environ):
        parser.add_option("--with-webdriver",
                          action="store_true", dest="webdriver",
                          default=False, help="Enable webdriver tests")

    def configure(self, options, conf):
        # force enabled to always be True.  This only gets loaded because we
        # manually specify the plugin in the dev_settings_test.py file.  So
        # it's pretty safe to assume the user wants us enabled.
        self.enabled = True
        self.include_webdriver_tests = options.webdriver

    def begin(self):
        from utils.test_utils import monkeypatch
        self.patcher = monkeypatch.MonkeyPatcher()
        before_tests.send(self)
        self.patcher.patch_functions()
        self.patch_for_rest_framework()
        settings.MEDIA_ROOT = tempfile.mkdtemp(prefix='amara-test-media-root')

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

    def finalize(self, result):
        from utils.test_utils import xvfb
        self.patcher.unpatch_functions()
        xvfb.stop_xvfb()
        shutil.rmtree(settings.MEDIA_ROOT)

    def beforeTest(self, test):
        # Ensure the anonymous user gets created
        from auth.models import CustomUser
        CustomUser.get_amara_anonymous()

    def afterTest(self, test):
        self.patcher.reset_mocks()
        cache.clear()

    def wantDirectory(self, dirname):
        if dirname in self.directories_to_skip:
            return False
        if not self.include_webdriver_tests and 'webdriver' in dirname:
            return False
        if dirname == os.path.join(settings.PROJECT_ROOT, 'apps'):
            # force the tests from the apps directory to be loaded, even
            # though it's not a package
            return True
        if dirname in optionalapps.get_repository_paths():
            # same thing for optional app repos
            return True
        return None
