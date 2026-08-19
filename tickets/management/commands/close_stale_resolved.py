from django.core.management.base import BaseCommand
from django.utils import timezone
from datetime import timedelta

from tickets.models import Ticket, Activity, Notification


class Command(BaseCommand):
    help = 'Tutup tiket yang resolved lebih dari N hari secara otomatis.'

    def add_arguments(self, parser):
        parser.add_argument(
            '--days', type=int, default=7,
            help='Jumlah hari sebelum tiket resolved ditutup (default: 7)',
        )
        parser.add_argument(
            '--dry-run', action='store_true',
            help='Tampilkan tiket yang akan ditutup tanpa menutupnya.',
        )

    def handle(self, *args, **options):
        days = options['days']
        dry_run = options['dry_run']
        cutoff = timezone.now() - timedelta(days=days)

        resolved_tickets = Ticket.objects.filter(
            status='resolved',
            closed_at__lt=cutoff,
        )

        count = resolved_tickets.count()
        if count == 0:
            self.stdout.write(self.style.SUCCESS('Tidak ada tiket yang perlu ditutup.'))
            return

        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN — {count} tiket akan ditutup:'))
            for t in resolved_tickets[:20]:
                self.stdout.write(f'  #{t.id} — {t.title} (resolved: {t.closed_at})')
            return

        for ticket in resolved_tickets:
            ticket.status = 'closed'
            ticket.save()
            Activity.objects.create(
                ticket=ticket,
                action='status',
                detail='Resolved -> Closed (otomatis)',
            )
            if ticket.assigned_to:
                Notification.objects.create(
                    user=ticket.assigned_to,
                    ticket=ticket,
                    message=f'Tiket #{ticket.id} ditutup otomatis setelah {days} hari resolved.',
                )

        self.stdout.write(self.style.SUCCESS(f'{count} tiket resolved ditutup otomatis.'))
