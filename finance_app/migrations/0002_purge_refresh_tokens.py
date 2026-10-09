"""
Delete existing refresh tokens before the schema change in 0003.

Old rows hold raw token strings. They are removed so no raw token survives in
the database; affected users simply log in again. Kept separate from 0003 so
the data change and the schema change run in separate transactions (Postgres
refuses ALTER TABLE after deleting rows that have pending FK trigger events).
"""

from django.db import migrations


def purge(apps, schema_editor):
    apps.get_model('finance_app', 'RefreshToken').objects.all().delete()


class Migration(migrations.Migration):

    dependencies = [
        ('finance_app', '0001_initial'),
    ]

    operations = [
        migrations.RunPython(purge, migrations.RunPython.noop),
    ]
