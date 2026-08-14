from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count


def site_settings(request):
    return {'registration_open': settings.REGISTRATION_OPEN}


def unread_notifications(request):
    if request.user.is_authenticated:
        count = request.user.notifications.filter(is_read=False).count()
        return {'unread_notif_count': count}
    return {'unread_notif_count': 0}


def user_is_admin(request):
    user = request.user
    if not user.is_authenticated:
        return {'user_is_admin': False, 'pending_approval_count': 0}
    is_admin = user.is_superuser or (
        hasattr(user, 'profile') and user.profile.role == 'admin'
    )
    pending_count = 0
    if is_admin:
        pending_count = User.objects.filter(profile__pending_approval=True).count()
    return {'user_is_admin': is_admin, 'pending_approval_count': pending_count}
