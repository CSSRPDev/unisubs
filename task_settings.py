# Amara, universalsubtitles.org
# 
# Copyright (C) 2014 Participatory Culture Foundation
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

"""periodic_task_settings -- settings for celery periodic tasks."""

from datetime import timedelta

from celery.schedules import crontab
from kombu import Exchange, Queue

CELERY_QUEUES = (
    Queue('default', routing_key='default'),
    Queue('priority', routing_key='priority'),
    Queue('feeds', routing_key='feeds'),
)

CELERY_DEFAULT_QUEUE = "default"

CELERYBEAT_SCHEDULE = {
    'expire-tasks': {
        'task': 'teams.tasks.expire_tasks',
        'schedule': crontab(minute=0, hour=7),
    },
    'expire-login-tokens': {
        'task': 'auth.tasks.expire_login_tokens',
        'schedule': crontab(minute=10, hour=23),
    },
    'add_videos_notification_daily': {
        'task': 'teams.tasks.add_videos_notification_daily',
        'schedule': crontab(minute=0, hour=23),
    },
    'add_videos_notification_hourly': {
        'task': 'teams.tasks.add_videos_notification_hourly',
        'schedule': crontab(minute=0),
    },
    'cleanup_videos': {
        'task': 'videos.tasks.cleanup',
        'schedule': crontab(hour=3, day_of_week=1),
    },
    'create_missing_video_index_objects': {
        'task': 'videos.tasks.create_missing_index_objects',
        'schedule': crontab(minute=2),
    },
    'update_feeds': {
        'task': 'videos.tasks.update_from_feed',
        'schedule': crontab(minute=0),
    },
    'import_from_accounts': {
        'task': 'externalsites.tasks.import_videos_from_accounts',
        'schedule': crontab(minute=0),
    },
    'retry_failed_sync': {
        'task': 'externalsites.tasks.retry_failed_sync',
        'schedule': timedelta(seconds=10),
    },
    'prune_notification_history': {
        'task': 'notifications.tasks.prune_notification_history',
        'schedule': crontab(hour=0),
    },
}

__all__ = ['CELERYBEAT_SCHEDULE', 'CELERY_QUEUES', 'CELERY_DEFAULT_QUEUE', ]
