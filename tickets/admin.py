from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import (
    Activity, AppSettings, Article, AutoAssignRule, Category,
    CannedResponse, Comment, Company, InternalNote, Notification,
    Profile, SatisfactionRating, TimeEntry, Ticket, TicketAttachment,
)


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False
    fields = ('company', 'role', 'phone', 'job_title', 'pending_approval')


class UserAdmin(BaseUserAdmin):
    inlines = [ProfileInline]
    list_display = ('username', 'email', 'first_name', 'last_name', 'is_active', 'is_staff')
    list_filter = ('is_active', 'is_staff', 'profile__role', 'profile__company')
    search_fields = ('username', 'email', 'first_name', 'last_name')


admin.site.unregister(User)
admin.site.register(User, UserAdmin)


@admin.register(Company)
class CompanyAdmin(admin.ModelAdmin):
    list_display = ('name', 'created_at')
    search_fields = ('name',)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description')
    search_fields = ('name',)


@admin.register(Ticket)
class TicketAdmin(admin.ModelAdmin):
    list_display = ('id', 'title', 'company', 'category', 'status', 'priority', 'created_by', 'assigned_to', 'created_at')
    list_filter = ('status', 'priority', 'company', 'category')
    search_fields = ('title', 'description')
    raw_id_fields = ('created_by', 'assigned_to')
    readonly_fields = ('created_at', 'updated_at', 'closed_at', 'first_response_at')
    list_per_page = 25


@admin.register(Comment)
class CommentAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'author', 'message_preview', 'created_at')
    search_fields = ('message',)
    raw_id_fields = ('ticket', 'author')

    def message_preview(self, obj):
        return obj.message[:80] + '...' if len(obj.message) > 80 else obj.message
    message_preview.short_description = 'Pesan'


@admin.register(Notification)
class NotificationAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'ticket', 'message', 'is_read', 'created_at')
    list_filter = ('is_read',)
    raw_id_fields = ('user', 'ticket')


@admin.register(Activity)
class ActivityAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'user', 'action', 'detail', 'created_at')
    list_filter = ('action',)
    raw_id_fields = ('ticket', 'user')


@admin.register(Article)
class ArticleAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'author', 'is_published', 'updated_at')
    list_filter = ('is_published', 'category')
    search_fields = ('title', 'content')
    raw_id_fields = ('author',)


@admin.register(TicketAttachment)
class TicketAttachmentAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'filename', 'uploaded_by', 'uploaded_at')
    raw_id_fields = ('ticket', 'uploaded_by')


@admin.register(InternalNote)
class InternalNoteAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'author', 'message_preview', 'created_at')
    raw_id_fields = ('ticket', 'author')

    def message_preview(self, obj):
        return obj.message[:80] + '...' if len(obj.message) > 80 else obj.message
    message_preview.short_description = 'Pesan'


@admin.register(TimeEntry)
class TimeEntryAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'user', 'description', 'duration_minutes', 'started_at', 'stopped_at')
    raw_id_fields = ('ticket', 'user')


@admin.register(AutoAssignRule)
class AutoAssignRuleAdmin(admin.ModelAdmin):
    list_display = ('name', 'company', 'category', 'priority', 'assign_to', 'is_active')
    list_filter = ('is_active', 'company', 'category')
    raw_id_fields = ('company', 'category', 'assign_to')


@admin.register(CannedResponse)
class CannedResponseAdmin(admin.ModelAdmin):
    list_display = ('title', 'category', 'company', 'created_by', 'created_at')
    list_filter = ('company', 'category')
    search_fields = ('title', 'content')
    raw_id_fields = ('created_by',)


@admin.register(SatisfactionRating)
class SatisfactionRatingAdmin(admin.ModelAdmin):
    list_display = ('id', 'ticket', 'rating', 'comment_preview', 'created_by', 'created_at')
    list_filter = ('rating',)
    raw_id_fields = ('ticket', 'created_by')

    def comment_preview(self, obj):
        return (obj.comment[:60] + '...') if obj.comment and len(obj.comment) > 60 else (obj.comment or '-')
    comment_preview.short_description = 'Komentar'


@admin.register(AppSettings)
class AppSettingsAdmin(admin.ModelAdmin):
    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False

    def has_view_permission(self, request, obj=None):
        return request.user.is_superuser


admin.site.site_header = 'Sokkafiber Helpdesk Admin'
admin.site.site_title = 'Helpdesk Admin'
admin.site.index_title = 'Manajemen'
