from django.urls import path
from . import views

urlpatterns = [
    path('', views.ticket_list, name='ticket_list'),
    path('dashboard/', views.dashboard, name='dashboard'),
    path('ticket/<int:pk>/', views.ticket_detail, name='ticket_detail'),
    path('ticket/new/', views.ticket_create, name='ticket_create'),
    path('notifications/', views.notification_list, name='notification_list'),

    # Laporan
    path('report/', views.report_page, name='report_page'),
    path('report/export/excel/', views.report_export_excel, name='report_export_excel'),
    path('report/export/pdf/', views.report_export_pdf, name='report_export_pdf'),

    # Master
    path('companies/', views.company_list, name='company_list'),
    path('companies/<int:pk>/delete/', views.company_delete, name='company_delete'),
    path('categories/', views.category_list, name='category_list'),
    path('categories/<int:pk>/delete/', views.category_delete, name='category_delete'),

    # Manajemen user & role
    path('users/', views.user_list, name='user_list'),
    path('users/new/', views.user_create, name='user_create'),
    path('users/<int:pk>/edit/', views.user_edit, name='user_edit'),
    path('users/<int:pk>/delete/', views.user_delete, name='user_delete'),
    path('users/<int:pk>/reset-password/', views.reset_password, name='reset_password'),
    path('account/password/', views.change_password, name='change_password'),

    # Knowledge base / FAQ
    path('kb/', views.article_list, name='article_list'),
    path('kb/<int:pk>/', views.article_detail, name='article_detail'),
    path('kb/new/', views.article_create, name='article_create'),
    path('kb/<int:pk>/edit/', views.article_edit, name='article_edit'),
    path('kb/<int:pk>/delete/', views.article_delete, name='article_delete'),
]
