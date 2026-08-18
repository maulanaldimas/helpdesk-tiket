import os

import bleach
import markdown

from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
from datetime import timedelta


class Company(models.Model):
    name = models.CharField(max_length=100)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Companies"


class Category(models.Model):
    name = models.CharField(max_length=100)
    description = models.TextField(blank=True)

    def __str__(self):
        return self.name

    class Meta:
        verbose_name_plural = "Categories"


class Profile(models.Model):
    ROLE_CHOICES = [
        ('admin', 'Admin'),
        ('staff', 'Staff'),
        ('requester', 'Requester'),
    ]
    user = models.OneToOneField(User, on_delete=models.CASCADE)
    company = models.ForeignKey(Company, on_delete=models.SET_NULL, null=True, blank=True)
    role = models.CharField(max_length=20, choices=ROLE_CHOICES, default='requester')
    phone = models.CharField(max_length=30, blank=True)
    job_title = models.CharField(max_length=100, blank=True)
    avatar = models.ImageField(upload_to='avatars/', blank=True, null=True)
    pending_approval = models.BooleanField(
        default=False,
        help_text='Menunggu persetujuan admin (dari registrasi mandiri).',
    )

    def avatar_url(self):
        if self.avatar:
            return self.avatar.url
        return None

    def __str__(self):
        return f"{self.user.username} ({self.role})"


class Ticket(models.Model):
    STATUS_CHOICES = [
        ('open', 'Open'),
        ('in_progress', 'In Progress'),
        ('resolved', 'Resolved'),
        ('closed', 'Closed'),
    ]
    PRIORITY_CHOICES = [
        ('low', 'Low'),
        ('medium', 'Medium'),
        ('high', 'High'),
        ('urgent', 'Urgent'),
    ]

    title = models.CharField(max_length=200)
    description = models.TextField()
    company = models.ForeignKey(Company, on_delete=models.CASCADE)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')
    priority = models.CharField(max_length=20, choices=PRIORITY_CHOICES, default='medium')

    created_by = models.ForeignKey(User, on_delete=models.CASCADE, related_name='tickets_created')
    assigned_to = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='tickets_assigned')

    sla_deadline = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    closed_at = models.DateTimeField(null=True, blank=True)
    sla_warning_sent = models.BooleanField(default=False, help_text='Notifikasi mendekati SLA sudah dikirim.')
    sla_overdue_sent = models.BooleanField(default=False, help_text='Notifikasi terlampaui SLA sudah dikirim.')

    def __str__(self):
        return f"#{self.id} - {self.title}"

    SLA_HOURS = {
        'urgent': 4,
        'high': 24,
        'medium': 72,
        'low': 168,
    }

    def save(self, *args, **kwargs):
        if not self.pk and not self.sla_deadline:
            hours = self.SLA_HOURS.get(self.priority, 72)
            self.sla_deadline = timezone.now() + timedelta(hours=hours)

        if self.status in ['resolved', 'closed'] and not self.closed_at:
            self.closed_at = timezone.now()
        elif self.status not in ['resolved', 'closed']:
            self.closed_at = None

        super().save(*args, **kwargs)

    def is_overdue(self):
        if self.status in ['resolved', 'closed']:
            return False
        if not self.sla_deadline:
            return False
        return timezone.now() > self.sla_deadline

    PRIORITY_BORDER = {
        'low': 'border-l-slate-200',
        'medium': 'border-l-sky-400',
        'high': 'border-l-amber-400',
        'urgent': 'border-l-rose-400',
    }

    PRIORITY_BADGE = {
        'low': 'bg-slate-100 text-slate-600',
        'medium': 'bg-sky-50 text-sky-700',
        'high': 'bg-amber-50 text-amber-700',
        'urgent': 'bg-rose-50 text-rose-700',
    }

    STATUS_BADGE = {
        'open': 'bg-emerald-50 text-emerald-700',
        'in_progress': 'bg-sky-50 text-sky-700',
        'resolved': 'bg-slate-100 text-slate-600',
        'closed': 'bg-slate-100 text-slate-500',
    }

    def priority_border_class(self):
        return self.PRIORITY_BORDER.get(self.priority, 'border-l-slate-300')

    def priority_badge_class(self):
        return self.PRIORITY_BADGE.get(self.priority, 'bg-slate-100 text-slate-600')

    def status_badge_class(self):
        return self.STATUS_BADGE.get(self.status, 'bg-slate-100 text-slate-600')

    def is_active(self):
        return self.status in ['open', 'in_progress']


class Comment(models.Model):
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='comments')
    author = models.ForeignKey(User, on_delete=models.CASCADE)
    message = models.TextField()
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Comment by {self.author.username} on Ticket #{self.ticket.id}"


class TicketAttachment(models.Model):
    """Lampiran file pada sebuah tiket (screenshot, log, dokumen, dll)."""
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='attachments')
    file = models.FileField(upload_to='tickets/%Y/%m/%d/')
    uploaded_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    uploaded_at = models.DateTimeField(auto_now_add=True)

    def filename(self):
        return os.path.basename(self.file.name)

    def size_kb(self):
        try:
            return round(self.file.size / 1024)
        except (OSError, ValueError):
            return 0

    def __str__(self):
        return f"Attachment on Ticket #{self.ticket.id}: {self.filename()}"


class Notification(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, related_name='notifications')
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, null=True, blank=True)
    message = models.CharField(max_length=255)
    is_read = models.BooleanField(default=False)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"Notification for {self.user.username}: {self.message}"


class Activity(models.Model):
    ACTION_CHOICES = [
        ('created', 'Dibuat'),
        ('status', 'Perubahan Status'),
        ('assign', 'Penugasan'),
        ('unassign', 'Batalkan Penugasan'),
        ('comment', 'Komentar'),
        ('attachment', 'Lampiran'),
    ]
    ticket = models.ForeignKey(Ticket, on_delete=models.CASCADE, related_name='activities')
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    detail = models.CharField(max_length=255, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"{self.get_action_display()} on Ticket #{self.ticket.id}"


class AppSettings(models.Model):
    """Pengaturan branding aplikasi (singleton, satu baris)."""

    site_name = models.CharField(max_length=100, default='Sokkafiber Helpdesk')
    tagline = models.CharField(max_length=200, blank=True, default='Internal IT Support')
    footer_text = models.CharField(max_length=200, blank=True, default='Sokkafiber Helpdesk · Internal IT Support')
    logo = models.ImageField(upload_to='brand/', blank=True, null=True, help_text='Kosongkan untuk memakai logo bawaan.')
    primary_color = models.CharField(max_length=7, default='#4f46e5', help_text='Warna aksen, format hex (mis. #4f46e5).')

    def save(self, *args, **kwargs):
        self.pk = 1
        super().save(*args, **kwargs)

    @classmethod
    def load(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Pengaturan aplikasi'


class Article(models.Model):
    """Artikel knowledge base / FAQ."""

    # Tag & atribut HTML yang diizinkan setelah render markdown
    ALLOWED_TAGS = [
        'a', 'abbr', 'acronym', 'b', 'blockquote', 'br', 'code', 'div',
        'em', 'h1', 'h2', 'h3', 'h4', 'h5', 'h6', 'hr', 'i', 'img', 'li',
        'ol', 'p', 'pre', 'span', 'strong', 'table', 'tbody', 'td', 'th',
        'thead', 'tr', 'ul',
    ]
    ALLOWED_ATTRS = {'a': ['href', 'title'], 'img': ['src', 'alt', 'title']}

    title = models.CharField(max_length=200)
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, related_name='articles')
    content = models.TextField(help_text='Ditulis dengan Markdown.')
    is_published = models.BooleanField(default=True)
    author = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='articles')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-updated_at']

    def content_html(self):
        """Render isi artikel dari Markdown menjadi HTML yang sudah disanitasi."""
        raw = markdown.markdown(self.content, extensions=['extra', 'fenced_code', 'tables', 'sane_lists'])
        return bleach.clean(raw, tags=self.ALLOWED_TAGS, attributes=self.ALLOWED_ATTRS)

    def __str__(self):
        return self.title


class CannedResponse(models.Model):
    """Jawaban template untuk staff agar respons lebih cepat."""
    title = models.CharField(max_length=100, help_text='Nama singkat untuk judul template.')
    content = models.TextField(help_text='Isi jawaban template. Gunakan {ticket_id} dan {requester} sebagai placeholder.')
    category = models.ForeignKey(Category, on_delete=models.SET_NULL, null=True, blank=True, help_text='Kategori tiket yang cocok.')
    company = models.ForeignKey(Company, on_delete=models.CASCADE, null=True, blank=True, help_text='Kosongkan untuk template global.')
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='canned_responses')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['title']

    def __str__(self):
        return self.title