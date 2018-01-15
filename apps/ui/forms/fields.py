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

import json

from django.utils.encoding import force_unicode
from django.utils.html import conditional_escape
from django.utils.safestring import mark_safe
from django.utils.translation import ugettext_lazy as _
from django import forms

from utils import translation
from ui.forms import widgets

class AmaraChoiceFieldMixin(object):
    def __init__(self, allow_search=True, border=False, max_choices=None,
                 choice_help_text=None, *args, **kwargs):
        self.border = border
        if choice_help_text:
            self.choice_help_text = dict(choice_help_text)
        else:
            self.choice_help_text = {}
        super(AmaraChoiceFieldMixin, self).__init__(*args, **kwargs)
        if not allow_search:
            self.set_select_data('nosearchbox')
        if max_choices:
            self.set_select_data('max-allowed-choices', max_choices)

    def _get_choices(self):
        return self._choices

    def _set_choices(self, value):
        self._choices = list(value)
        self._setup_widget_choices()

    choices = property(_get_choices, _set_choices)

    def _setup_widget_choices(self):
        null_choice = None
        widget_choices = []
        for choice in self.choices:
            if not choice[0]:
                null_choice = choice[1]
        self.widget.choices = [
            self.make_widget_choice(c)
            for c in self.choices
        ]
        if null_choice:
            self.set_select_data('placeholder', null_choice)
            self.set_select_data('clear', 'true')
        else:
            self.unset_select_data('placeholder')
            self.set_select_data('clear', 'false')

    def make_widget_choice(self, choice):
        name, label = choice

        help_text = self.choice_help_text.get(name)
        if help_text:
            label = u''.join([
                force_unicode(label),
                mark_safe(
                    '<div class="helpBlock helpBlock-radio">{}</div>'.format(
                        force_unicode(conditional_escape(help_text))))
            ])
            print(label)
        return (name, label)

    def widget_attrs(self, widget):
        if isinstance(widget, forms.Select):
            if self.border:
                return { 'class': 'select border' }
            else:
                return { 'class': 'select' }
        else:
            return {}

    def set_select_data(self, name, value=1):
        name = 'data-' + name
        if isinstance(self.widget, forms.Select):
            if isinstance(value, (list, dict)):
                value = json.dumps(value)
            self.widget.attrs[name] = value

    def unset_select_data(self, name):
        name = 'data-' + name
        if isinstance(self.widget, forms.Select):
            self.widget.attrs.pop(name, None)

class AmaraChoiceField(AmaraChoiceFieldMixin, forms.ChoiceField):
    pass

class AmaraMultipleChoiceField(AmaraChoiceFieldMixin,
                               forms.MultipleChoiceField):
    pass

class LanguageFieldMixin(AmaraChoiceFieldMixin):
    def __init__(self, options="null my popular all",
                 placeholder=_("Select language"), *args, **kwargs):
        kwargs['choices'] = translation.get_language_choices(flat=True)
        super(LanguageFieldMixin, self).__init__(*args, **kwargs)
        self.set_select_data('language-options', options)
        if "null" in options:
            self.set_placeholder(placeholder)

    def exclude(self, languages):
        self.set_select_data('exclude', json.dumps(languages))
        self.choices = [
            c for c in self.choices if c[0] not in languages
        ]

    def limit_to(self, languages):
        self.set_select_data('limit-to', json.dumps(languages))
        self.choices = [
            c for c in self.choices if c[0] in languages
        ]

    def set_flat(self, enabled):
        if enabled:
            self.set_select_data('flat', 1)
        else:
            self.unset_select_data('flat')

    def set_placeholder(self, placeholder):
        self.set_select_data('placeholder', placeholder)

    def _setup_widget_choices(self):
        pass

class LanguageField(LanguageFieldMixin, forms.ChoiceField):
    widget = widgets.AmaraLanguageSelect

class MultipleLanguageField(LanguageFieldMixin, forms.MultipleChoiceField):
    widget = widgets.AmaraLanguageSelectMultiple

class SearchField(forms.CharField):
    widget = widgets.SearchBar

    def __init__(self, **kwargs):
        label = kwargs.pop('label')
        kwargs['label'] = ''
        super(SearchField, self).__init__(**kwargs)
        if label:
            self.widget.attrs['placeholder'] = label

__all__ = [
    'AmaraChoiceField', 'AmaraMultipleChoiceField', 'LanguageField',
    'MultipleLanguageField', 'SearchField',
]
