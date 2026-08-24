from django.urls import path
from . import views

urlpatterns = [
    path('', views.dashboard, name='dashboard'),
    path('register/', views.register, name='register'),
    path('tickets/', views.ticket_list, name='ticket_list'),
    path('dashboard/saya/', views.my_dashboard, name='my_dashboard'),
    path('ticket/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('ticket/<int:pk>/merge/', views.ticket_merge, name='ticket_merge'),
    path('ticket/<int:pk>/print/', views.ticket_print_pdf, name='ticket_print_pdf'),
    path('ticket/new/', views.ticket_create, name='ticket_create'),
    path('tickets/import/', views.import_tickets, name='import_tickets'),
    path('tickets/import/template/', views.import_template, name='import_template'),
    path('notifications/', views.notification_list, name='notification_list'),

    # Lampiran tiket (hanya untuk user dengan akses tiket)
    path('media/tickets/<path:path>', views.protected_media, name='protected_media'),

    # Laporan
    path('report/', views.report_page, name='report_page'),
    path('report/export/excel/', views.report_export_excel, name='report_export_excel'),
    path('report/export/csv/', views.report_export_csv, name='report_export_csv'),
    path('report/export/pdf/', views.report_export_pdf, name='report_export_pdf'),

    # Master
    path('companies/', views.company_list, name='company_list'),
    path('companies/<int:pk>/delete/', views.company_delete, name='company_delete'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),

    # Manajemen user & role
    path('users/', views.user_list, name='user_list'),
    path('users/pending/', views.pending_approvals, name='pending_approvals'),
    path('users/pending/<int:pk>/approve/', views.approve_user, name='approve_user'),
    path('users/pending/<int:pk>/reject/', views.reject_user, name='reject_user'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:pk>/reset-password/', views.reset_password, name='reset_password'),
    path('account/', views.profile_page, name='profile'),
    path('account/password/', views.change_password, name='change_password'),
    path('settings/', views.settings_page, name='settings_page'),

    # Knowledge base / FAQ
    path('kb/', views.article_list, name='article_list'),
    path('kb/preview/', views.article_preview, name='article_preview'),
    path('kb/<int:pk>/', views.article_detail, name='article_detail'),
    path('kb/new/', views.article_create, name='article_create'),
    path('kb/<int:pk>/edit/', views.article_edit, name='article_edit'),
    path('kb/<int:pk>/delete/', views.article_delete, name='article_delete'),

    # Activity log
    path('activity/', views.activity_log, name='activity_log'),

    # Canned responses
    path('templates/', views.canned_response_list, name='canned_response_list'),
    path('templates/<int:pk>/edit/', views.canned_response_edit, name='canned_response_edit'),
    path('templates/<int:pk>/delete/', views.canned_response_delete, name='canned_response_delete'),

    # Auto-assignment rules
    path('auto-assign/', views.auto_assign_rules, name='auto_assign_rules'),
    path('auto-assign/<int:pk>/delete/', views.auto_assign_rule_delete, name='auto_assign_rule_delete'),

    # API — real-time notifications
    path('api/notifications/', views.api_notifications, name='api_notifications'),
    path('api/notifications/mark-read/', views.api_mark_notifications_read, name='api_mark_notifications_read'),

    # Audit log export
    path('activity/export/excel/', views.activity_export_excel, name='activity_export_excel'),
    path('activity/export/csv/', views.activity_export_csv, name='activity_export_csv'),
    path('activity/export/pdf/', views.activity_export_pdf, name='activity_export_pdf'),

    # SLA escalation
    path('sla/escalations/', views.sla_escalation_log, name='sla_escalation_log'),
]
