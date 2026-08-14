import logging
from datetime import timedelta

import openpyxl
from openpyxl.styles import Font, PatternFill
from reportlab.lib import colors
from reportlab.lib.pagesizes import A4, landscape
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.lib.units import cm
from reportlab.platypus import SimpleDocTemplate, Table, TableStyle, Paragraph

from django.conf import settings
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.contrib.auth.forms import PasswordChangeForm
from django.contrib.auth.models import User
from django.contrib.auth import update_session_auth_hash
from django.core.mail import send_mail
from django.core.paginator import Paginator
from django.db.models import Avg, Count, ExpressionWrapper, DurationField, F, Q
from django.http import HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone

from .forms import (
    ArticleForm,
    CategoryForm,
    CommentForm,
    CompanyForm,
    TicketForm,
    UserCreateForm,
    UserEditForm,
)
from .models import Activity, Article, Category, Company, Notification, Profile, Ticket

logger = logging.getLogger('tickets')


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def notify(user, ticket, message):
    if not user:
        return
    Notification.objects.create(user=user, ticket=ticket, message=message)


def notify_many(users, ticket, message):
    """Kirim notifikasi in-app ke setiap user, tapi email cuma sekali per alamat unik."""
    sent_emails = set()
    for user in users:
        if not user:
            continue
        notify(user, ticket, message)
        if user.email and user.email not in sent_emails:
            send_mail(
                subject=f'[Helpdesk] {message}',
                message=(
                    f'{message}\n\n'
                    f'Tiket: #{ticket.id} - {ticket.title}\n'
                    f'Company: {ticket.company.name}\n'
                    f'Status: {ticket.get_status_display()}\n\n'
                    f'Buka: {settings.SITE_URL}/ticket/{ticket.id}/'
                ),
                from_email=settings.DEFAULT_FROM_EMAIL,
                recipient_list=[user.email],
                fail_silently=True,
            )
            sent_emails.add(user.email)


def log_activity(ticket, user, action, detail=''):
    Activity.objects.create(ticket=ticket, user=user, action=action, detail=detail[:255])


def get_user_tickets(request):
    """QuerySet tiket yang boleh dilihat user sesuai role-nya."""
    profile = request.user.profile
    if request.user.is_superuser or profile.role == 'admin':
        return Ticket.objects.all()
    if profile.role == 'staff':
        return Ticket.objects.filter(company=profile.company)
    return Ticket.objects.filter(created_by=request.user)


def get_visible_ticket(request, pk):
    """Ambil tiket yang boleh diakses user; 404 kalau di luar scope-nya."""
    return get_object_or_404(get_user_tickets(request), pk=pk)


def admin_required(user):
    if user.is_superuser:
        return True
    return hasattr(user, 'profile') and user.profile.role == 'admin'


# ---------------------------------------------------------------------------
# Ticket
# ---------------------------------------------------------------------------

@login_required
def ticket_list(request):
    tickets = get_user_tickets(request)

    query = request.GET.get('q', '').strip()
    if query:
        tickets = tickets.filter(
            Q(title__icontains=query) | Q(description__icontains=query)
        )

    tickets = tickets.select_related('company', 'category').order_by('-created_at')

    paginator = Paginator(tickets, 10)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)

    return render(request, 'tickets/ticket_list.html', {
        'tickets': page_obj,
        'query': query,
    })


@login_required
def ticket_detail(request, pk):
    ticket = get_visible_ticket(request, pk)
    profile = request.user.profile
    can_manage = profile.role in ['admin', 'staff']

    if request.method == 'POST':
        if 'comment_submit' in request.POST:
            comment_form = CommentForm(request.POST)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.ticket = ticket
                comment.author = request.user
                comment.save()
                log_activity(ticket, request.user, 'comment', comment.message[:255])

                recipients = {ticket.created_by, ticket.assigned_to}
                recipients.discard(request.user)
                recipients.discard(None)
                notify_many(recipients, ticket, f"{request.user.username} menambahkan komentar di tiket #{ticket.id}")

                return redirect('ticket_detail', pk=ticket.pk)

        elif 'status_submit' in request.POST and can_manage:
            new_status = request.POST.get('status')
            valid_statuses = dict(Ticket.STATUS_CHOICES)
            if new_status in valid_statuses and new_status != ticket.status:
                old_display = ticket.get_status_display()
                ticket.status = new_status
                ticket.save()
                log_activity(
                    ticket, request.user, 'status',
                    f"{old_display} -> {ticket.get_status_display()}",
                )
                notify_many({ticket.created_by}, ticket, f"Status tiket #{ticket.id} diubah menjadi {ticket.get_status_display()}")
                return redirect('ticket_detail', pk=ticket.pk)

        elif 'assign_submit' in request.POST and can_manage:
            assignee_id = request.POST.get('assigned_to')
            previous = ticket.assigned_to
            if assignee_id:
                ticket.assigned_to_id = assignee_id
                action = 'assign'
            else:
                ticket.assigned_to = None
                action = 'unassign'
            ticket.save()
            if ticket.assigned_to:
                log_activity(ticket, request.user, action, f"ke {ticket.assigned_to.username}")
                notify_many({ticket.assigned_to}, ticket, f"Kamu ditugaskan ke tiket #{ticket.id}")
            else:
                log_activity(ticket, request.user, action, f"dari {previous.username}" if previous else '')
            return redirect('ticket_detail', pk=ticket.pk)

    comment_form = CommentForm()
    comments = ticket.comments.all().order_by('created_at')
    activities = ticket.activities.select_related('user').order_by('-created_at')[:30]

    staff_users = []
    if can_manage:
        staff_users = User.objects.filter(profile__role__in=['staff', 'admin'])

    return render(request, 'tickets/ticket_detail.html', {
        'ticket': ticket,
        'comments': comments,
        'activities': activities,
        'comment_form': comment_form,
        'can_manage': can_manage,
        'staff_users': staff_users,
    })


@login_required
def ticket_create(request):
    profile = request.user.profile
    locked_company = profile.company if profile.role != 'admin' else None

    if request.method == 'POST':
        form = TicketForm(request.POST)
        if locked_company:
            form.fields['company'].queryset = Company.objects.filter(id=locked_company.id)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.created_by = request.user
            if locked_company:
                ticket.company = locked_company
            ticket.save()
            log_activity(ticket, request.user, 'created', f"Prioritas {ticket.get_priority_display()}")
            logger.info("Ticket #%s dibuat oleh %s", ticket.id, request.user.username)
            return redirect('ticket_detail', pk=ticket.pk)
    else:
        initial = {}
        if locked_company:
            initial['company'] = locked_company
        form = TicketForm(initial=initial)
        if locked_company:
            form.fields['company'].queryset = Company.objects.filter(id=locked_company.id)
    return render(request, 'tickets/ticket_form.html', {
        'form': form,
        'locked_company': locked_company,
    })


@login_required
def notification_list(request):
    notifications = request.user.notifications.all().order_by('-created_at')
    notifications.filter(is_read=False).update(is_read=True)
    return render(request, 'tickets/notification_list.html', {'notifications': notifications})


# ---------------------------------------------------------------------------
# Laporan
# ---------------------------------------------------------------------------

def get_filtered_tickets(request):
    """Ambil tiket sesuai role, lalu terapkan filter dari query string."""
    tickets = get_user_tickets(request)

    status = request.GET.get('status')
    priority = request.GET.get('priority')
    company_id = request.GET.get('company')

    if status:
        tickets = tickets.filter(status=status)
    if priority:
        tickets = tickets.filter(priority=priority)
    if company_id:
        tickets = tickets.filter(company_id=company_id)

    return tickets.select_related('company', 'category', 'created_by', 'assigned_to').order_by('-created_at')


@login_required
def report_page(request):
    tickets = get_filtered_tickets(request)
    profile = request.user.profile

    companies = Company.objects.all() if profile.role == 'admin' else Company.objects.filter(id=profile.company_id)

    return render(request, 'tickets/report.html', {
        'tickets': tickets,
        'companies': companies,
        'status_choices': Ticket.STATUS_CHOICES,
        'priority_choices': Ticket.PRIORITY_CHOICES,
    })


@login_required
def report_export_excel(request):
    tickets = get_filtered_tickets(request)

    wb = openpyxl.Workbook()
    ws = wb.active
    ws.title = "Laporan Tiket"

    headers = ['ID', 'Judul', 'Company', 'Kategori', 'Status', 'Prioritas', 'Dibuat Oleh', 'Assigned To', 'Dibuat Pada', 'SLA Deadline', 'Overdue']
    ws.append(headers)

    header_fill = PatternFill(start_color='1E293B', end_color='1E293B', fill_type='solid')
    header_font = Font(color='FFFFFF', bold=True)
    for cell in ws[1]:
        cell.fill = header_fill
        cell.font = header_font

    for t in tickets:
        ws.append([
            t.id,
            t.title,
            t.company.name,
            t.category.name if t.category else '-',
            t.get_status_display(),
            t.get_priority_display(),
            t.created_by.username,
            t.assigned_to.username if t.assigned_to else '-',
            t.created_at.strftime('%Y-%m-%d %H:%M'),
            t.sla_deadline.strftime('%Y-%m-%d %H:%M') if t.sla_deadline else '-',
            'Ya' if t.is_overdue() else 'Tidak',
        ])

    for col in ws.columns:
        max_len = max(len(str(cell.value)) if cell.value else 0 for cell in col)
        ws.column_dimensions[col[0].column_letter].width = min(max_len + 3, 40)

    response = HttpResponse(content_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
    filename = f"laporan-tiket-{timezone.now().strftime('%Y%m%d-%H%M')}.xlsx"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    wb.save(response)
    return response


@login_required
def report_export_pdf(request):
    tickets = get_filtered_tickets(request)

    response = HttpResponse(content_type='application/pdf')
    filename = f"laporan-tiket-{timezone.now().strftime('%Y%m%d-%H%M')}.pdf"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'

    doc = SimpleDocTemplate(response, pagesize=landscape(A4), topMargin=1.5*cm, bottomMargin=1.5*cm)
    styles = getSampleStyleSheet()
    elements = [Paragraph("Laporan Tiket Helpdesk - Sokkafiber", styles['Title'])]
    elements.append(Paragraph(f"Dicetak: {timezone.now().strftime('%d %B %Y %H:%M')}", styles['Normal']))
    elements.append(Paragraph(" ", styles['Normal']))

    data = [['ID', 'Judul', 'Company', 'Status', 'Prioritas', 'Assigned To', 'Dibuat Pada', 'Overdue']]
    for t in tickets:
        data.append([
            str(t.id),
            t.title[:30],
            t.company.name,
            t.get_status_display(),
            t.get_priority_display(),
            t.assigned_to.username if t.assigned_to else '-',
            t.created_at.strftime('%d/%m/%Y'),
            'Ya' if t.is_overdue() else 'Tidak',
        ])

    table = Table(data, repeatRows=1)
    table.setStyle(TableStyle([
        ('BACKGROUND', (0, 0), (-1, 0), colors.HexColor('#1E293B')),
        ('TEXTCOLOR', (0, 0), (-1, 0), colors.white),
        ('FONTSIZE', (0, 0), (-1, -1), 8),
        ('GRID', (0, 0), (-1, -1), 0.5, colors.HexColor('#CBD5E1')),
        ('ROWBACKGROUNDS', (0, 1), (-1, -1), [colors.white, colors.HexColor('#F8FAFC')]),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('TOPPADDING', (0, 0), (-1, -1), 6),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 6),
    ]))
    elements.append(table)

    doc.build(elements)
    return response


# ---------------------------------------------------------------------------
# Dashboard
# ---------------------------------------------------------------------------

@login_required
def dashboard(request):
    profile = request.user.profile
    tickets = get_user_tickets(request)

    total = tickets.count()

    status_counts = {value: tickets.filter(status=value).count() for value, label in Ticket.STATUS_CHOICES}
    priority_counts = {value: tickets.filter(priority=value).count() for value, label in Ticket.PRIORITY_CHOICES}

    status_data = [
        {'value': value, 'label': label, 'count': status_counts.get(value, 0)}
        for value, label in Ticket.STATUS_CHOICES
    ]
    priority_data = [
        {'value': value, 'label': label, 'count': priority_counts.get(value, 0)}
        for value, label in Ticket.PRIORITY_CHOICES
    ]

    overdue_count = tickets.exclude(status__in=['resolved', 'closed']).filter(
        sla_deadline__lt=timezone.now()
    ).count()

    category_breakdown = (
        tickets.values('category__name')
        .annotate(count=Count('id'))
        .order_by('-count')[:5]
    )

    # SLA compliance & rata-rata waktu penyelesaian
    closed_qs = tickets.filter(status__in=['resolved', 'closed'])
    total_closed = closed_qs.count()
    on_time_count = sum(
        1 for t in closed_qs.only('closed_at', 'sla_deadline')
        if t.closed_at and t.sla_deadline and t.closed_at <= t.sla_deadline
    )
    sla_compliance = round(on_time_count / total_closed * 100) if total_closed else 0

    avg_duration = closed_qs.filter(closed_at__isnull=False).annotate(
        dur=ExpressionWrapper(F('closed_at') - F('created_at'), output_field=DurationField())
    ).aggregate(avg=Avg('dur'))['avg']
    avg_resolution_hours = round(avg_duration.total_seconds() / 3600, 1) if avg_duration else 0

    # Tren 14 hari terakhir
    trend_labels, trend_counts = [], []
    today = timezone.localdate()
    for i in range(13, -1, -1):
        day = today - timedelta(days=i)
        trend_labels.append(day.strftime('%d/%m'))
        trend_counts.append(tickets.filter(created_at__date=day).count())

    # Beban per staff (admin)
    staff_workload = []
    if profile.role == 'admin':
        staff_workload = list(
            Ticket.objects.filter(assigned_to__isnull=False)
            .values('assigned_to__username', 'assigned_to_id')
            .annotate(total=Count('id'))
            .order_by('-total')
        )

    recent_tickets = tickets.select_related('company', 'category').order_by('-created_at')[:5]

    return render(request, 'tickets/dashboard.html', {
        'total': total,
        'status_counts': status_counts,
        'priority_counts': priority_counts,
        'status_data': status_data,
        'priority_data': priority_data,
        'overdue_count': overdue_count,
        'category_breakdown': category_breakdown,
        'sla_compliance': sla_compliance,
        'avg_resolution_hours': avg_resolution_hours,
        'trend_labels': trend_labels,
        'trend_counts': trend_counts,
        'staff_workload': staff_workload,
        'recent_tickets': recent_tickets,
    })


# ---------------------------------------------------------------------------
# Master: Company & Category
# ---------------------------------------------------------------------------

@login_required
def company_list(request):
    if not admin_required(request.user):
        return redirect('dashboard')

    if request.method == 'POST':
        form = CompanyForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Company berhasil ditambahkan.')
            return redirect('company_list')
    else:
        form = CompanyForm()

    companies = Company.objects.all().order_by('name')
    return render(request, 'tickets/company_list.html', {'companies': companies, 'form': form})


@login_required
def company_delete(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    company = get_object_or_404(Company, pk=pk)
    if request.method == 'POST':
        company.delete()
        messages.success(request, 'Company berhasil dihapus.')
    return redirect('company_list')


@login_required
def category_list(request):
    if not admin_required(request.user):
        return redirect('dashboard')

    if request.method == 'POST':
        form = CategoryForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, 'Kategori berhasil ditambahkan.')
            return redirect('category_list')
    else:
        form = CategoryForm()

    categories = Category.objects.all().order_by('name')
    return render(request, 'tickets/category_list.html', {'categories': categories, 'form': form})


@login_required
def category_delete(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    category = get_object_or_404(Category, pk=pk)
    if request.method == 'POST':
        category.delete()
        messages.success(request, 'Kategori berhasil dihapus.')
    return redirect('category_list')


# ---------------------------------------------------------------------------
# Manajemen User & Role
# ---------------------------------------------------------------------------

@login_required
def user_list(request):
    if not admin_required(request.user):
        return redirect('dashboard')

    role_filter = request.GET.get('role', '')
    users = User.objects.select_related('profile', 'profile__company').all()
    if role_filter:
        users = users.filter(profile__role=role_filter)

    return render(request, 'tickets/user_list.html', {
        'users': users,
        'role_filter': role_filter,
        'role_choices': [('', 'Semua')] + Profile.ROLE_CHOICES,
    })


@login_required
def user_create(request):
    if not admin_required(request.user):
        return redirect('dashboard')

    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, f"User '{form.cleaned_data['username']}' berhasil dibuat.")
            return redirect('user_list')
    else:
        form = UserCreateForm()

    return render(request, 'tickets/user_form.html', {'form': form, 'title': 'Tambah User'})


@login_required
def user_edit(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        form = UserEditForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, f"User '{user.username}' berhasil diupdate.")
            return redirect('user_list')
    else:
        form = UserEditForm(instance=user)

    return render(request, 'tickets/user_form.html', {'form': form, 'title': f'Edit User: {user.username}'})


@login_required
def user_delete(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if user == request.user:
        messages.error(request, 'Tidak bisa menghapus akun sendiri.')
        return redirect('user_list')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f"User '{username}' berhasil dihapus.")
    return redirect('user_list')


@login_required
def reset_password(request, pk):
    """Admin mereset password user ke nilai sementara."""
    if not admin_required(request.user):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if request.method == 'POST':
        new_password = request.POST.get('new_password', '').strip()
        if len(new_password) < 8:
            messages.error(request, 'Password minimal 8 karakter.')
        else:
            user.set_password(new_password)
            user.save()
            messages.success(request, f"Password untuk '{user.username}' berhasil direset.")
            return redirect('user_list')
    return render(request, 'tickets/reset_password.html', {'target_user': user})


@login_required
def change_password(request):
    if request.method == 'POST':
        form = PasswordChangeForm(request.user, request.POST)
        if form.is_valid():
            form.save()
            update_session_auth_hash(request, form.user)
            messages.success(request, 'Password berhasil diubah.')
            return redirect('dashboard')
    else:
        form = PasswordChangeForm(request.user)
    return render(request, 'tickets/change_password.html', {'form': form})


# ---------------------------------------------------------------------------
# Knowledge Base / FAQ
# ---------------------------------------------------------------------------

def article_list(request):
    articles = Article.objects.filter(is_published=True)

    query = request.GET.get('q', '').strip()
    category_id = request.GET.get('category', '')
    if query:
        articles = articles.filter(
            Q(title__icontains=query) | Q(content__icontains=query)
        )
    if category_id:
        articles = articles.filter(category_id=category_id)

    paginator = Paginator(articles.select_related('category', 'author'), 12)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'tickets/article_list.html', {
        'articles': page_obj,
        'query': query,
        'categories': Category.objects.all(),
        'selected_category': category_id,
    })


def article_detail(request, pk):
    article = get_object_or_404(
        Article.objects.select_related('author', 'category'),
        pk=pk,
        is_published=True,
    )
    related = (
        Article.objects.filter(is_published=True)
        .exclude(pk=article.pk)
        .order_by('-updated_at')[:5]
    )
    return render(request, 'tickets/article_detail.html', {
        'article': article,
        'related': related,
    })


@login_required
def article_create(request):
    if not admin_required(request.user):
        return redirect('dashboard')

    if request.method == 'POST':
        form = ArticleForm(request.POST)
        if form.is_valid():
            article = form.save(commit=False)
            article.author = request.user
            article.save()
            messages.success(request, 'Artikel berhasil dipublikasikan.')
            return redirect('article_detail', pk=article.pk)
    else:
        form = ArticleForm()

    return render(request, 'tickets/article_form.html', {'form': form, 'title': 'Tulis Artikel'})


@login_required
def article_edit(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    article = get_object_or_404(Article, pk=pk)
    if request.method == 'POST':
        form = ArticleForm(request.POST, instance=article)
        if form.is_valid():
            form.save()
            messages.success(request, 'Artikel berhasil diupdate.')
            return redirect('article_detail', pk=article.pk)
    else:
        form = ArticleForm(instance=article)

    return render(request, 'tickets/article_form.html', {'form': form, 'title': f'Edit Artikel: {article.title}'})


@login_required
def article_delete(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    article = get_object_or_404(Article, pk=pk)
    if request.method == 'POST':
        article.delete()
        messages.success(request, 'Artikel berhasil dihapus.')
    return redirect('article_list')
