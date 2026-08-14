from datetime import timedelta

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse
from django.utils import timezone

from .models import Activity, Article, Category, Company, Profile, Ticket


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
        self.admin = make_user('admin', 'admin')
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

    def test_admin_sees_all_tickets(self):
        self.login(self.admin)
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

    def test_admin_can_open_any_ticket(self):
        self.login(self.admin)
        response = self.client.get(reverse('ticket_detail', args=[self.ticket_b.pk]))
        self.assertEqual(response.status_code, 200)

    def test_requester_can_open_own_ticket(self):
        self.login(self.requester_a)
        response = self.client.get(reverse('ticket_detail', args=[self.ticket_a.pk]))
        self.assertEqual(response.status_code, 200)


class TicketFlowTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.category = Category.objects.create(name='Hardware')
        self.admin = make_user('admin', 'admin')
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

    def test_login_flow(self):
        response = self.client.post(reverse('login'), {
            'username': 'req', 'password': 'pass12345',
        })
        self.assertEqual(response.status_code, 302)
        self.assertRedirects(response, reverse('dashboard'))


class AdminOnlyTests(TestCase):
    def setUp(self):
        self.company = Company.objects.create(name='PT Uji')
        self.admin = make_user('admin', 'admin')
        self.staff = make_user('staff', 'staff', self.company)

    def login(self, user):
        self.client.login(username=user.username, password='pass12345')

    def test_company_page_admin_only(self):
        self.login(self.staff)
        self.assertEqual(self.client.get(reverse('company_list')).status_code, 302)
        self.login(self.admin)
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
        self.admin = make_user('admin', 'admin')
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
