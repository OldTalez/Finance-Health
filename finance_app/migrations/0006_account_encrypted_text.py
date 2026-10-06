from django.db import migrations, models


class Migration(migrations.Migration):
    """Widen the encrypted account columns: AES-GCM output is longer than the plaintext.

    No data migration is needed: nothing ever wrote to these columns (the
    serializer does not expose them), so existing rows hold empty strings.
    """

    dependencies = [
        ('finance_app', '0005_invitecode'),
    ]

    operations = [
        migrations.AlterField(
            model_name='account',
            name='account_number_encrypted',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='account',
            name='account_holder_name_encrypted',
            field=models.TextField(blank=True),
        ),
    ]
