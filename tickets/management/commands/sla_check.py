from django.contrib.auth.models import User
from django.core.management.base import BaseCommand

from tickets.models import Activity, Notification, Profile, Ticket
from tickets.views import notify_many


class Command(BaseCommand):
    help = 'Kirim notifikasi untuk tiket yang mendekati atau melampaui SLA. Eskalasi otomatis ke admin jika terlambat.'

    def add_arguments(self, parser):
        parser.add_argument('--escalate-after-hours', type=int, default=2,
                            help='Jam tambahan setelah SLA overdue sebelum eskalasi ke admin (default: 2)')

    def handle(self, *args, **options):
        from django.utils import timezone

        now = timezone.now()
        escalate_after = options['escalate_after_hours']
        active = (
            Ticket.objects.filter(
                status__in=['open', 'in_progress'],
                sla_deadline__isnull=False,
            )
            .select_related('created_by', 'assigned_to', 'company')
        )

        warnings = 0
        escalations = 0
        admin_escalations = 0

        for ticket in active:
            window_seconds = Ticket.SLA_HOURS.get(ticket.priority, 72) * 3600
            remaining = (ticket.sla_deadline - now).total_seconds()

            # Peringatan: sisa waktu <= 25% dari jendela SLA
            if 0 < remaining <= window_seconds * 0.25 and not ticket.sla_warning_sent:
                notify_many(
                    {ticket.assigned_to, ticket.created_by},
                    ticket,
                    f"Tiket #{ticket.id} mendekati batas SLA "
                    f"({ticket.get_priority_display()}, sisa ±{int(remaining // 3600)} jam). "
                    f"Segera ditindaklanjuti.",
                )
                ticket.sla_warning_sent = True
                ticket.save(update_fields=['sla_warning_sent'])
                warnings += 1

            # Eskalasi: sudah melewati deadline
            if remaining <= 0 and not ticket.sla_overdue_sent:
                overdue_hours = int(abs(remaining) // 3600)
                notify_many(
                    {ticket.assigned_to, ticket.created_by},
                    ticket,
                    f"Tiket #{ticket.id} TERLAMPAUI SLA "
                    f"({ticket.get_priority_display()}, terlambat ±{overdue_hours} jam). "
                    f"Harap segera diselesaikan.",
                )
                ticket.sla_overdue_sent = True
                ticket.save(update_fields=['sla_overdue_sent'])
                escalations += 1

            # Eskalasi ke admin: sudah overdue lebih dari X jam
            if remaining <= -(escalate_after * 3600) and not ticket.sla_paused:
                admin_users = User.objects.filter(
                    profile__role='admin',
                    profile__company=ticket.company,
                    is_active=True,
                )
                if ticket.company:
                    admin_users = admin_users.filter(profile__company=ticket.company)

                already_notified = Notification.objects.filter(
                    ticket=ticket,
                    message__startswith=f'ESKALASI',
                ).exists()

                if not already_notified and admin_users.exists():
                    overdue_hours = int(abs(remaining) // 3600)
                    for admin in admin_users:
                        Notification.objects.create(
                            user=admin,
                            ticket=ticket,
                            message=(
                                f'ESKALASI: Tiket #{ticket.id} telah melampaui SLA '
                                f'selama {overdue_hours} jam dan membutuhkan perhatian segera.'
                            ),
                        )
                    Activity.objects.create(
                        ticket=ticket,
                        user=None,
                        action='assign',
                        detail=f'SLA escalation: diteruskan ke admin ({overdue_hours}jam overdue)',
                    )
                    admin_escalations += 1

        self.stdout.write(self.style.SUCCESS(
            f"SLA check selesai: {warnings} peringatan, "
            f"{escalations} eskalasi awal, {admin_escalations} eskalasi ke admin."
        ))
