from django.core.management.base import BaseCommand

from tickets.models import Ticket
from tickets.views import notify_many


class Command(BaseCommand):
    help = 'Kirim notifikasi untuk tiket yang mendekati atau melampaui SLA.'

    def handle(self, *args, **options):
        from django.utils import timezone

        now = timezone.now()
        active = (
            Ticket.objects.filter(
                status__in=['open', 'in_progress'],
                sla_deadline__isnull=False,
            )
            .select_related('created_by', 'assigned_to')
        )

        warnings = 0
        escalations = 0

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
                notify_many(
                    {ticket.assigned_to, ticket.created_by},
                    ticket,
                    f"Tiket #{ticket.id} TERLAMPAUI SLA "
                    f"({ticket.get_priority_display()}). Harap segera diselesaikan.",
                )
                ticket.sla_overdue_sent = True
                ticket.save(update_fields=['sla_overdue_sent'])
                escalations += 1

        self.stdout.write(self.style.SUCCESS(f"SLA check selesai: {warnings} peringatan, {escalations} eskalasi."))
