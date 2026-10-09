import django.db.models.deletion
from django.conf import settings
from django.db import migrations, models


class Migration(migrations.Migration):
    """Single-use invite codes (sign-up is invite-only)."""

    dependencies = [
        ('finance_app', '0004_loginfailure'),
    ]

    operations = [
        migrations.CreateModel(
            name='InviteCode',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('code_hash', models.CharField(max_length=64, unique=True)),
                ('label', models.CharField(blank=True, help_text='Who this invite is for (note to self).', max_length=100)),
                ('expires_at', models.DateTimeField(blank=True, help_text='Leave empty for no expiry.', null=True)),
                ('used_at', models.DateTimeField(blank=True, null=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('used_by', models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.SET_NULL, related_name='invite_used', to=settings.AUTH_USER_MODEL)),
            ],
            options={
                'db_table': 'invite_codes',
            },
        ),
    ]
