"""
Utility modules: JWT, encryption, audit logging, validators
"""

import jwt
import logging
import uuid
from datetime import timedelta
from django.utils import timezone
from django.conf import settings
from rest_framework.authentication import TokenAuthentication
from rest_framework.exceptions import AuthenticationFailed

logger = logging.getLogger(__name__)


# ============ JWT UTILITIES ============

class JWTUtils:
    """JWT token generation and validation"""

    SECRET = settings.JWT_SECRET
    ALGORITHM = settings.JWT_ALGORITHM
    EXPIRY = settings.JWT_EXPIRY
    REFRESH_EXPIRY = settings.REFRESH_TOKEN_EXPIRY

    @classmethod
    def generate_tokens(cls, user, family_id=None):
        """Generate access and refresh tokens. Only a hash of the refresh token is stored."""
        from .models import RefreshToken

        now = timezone.now()

        # Access token (15-min expiry)
        access_payload = {
            'user_id': user.id,
            'email': user.email,
            'type': 'access',
            'iat': int(now.timestamp()),
            'exp': int((now + cls.EXPIRY).timestamp())
        }
        access_token = jwt.encode(access_payload, cls.SECRET, algorithm=cls.ALGORITHM)

        # Refresh token (7-day expiry); jti makes every token unique
        refresh_payload = {
            'user_id': user.id,
            'type': 'refresh',
            'jti': uuid.uuid4().hex,
            'iat': int(now.timestamp()),
            'exp': int((now + cls.REFRESH_EXPIRY).timestamp())
        }
        refresh_token = jwt.encode(refresh_payload, cls.SECRET, algorithm=cls.ALGORITHM)

        RefreshToken.objects.create(
            user=user,
            token_hash=RefreshToken.hash_token(refresh_token),
            family_id=family_id or uuid.uuid4(),
            expires_at=now + cls.REFRESH_EXPIRY
        )

        return access_token, refresh_token, int(cls.EXPIRY.total_seconds())

    @classmethod
    def verify_token(cls, token, is_refresh=False):
        """Verify and decode token"""
        try:
            payload = jwt.decode(token, cls.SECRET, algorithms=[cls.ALGORITHM])

            # Check token type
            if is_refresh and payload.get('type') != 'refresh':
                raise AuthenticationFailed('Invalid token type')
            if not is_refresh and payload.get('type') != 'access':
                raise AuthenticationFailed('Invalid token type')

            return payload
        except jwt.ExpiredSignatureError:
            raise AuthenticationFailed('Token expired')
        except jwt.InvalidTokenError:
            raise AuthenticationFailed('Invalid token')

    @classmethod
    def get_user_from_token(cls, token):
        """Get user ID from token"""
        try:
            payload = cls.verify_token(token, is_refresh=False)
            return payload['user_id']
        except Exception:
            return None

    @classmethod
    def rotate_refresh_token(cls, raw_token):
        """
        Exchange a refresh token for a new pair.

        Returns (access, refresh, expires_in) or None when the token is unknown,
        expired, revoked or its user is inactive. Reuse of a revoked token
        revokes the entire family.
        """
        from .models import RefreshToken

        if not isinstance(raw_token, str):
            return None
        try:
            cls.verify_token(raw_token, is_refresh=True)
        except AuthenticationFailed:
            return None

        token_hash = RefreshToken.hash_token(raw_token)
        record = RefreshToken.objects.select_related('user').filter(token_hash=token_hash).first()
        if record is None:
            return None

        now = timezone.now()
        if record.is_revoked:
            # Reuse of a rotated or logged-out token: assume theft, kill the family
            RefreshToken.objects.filter(family_id=record.family_id).update(is_revoked=True)
            logger.warning('Refresh token reuse detected; family revoked (user_id=%s)', record.user_id)
            return None
        if record.expires_at <= now or not record.user.is_active:
            return None

        # Atomic claim: only one concurrent request can flip is_revoked
        claimed = RefreshToken.objects.filter(pk=record.pk, is_revoked=False).update(is_revoked=True)
        if claimed != 1:
            RefreshToken.objects.filter(family_id=record.family_id).update(is_revoked=True)
            return None

        return cls.generate_tokens(record.user, family_id=record.family_id)

    @classmethod
    def revoke_refresh_token(cls, raw_token):
        """Revoke the family of this refresh token (logout). Returns True if found."""
        from .models import RefreshToken

        record = RefreshToken.objects.filter(token_hash=RefreshToken.hash_token(raw_token)).first()
        if record is None:
            return False
        RefreshToken.objects.filter(family_id=record.family_id).update(is_revoked=True)
        return True


class JWTAuthentication(TokenAuthentication):
    """Custom authentication using JWT"""

    def authenticate(self, request):
        auth = request.META.get('HTTP_AUTHORIZATION', '').split()

        if not auth or auth[0].lower() != 'bearer':
            return None

        if len(auth) == 1:
            raise AuthenticationFailed('No token provided')

        try:
            token = auth[1]
            payload = JWTUtils.verify_token(token, is_refresh=False)

            from .models import User
            user = User.objects.get(id=payload['user_id'])
            if not user.is_active:
                raise AuthenticationFailed('User inactive')
            return (user, None)
        except AuthenticationFailed:
            raise
        except Exception as e:
            raise AuthenticationFailed('Invalid authentication')


# ============ ENCRYPTION UTILITIES ============

class EncryptionUtils:
    """AES-256-GCM encryption for sensitive fields"""

    @staticmethod
    def encrypt(plaintext, user_key=None):
        """Encrypt plaintext using AES-256-GCM"""
        # Note: Full implementation would use cryptography.Fernet or similar
        # For now, return as-is (TODO: implement proper encryption)
        return plaintext

    @staticmethod
    def decrypt(ciphertext, user_key=None):
        """Decrypt ciphertext using AES-256-GCM"""
        # Note: Full implementation would use cryptography.Fernet or similar
        return ciphertext


# ============ AUDIT LOGGING ============

class AuditLogger:
    """Log user actions for compliance"""

    @staticmethod
    def log(user, action, resource_type, resource_id, details=None, request=None):
        """Log an audit event"""
        try:
            from .models import AuditLog

            ip_address = None
            user_agent = None

            if request:
                x_forwarded_for = request.META.get('HTTP_X_FORWARDED_FOR')
                if x_forwarded_for:
                    ip_address = x_forwarded_for.split(',')[0].strip()
                else:
                    ip_address = request.META.get('REMOTE_ADDR')
                user_agent = request.META.get('HTTP_USER_AGENT')

            AuditLog.objects.create(
                user=user,
                action=action,
                resource_type=resource_type,
                resource_id=resource_id,
                details=details or {},
                ip_address=ip_address,
                user_agent=user_agent
            )
        except Exception as e:
            logger.error(f"Audit logging failed: {e}")


# ============ VALIDATORS ============

class PasswordValidator:
    """Validate password strength"""

    MIN_LENGTH = 12
    REQUIRED_UPPERCASE = True
    REQUIRED_LOWERCASE = True
    REQUIRED_DIGIT = True
    REQUIRED_SPECIAL = True

    @classmethod
    def validate(cls, password):
        """Validate password and return list of errors"""
        errors = []

        if len(password) < cls.MIN_LENGTH:
            errors.append(f"Password must be at least {cls.MIN_LENGTH} characters")

        if cls.REQUIRED_UPPERCASE and not any(c.isupper() for c in password):
            errors.append("Password must contain at least one uppercase letter")

        if cls.REQUIRED_LOWERCASE and not any(c.islower() for c in password):
            errors.append("Password must contain at least one lowercase letter")

        if cls.REQUIRED_DIGIT and not any(c.isdigit() for c in password):
            errors.append("Password must contain at least one digit")

        if cls.REQUIRED_SPECIAL:
            import re
            if not re.search(r'[!@#$%^&*(),.?":{}|<>]', password):
                errors.append("Password must contain at least one special character")

        return errors


class EmailValidator:
    """Validate email format"""

    @staticmethod
    def validate(email):
        """Validate email and return error or None"""
        import re
        pattern = r'^[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$'
        if not re.match(pattern, email):
            return "Invalid email format"
        return None
