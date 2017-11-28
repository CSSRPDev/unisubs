# Amara, universalsubtitles.org
#
# Copyright (C) 2017 Participatory Culture Foundation
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

import babelsubs
from google import APIError
from django.conf import settings
from django.contrib.sites.models import Site
from django.core.urlresolvers import reverse
import base64, requests, logging

logger = logging.getLogger(__name__)

VIMEO_API_KEY = getattr(settings, 'VIMEO_API_KEY')
VIMEO_API_SECRET = getattr(settings, 'VIMEO_API_SECRET')

VIMEO_API_BASE_URL = "https://api.vimeo.com"

def get_redirect_uri(host):
    return host + reverse("externalsites:vimeo-login-done")

def get_texttracks_url(video_id):
    return "/videos/" + video_id + "/texttracks"

def get_auth_url(host, state):
    callback_url = get_redirect_uri(host)
    scope = "private public upload delete edit"
    url = "/oauth/authorize?client_id={}&response_type=code&redirect_uri={}&state={}&scope={}".format(VIMEO_API_KEY,
                                                                                       callback_url,
                                                                                       state, scope)
    auth_url =  VIMEO_API_BASE_URL + url
    return auth_url

def get_token(code):
    headers = {"Authorization":
               ("basic " + \
                base64.b64encode(VIMEO_API_KEY + ":" + VIMEO_API_SECRET))}
    protocol = getattr(settings, "DEFAULT_PROTOCOL", 'https')
    host = protocol + '://' + Site.objects.get_current().domain
    data = {"grant_type": "authorization_code",
            "code": code,
            "redirect_uri": get_redirect_uri(host)}
    url = "/oauth/access_token"
    response = requests.post(VIMEO_API_BASE_URL + url,
                             data=data,
                             headers=headers)
    if response.ok:
        return response.json()
    else:
        None

def get_video(account, video_id):
    headers = {"Authorization":
               ("Bearer " + account.access_token)}
    url = "/videos/" + video_id
    response = requests.get(VIMEO_API_BASE_URL + url,
                            headers=headers)
    if response.ok:
        return response.json()
    return None

def get_text_tracks(account, video_id):
    headers = {"Authorization":
               ("Bearer " + account.access_token)}
    url = get_texttracks_url(video_id)
    response = requests.get(VIMEO_API_BASE_URL + url,
                            headers=headers)
    if response.ok:
        return response.json()
    return None

def get_text_track(account, uri):
    headers = {"Authorization":
               ("Bearer " + account.access_token)}
    response = requests.get(VIMEO_API_BASE_URL + uri,
                            headers=headers)
    if response.ok:
        return response.json()
    return None

def update_subtitles(account, video_id, subtitle_version):
    headers = {"Authorization":
               ("Bearer " + account.access_token)}
    text_tracks = get_text_tracks(account, video_id)
    subtitles = subtitle_version.get_subtitles()
    encoded_subtitles = babelsubs.to(subtitles, 'vtt').encode('utf-8')
    language_code = subtitle_version.language_code
    if text_tracks is not None and 'data' in text_tracks:
        for track in text_tracks['data']:
            if track['language'] == language_code:
                delete_subtitles(account, video_id, language_code)
    url = get_texttracks_url(video_id)
    data = {"type": "subtitles",
            "language": language_code,
            "name": subtitle_version.get_version_display()}
    response = requests.post(VIMEO_API_BASE_URL + url, data=data,
                             headers=headers)
    if response.ok:
        content = response.json()
        if 'link' in content:
            response = requests.put(content['link'], data=encoded_subtitles,
                                    headers=headers)
            if not response.ok:
                raise APIError(response.text)
    else:
        raise APIError(response.text)

def delete_subtitles(account, video_id, language_code):
    headers = {"Authorization":
               ("Bearer " + account.access_token)}
    text_tracks = get_text_tracks(account, video_id)
    if text_tracks is not None and 'data' in text_tracks:
        for track in text_tracks['data']:
            if track['language'] == language_code:
                response = requests.delete(VIMEO_API_BASE_URL + track['uri'],
                                        headers=headers)
                if response.ok:
                    return
                else:
                    raise APIError(response.text)

def get_values(video_id, user=None, team=None):
    from externalsites.models import VimeoSyncAccount
    accounts = None
    if team:
        accounts = VimeoSyncAccount.objects.for_team_or_synced_with_team(team)
    elif user:
        accounts = VimeoSyncAccount.objects.for_owner(user)
    else:
        accounts = VimeoSyncAccount.objects.none()
    video_url = "/videos/" + video_id
    video_data = None
    for account in accounts:
        headers = {"Authorization":
                   ("Bearer " + account.access_token)}
        response = requests.get(VIMEO_API_BASE_URL + video_url,
                                headers=headers)
        if response.ok:
            video_data = response.json()
            break
    if video_data is None:
        headers = {"Authorization":
                   ("basic " + \
                    base64.b64encode(VIMEO_API_KEY + ":" + VIMEO_API_SECRET))}
        data = {"grant_type": "client_credentials"}
        url = "/oauth/authorize/client"
        response = requests.post(VIMEO_API_BASE_URL + url,
                                 data=data,
                                 headers=headers)
        if response.ok:
            access_token = response.json()['access_token']
            headers = {"Authorization": "Bearer " + access_token}
            response = requests.get(VIMEO_API_BASE_URL + url,
                                    headers=headers)
            if response.ok:
                video_data = response.json()
    if video_data is not None:
        small = large = None
        thumbnail = sorted(video_data['pictures']['sizes'], key=lambda x: -x["width"])[0]['link']
        return (video_data["name"],
                video_data["description"],
                video_data['duration'],
                thumbnail)
    raise Exception("Vimeo API Error")
