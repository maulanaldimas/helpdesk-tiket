from django.contrib import admin
from django.urls import path, include
from django.contrib.auth import views as auth_views


class BrandLoginView(auth_views.LoginView):
    """LoginView tanpa override site_name — biarkan context processor yang handle."""

    def get_context_data(self, **kwargs):
        ctx = super().get_context_data(**kwargs)
        ctx.pop('site_name', None)
        return ctx


urlpatterns = [
    path('admin/', admin.site.urls),
    path('login/', BrandLoginView.as_view(template_name='tickets/login.html', redirect_authenticated_user=True), name='login'),
    path('logout/', auth_views.LogoutView.as_view(next_page='login'), name='logout'),
    path('', include('tickets.urls')),
]