import logging

from celery import shared_task
from django.conf import settings
from django.core.mail import EmailMultiAlternatives
from django.template.loader import render_to_string

logger = logging.getLogger('tickets')


@shared_task(bind=True, max_retries=3, default_retry_delay=60)
def send_notification_email(self, subject, text_body, recipient_list, ticket_id=None, message=''):
    """Kirim email notifikasi secara async via Celery. Fallback ke log jika gagal."""
    ctx = {
        'message': message,
        'action_url': f"{settings.SITE_URL}/ticket/{ticket_id}/" if ticket_id else settings.SITE_URL,
        'action_label': 'Lihat Tiket' if ticket_id else 'Buka Helpdesk',
        'site_name': 'Helpdesk',
        'site_url': settings.SITE_URL,
        'footer_text': 'Ini email notifikasi otomatis dari helpdesk.',
    }
    if ticket_id:
        from .models import Ticket
        try:
            ctx['ticket'] = Ticket.objects.select_related('company').get(pk=ticket_id)
        except Ticket.DoesNotExist:
            pass

    try:
        html_body = render_to_string('emails/notification.html', ctx)
    except Exception:
        html_body = None

    try:
        msg = EmailMultiAlternatives(
            subject=subject,
            body=text_body,
            from_email=settings.DEFAULT_FROM_EMAIL,
            to=recipient_list,
        )
        if html_body:
            msg.attach_alternative(html_body, 'text/html')
        msg.send(fail_silently=False)
        logger.info("Email terkirim ke %s (ticket #%s)", recipient_list, ticket_id)
    except Exception as exc:
        logger.error("Gagal kirim email ke %s: %s", recipient_list, exc)
        raise self.retry(exc=exc)
