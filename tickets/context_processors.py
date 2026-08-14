from django.conf import settings
from django.contrib.auth.models import User
from django.db.models import Count
from django.templatetags.static import static

from .models import AppSettings


def site_settings(request):
    cfg = AppSettings.load()
    logo_url = cfg.logo.url if cfg.logo else static('tickets/img/logo.png')
    return {
        'registration_open': settings.REGISTRATION_OPEN,
        'site_name': cfg.site_name,
        'site_tagline': cfg.tagline,
        'site_footer': cfg.footer_text,
        'site_logo_url': logo_url,
        'primary_color': cfg.primary_color,
    }


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
