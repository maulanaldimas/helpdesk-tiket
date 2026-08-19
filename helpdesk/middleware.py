import time

from django.conf import settings
from django.contrib.auth import logout
from django.contrib import messages
from django.shortcuts import redirect
from django.utils.deprecation import MiddlewareMixin


class IdleSessionMiddleware(MiddlewareMixin):
    """Logout user jika tidak ada aktivitas selama IDLE_TIMEOUT detik."""

    EXEMPT_URL_NAMES = {
        'login', 'logout', 'register',
    }
    EXEMPT_PATH_PREFIXES = ('/admin/',)

    def process_request(self, request):
        if not request.user.is_authenticated:
            return None

        path = request.path.rstrip('/')
        if request.resolver_match and request.resolver_match.url_name in self.EXEMPT_URL_NAMES:
            return None
        for prefix in self.EXEMPT_PATH_PREFIXES:
            if request.path.startswith(prefix):
                return None

        idle_limit = getattr(settings, 'IDLE_TIMEOUT', 1800)
        if idle_limit <= 0:
            return None

        last = request.session.get('_last_activity')
        now = time.time()

        if last and (now - last) > idle_limit:
            logout(request)
            messages.warning(request, 'Sesi telah berakhir karena tidak ada aktivitas. Silakan masuk kembali.')
            return redirect(settings.LOGIN_URL)

        request.session['_last_activity'] = now
        return None
