"""
Django admin for invite codes (sign-up is invite-only).

Add an invite in /admin/ -> Invite codes -> Add. On save the plain code is shown
once in a banner. Only its hash is stored, so it cannot be shown again.
"""

from datetime import timedelta

from django.contrib import admin, messages
from django.utils import timezone

from .models import InviteCode

DEFAULT_INVITE_DAYS = 7


@admin.register(InviteCode)
class InviteCodeAdmin(admin.ModelAdmin):
    list_display = ('label', 'created_at', 'expires_at', 'used_at', 'used_by')
    fields = ('label', 'expires_at', 'used_at', 'used_by', 'created_at')
    readonly_fields = ('used_at', 'used_by', 'created_at')
    ordering = ('-created_at',)

    def get_changeform_initial_data(self, request):
        return {'expires_at': timezone.now() + timedelta(days=DEFAULT_INVITE_DAYS)}

    def save_model(self, request, obj, form, change):
        if change:
            super().save_model(request, obj, form, change)
            return
        invite, code = InviteCode.issue(label=obj.label)
        invite.expires_at = obj.expires_at
        invite.save(update_fields=['expires_at'])
        obj.pk = invite.pk
        obj.code_hash = invite.code_hash
        obj.created_at = invite.created_at
        messages.warning(
            request,
            f'Invite code (copy it now, it is shown only once): {code}',
        )

    def has_change_permission(self, request, obj=None):
        # Issued codes are immutable except through delete; keeps the audit trail honest
        return False if obj is not None else super().has_change_permission(request, obj)
