import uuid

from django.db import migrations, models


class Migration(migrations.Migration):
    """Refresh tokens: store a SHA-256 hash and a rotation family id, not the raw token."""

    dependencies = [
        ('finance_app', '0002_purge_refresh_tokens'),
    ]

    operations = [
        migrations.RemoveField(
            model_name='refreshtoken',
            name='token',
        ),
        migrations.AddField(
            model_name='refreshtoken',
            name='token_hash',
            field=models.CharField(default='', max_length=64, unique=True),
            preserve_default=False,
        ),
        migrations.AddField(
            model_name='refreshtoken',
            name='family_id',
            field=models.UUIDField(db_index=True, default=uuid.uuid4),
        ),
    ]
