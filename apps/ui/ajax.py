# Amara, universalsubtitles.org
#
# Copyright (C) 2016 Participatory Culture Foundation
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as
# published by the Free Software Foundation, either version 3 of the
# License, or (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see
# http://www.gnu.org/licenses/agpl-3.0.html.

"""Ajax-related functionality."""

import json

from django.core.urlresolvers import reverse
from django.http import HttpResponse
from django.template import RequestContext
from django.template.loader import render_to_string

class AJAXResponseRenderer(object):
    """Render a AJAX response

    This class helps build up AJAX responses for our views.  Typical use is to
    create an AJAXResponseRenderer object.  Call various methods to update the
    page, then call return the results of render().

    See media/amara/js/ajax.js for the JS code that processes these responses.
    """

    def __init__(self, request):
        self.request_context = RequestContext(request)
        self.changes = []
        self.headers = []

    def add_header(self, name, value):
        self.headers.append((name, value))

    def add_change(self, *data):
        self.changes.append(data)

    def replace(self, selector, template, context):
        """Replace content on the page

        Args:
            selector: CSS selector of the element to replace
            template: template name to use to render the content
            context: context dict to pass to the template
        """
        content = render_to_string(template, context, self.request_context)
        self.add_change('replace', selector, content)

    def remove(self, selector):
        """Remove content from the page."""
        self.add_change('remove', selector)

    def show_modal(self, template, context):
        """Display a modal dialog

        If we are already displaying a modal, then this will replace the
        content of that modal.

        Args:
            template: template name to use to render the content
            context: context dict to pass to the template
        """
        content = render_to_string(template, context, self.request_context)
        self.add_change('showModal', content)

    def show_modal_progress(self, progress, label):
        """Show a progress bar on the current modal

        Args:
            progress: current progress (0.0 - 1.0)
            label: label to show under the progress bar
        """
        self.add_change('showModalProgress', progress, label)

    def perform_request(self, delay, view_name, *args, **kwargs):
        """Perform another AJAX request after a delay

        Args:
            url: URL to load
            delay: delay in seconds to wait
        """
        url = reverse(view_name, args=args, kwargs=kwargs)
        self.add_change('performRequest', url, int(delay * 1000))

    def clear_form(self, selector):
        """Clear all inputs in a form

        Args:
            selector: CSS selector to clear
        """
        self.add_change('clearForm', selector)

    def reload_page(self):
        self.add_change('reloadPage')

    def render(self):
        response = HttpResponse(json.dumps(self.changes),
                                content_type='application/json')
        for name, value in self.headers:
            response[name] = value
        return response
