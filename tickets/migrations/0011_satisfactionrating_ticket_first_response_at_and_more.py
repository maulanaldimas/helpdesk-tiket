from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
        ('tickets', '0010_ticket_sla_pause_reason_ticket_sla_paused_and_more'),
    ]

    operations = [
        migrations.CreateModel(
            name='SatisfactionRating',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('rating', models.PositiveSmallIntegerField(choices=[(1, 'Sangat Tidak Puas'), (2, 'Tidak Puas'), (3, 'Netral'), (4, 'Puas'), (5, 'Sangat Puas')])),
                ('comment', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('created_by', models.ForeignKey(on_delete=django.db.models.deletion.CASCADE, to=settings.AUTH_USER_MODEL)),
                ('ticket', models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, related_name='satisfaction_rating', to='tickets.ticket')),
            ],
            options={
                'verbose_name': 'Rating Kepuasan',
                'verbose_name_plural': 'Rating Kepuasan',
            },
        ),
        migrations.AddField(
            model_name='ticket',
            name='first_response_at',
            field=models.DateTimeField(blank=True, help_text='Waktu balasan pertama dari staff.', null=True),
        ),
        migrations.AlterField(
            model_name='profile',
            name='role',
            field=models.CharField(choices=[('admin', 'Admin'), ('staff', 'Staff'), ('requester', 'Requester')], db_index=True, default='requester', max_length=20),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='sla_deadline',
            field=models.DateTimeField(blank=True, db_index=True, null=True),
        ),
        migrations.AlterField(
            model_name='ticket',
            name='status',
            field=models.CharField(choices=[('open', 'Open'), ('in_progress', 'In Progress'), ('resolved', 'Resolved'), ('closed', 'Closed')], db_index=True, default='open', max_length=20),
        ),
        migrations.AddIndex(
            model_name='notification',
            index=models.Index(fields=['user', 'is_read'], name='not_user_id_eeb5cc_idx'),
        ),
        migrations.AddIndex(
            model_name='profile',
            index=models.Index(fields=['company', 'role'], name='pro_company_e7439c_idx'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['company', 'status'], name='tic_company_0e5f54_idx'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['status', 'priority'], name='tic_status_b256f6_idx'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['created_by', 'status'], name='tic_created_d1e02b_idx'),
        ),
        migrations.AddIndex(
            model_name='ticket',
            index=models.Index(fields=['assigned_to', 'status'], name='tic_assigne_e36302_idx'),
        ),
    ]
