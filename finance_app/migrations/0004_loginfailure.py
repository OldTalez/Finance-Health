from django.db import migrations, models


class Migration(migrations.Migration):
    """Failed-login records for per-account lockout."""

    dependencies = [
        ('finance_app', '0003_refresh_token_hash'),
    ]

    operations = [
        migrations.CreateModel(
            name='LoginFailure',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('email', models.CharField(db_index=True, max_length=254)),
                ('created_at', models.DateTimeField(auto_now_add=True, db_index=True)),
            ],
            options={
                'db_table': 'login_failures',
            },
        ),
    ]
