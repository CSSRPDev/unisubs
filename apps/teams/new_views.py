# Get the main project for a team Amara, universalsubtitles.org
#
# Copyright (C) 2013 Participatory Culture Foundation
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

"""new_views -- New team views

This module holds view functions for new-style teams.  Eventually it should
replace the old views.py module.
"""

from __future__ import absolute_import
import functools
import json
import logging
import pickle
from collections import namedtuple, OrderedDict

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.views import redirect_to_login
from django.core.cache import cache
from django.core.paginator import Paginator
from django.core.urlresolvers import reverse
from django.db.models import Q
from django.core.exceptions import PermissionDenied
from django.http import (Http404, HttpResponse, HttpResponseRedirect,
                         HttpResponseBadRequest, HttpResponseForbidden)
from django.shortcuts import render, redirect, get_object_or_404
from django.utils.translation import ugettext as _, ungettext

from . import views as old_views
from . import forms
from . import permissions
from . import signals
from . import tasks
from .behaviors import get_main_project
from .bulk_actions import add_videos_from_csv
from .exceptions import ApplicationInvalidException
from .models import (Invite, Setting, Team, Project, TeamVideo,
                     TeamLanguagePreference, TeamMember, Application)
from .statistics import compute_statistics
from activity.models import ActivityRecord
from auth.models import CustomUser as User
from messages import tasks as messages_tasks
from subtitles.models import SubtitleLanguage
from teams.workflows import TeamWorkflow
from ui import (
    AJAXResponseRenderer, ManagementFormList, render_management_form_submit,
    AjaxLink, ContextMenu)
from utils.breadcrumbs import BreadCrumb
from utils.decorators import staff_member_required
from utils.pagination import AmaraPaginator, AmaraPaginatorFuture
from utils.forms import autocomplete_user_view, FormRouter
from utils.text import fmt
from utils.translation import get_language_label
from videos.models import Video

logger = logging.getLogger('teams.views')

ACTIONS_PER_PAGE = 20
VIDEOS_PER_PAGE = 12
VIDEOS_PER_PAGE_MANAGEMENT = 20
MEMBERS_PER_PAGE = 10

def team_view(view_func):
    @functools.wraps(view_func)
    def wrapper(request, slug, *args, **kwargs):
        if not request.user.is_authenticated():
            return redirect_to_login(request.path)
        if isinstance(slug, Team):
            # we've already fetched the team in with_old_view
            team = slug
        else:
            try:
                team = Team.objects.get(slug=slug)
            except Team.DoesNotExist:
                raise Http404
        if not team.user_is_member(request.user):
            raise Http404
        return view_func(request, team, *args, **kwargs)
    return wrapper

def with_old_view(old_view_func):
    def wrap(view_func):
        @functools.wraps(view_func)
        def wrapper(request, slug, *args, **kwargs):
            try:
                team = Team.objects.get(slug=slug)
            except Team.DoesNotExist:
                raise Http404
            if team.is_old_style():
                return old_view_func(request, team, *args, **kwargs)
            return view_func(request, team, *args, **kwargs)
        return wrapper
    return wrap

def admin_only_view(view_func):
    @functools.wraps(view_func)
    @team_view
    def wrapper(request, team, *args, **kwargs):
        member = team.get_member(request.user)
        if not member.is_admin():
            messages.error(request,
                           _("You are not authorized to see this page"))
            return redirect(team)
        return view_func(request, team, member, *args, **kwargs)
    return wrapper

def public_team_view(view_func):
    def wrapper(request, slug, *args, **kwargs):
        try:
            team = Team.objects.get(slug=slug)
        except Team.DoesNotExist:
            raise Http404
        return view_func(request, team, *args, **kwargs)
    return wrapper

def team_settings_view(view_func):
    """Decorator for the team settings pages."""
    @functools.wraps(view_func)
    def wrapper(request, slug, *args, **kwargs):
        team = get_object_or_404(Team, slug=slug)
        if not permissions.can_view_settings_tab(team, request.user):
            messages.error(request,
                           _(u'You do not have permission to edit this team.'))
            return HttpResponseRedirect(team.get_absolute_url())
        return view_func(request, team, *args, **kwargs)
    return login_required(wrapper)

def application_review_view(view_func):
    """Decorator for the application review page."""
    @functools.wraps(view_func)
    def wrapper(request, team, *args, **kwargs):
        if not team.user_is_admin(request.user):
            messages.error(request,
                           _(u'You do not have permission to review applications to this team.'))
            return HttpResponseRedirect(team.get_absolute_url())
        return view_func(request, team, *args, **kwargs)
    return login_required(wrapper)

@with_old_view(old_views.detail)
@team_view
def videos(request, team):
    filters_form = forms.VideoFiltersForm(team, request.GET)
    videos = filters_form.get_queryset().select_related('teamvideo',
                                                        'teamvideo__video')

    paginator = AmaraPaginatorFuture(videos, VIDEOS_PER_PAGE)
    page = paginator.get_page(request)
    next_page, prev_page = paginator.make_next_previous_page_links(page, request)
    add_completed_subtitles_count(list(page))
    context = {
        'team': team,
        'page': page,
        'paginator': paginator,
        'next': next_page,
        'previous': prev_page,
        'filters_form': filters_form,
        'team_nav': 'videos',
        'current_tab': 'videos',
    }
    if request.is_ajax():
        response_renderer = AJAXResponseRenderer(request)
        response_renderer.replace(
            '#video-list', 'future/teams/videos/list.html', context
        )
        return response_renderer.render()

    return render(request, 'future/teams/videos/videos.html', context)

def add_completed_subtitles_count(videos):
    counts = SubtitleLanguage.count_completed_subtitles(videos)
    for v in videos:
        count = counts[v.id][1]
        msg = ungettext((u'%(count)s completed subtitle'),
                        (u'%(count)s completed subtitles'),
                        count)
        v.completed_subtitles = fmt(msg, count=count)

@with_old_view(old_views.detail_members)
@team_view
def members(request, team):
    filters_form = forms.MemberFiltersForm(request.GET)
    form_name = request.GET.get('form', None)
    is_team_admin = team.user_is_admin(request.user)
    show_application_link = (is_team_admin and team.is_by_application())
    members = filters_form.update_qs(
        team.members.prefetch_related('user__userlanguage_set',
                          'projects_managed',
                          'languages_managed'))

    paginator = AmaraPaginatorFuture(members, MEMBERS_PER_PAGE)
    page = paginator.get_page(request)
    next_page, prev_page = paginator.make_next_previous_page_links(page, request)

    context = {
        'team': team,
        'is_team_admin': is_team_admin,
        'paginator': paginator,
        'page': page,
        'next': next_page,
        'previous': prev_page,
        'filters_form': filters_form,
        'show_invite_link': permissions.can_invite(team, request.user),
        'show_add_link': permissions.can_add_members(team, request.user),
        'show_application_link': show_application_link,
    }

    if form_name and is_team_admin:
        return manage_members_form(request, team, form_name, members)

    if not form_name and request.is_ajax():
        response_renderer = AJAXResponseRenderer(request)
        response_renderer.replace(
            '#member-list-all',
            'future/teams/members/member-list.html',
            context
        )
        response_renderer.replace(
            '#members-select-all',
            'future/teams/members/members-select-all.html',
            context
        )
        response_renderer.replace(
            '#memberDirectory-actionBar',
            'future/teams/members/members-action-bar.html',
            context
        )
        return response_renderer.render()

    return render(request, 'future/teams/members/members.html', context)

def manage_members_form(request, team, form_name, members):

    try:
        selection = request.GET['selection'].split('-')
    except StandardError:
        return HttpResponseBadRequest()

    if form_name == 'role':
        FormClass = forms.ChangeMemberRoleForm
    elif form_name == 'remove':
        FormClass = forms.RemoveMemberForm
    else:
        raise Http404()

    all_selected = len(selection) >= MEMBERS_PER_PAGE
    response_renderer = AJAXResponseRenderer(request)

    if request.method == 'POST':
        try:
            form = FormClass(request.user, members, selection, all_selected,
                             data=request.POST, files=request.FILES)
        except Exception as e:
            logger.error(e, exc_info=True)
        if form.is_valid():
            return render_management_form_submit(request, form)
    else:
        try:
            form = FormClass(request.user, members, selection, all_selected)
        except Exception as e:
            logger.error(e, exc_info=True)

    template_name = 'future/teams/members/forms/{}.html'.format(form_name)
    modal_context = {
        'form': form,
        'team': team,
        'selection_count': len(selection),
        'single_selection': len(selection) == 1,
    }
    if modal_context['single_selection']:
        modal_context['member'] = members.get(id=selection[0])
        modal_context['username'] = modal_context['member'].user.username
        modal_context['role'] = modal_context['member'].role

    response_renderer.show_modal(template_name, modal_context)
    return response_renderer.render()

@with_old_view(old_views.applications)
@team_view
@application_review_view
def applications(request, team):
    if not team.user_is_admin(request.user):
        raise PermissionDenied()

    filters_form = forms.ApplicationFiltersForm(request.GET)
    form_name = request.GET.get('form', None)
    applications = filters_form.update_qs(team.applications.filter(
                                          status=Application.STATUS_PENDING))
    paginator = AmaraPaginatorFuture(applications, MEMBERS_PER_PAGE)
    page = paginator.get_page(request)
    next_page, prev_page = paginator.make_next_previous_page_links(page, request)

    context = {
        'request': request,
        'filters_form': filters_form,
        'paginator': paginator,
        'page': page,
        'next': next_page,
        'previous': prev_page,
        'team': team,
    }

    if form_name:
        return manage_application_form(request, team, form_name, applications)

    if not form_name and request.is_ajax():
        response_renderer = AJAXResponseRenderer(request)
        response_renderer.replace(
            '#application-list-all',
            'future/teams/applications/application-list.html',
            context
        )
        return response_renderer.render()

    return render(request, 'future/teams/applications/applications.html', context)

def manage_application_form(request, team, form_name, applications):

    try:
        selection = request.GET['selection'].split('-')
    except StandardError:
        return HttpResponseBadRequest()

    if form_name == 'approve':
        FormClass = forms.ApproveApplicationForm
    elif form_name == 'deny':
        FormClass = forms.DenyApplicationForm
    else:
        raise Http404()

    all_selected = len(selection) >= MEMBERS_PER_PAGE
    response_renderer = AJAXResponseRenderer(request)

    if request.method == 'POST':
        try:
            form = FormClass(request.user, applications, selection, all_selected,
                             data=request.POST, files=request.FILES)
        except Exception as e:
            logger.error(e, exc_info=True)
        if form.is_valid():
            return render_management_form_submit(request, form)
    else:
        try:
            form = FormClass(request.user, applications, selection, all_selected)
        except Exception as e:
            logger.error(e, exc_info=True)

    template_name = 'future/teams/applications/forms/{}.html'.format(form_name)
    modal_context = {
        'team': team,
        'selection_count': len(selection),
        'single_selection': len(selection) == 1,
    }
    if modal_context['single_selection']:
        modal_context['user'] = applications.get(id=selection[0]).user
    response_renderer.show_modal(template_name, modal_context)
    return response_renderer.render()

@team_view
def project(request, team, project_slug):
    project = get_object_or_404(team.project_set, slug=project_slug)
    if permissions.can_change_project_managers(team, request.user):
        form = request.POST.get('form')
        if request.method == 'POST' and form == 'add':
            add_manager_form = forms.AddProjectManagerForm(
                team, project, data=request.POST)
            if add_manager_form.is_valid():
                add_manager_form.save()
                member = add_manager_form.cleaned_data['member']
                msg = fmt(_(u'%(user)s added as a manager'), user=member.user)
                messages.success(request, msg)
                return redirect('teams:project', team.slug, project.slug)
        else:
            add_manager_form = forms.AddProjectManagerForm(team, project)

        if request.method == 'POST' and form == 'remove':
            remove_manager_form = forms.RemoveProjectManagerForm(
                team, project, data=request.POST)
            if remove_manager_form.is_valid():
                remove_manager_form.save()
                member = remove_manager_form.cleaned_data['member']
                msg = fmt(_(u'%(user)s removed as a manager'),
                          user=member.user)
                messages.success(request, msg)
                return redirect('teams:project', team.slug, project.slug)
        else:
            remove_manager_form = forms.RemoveProjectManagerForm(team, project)
    else:
        add_manager_form = None
        remove_manager_form = None

    data = {
        'team': team,
        'project': project,
        'managers': project.managers.all(),
        'add_manager_form': add_manager_form,
        'remove_manager_form': remove_manager_form,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(project),
        ],
    }
    return team.new_workflow.render_project_page(request, team, project, data)

@team_view
def all_languages_page(request, team):
    video_language_counts = dict(team.get_video_language_counts())
    completed_language_counts = dict(team.get_completed_language_counts())

    all_languages = set(video_language_counts.keys() +
                        completed_language_counts.keys())
    languages = [
        (lc,
         get_language_label(lc),
         video_language_counts.get(lc, 0),
         completed_language_counts.get(lc, 0),
        )
        for lc in all_languages
        if lc != ''
    ]
    languages.sort(key=lambda row: (-row[2], row[1]))

    data = {
        'team': team,
        'languages': languages,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Languages')),
        ],
    }
    return team.new_workflow.render_all_languages_page(
        request, team, data,
    )

@team_view
def language_page(request, team, language_code):
    try:
        language_label = get_language_label(language_code)
    except KeyError:
        raise Http404
    if permissions.can_change_language_managers(team, request.user):
        form = request.POST.get('form')
        if request.method == 'POST' and form == 'add':
            add_manager_form = forms.AddLanguageManagerForm(
                team, language_code, data=request.POST)
            if add_manager_form.is_valid():
                add_manager_form.save()
                member = add_manager_form.cleaned_data['member']
                msg = fmt(_(u'%(user)s added as a manager'), user=member.user)
                messages.success(request, msg)
                return redirect('teams:language-page', team.slug,
                                language_code)
        else:
            add_manager_form = forms.AddLanguageManagerForm(team,
                                                            language_code)

        if request.method == 'POST' and form == 'remove':
            remove_manager_form = forms.RemoveLanguageManagerForm(
                team, language_code, data=request.POST)
            if remove_manager_form.is_valid():
                remove_manager_form.save()
                member = remove_manager_form.cleaned_data['member']
                msg = fmt(_(u'%(user)s removed as a manager'),
                          user=member.user)
                messages.success(request, msg)
                return redirect('teams:language-page', team.slug,
                                language_code)
        else:
            remove_manager_form = forms.RemoveLanguageManagerForm(
                team, language_code)
    else:
        add_manager_form = None
        remove_manager_form = None

    data = {
        'team': team,
        'language_code': language_code,
        'language': language_label,
        'managers': (team.members
                     .filter(languages_managed__code=language_code)),
        'add_manager_form': add_manager_form,
        'remove_manager_form': remove_manager_form,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Languages'), 'teams:all-languages-page', team.slug),
            BreadCrumb(language_label),
        ],
    }
    return team.new_workflow.render_language_page(
        request, team, language_code, data,
    )

@team_view
def member_profile(request, team, username):
    if team.is_old_style():
        raise Http404
    try:
        user = User.objects.get(username=username)
        member = TeamMember.objects.get(team=team, user=user)
    except (User.DoesNotExist, TeamMember.DoesNotExist):
        raise Http404
    return team.new_workflow.member_view(request, team, member)

@team_view
def add_members(request, team):
    summary = None
    if not permissions.can_add_members(team, request.user):
        return HttpResponseForbidden(_(u'You cannot invite people to this team.'))
    if request.POST:
        form = forms.AddMembersForm(team, request.user, request.POST)
        if form.is_valid():
            summary = form.save()

    form = forms.AddMembersForm(team, request.user)

    if team.is_old_style():
        template_name = 'teams/add_members.html'
    else:
        template_name = 'new-teams/add_members.html'

    return render(request, template_name,  {
        'team': team,
        'form': form,
        'summary': summary,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Members'), 'teams:members', team.slug),
            BreadCrumb(_('Invite')),
        ],
    })

@team_view
def invite(request, team):
    if not permissions.can_invite(team, request.user):
        return HttpResponseForbidden(_(u'You cannot invite people to this team.'))
    if request.POST:
        form = forms.InviteForm(team, request.user, request.POST)
        if form.is_valid():
            # the form will fire the notifications for invitees
            # this cannot be done on model signal, since you might be
            # sending invites twice for the same user, and that borks
            # the naive signal for only created invitations
            form.save()
            return HttpResponseRedirect(reverse('teams:members',
                                                args=[team.slug]))
    else:
        form = forms.InviteForm(team, request.user)

    if team.is_old_style():
        template_name = 'teams/invite_members.html'
    else:
        template_name = 'new-teams/invite.html'

    return render(request, template_name,  {
        'team': team,
        'form': form,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Members'), 'teams:members', team.slug),
            BreadCrumb(_('Invite')),
        ],
    })

@team_view
def autocomplete_invite_user(request, team):
    return autocomplete_user_view(request, team.invitable_users())

@team_view
def autocomplete_project_manager(request, team, project_slug):
    project = get_object_or_404(team.project_set, slug=project_slug)
    return autocomplete_user_view(request, project.potential_managers())

@team_view
def autocomplete_language_manager(request, team, language_code):
    return autocomplete_user_view(
        request,
        team.potential_language_managers(language_code))

def member_search(request, team, qs):
    query = request.GET.get('query')
    if query:
        members_qs = (qs.filter(user__username__icontains=query)
                      .select_related('user'))
    else:
        members_qs = TeamMember.objects.none()

    data = [
        {
            'value': member.user.username,
            'label': fmt(_('%(username)s (%(full_name)s)'),
                         username=member.user.username,
                         full_name=unicode(member.user)),
        }
        for member in members_qs
    ]

    return HttpResponse(json.dumps(data), mimetype='application/json')

@public_team_view
@login_required
def join(request, team):
    user = request.user

    if team.user_is_member(request.user):
        messages.info(request,
                      fmt(_(u'You are already a member of %(team)s.'),
                          team=team))
    elif team.is_open():
        member = TeamMember.objects.create(team=team, user=request.user,
                                           role=TeamMember.ROLE_CONTRIBUTOR)
        messages.success(request,
                         fmt(_(u'You are now a member of %(team)s.'),
                             team=team))
        messages_tasks.team_member_new.delay(member.pk)
    elif team.is_by_application():
        return application_form(request, team)
    else:
        messages.error(request,
                       fmt(_(u'You cannot join %(team)s.'), team=team))
    return redirect(team)

def application_form(request, team):
    try:
        application = team.applications.get(user=request.user)
    except Application.DoesNotExist:
        application = Application(team=team, user=request.user)
    try:
        application.check_can_submit()
    except ApplicationInvalidException, e:
        messages.error(request, e.message)
        return redirect(team)

    if request.method == 'POST':
        form = forms.ApplicationForm(application, data=request.POST)
        if form.is_valid():
            form.save()
            return redirect(team)
    else:
        form = forms.ApplicationForm(application)
    return render(request, "new-teams/application.html", {
        'team': team,
        'form': form,
    })

@public_team_view
def admin_list(request, team):
    if team.is_old_style():
        return old_views.detail_members(request, team,
                                        role=TeamMember.ROLE_ADMIN)

    # The only real reason to view this page is if you want to ask an admin to
    # invite you, so let's limit the access a bit
    if (not team.is_by_invitation() and not
        team.user_is_member(request.user)):
        return HttpResponseForbidden()
    return render(request, 'new-teams/admin-list.html', {
        'team': team,
        'admins': (team.members
                   .filter(Q(role=TeamMember.ROLE_ADMIN)|
                           Q(role=TeamMember.ROLE_OWNER))
                   .select_related('user'))
    })

@team_view
def activity(request, team):
    filters_form = forms.ActivityFiltersForm(team, request.GET)
    paginator = AmaraPaginator(filters_form.get_queryset(), ACTIONS_PER_PAGE)
    page = paginator.get_page(request)

    action_choices = ActivityRecord.type_choices()

    next_page_query = request.GET.copy()
    next_page_query['page'] = page.next_page_number()

    context = {
        'paginator': paginator,
        'page': page,
        'filters_form': filters_form,
        'filtered': filters_form.is_bound,
        'team': team,
        'tab': 'activity',
        'user': request.user,
        'next_page_query': next_page_query.urlencode(),
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Activity')),
        ],
    }
    # tells the template to use get_old_message instead
    context['use_old_messages'] = True
    if team.is_old_style():
        template_dir = 'teams/'
    else:
        template_dir = 'new-teams/'

    if not request.is_ajax():
        return render(request, template_dir + 'activity.html', context)
    else:
        # for ajax requests we only want to return the activity list, since
        # that's all that the JS code needs.
        return render(request, template_dir + '_activity-list.html', context)

@team_view
def statistics(request, team, tab):
    """For the team activity, statistics tabs
    """
    if (tab == 'teamstats' and
        not permissions.can_view_stats_tab(team, request.user)):
        return HttpResponseForbidden("Not allowed")
    cache_key = 'stats-' + team.slug + '-' + tab
    cached_context = cache.get(cache_key)
    if cached_context:
        context = pickle.loads(cached_context)
    else:
        context = compute_statistics(team, stats_type=tab)
        cache.set(cache_key, pickle.dumps(context), 60*60*24)
    context['tab'] = tab
    context['team'] = team
    context['breadcrumbs'] = [
        BreadCrumb(team, 'teams:dashboard', team.slug),
        BreadCrumb(_('Activity')),
    ]
    if team.is_old_style():
        return render(request, 'teams/statistics.html', context)
    else:
        return render(request, 'new-teams/statistics.html', context)


def dashboard(request, slug):
    team = get_object_or_404(
        Team.objects.for_user(request.user, exclude_private=False),
        slug=slug)
    if not team.is_old_style() and not team.user_is_member(request.user):
        return welcome(request, team)
    else:
        return team.new_workflow.dashboard_view(request, team)

def welcome(request, team):
    if team.is_visible:
        videos = team.videos.order_by('-id')[:2]
    else:
        videos = None

    if Application.objects.open(team, request.user):
        messages.info(request,
                      _(u"Your application has been submitted. "
                        u"You will be notified of the team "
                        "administrator's response"))

    return render(request, 'new-teams/welcome.html', {
        'team': team,
        'join_mode': team.get_join_mode(request.user),
        'team_messages': team.get_messages([
            'pagetext_welcome_heading',
        ]),
        'videos': videos,
    })

@team_view
def manage_videos(request, team):
    if not permissions.can_view_management_tab(team, request.user):
        raise PermissionDenied()
    filters_form = forms.ManagementVideoFiltersForm(team, request.GET,
                                                    auto_id="id_filters_%s")
    videos = filters_form.get_queryset().select_related('teamvideo',
                                                        'teamvideo__video')
    form_name = request.GET.get('form')
    if form_name:
        if form_name == 'add-videos':
            return add_video_forms(request, team)
        else:
            return manage_videos_form(request, team, form_name, videos)
    enabled_forms = all_video_management_forms(team, request.user)
    paginator = AmaraPaginatorFuture(videos, VIDEOS_PER_PAGE_MANAGEMENT)
    page = paginator.get_page(request)
    next_page, prev_page = paginator.make_next_previous_page_links(page, request)
    team.new_workflow.video_management_add_counts(list(page))
    for video in page:
        video.context_menu = manage_videos_context_menu(team, video,
                                                        enabled_forms)
    context = {
        'team': team,
        'page': page,
        'paginator': paginator,
        'next': next_page,
        'previous': prev_page,
        'filters_form': filters_form,
        'team_nav': 'management',
        'current_tab': 'videos',
        'enable_add_form': permissions.can_add_video(team, request.user),
        'manage_forms': [
            (form.name, form.css_class, form.label)
            for form in enabled_forms
        ],
    }
    if request.is_ajax():
        response_renderer = AJAXResponseRenderer(request)
        response_renderer.replace(
            '#video-list', 'future/teams/management/video-list.html', context
        )
        response_renderer.replace(
            '#videos-select-all', 'future/teams/management/videos-select-all.html', 
            {})
        response_renderer.replace(
            '#videos-deselect-all', 'future/teams/management/videos-deselect-all.html',
            {})
        return response_renderer.render()

    return render(request, 'future/teams/management/videos.html', context)

def manage_videos_context_menu(team, video, enabled_forms):
    menu = ContextMenu([
        AjaxLink(form.label, form=form.name, selection=video.id)
        for form in reversed(enabled_forms)
    ])
    team.new_workflow.video_management_alter_context_menu(video, menu)
    return menu

# Functions to handle the forms on the videos pages
def get_video_management_forms(team):
    form_list = ManagementFormList([
        forms.DeleteVideosForm,
        forms.MoveVideosForm,
        forms.EditVideosForm,
    ])
    signals.build_video_management_forms.send(sender=team, form_list=form_list)
    return form_list

def all_video_management_forms(team, user):
    return get_video_management_forms(team).all(team, user)

def lookup_video_managment_form(team, user, form_name):
    return get_video_management_forms(team).lookup(form_name, team, user)

def manage_videos_form(request, team, form_name, videos):
    """Render a form from the action bar on the video management page.
    """
    try:
        selection = request.GET['selection'].split('-')
    except StandardError:
        return HttpResponseBadRequest()
    FormClass = lookup_video_managment_form(team, request.user, form_name)
    if FormClass is None:
        raise Http404()

    all_selected = len(selection) >= VIDEOS_PER_PAGE_MANAGEMENT

    if request.method == 'POST':
        form = FormClass(team, request.user, videos, selection, all_selected,
                         data=request.POST, files=request.FILES)
        if form.is_valid():
            return render_management_form_submit(request, form)
    else:
        form = FormClass(team, request.user, videos, selection, all_selected)

    response_renderer = AJAXResponseRenderer(request)
    first_video = Video.objects.get(id=selection[0])
    template_name = 'future/teams/management/video-forms/{}.html'.format(
        form_name)
    response_renderer.show_modal(template_name, {
        'team': team,
        'form': form,
        'first_video': first_video,
        'selection_count': len(selection),
        'single_selection': len(selection) == 1,
        'all_selected': all_selected,
    })
    return response_renderer.render()

def add_video_forms(request, team):
    if not permissions.can_add_video(team, request.user):
        return HttpResponseForbidden()
    response_renderer = AJAXResponseRenderer(request)
    form = None
    form_bulk = None
    form_multiple = None
    current_tab = 'add-form'
    if request.method == 'POST' and 'form' in request.POST:
        if request.POST['form'] == 'add-form':
            form = forms.AddTeamVideoForm(team, request.user, data=request.POST)
            if form.is_valid():
                form.save()
                messages.success(request, form.success_message())
                response_renderer.reload_page()
                return response_renderer.render()
            else:
                if permissions.can_add_videos_bulk(request.user, team):
                    form_bulk = forms.TeamVideoCSVForm
        elif request.POST['form'] == 'add-multiple':
            current_tab = 'add-multiple'
            form_multiple = forms.AddMultipleTeamVideoForm(team, request.user, data=request.POST)
            if form_multiple.is_valid():
                messages.success(request, form_multiple.success_message())
                response_renderer.reload_page()
                return response_renderer.render()
            else:
                if permissions.can_add_videos_bulk(request.user, team):
                    form_bulk = forms.TeamVideoCSVForm
        elif request.POST['form'] == 'add-csv':
            current_tab = 'add-csv'
            form_bulk = forms.TeamVideoCSVForm(data=request.POST, files=request.FILES)
            if form_bulk.is_bound and form_bulk.is_valid():
                csv_file = form_bulk.cleaned_data['csv_file']
                if csv_file is not None:
                    try:
                        add_videos_from_csv(team, request.user, csv_file)
                        message = fmt(_(u"File successfully uploaded, you should receive the summary shortly."))
                    except:
                        message = fmt(_(u"File was not successfully parsed."))
                    messages.success(request, message)
                    response_renderer.reload_page()
                    return response_renderer.render()
    if form is None:
        form = forms.AddTeamVideoForm(team, request.user)
    if form_multiple is None:
        form_multiple = forms.AddMultipleTeamVideoForm(team, request.user)
    if form_bulk is None and permissions.can_add_videos_bulk(request.user, team=team):
        form_bulk = forms.TeamVideoCSVForm()
    form.use_future_ui()
    form_multiple.use_future_ui()
    template_name = 'future/teams/management/video-forms/add-videos.html'
    context = {
        'team': team,
        'form': form,
        'form_multiple': form_multiple,
        'current_tab': current_tab,
    }
    if form_bulk is not None:
        context['form_bulk'] = form_bulk
    response_renderer.show_modal(template_name, context)
    return response_renderer.render()

@team_settings_view
def settings_basic(request, team):
    if team.is_old_style():
        return old_views.settings_basic(request, team)

    if permissions.can_rename_team(team, request.user):
        FormClass = forms.RenameableSettingsForm
    else:
        FormClass = forms.SettingsForm

    if request.POST:
        form = FormClass(request.POST, request.FILES, instance=team)

        is_visible = team.is_visible

        if form.is_valid():
            try:
                form.save(request.user)
            except:
                logger.exception("Error on changing team settings")
                raise

            if is_visible != form.instance.is_visible:
                tasks.update_video_public_field.delay(team.id)
                tasks.invalidate_video_visibility_caches.delay(team)

            messages.success(request, _(u'Settings saved.'))
            return HttpResponseRedirect(request.path)
    else:
        form = FormClass(instance=team)

    return render(request, "new-teams/settings.html", {
        'team': team,
        'form': form,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Settings')),
        ],
    })

@team_settings_view
def settings_messages(request, team):
    if team.is_old_style():
        return old_views.settings_messages(request, team)

    initial = team.settings.all_messages()
    if request.POST:
        form = forms.GuidelinesMessagesForm(request.POST, initial=initial)

        if form.is_valid():
            for key, val in form.cleaned_data.items():
                setting, c = Setting.objects.get_or_create(team=team, key=Setting.KEY_IDS[key])
                setting.data = val
                setting.save()

            messages.success(request, _(u'Guidelines and messages updated.'))
            return HttpResponseRedirect(request.path)
    else:
        form = forms.GuidelinesMessagesForm(initial=initial)

    return render(request, "new-teams/settings-messages.html", {
        'team': team,
        'form': form,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Settings'), 'teams:settings_basic', team.slug),
            BreadCrumb(_('Messages')),
        ],
    })

@team_settings_view
def settings_lang_messages(request, team):
    if team.is_old_style():
        return old_views.settings_lang_messages(request, team)

    initial = team.settings.all_messages()
    languages = [{"code": l.language_code, "data": l.data} for l in team.settings.localized_messages()]
    if request.POST:
        form = forms.GuidelinesLangMessagesForm(request.POST, languages=languages)
        if form.is_valid():
            new_language = None
            new_message = None
            for key, val in form.cleaned_data.items():
                if key == "messages_joins_localized":
                    new_message = val
                elif key == "messages_joins_language":
                    new_language = val
                else:
                    l = key.split("messages_joins_localized_")
                    if len(l) == 2:
                        code = l[1]
                        try:
                            setting = Setting.objects.get(team=team, key=Setting.KEY_IDS["messages_joins_localized"], language_code=code)
                            if val == "":
                                setting.delete()
                            else:
                                setting.data = val
                                setting.save()
                        except:
                            messages.error(request, _(u'No message for that language.'))
                            return HttpResponseRedirect(request.path)
            if new_message and new_language:
                setting, c = Setting.objects.get_or_create(team=team,
                                  key=Setting.KEY_IDS["messages_joins_localized"],
                                  language_code=new_language)
                if c:
                    setting.data = new_message
                    setting.save()
                else:
                    messages.error(request, _(u'There is already a message for that language.'))
                    return HttpResponseRedirect(request.path)
            elif new_message or new_language:
                messages.error(request, _(u'Please set the language and the message.'))
                return HttpResponseRedirect(request.path)
            messages.success(request, _(u'Guidelines and messages updated.'))
            return HttpResponseRedirect(request.path)
    else:
        form = forms.GuidelinesLangMessagesForm(languages=languages)

    return render(request, "new-teams/settings-lang-messages.html", {
        'team': team,
        'form': form,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Settings'), 'teams:settings_basic', team.slug),
            BreadCrumb(_('Language-specific Messages')),
        ],
    })

@team_settings_view
def settings_feeds(request, team):
    if team.is_old_style():
        return old_views.video_feeds(request, team)

    action = request.POST.get('action')
    if request.method == 'POST' and action == 'import':
        feed = get_object_or_404(team.videofeed_set, id=request.POST['feed'])
        feed.update()
        messages.success(request, _(u'Importing videos now'))
        return HttpResponseRedirect(request.build_absolute_uri())
    if request.method == 'POST' and action == 'delete':
        feed = get_object_or_404(team.videofeed_set, id=request.POST['feed'])
        feed.delete()
        messages.success(request, _(u'Feed deleted'))
        return HttpResponseRedirect(request.build_absolute_uri())

    if request.method == 'POST' and action == 'add':
        add_form = forms.AddTeamVideosFromFeedForm(team, request.user,
                                                   data=request.POST)
        if add_form.is_valid():
            add_form.save()
            messages.success(request, _(u'Video Feed Added'))
            return HttpResponseRedirect(request.build_absolute_uri())
    else:
        add_form = forms.AddTeamVideosFromFeedForm(team, request.user)

    return render(request, "new-teams/settings-feeds.html", {
        'team': team,
        'add_form': add_form,
        'feeds': team.videofeed_set.all(),
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Settings'), 'teams:settings_basic', team.slug),
            BreadCrumb(_('Video Feeds')),
        ],
    })

@team_settings_view
def settings_projects(request, team):
    if team.is_old_style():
        return old_views.settings_projects(request, team)

    projects = Project.objects.for_team(team)

    form = request.POST.get('form')

    if request.method == 'POST' and form == 'add':
        add_form = forms.ProjectForm(team, data=request.POST)

        if add_form.is_valid():
            add_form.save()
            messages.success(request, _('Project added.'))
            return HttpResponseRedirect(
                reverse('teams:settings_projects', args=(team.slug,))
            )
    else:
        add_form = forms.ProjectForm(team)

    if request.method == 'POST' and form == 'edit':
        edit_form = forms.EditProjectForm(team, data=request.POST)

        if edit_form.is_valid():
            edit_form.save()
            messages.success(request, _('Project updated.'))
            return HttpResponseRedirect(
                reverse('teams:settings_projects', args=(team.slug,))
            )
    else:
        edit_form = forms.EditProjectForm(team)

    if request.method == 'POST' and form == 'delete':
        try:
            project = projects.get(id=request.POST['project'])
        except Project.DoesNotExist:
            pass
        else:
            project.delete()
            messages.success(request, _('Project deleted.'))
            return HttpResponseRedirect(
                reverse('teams:settings_projects', args=(team.slug,))
            )

    return render(request, "new-teams/settings-projects.html", {
        'team': team,
        'projects': projects,
        'add_form': add_form,
        'edit_form': edit_form,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Settings'), 'teams:settings_basic', team.slug),
            BreadCrumb(_('Projects')),
        ],
    })

@team_settings_view
def edit_project(request, team, project_slug):
    if team.is_old_style():
        return old_views.edit_project(request, team, project_slug)

    project = get_object_or_404(Project, slug=project_slug)
    if 'delete' in request.POST:
        project.delete()
        return HttpResponseRedirect(
            reverse('teams:settings_projects', args=(team.slug,))
        )
    elif request.POST:
        form = forms.ProjectForm(team, instance=project, data=request.POST)

        if form.is_valid():
            form.save()
            return HttpResponseRedirect(
                reverse('teams:settings_projects', args=(team.slug,))
            )
    else:
        form = forms.ProjectForm(team, instance=project)

    return render(request, "new-teams/settings-projects-edit.html", {
        'team': team,
        'form': form,
        'breadcrumbs': [
            BreadCrumb(team, 'teams:dashboard', team.slug),
            BreadCrumb(_('Settings'), 'teams:settings_basic', team.slug),
            BreadCrumb(_('Projects'), 'teams:settings_projects', team.slug),
            BreadCrumb(project.name),
        ],
    })

@team_settings_view
def settings_workflows(request, team):
    return team.new_workflow.workflow_settings_view(request, team)

@staff_member_required
@team_view
def video_durations(request, team):
    projects = team.projects_with_video_stats()
    totals = (
        sum(p.video_count for p in projects),
        sum(p.videos_without_duration for p in projects),
        sum(p.total_duration for p in projects),
    )
    return render(request, "new-teams/video-durations.html", {
        'team': team,
        'projects': projects,
        'totals': totals,
    })

@team_view
def ajax_member_search(request, team):
    query = request.GET.get('q', '')
    qs = User.objects.search(query).filter(team_members__team=team)
    data = {
        'results': [
            {
                'id': user.username,
                'avatar': user.avatar_tag(),
                'text': unicode(user)
            }
            for user in qs[:8]
        ]
    }

    return HttpResponse(json.dumps(data), 'application/json')

@team_view
def ajax_video_search(request, team):
    query = request.GET.get('q', '')
    qs = Video.objects.search(query).filter(teamvideo__team=team)[:8]
    title_set = set(v.title_display() for v in qs)
    has_duplicate_title = len(title_set) != len(qs)
    def get_title(video):
        if has_duplicate_title:
            return '{} ({})'.format(video.title_display(), video.video_id)
        else:
            return video.title_display()
    data = {
        'results': [
            {
                'id': video.video_id,
                'text': get_title(video),
                'primaryAudioLanguage': video.primary_audio_language_code,
            }
            for video in qs[:8]
        ]
    }

    return HttpResponse(json.dumps(data), 'application/json')
