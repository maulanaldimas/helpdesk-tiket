import csv
import io
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
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string
from django.core.paginator import Paginator
from django.db.models import Avg, Count, ExpressionWrapper, DurationField, F, Q
from django.http import FileResponse, HttpResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .forms import (
    AppSettingsForm,
    ArticleForm,
    CategoryForm,
    CommentForm,
    CompanyForm,
    ProfileForm,
    RegistrationForm,
    TicketForm,
    UserCreateForm,
    UserEditForm,
)
from .models import Activity, AppSettings, Article, Category, CannedResponse, Company, Notification, Profile, Ticket, TicketAttachment

logger = logging.getLogger('tickets')

MAX_ATTACHMENT_SIZE = 10 * 1024 * 1024  # 10 MB per file


# ---------------------------------------------------------------------------
# Helper
# ---------------------------------------------------------------------------

def save_attachments(ticket, files, user):
    """Simpan daftar lampiran ke tiket; abaikan file yang melebihi batas. Return jumlah tersimpan."""
    count = 0
    for f in files or []:
        if not f:
            continue
        if f.size > MAX_ATTACHMENT_SIZE:
            continue
        TicketAttachment.objects.create(ticket=ticket, file=f, uploaded_by=user)
        count += 1
    return count

def notify(user, ticket, message):
    if not user:
        return
    Notification.objects.create(user=user, ticket=ticket, message=message)


def notify_system(users, message):
    """Kirim notifikasi in-app tanpa keterkaitan tiket (mis. persetujuan akun)."""
    for user in users:
        if user:
            notify(user, None, message)


def notify_many(users, ticket, message):
    """Kirim notifikasi in-app ke setiap user, tapi email cuma sekali per alamat unik."""
    sent_emails = set()
    ctx = {
        'message': message,
        'ticket': ticket,
        'action_url': f"{settings.SITE_URL}/ticket/{ticket.id}/",
        'action_label': 'Lihat Tiket',
        'site_name': 'Helpdesk',
        'site_url': settings.SITE_URL,
        'footer_text': 'Ini email notifikasi otomatis dari helpdesk.',
    }
    subject = f'[Helpdesk] {message}'
    text_body = (
        f'{message}\n\n'
        f'Tiket: #{ticket.id} - {ticket.title}\n'
        f'Company: {ticket.company.name}\n'
        f'Status: {ticket.get_status_display()}\n\n'
        f'Buka: {settings.SITE_URL}/ticket/{ticket.id}/'
    )
    try:
        html_body = render_to_string('emails/notification.html', ctx)
    except Exception:
        html_body = None
    for user in users:
        if not user:
            continue
        notify(user, ticket, message)
        if user.email and user.email not in sent_emails:
            try:
                msg = EmailMultiAlternatives(
                    subject=subject,
                    body=text_body,
                    from_email=settings.DEFAULT_FROM_EMAIL,
                    to=[user.email],
                )
                if html_body:
                    msg.attach_alternative(html_body, 'text/html')
                msg.send(fail_silently=True)
            except Exception:
                pass
            sent_emails.add(user.email)


def log_activity(ticket, user, action, detail=''):
    Activity.objects.create(ticket=ticket, user=user, action=action, detail=detail[:255])


def get_user_tickets(request):
    """QuerySet tiket yang boleh dilihat user sesuai role-nya."""
    profile = request.user.profile
    if request.user.is_superuser:
        return Ticket.objects.all()
    if profile.role in ('admin', 'staff'):
        return Ticket.objects.filter(company=profile.company)
    return Ticket.objects.filter(created_by=request.user)


def get_visible_ticket(request, pk):
    """Ambil tiket yang boleh diakses user; 404 kalau di luar scope-nya."""
    return get_object_or_404(get_user_tickets(request), pk=pk)


def admin_required(user):
    """True jika superuser atau admin perusahaan."""
    if user.is_superuser:
        return True
    return hasattr(user, 'profile') and user.profile.role == 'admin'


def superuser_required(user):
    """Hanya superuser yang boleh (manajemen lintas perusahaan)."""
    return user.is_superuser


@login_required
def protected_media(request, path):
    """Sajikan lampiran tiket hanya untuk user yang boleh mengakses tiketnya."""
    attachment = get_object_or_404(TicketAttachment, file='tickets/' + path)
    get_visible_ticket(request, attachment.ticket_id)
    return FileResponse(attachment.file.open('rb'))


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
        'breadcrumbs': [{'label': 'Daftar Tiket'}],
    })


@login_required
def ticket_detail(request, pk):
    ticket = get_visible_ticket(request, pk)
    profile = request.user.profile
    can_manage = profile.role in ['admin', 'staff']

    if request.method == 'POST':
        if 'comment_submit' in request.POST:
            comment_form = CommentForm(request.POST, request.FILES)
            if comment_form.is_valid():
                comment = comment_form.save(commit=False)
                comment.ticket = ticket
                comment.author = request.user
                comment.save()
                log_activity(ticket, request.user, 'comment', comment.message[:255])

                added = save_attachments(ticket, comment_form.cleaned_data.get('files') or [], request.user)
                if added:
                    log_activity(ticket, request.user, 'attachment', f"{added} file")

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
    attachments = ticket.attachments.order_by('-uploaded_at')

    staff_users = []
    canned_responses = []
    if can_manage:
        staff_users = User.objects.filter(
            profile__role__in=['staff', 'admin'],
            profile__company=ticket.company,
        )
        canned_responses = CannedResponse.objects.filter(
            Q(company=ticket.company) | Q(company__isnull=True)
        ).select_related('category')

    return render(request, 'tickets/ticket_detail.html', {
        'ticket': ticket,
        'comments': comments,
        'activities': activities,
        'attachments': attachments,
        'comment_form': comment_form,
        'can_manage': can_manage,
        'staff_users': staff_users,
        'canned_responses': canned_responses,
        'breadcrumbs': [
            {'label': 'Tiket', 'url': '/'},
            {'label': f'#{ticket.id}'},
        ],
    })


@login_required
def ticket_create(request):
    profile = request.user.profile
    if request.user.is_superuser:
        locked_company = None
    else:
        locked_company = profile.company

    if request.method == 'POST':
        form = TicketForm(request.POST, request.FILES)
        if locked_company:
            form.fields['company'].queryset = Company.objects.filter(id=locked_company.id)
        if form.is_valid():
            ticket = form.save(commit=False)
            ticket.created_by = request.user
            if locked_company:
                ticket.company = locked_company
            ticket.save()
            log_activity(ticket, request.user, 'created', f"Prioritas {ticket.get_priority_display()}")
            added = save_attachments(ticket, form.cleaned_data.get('files') or [], request.user)
            if added:
                log_activity(ticket, request.user, 'attachment', f"{added} file")
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
def import_template(request):
    response = HttpResponse(content_type='text/csv; charset=utf-8')
    response['Content-Disposition'] = 'attachment; filename="template-import-tiket.csv"'
    response.write('\ufeff')
    writer = csv.writer(response)
    writer.writerow(['title', 'description', 'company', 'category', 'priority', 'status'])
    writer.writerow(['Laptop tidak menyala', 'Deskripsi masalah lengkap di sini...',
                     'Sokka Tama Fiber', 'Hardware', 'high', 'open'])
    writer.writerow(['Printer bermasalah', '', 'Sokka Tama Fiber', 'Hardware', 'medium', 'in_progress'])
    return response


@login_required
def import_tickets(request):
    if not admin_required(request.user):
        return redirect('dashboard')

    if request.method == 'POST':
        uploaded = request.FILES.get('file')
        if not uploaded:
            messages.error(request, 'Pilih file CSV terlebih dahulu.')
            return redirect('import_tickets')
        if uploaded.size > 2 * 1024 * 1024:
            messages.error(request, 'File terlalu besar (maks 2 MB).')
            return redirect('import_tickets')
        try:
            decoded = uploaded.read().decode('utf-8-sig')
        except UnicodeDecodeError:
            messages.error(request, 'File harus berformat CSV ber-encoding UTF-8.')
            return redirect('import_tickets')

        reader = csv.DictReader(io.StringIO(decoded))
        valid_priorities = dict(Ticket.PRIORITY_CHOICES)
        valid_statuses = dict(Ticket.STATUS_CHOICES)
        created = 0
        skipped = []

        for idx, row in enumerate(reader, start=2):
            title = (row.get('title') or '').strip()
            company_name = (row.get('company') or '').strip()
            if not title or not company_name:
                skipped.append(f'baris {idx}: judul/company kosong')
                continue
            if request.user.is_superuser:
                company, _ = Company.objects.get_or_create(name=company_name)
            else:
                company = request.user.profile.company
            cat_name = (row.get('category') or '').strip()
            category = None
            if cat_name:
                category = Category.objects.filter(name__iexact=cat_name).first()
                if not category:
                    category = Category.objects.create(name=cat_name)
            priority = (row.get('priority') or 'medium').strip().lower()
            priority = priority if priority in valid_priorities else 'medium'
            status = (row.get('status') or 'open').strip().lower()
            status = status if status in valid_statuses else 'open'
            Ticket.objects.create(
                title=title,
                description=(row.get('description') or '').strip() or '-',
                company=company,
                category=category,
                priority=priority,
                status=status,
                created_by=request.user,
            )
            created += 1

        messages.success(request, f'{created} tiket berhasil diimpor.')
        if skipped:
            messages.error(request, 'Dilewati: ' + '; '.join(skipped[:10]))
        return redirect('ticket_list')

    return render(request, 'tickets/import_tickets.html')


@login_required
def my_dashboard(request):
    """Ringkasan personal: staff melihat tiket yang ditugaskan, requester tiket buatannya."""
    profile = request.user.profile
    if profile.role == 'staff':
        tickets = Ticket.objects.filter(assigned_to=request.user, company=profile.company)
        scope_label = 'tiket yang ditugaskan ke saya'
    else:
        tickets = Ticket.objects.filter(created_by=request.user)
        scope_label = 'tiket yang saya buat'

    total = tickets.count()
    open_count = tickets.filter(status__in=['open', 'in_progress']).count()
    overdue_count = tickets.exclude(status__in=['resolved', 'closed']).filter(
        sla_deadline__lt=timezone.now()
    ).count()
    resolved_count = tickets.filter(status__in=['resolved', 'closed']).count()

    recent = tickets.select_related('company', 'category').order_by('-updated_at')[:5]

    return render(request, 'tickets/my_dashboard.html', {
        'scope_label': scope_label,
        'total': total,
        'open_count': open_count,
        'overdue_count': overdue_count,
        'resolved_count': resolved_count,
        'recent': recent,
        'breadcrumbs': [{'label': 'Ringkasan Saya'}],
    })


@login_required
def notification_list(request):
    notifications = request.user.notifications.all().order_by('-created_at')
    notifications.filter(is_read=False).update(is_read=True)

    paginator = Paginator(notifications, 20)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'tickets/notification_list.html', {'notifications': page_obj})


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

    companies = Company.objects.filter(id=profile.company_id) if not request.user.is_superuser else Company.objects.all()

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
def report_export_csv(request):
    tickets = get_filtered_tickets(request)

    response = HttpResponse(content_type='text/csv; charset=utf-8')
    filename = f"laporan-tiket-{timezone.now().strftime('%Y%m%d-%H%M')}.csv"
    response['Content-Disposition'] = f'attachment; filename="{filename}"'
    response.write('\ufeff')  # BOM agar Excel membaca UTF-8 dengan benar

    writer = csv.writer(response)
    writer.writerow(['ID', 'Judul', 'Company', 'Kategori', 'Status', 'Prioritas',
                     'Dibuat Oleh', 'Assigned To', 'Dibuat Pada', 'SLA Deadline', 'Overdue'])
    for t in tickets:
        writer.writerow([
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
            Ticket.objects.filter(assigned_to__isnull=False, company=profile.company)
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
        'breadcrumbs': [{'label': 'Dashboard'}],
    })


# ---------------------------------------------------------------------------
# Master: Company & Category
# ---------------------------------------------------------------------------

@login_required
def company_list(request):
    if not superuser_required(request.user):
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
    if not superuser_required(request.user):
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
    if not request.user.is_superuser:
        users = users.filter(profile__company=request.user.profile.company)
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

    locked_company = request.user.profile.company if not request.user.is_superuser else None

    if request.method == 'POST':
        form = UserCreateForm(request.POST)
        if locked_company:
            form.fields['company'].queryset = Company.objects.filter(id=locked_company.id)
        if form.is_valid():
            user = form.save()
            if locked_company:
                Profile.objects.filter(user=user).update(company=locked_company)
            messages.success(request, f"User '{form.cleaned_data['username']}' berhasil dibuat.")
            return redirect('user_list')
    else:
        form = UserCreateForm()
        if locked_company:
            form.fields['company'].queryset = Company.objects.filter(id=locked_company.id)

    return render(request, 'tickets/user_form.html', {'form': form, 'title': 'Tambah User'})


@login_required
def user_edit(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if not request.user.is_superuser and user.profile.company != request.user.profile.company:
        return redirect('user_list')
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
    if not request.user.is_superuser and user.profile.company != request.user.profile.company:
        return redirect('user_list')
    if user == request.user:
        messages.error(request, 'Tidak bisa menghapus akun sendiri.')
        return redirect('user_list')

    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f"User '{username}' berhasil dihapus.")
    return redirect('user_list')


def register(request):
    """Registrasi mandiri: akun dibuat nonaktif sampai disetujui admin."""
    if request.user.is_authenticated:
        return redirect('dashboard')

    if not settings.REGISTRATION_OPEN:
        return render(request, 'tickets/register.html', {'registration_closed': True})

    if request.method == 'POST':
        form = RegistrationForm(request.POST)
        if form.is_valid():
            data = form.cleaned_data
            user = User.objects.create_user(
                username=data['username'],
                email=data['email'],
                password=data['password1'],
                first_name=data['first_name'],
                is_active=False,
            )
            Profile.objects.update_or_create(user=user, defaults={
                'company': data['company'],
                'role': 'requester',
                'pending_approval': True,
            })
            admins = User.objects.filter(is_superuser=True) | User.objects.filter(
                profile__role='admin', profile__company=data['company']
            )
            notify_system(admins.distinct(), f"Registrasi baru menunggu persetujuan: {user.username}")
            logger.info("Registrasi baru: %s (menunggu persetujuan)", user.username)
            return render(request, 'tickets/register.html', {'registered': True})
    else:
        form = RegistrationForm()

    return render(request, 'tickets/register.html', {'form': form})


@login_required
def pending_approvals(request):
    if not admin_required(request.user):
        return redirect('dashboard')

    pending = User.objects.filter(profile__pending_approval=True).select_related('profile', 'profile__company')
    if not request.user.is_superuser:
        pending = pending.filter(profile__company=request.user.profile.company)
    return render(request, 'tickets/pending_approvals.html', {'pending': pending})


@login_required
def approve_user(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if not request.user.is_superuser and hasattr(user, 'profile') and user.profile.company != request.user.profile.company:
        return redirect('pending_approvals')
    if request.method == 'POST':
        profile, _ = Profile.objects.get_or_create(user=user)
        profile.pending_approval = False
        profile.save()
        user.profile = profile
        user.is_active = True
        user.save()
        notify_system([user], f"Akun kamu ({user.username}) telah disetujui. Silakan masuk.")
        messages.success(request, f"Akun '{user.username}' disetujui dan aktif.")
    return redirect('pending_approvals')


@login_required
def reject_user(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if not request.user.is_superuser and hasattr(user, 'profile') and user.profile.company != request.user.profile.company:
        return redirect('pending_approvals')
    if request.method == 'POST':
        username = user.username
        user.delete()
        messages.success(request, f"Permintaan '{username}' ditolak dan dihapus.")
    return redirect('pending_approvals')


@login_required
def reset_password(request, pk):
    """Admin mereset password user ke nilai sementara."""
    if not admin_required(request.user):
        return redirect('dashboard')

    user = get_object_or_404(User, pk=pk)
    if not request.user.is_superuser and hasattr(user, 'profile') and user.profile.company != request.user.profile.company:
        return redirect('user_list')
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
def settings_page(request):
    if not superuser_required(request.user):
        return redirect('dashboard')

    cfg = AppSettings.load()
    if request.method == 'POST':
        form = AppSettingsForm(request.POST, request.FILES, instance=cfg)
        if form.is_valid():
            form.save()
            messages.success(request, 'Pengaturan aplikasi disimpan.')
            return redirect('settings_page')
    else:
        form = AppSettingsForm(instance=cfg)

    return render(request, 'tickets/settings_form.html', {'form': form})


@login_required
def profile_page(request):
    profile, _ = Profile.objects.get_or_create(user=request.user)
    if request.method == 'POST':
        form = ProfileForm(request.POST, request.FILES, instance=profile)
        if form.is_valid():
            form.save()
            messages.success(request, 'Profil berhasil diperbarui.')
            return redirect('profile')
    else:
        form = ProfileForm(instance=profile)

    return render(request, 'tickets/profile_form.html', {'form': form, 'profile': profile})


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
@require_POST
def article_preview(request):
    """Render Markdown ke HTML untuk pratinjau di editor artikel."""
    if not admin_required(request.user):
        return redirect('dashboard')
    html = Article(content=request.POST.get('content', '')).content_html()
    return HttpResponse(html)


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


# ---------------------------------------------------------------------------
# Activity Log (audit trail)
# ---------------------------------------------------------------------------

@login_required
def activity_log(request):
    """Halaman audit trail terpusat — superuser lihat semua, admin/staff lihat company sendiri."""
    if not admin_required(request.user):
        return redirect('dashboard')

    activities = Activity.objects.select_related('ticket', 'user', 'ticket__company').order_by('-created_at')
    if not request.user.is_superuser:
        activities = activities.filter(ticket__company=request.user.profile.company)

    action_filter = request.GET.get('action', '')
    if action_filter:
        activities = activities.filter(action=action_filter)

    paginator = Paginator(activities, 30)
    page_obj = paginator.get_page(request.GET.get('page'))

    return render(request, 'tickets/activity_log.html', {
        'activities': page_obj,
        'action_filter': action_filter,
        'action_choices': Activity.ACTION_CHOICES,
    })


# ---------------------------------------------------------------------------
# Canned Responses (jawaban template)
# ---------------------------------------------------------------------------

@login_required
def canned_response_list(request):
    if not admin_required(request.user):
        return redirect('dashboard')

    profile = request.user.profile
    if request.user.is_superuser:
        responses = CannedResponse.objects.select_related('category', 'company').all()
    else:
        responses = CannedResponse.objects.select_related('category', 'company').filter(
            Q(company=profile.company) | Q(company__isnull=True)
        )

    if request.method == 'POST':
        title = request.POST.get('title', '').strip()
        content = request.POST.get('content', '').strip()
        category_id = request.POST.get('category', '')
        company_id = request.POST.get('company', '')
        if not title or not content:
            messages.error(request, 'Judul dan isi wajib diisi.')
        else:
            CannedResponse.objects.create(
                title=title,
                content=content,
                category_id=category_id or None,
                company_id=company_id or None,
                created_by=request.user,
            )
            messages.success(request, 'Template jawaban berhasil dibuat.')
            return redirect('canned_response_list')

    return render(request, 'tickets/canned_response_list.html', {
        'responses': responses,
        'categories': Category.objects.all(),
        'companies': Company.objects.all(),
    })


@login_required
def canned_response_edit(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    response = get_object_or_404(CannedResponse, pk=pk)
    if request.method == 'POST':
        response.title = request.POST.get('title', response.title).strip()
        response.content = request.POST.get('content', response.content).strip()
        response.category_id = request.POST.get('category') or None
        response.company_id = request.POST.get('company') or None
        response.save()
        messages.success(request, 'Template berhasil diupdate.')
        return redirect('canned_response_list')

    return render(request, 'tickets/canned_response_form.html', {
        'response': response,
        'categories': Category.objects.all(),
        'companies': Company.objects.all(),
    })


@login_required
def canned_response_delete(request, pk):
    if not admin_required(request.user):
        return redirect('dashboard')

    if request.method == 'POST':
        CannedResponse.objects.filter(pk=pk).delete()
        messages.success(request, 'Template berhasil dihapus.')
    return redirect('canned_response_list')
