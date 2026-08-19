from datetime import timedelta
import time
from unittest.mock import patch

from django.contrib.auth.models import User
from django.test import TestCase, override_settings
from django.urls import reverse
from django.utils import timezone

from .models import Activity, AppSettings, Article, Category, Company, Profile, Ticket


def make_user(username, role, company=None, password='pass12345'):
    user = User.objects.create_user(
        username=username, password=password, email=f'{username}@test.com',
    )
    profile = user.profile
    profile.role = role
    profile.company = company
    profile.save()
    return user


def make_ticket(created_by, company, category, priority='medium', status='open', **kwargs):
    return Ticket.objects.create(
        title='Tiket uji',
        description='Deskripsi uji',
        company=company,
        category=category,
        priority=priority,
        status=status,
        created_by=created_by,
        **kwargs,
    )


class ModelTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.category = Category.objects.create(name='Software')
        self.user = make_user('requester1', 'requester', self.company)
        self.staff = make_user('staff1', 'staff', self.company)

    def test_profile_auto_created(self):
        u = User.objects.create_user('bare', 'pass12345')
        self.assertTrue(hasattr(u, 'profile'))
        self.assertEqual(u.profile.role, 'requester')

    def test_sla_deadline_set_on_create(self):
        ticket = make_ticket(self.user, self.company, self.category, priority='urgent')
        self.assertIsNotNone(ticket.sla_deadline)
        # urgent = 4 jam
        diff = ticket.sla_deadline - ticket.created_at
        self.assertAlmostEqual(diff.total_seconds(), 4 * 3600, delta=60)

    def test_sla_not_overwritten_on_update(self):
        ticket = make_ticket(self.user, self.company, self.category, priority='low')
        original = ticket.sla_deadline
        ticket.status = 'in_progress'
        ticket.save()
        ticket.refresh_from_db()
        self.assertEqual(ticket.sla_deadline, original)

    def test_overdue(self):
        ticket = make_ticket(self.user, self.company, self.category)
        ticket.sla_deadline = timezone.now() - timedelta(hours=1)
        ticket.save()
        self.assertTrue(ticket.is_overdue())

    def test_not_overdue_when_resolved(self):
        ticket = make_ticket(self.user, self.company, self.category, status='resolved')
        ticket.sla_deadline = timezone.now() - timedelta(hours=1)
        ticket.save()
        self.assertFalse(ticket.is_overdue())

    def test_closed_at_set_on_resolve(self):
        ticket = make_ticket(self.user, self.company, self.category)
        ticket.status = 'resolved'
        ticket.save()
        ticket.refresh_from_db()
        self.assertIsNotNone(ticket.closed_at)

    def test_activity_logging(self):
        ticket = make_ticket(self.user, self.company, self.category)
        Activity.objects.create(ticket=ticket, user=self.staff, action='status', detail='Open -> In Progress')
        self.assertEqual(ticket.activities.count(), 1)

    def test_article_str(self):
        article = Article.objects.create(title='Cara X', content='Isi', author=self.user)
        self.assertEqual(str(article), 'Cara X')


class AccessScopeTests(TestCase):
    def setUp(self):
        self.comp_a = Company.objects.create(name='Company A')
        self.comp_b = Company.objects.create(name='Company B')
        self.category = Category.objects.create(name='Network')
        self.admin = make_user('admin', 'admin', self.comp_a)
        self.superadmin = User.objects.create_superuser('superadmin', password='pass12345')
        Profile.objects.get_or_create(user=self.superadmin, defaults={'company': self.comp_a, 'role': 'admin'})
        self.staff_a = make_user('staff_a', 'staff', self.comp_a)
        self.staff_b = make_user('staff_b', 'staff', self.comp_b)
        self.requester_a = make_user('req_a', 'requester', self.comp_a)
        self.requester_b = make_user('req_b', 'requester', self.comp_b)
        self.ticket_a = make_ticket(self.requester_a, self.comp_a, self.category)
        self.ticket_b = make_ticket(self.requester_b, self.comp_b, self.category)

    def login(self, user):
        self.client.login(username=user.username, password='pass12345')

    def test_anonymous_redirected(self):
        response = self.client.get(reverse('ticket_list'))
        self.assertEqual(response.status_code, 302)

    def test_admin_sees_own_company_tickets(self):
        self.login(self.admin)
        response = self.client.get(reverse('ticket_list'))
        self.assertEqual(list(response.context['tickets']), [self.ticket_a])

    def test_superadmin_sees_all_tickets(self):
        self.login(self.superadmin)
        response = self.client.get(reverse('ticket_list'))
        self.assertEqual(list(response.context['tickets']), [self.ticket_b, self.ticket_a])

    def test_staff_sees_only_own_company(self):
        self.login(self.staff_a)
        response = self.client.get(reverse('ticket_list'))
        self.assertEqual(list(response.context['tickets']), [self.ticket_a])

    def test_requester_sees_only_own_tickets(self):
        self.login(self.requester_a)
        response = self.client.get(reverse('ticket_list'))
        self.assertEqual(list(response.context['tickets']), [self.ticket_a])

    def test_requester_cannot_open_other_ticket(self):
        self.login(self.requester_a)
        response = self.client.get(reverse('ticket_detail', args=[self.ticket_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_staff_cannot_open_other_company_ticket(self):
        self.login(self.staff_a)
        response = self.client.get(reverse('ticket_detail', args=[self.ticket_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_admin_cannot_open_other_company_ticket(self):
        self.login(self.admin)
        response = self.client.get(reverse('ticket_detail', args=[self.ticket_b.pk]))
        self.assertEqual(response.status_code, 404)

    def test_requester_can_open_own_ticket(self):
        self.login(self.requester_a)
        response = self.client.get(reverse('ticket_detail', args=[self.ticket_a.pk]))
        self.assertEqual(response.status_code, 200)


class TicketFlowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.category = Category.objects.create(name='Hardware')
        self.admin = make_user('admin', 'admin', self.company)
        self.requester = make_user('req', 'requester', self.company)
        self.staff = make_user('staff', 'staff', self.company)

    def login(self, user):
        self.client.login(username=user.username, password='pass12345')

    def test_create_sets_created_by(self):
        self.login(self.requester)
        response = self.client.post(reverse('ticket_create'), {
            'title': 'Komputer mati',
            'description': 'Tidak menyala',
            'company': self.company.id,
            'category': self.category.id,
            'priority': 'high',
        })
        self.assertEqual(response.status_code, 302)
        ticket = Ticket.objects.get(title='Komputer mati')
        self.assertEqual(ticket.created_by, self.requester)
        self.assertEqual(ticket.company, self.company)

    def test_requester_cannot_create_for_other_company(self):
        other = Company.objects.create(name='PT Lain')
        self.login(self.requester)
        response = self.client.post(reverse('ticket_create'), {
            'title': 'Tiket nakal',
            'description': 'x',
            'company': other.id,
            'category': self.category.id,
            'priority': 'medium',
        })
        # company field queryset dibatasi -> data tidak valid
        self.assertEqual(response.status_code, 200)

    def test_status_change_logs_activity(self):
        self.login(self.admin)
        ticket = make_ticket(self.requester, self.company, self.category)
        self.client.post(reverse('ticket_detail', args=[ticket.pk]), {
            'status_submit': '1', 'status': 'in_progress',
        })
        self.assertTrue(Activity.objects.filter(ticket=ticket, action='status').exists())

    def test_comment_creates_activity(self):
        self.login(self.admin)
        ticket = make_ticket(self.requester, self.company, self.category)
        self.client.post(reverse('ticket_detail', args=[ticket.pk]), {
            'comment_submit': '1', 'message': 'Menuju solusi.',
        })
        self.assertTrue(Activity.objects.filter(ticket=ticket, action='comment').exists())

    def test_create_ticket_with_attachments(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.login(self.requester)
        upload = SimpleUploadedFile('screenshot.png', b'fake-image-bytes', content_type='image/png')
        self.client.post(reverse('ticket_create'), {
            'title': 'Monitor mati',
            'description': 'Tidak ada gambar',
            'company': self.company.id,
            'category': self.category.id,
            'priority': 'high',
            'files': upload,
        })
        ticket = Ticket.objects.get(title='Monitor mati')
        self.assertEqual(ticket.attachments.count(), 1)
        self.assertEqual(ticket.attachments.first().uploaded_by, self.requester)
        self.assertTrue(Activity.objects.filter(ticket=ticket, action='attachment').exists())

    def test_comment_with_attachment(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.login(self.admin)
        ticket = make_ticket(self.requester, self.company, self.category)
        upload = SimpleUploadedFile('log.txt', b'log-contents', content_type='text/plain')
        self.client.post(reverse('ticket_detail', args=[ticket.pk]), {
            'comment_submit': '1',
            'message': 'Ini lognya.',
            'files': upload,
        })
        self.assertEqual(ticket.attachments.count(), 1)
        self.assertTrue(ticket.attachments.first().filename().startswith('log'))

    def test_attachment_access_control(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        self.login(self.requester)
        upload = SimpleUploadedFile('rahasia.txt', b'secrets', content_type='text/plain')
        self.client.post(reverse('ticket_create'), {
            'title': 'Tiket rahasia',
            'description': 'x',
            'company': self.company.id,
            'category': self.category.id,
            'priority': 'medium',
            'files': upload,
        })
        ticket = Ticket.objects.get(title='Tiket rahasia')
        att = ticket.attachments.first()
        url = f'/media/{att.file.name}'
        # pemilik tiket bisa mengakses lampirannya
        r = self.client.get(url)
        self.assertEqual(r.status_code, 200)
        # requester lain tidak boleh (404)
        other = make_user('req2', 'requester', self.company)
        self.client.login(username='req2', password='pass12345')
        r2 = self.client.get(url)
        self.assertEqual(r2.status_code, 404)

    def test_login_flow(self):
        response = self.client.post(reverse('login'), {
            'username': 'req', 'password': 'pass12345',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))


class AdminOnlyTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.admin = make_user('admin', 'admin', self.company)
        self.superadmin = User.objects.create_superuser('superadmin', password='pass12345')
        Profile.objects.get_or_create(user=self.superadmin, defaults={'company': self.company, 'role': 'admin'})
        self.staff = make_user('staff', 'staff', self.company)

    def login(self, user):
        self.client.login(username=user.username, password='pass12345')

    def test_company_page_superuser_only(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse('company_list')).status_code, 302)
        self.login(self.admin)
        self.assertEqual(self.client.get(reverse('company_list')).status_code, 302)
        self.login(self.superadmin)
        self.assertEqual(self.client.get(reverse('company_list')).status_code, 200)

    def test_user_pages_admin_only(self):
        self.login(self.staff)
        for url in ['user_list', 'user_create']:
            self.assertEqual(self.client.get(reverse(url)).status_code, 302)

    def test_user_create(self):
        self.login(self.admin)
        response = self.client.post(reverse('user_create'), {
            'username': 'staff_baru',
            'first_name': 'Staff',
            'email': 'staff@test.com',
            'password': 'pass12345',
            'role': 'staff',
            'company': self.company.id,
        })
        self.assertEqual(response.status_code, 302)
        user = User.objects.get(username='staff_baru')
        self.assertEqual(user.profile.role, 'staff')
        self.assertEqual(user.profile.company, self.company)

    def test_article_create_admin_only(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse('article_create')).status_code, 302)


class ExportTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.category = Category.objects.create(name='Software')
        self.admin = make_user('admin', 'admin', self.company)
        self.requester = make_user('req', 'requester', self.company)
        make_ticket(self.requester, self.company, self.category)

    def test_excel_export(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('report_export_excel'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('spreadsheetml', response['Content-Type'])

    def test_pdf_export(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('report_export_pdf'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response['Content-Type'], 'application/pdf')


class RegistrationTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.admin = make_user('admin', 'admin', self.company)

    def register(self, username='budi', **overrides):
        data = {
            'username': username,
            'first_name': 'Budi Setiawan',
            'email': f'{username}@test.com',
            'company': self.company.id,
            'password1': 'rahasia123',
            'password2': 'rahasia123',
        }
        data.update(overrides)
        return self.client.post(reverse('register'), data)

    def test_register_creates_pending_user(self):
        response = self.register()
        self.assertEqual(response.status_code, 200)
        user = User.objects.get(username='budi')
        self.assertFalse(user.is_active)
        self.assertEqual(user.profile.role, 'requester')
        self.assertEqual(user.profile.company, self.company)
        self.assertTrue(user.profile.pending_approval)

    def test_pending_user_cannot_login(self):
        self.register()
        response = self.client.post(reverse('login'), {
            'username': 'budi', 'password': 'rahasia123',
        })
        self.assertEqual(response.status_code, 200)  # form error, tidak redirect
        self.assertFalse(response.wsgi_request.user.is_authenticated)

    def test_duplicate_username_rejected(self):
        make_user('budi', 'requester', self.company)
        response = self.register()
        self.assertContains(response, 'sudah dipakai')

    def test_password_mismatch_rejected(self):
        response = self.register(password2='berbeda123')
        self.assertContains(response, 'tidak cocok')

    def test_admin_approve_activates_user(self):
        self.register()
        user = User.objects.get(username='budi')
        self.client.login(username='admin', password='pass12345')
        response = self.client.post(reverse('approve_user', args=[user.pk]))
        self.assertRedirects(response, reverse('pending_approvals'))
        user.refresh_from_db()
        self.assertTrue(user.is_active)
        self.assertFalse(user.profile.pending_approval)
        # user yang disetujui menerima notifikasi
        self.assertTrue(user.notifications.exists())

    def test_admin_reject_deletes_user(self):
        self.register()
        user = User.objects.get(username='budi')
        self.client.login(username='admin', password='pass12345')
        response = self.client.post(reverse('reject_user', args=[user.pk]))
        self.assertRedirects(response, reverse('pending_approvals'))
        self.assertFalse(User.objects.filter(username='budi').exists())

    def test_non_admin_cannot_access_pending(self):
        staff = make_user('staff', 'staff', self.company)
        self.client.login(username='staff', password='pass12345')
        response = self.client.get(reverse('pending_approvals'))
        self.assertEqual(response.status_code, 302)

    def test_register_page_requires_company(self):
        response = self.register(company='')
        self.assertEqual(response.status_code, 200)
        self.assertFalse(User.objects.filter(username='budi').exists())

    def test_registration_closed(self):
        from django.test import override_settings
        with override_settings(REGISTRATION_OPEN=False):
            response = self.client.get(reverse('register'))
            self.assertEqual(response.status_code, 200)
            self.assertContains(response, 'ditutup')
            # POST juga tidak membuat akun
            self.register()
            self.assertFalse(User.objects.filter(username='budi').exists())


class MarkdownTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.category = Category.objects.create(name='Software')
        self.admin = make_user('admin', 'admin', self.company)
        self.staff = make_user('staff', 'staff', self.company)

    def test_content_html_renders_markdown(self):
        article = Article.objects.create(
            title='Cara Reset',
            content='# Judul\n\nTeks **tebal** dan `kode`.\n\n- item a\n- item b',
            author=self.admin,
        )
        html = article.content_html()
        self.assertIn('<h1>', html)
        self.assertIn('<strong>tebal</strong>', html)
        self.assertIn('<code>kode</code>', html)
        self.assertIn('<ul>', html)

    def test_content_html_escapes_script(self):
        article = Article.objects.create(
            title='X', content='<script>alert(1)</script><b>ok</b>', author=self.admin,
        )
        html = article.content_html()
        self.assertNotIn('<script>alert(1)</script>', html)
        self.assertIn('<b>ok</b>', html)

    def test_table_and_fenced_code(self):
        article = Article.objects.create(
            title='X',
            content='| a | b |\n|---|---|\n| 1 | 2 |\n\n```python\nprint(1)\n```',
            author=self.admin,
        )
        html = article.content_html()
        self.assertIn('<table>', html)
        self.assertIn('<pre>', html)

    def test_preview_endpoint_renders(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.post(reverse('article_preview'), {'content': '**halo**'})
        self.assertEqual(response.status_code, 200)
        self.assertIn('<strong>halo</strong>', response.content.decode())

    def test_preview_only_post(self):
        self.client.login(username='admin', password='pass12345')
        self.assertEqual(self.client.get(reverse('article_preview')).status_code, 405)

    def test_preview_requires_admin(self):
        self.client.login(username='staff', password='pass12345')
        response = self.client.post(reverse('article_preview'), {'content': '# Hai'})
        self.assertEqual(response.status_code, 302)


class SettingsTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.superadmin = User.objects.create_superuser('superadmin', password='pass12345')
        Profile.objects.get_or_create(user=self.superadmin, defaults={'company': self.company, 'role': 'admin'})
        self.admin = make_user('admin', 'admin', self.company)
        self.staff = make_user('staff', 'staff', self.company)

    def test_settings_page_superuser_only(self):
        self.client.login(username='staff', password='pass12345')
        self.assertEqual(self.client.get(reverse('settings_page')).status_code, 302)
        self.client.login(username='admin', password='pass12345')
        self.assertEqual(self.client.get(reverse('settings_page')).status_code, 302)
        self.client.login(username='superadmin', password='pass12345')
        self.assertEqual(self.client.get(reverse('settings_page')).status_code, 200)

    def test_update_settings(self):
        self.client.login(username='superadmin', password='pass12345')
        response = self.client.post(reverse('settings_page'), {
            'site_name': 'Helpdesk Baru',
            'tagline': 'Support 24/7',
            'footer_text': 'Copyright 2026',
            'primary_color': '#7c3aed',
        })
        self.assertEqual(response.status_code, 302)
        cfg = AppSettings.objects.get(pk=1)
        self.assertEqual(cfg.site_name, 'Helpdesk Baru')
        self.assertEqual(cfg.primary_color, '#7c3aed')

    def test_upload_logo(self):
        import io
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        self.client.login(username='superadmin', password='pass12345')
        buf = io.BytesIO()
        Image.new('RGBA', (60, 60), (79, 70, 229, 255)).save(buf, format='PNG')
        img = SimpleUploadedFile('brand.png', buf.getvalue(), content_type='image/png')
        self.client.post(reverse('settings_page'), {
            'site_name': 'Helpdesk Baru',
            'tagline': '',
            'footer_text': '',
            'primary_color': '#4f46e5',
            'logo': img,
        })
        cfg = AppSettings.objects.get(pk=1)
        self.assertIn('brand', cfg.logo.name)

    def test_invalid_color_rejected(self):
        self.client.login(username='superadmin', password='pass12345')
        response = self.client.post(reverse('settings_page'), {
            'site_name': 'X',
            'tagline': '',
            'footer_text': '',
            'primary_color': 'hijau',
        })
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'hex')

    def test_singleton(self):
        AppSettings.load()
        AppSettings.load()
        self.assertEqual(AppSettings.objects.count(), 1)

    def test_login_page_exposes_branding(self):
        response = self.client.get(reverse('login'))
        content = response.content.decode()
        self.assertIn('Sokkafiber Helpdesk', content)
        self.assertIn('/static/tickets/img/logo', content)


class SlaCheckTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.category = Category.objects.create(name='Network')
        self.staff = make_user('staff', 'staff', self.company)
        self.requester = make_user('req', 'requester', self.company)

    def call(self):
        from io import StringIO
        from django.core.management import call_command
        out = StringIO()
        call_command('sla_check', stdout=out)
        return out.getvalue()

    def test_overdue_escalation(self):
        ticket = make_ticket(self.requester, self.company, self.category)
        ticket.sla_deadline = timezone.now() - timedelta(hours=2)
        ticket.assigned_to = self.staff
        ticket.save()
        self.call()
        ticket.refresh_from_db()
        self.assertTrue(ticket.sla_overdue_sent)
        self.assertTrue(self.staff.notifications.filter(ticket=ticket, message__icontains='TERLAMPAUI').exists())
        # tidak duplikat saat dijalankan ulang
        self.call()
        self.assertEqual(self.staff.notifications.filter(ticket=ticket, message__icontains='TERLAMPAUI').count(), 1)

    def test_warning_before_deadline(self):
        ticket = make_ticket(self.requester, self.company, self.category, priority='urgent')
        ticket.sla_deadline = timezone.now() + timedelta(minutes=30)
        ticket.assigned_to = self.staff
        ticket.save()
        self.call()
        ticket.refresh_from_db()
        self.assertTrue(ticket.sla_warning_sent)
        self.assertFalse(ticket.sla_overdue_sent)
        self.assertTrue(self.staff.notifications.filter(ticket=ticket, message__icontains='mendekati').exists())

    def test_no_notify_within_sla(self):
        ticket = make_ticket(self.requester, self.company, self.category, priority='low')
        ticket.sla_deadline = timezone.now() + timedelta(hours=80)
        ticket.save()
        self.call()
        ticket.refresh_from_db()
        self.assertFalse(ticket.sla_warning_sent)
        self.assertFalse(ticket.sla_overdue_sent)

    def test_closed_ticket_not_escalated(self):
        ticket = make_ticket(self.requester, self.company, self.category, status='resolved')
        ticket.sla_deadline = timezone.now() - timedelta(hours=2)
        ticket.save()
        self.call()
        ticket.refresh_from_db()
        self.assertFalse(ticket.sla_overdue_sent)


class ProfileTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.user = make_user('req', 'requester', self.company)

    def test_profile_page_login_required(self):
        self.assertEqual(self.client.get(reverse('profile')).status_code, 302)

    def test_profile_page_renders(self):
        self.client.login(username='req', password='pass12345')
        self.assertEqual(self.client.get(reverse('profile')).status_code, 200)

    def test_update_profile(self):
        import io
        from django.core.files.uploadedfile import SimpleUploadedFile
        from PIL import Image
        self.client.login(username='req', password='pass12345')
        buf = io.BytesIO()
        Image.new('RGB', (40, 40), (200, 50, 50)).save(buf, format='PNG')
        avatar = SimpleUploadedFile('foto.png', buf.getvalue(), content_type='image/png')
        response = self.client.post(reverse('profile'), {
            'first_name': 'Rina',
            'email': 'rina@test.com',
            'phone': '08123456789',
            'job_title': 'Supervisor',
            'avatar': avatar,
        })
        self.assertEqual(response.status_code, 302)
        self.user.refresh_from_db()
        self.assertEqual(self.user.first_name, 'Rina')
        self.assertEqual(self.user.email, 'rina@test.com')
        self.assertEqual(self.user.profile.phone, '08123456789')
        self.assertEqual(self.user.profile.job_title, 'Supervisor')
        self.assertIn('foto', self.user.profile.avatar.name)


class MyDashboardTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.category = Category.objects.create(name='Software')
        self.staff = make_user('staff', 'staff', self.company)
        self.requester = make_user('req', 'requester', self.company)

    def test_login_required(self):
        self.assertEqual(self.client.get(reverse('my_dashboard')).status_code, 302)

    def test_staff_sees_assigned_only(self):
        own = make_ticket(self.requester, self.company, self.category)
        own.assigned_to = self.staff
        own.save()
        make_ticket(self.requester, self.company, self.category)
        self.client.login(username='staff', password='pass12345')
        response = self.client.get(reverse('my_dashboard'))
        self.assertEqual(response.context['total'], 1)
        self.assertEqual(list(response.context['recent']), [own])

    def test_requester_sees_own_created_only(self):
        make_ticket(self.requester, self.company, self.category)
        make_ticket(make_user('req2', 'requester', self.company), self.company, self.category)
        self.client.login(username='req', password='pass12345')
        response = self.client.get(reverse('my_dashboard'))
        self.assertEqual(response.context['total'], 1)

    def test_kpi_counts(self):
        t = make_ticket(self.requester, self.company, self.category)
        t.assigned_to = self.staff
        t.save()
        t2 = make_ticket(self.requester, self.company, self.category)
        t2.assigned_to = self.staff
        t2.status = 'resolved'
        t2.save()
        self.client.login(username='staff', password='pass12345')
        response = self.client.get(reverse('my_dashboard'))
        self.assertEqual(response.context['total'], 2)
        self.assertEqual(response.context['open_count'], 1)
        self.assertEqual(response.context['resolved_count'], 1)


class ImportExportTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.category = Category.objects.create(name='Software')
        self.admin = make_user('admin', 'admin', self.company)
        self.staff = make_user('staff', 'staff', self.company)

    def test_export_csv(self):
        make_ticket(self.admin, self.company, self.category)
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('report_export_csv'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('text/csv', response['Content-Type'])
        self.assertIn('ID', response.content.decode('utf-8-sig'))
        self.assertIn('Software', response.content.decode('utf-8-sig'))

    def test_export_csv_requires_login(self):
        self.assertEqual(self.client.get(reverse('report_export_csv')).status_code, 302)

    def test_template_download(self):
        self.client.login(username='admin', password='pass12345')
        response = self.client.get(reverse('import_template'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('title', response.content.decode('utf-8-sig'))

    def test_import_admin_only(self):
        self.client.login(username='staff', password='pass12345')
        response = self.client.get(reverse('import_tickets'))
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('dashboard'))

    def test_import_creates_tickets(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_data = ('title,description,company,category,priority,status\n'
                    'Laptop rusak,layar gelap,PT Baru,Hardware,high,open\n'
                    'Printer error,,PT Uji,Software,low,resolved\n').encode('utf-8-sig')
        self.client.login(username='admin', password='pass12345')
        response = self.client.post(reverse('import_tickets'), {
            'file': SimpleUploadedFile('data.csv', csv_data, content_type='text/csv'),
        })
        self.assertEqual(response.status_code, 302)
        self.assertEqual(response.url, reverse('ticket_list'))
        self.assertEqual(Ticket.objects.count(), 2)
        self.assertTrue(Category.objects.filter(name='Hardware').exists())
        t = Ticket.objects.get(title='Laptop rusak')
        self.assertEqual(t.priority, 'high')
        self.assertEqual(t.created_by, self.admin)
        self.assertEqual(t.company, self.company)

    def test_import_skips_invalid_rows(self):
        from django.core.files.uploadedfile import SimpleUploadedFile
        csv_data = ('title,description,company\n'
                    ',tanpa judul,PT Uji\n'
                    'Valid,ok,PT Uji\n').encode('utf-8')
        self.client.login(username='admin', password='pass12345')
        self.client.post(reverse('import_tickets'), {
            'file': SimpleUploadedFile('data.csv', csv_data, content_type='text/csv'),
        })
        self.assertEqual(Ticket.objects.count(), 1)


class TenantIsolationTests(TestCase):
    """Pastikan data tidak bocor antar perusahaan."""

    def setUp(self):
        self.company_a = Company.objects.create(name='PT Alpha')
        self.company_b = Company.objects.create(name='PT Beta')
        self.admin_a = make_user('admin_a', 'admin', self.company_a)
        self.admin_b = make_user('admin_b', 'admin', self.company_b)
        self.staff_a = make_user('staff_a', 'staff', self.company_a)
        self.staff_b = make_user('staff_b', 'staff', self.company_b)
        self.requester_a = make_user('req_a', 'requester', self.company_a)
        self.requester_b = make_user('req_b', 'requester', self.company_b)
        self.cat = Category.objects.create(name='Umum')
        self.ticket_a = make_ticket(self.requester_a, self.company_a, self.cat)
        self.ticket_b = make_ticket(self.requester_b, self.company_b, self.cat)

    def _login(self, username):
        self.client.login(username=username, password='pass12345')

    # --- Ticket list ---
    def test_admin_a_does_not_see_ticket_b(self):
        self._login('admin_a')
        resp = self.client.get(reverse('ticket_list'))
        self.assertEqual(resp.context['tickets'].paginator.count, 1)
        self.assertEqual(resp.context['tickets'][0].pk, self.ticket_a.pk)

    def test_staff_a_does_not_see_ticket_b(self):
        self._login('staff_a')
        resp = self.client.get(reverse('ticket_list'))
        self.assertEqual(resp.context['tickets'].paginator.count, 1)

    def test_requester_a_does_not_see_ticket_b(self):
        self._login('req_a')
        resp = self.client.get(reverse('ticket_list'))
        self.assertEqual(resp.context['tickets'].paginator.count, 1)

    # --- Ticket detail ---
    def test_admin_a_cannot_access_ticket_b(self):
        self._login('admin_a')
        self.assertEqual(self.client.get(reverse('ticket_detail', args=[self.ticket_b.pk])).status_code, 404)

    def test_staff_a_cannot_access_ticket_b(self):
        self._login('staff_a')
        self.assertEqual(self.client.get(reverse('ticket_detail', args=[self.ticket_b.pk])).status_code, 404)

    # --- Dashboard ---
    def test_dashboard_only_shows_own_company(self):
        self._login('admin_a')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.context['total'], 1)

    def test_staff_workload_scoped(self):
        self.ticket_a.assigned_to = self.staff_a
        self.ticket_a.save()
        self._login('admin_a')
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(len(resp.context['staff_workload']), 1)
        self.assertEqual(resp.context['staff_workload'][0]['assigned_to__username'], 'staff_a')

    # --- User management ---
    def test_admin_a_does_not_see_user_b(self):
        self._login('admin_a')
        resp = self.client.get(reverse('user_list'))
        usernames = [u.username for u in resp.context['users']]
        self.assertIn('staff_a', usernames)
        self.assertNotIn('admin_b', usernames)
        self.assertNotIn('staff_b', usernames)
        self.assertNotIn('req_b', usernames)

    def test_admin_a_cannot_edit_user_b(self):
        self._login('admin_a')
        resp = self.client.get(reverse('user_edit', args=[self.admin_b.pk]))
        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse('user_list'))

    def test_admin_a_cannot_delete_user_b(self):
        self._login('admin_a')
        self.client.post(reverse('user_delete', args=[self.admin_b.pk]))
        self.assertTrue(User.objects.filter(pk=self.admin_b.pk).exists())

    # --- Pending approvals ---
    def test_admin_a_does_not_see_pending_b(self):
        self.req_c = make_user('req_c', 'requester', self.company_b)
        self.req_c.is_active = False
        self.req_c.save()
        self.req_c.profile.pending_approval = True
        self.req_c.profile.save()
        self._login('admin_a')
        resp = self.client.get(reverse('pending_approvals'))
        self.assertEqual(len(resp.context['pending']), 0)

    def test_admin_a_cannot_approve_user_b(self):
        self.req_c = make_user('req_c', 'requester', self.company_b)
        self.req_c.is_active = False
        self.req_c.save()
        self.req_c.profile.pending_approval = True
        self.req_c.profile.save()
        self._login('admin_a')
        self.client.post(reverse('approve_user', args=[self.req_c.pk]))
        self.req_c.refresh_from_db()
        self.assertFalse(self.req_c.is_active)

    # --- Company management ---
    def test_company_list_requires_superuser(self):
        self._login('admin_a')
        resp = self.client.get(reverse('company_list'))
        self.assertEqual(resp.status_code, 302)

    def test_superuser_sees_all_tickets(self):
        superuser = User.objects.create_superuser('superadmin', password='pass12345')
        Profile.objects.get_or_create(user=superuser, defaults={'company': self.company_a, 'role': 'admin'})
        self._login('superadmin')
        resp = self.client.get(reverse('ticket_list'))
        self.assertEqual(resp.context['tickets'].paginator.count, 2)


class IdleSessionTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.user = make_user('staff1', 'staff', self.company)
        self.client.login(username='staff1', password='pass12345')

    @override_settings(IDLE_TIMEOUT=60)
    def test_active_session_stays_logged_in(self):
        resp = self.client.get(reverse('dashboard'))
        self.assertEqual(resp.status_code, 200)
        self.assertIn('_last_activity', self.client.session)

    @override_settings(IDLE_TIMEOUT=60)
    def test_idle_session_gets_logged_out(self):
        base = time.time()
        with patch('helpdesk.middleware.time') as mock_time:
            mock_time.time.return_value = base
            self.client.get(reverse('dashboard'))

            mock_time.time.return_value = base + 120
            resp = self.client.get(reverse('dashboard'))
            self.assertEqual(resp.status_code, 302)
            self.assertIn('login', resp.url)

    @override_settings(IDLE_TIMEOUT=0)
    def test_timeout_disabled_never_logs_out(self):
        base = time.time()
        with patch('helpdesk.middleware.time') as mock_time:
            mock_time.time.return_value = base
            self.client.get(reverse('dashboard'))

            mock_time.time.return_value = base + 99999
            resp = self.client.get(reverse('dashboard'))
            self.assertEqual(resp.status_code, 200)

    @override_settings(IDLE_TIMEOUT=60)
    def test_unauthenticated_bypasses_middleware(self):
        self.client.logout()
        resp = self.client.get(reverse('login'))
        self.assertEqual(resp.status_code, 200)
