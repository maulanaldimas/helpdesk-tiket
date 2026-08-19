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
    path('password-reset/', auth_views.PasswordResetView.as_view(
        template_name='tickets/password_reset.html',
        email_template_name='tickets/emails/password_reset.html',
        subject_template_name='tickets/emails/password_reset_subject.txt',
        from_email=None,
        success_url='/password-reset/done/',
    ), name='password_reset'),
    path('password-reset/done/', auth_views.PasswordResetDoneView.as_view(
        template_name='tickets/password_reset_done.html',
    ), name='password_reset_done'),
    path('password-reset/<uidb64>/<token>/', auth_views.PasswordResetConfirmView.as_view(
        template_name='tickets/password_reset_confirm.html',
        success_url='/password-reset/complete/',
    ), name='password_reset_confirm'),
    path('password-reset/complete/', auth_views.PasswordResetCompleteView.as_view(
        template_name='tickets/password_reset_complete.html',
    ), name='password_reset_complete'),
    path('', include('tickets.urls')),
]
