def unread_notifications(request):
    if request.user.is_authenticated:
        count = request.user.notifications.filter(is_read=False).count()
        return {'unread_notif_count': count}
    return {'unread_notif_count': 0}


def user_is_admin(request):
    user = request.user
    if not user.is_authenticated:
        return {'user_is_admin': False}
    is_admin = user.is_superuser or (
        hasattr(user, 'profile') and user.profile.role == 'admin'
    )
    return {'user_is_admin': is_admin}
