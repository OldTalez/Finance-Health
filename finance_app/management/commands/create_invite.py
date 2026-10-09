"""
Issue a single-use registration invite from the command line.

    python manage.py create_invite --label "Family member" --days 7

Prints the plain code once; only its hash is stored. Use this when no admin
login exists yet (for example the very first invite on a fresh deployment).
"""

from django.core.management.base import BaseCommand

from finance_app.models import InviteCode


class Command(BaseCommand):
    help = 'Create a single-use registration invite and print its code once.'

    def add_arguments(self, parser):
        parser.add_argument('--label', default='', help='Who the invite is for (note to self).')
        parser.add_argument('--days', type=int, default=7, help='Days until it expires; 0 means never.')

    def handle(self, *args, **options):
        invite, code = InviteCode.issue(label=options['label'], days=options['days'] or None)
        expiry = invite.expires_at.isoformat() if invite.expires_at else 'never'
        self.stdout.write(f'Invite code (shown once): {code}')
        self.stdout.write(f'Expires: {expiry}')
