from django.contrib import admin
from .models import Company, Category, Profile, Ticket, Comment, Notification, Activity, Article, TicketAttachment

admin.site.register(Company)
admin.site.register(Category)
admin.site.register(Profile)
admin.site.register(Ticket)
admin.site.register(Comment)
admin.site.register(Notification)
admin.site.register(Activity)
admin.site.register(Article)
admin.site.register(TicketAttachment)