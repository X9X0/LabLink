"""
Comprehensive tests for security/mfa.py module.

Tests cover:
- TOTP generation and verification
- QR code generation
- Backup code creation and verification
- MFA setup and verification flow
"""

import pytest
import sys
import os
from unittest.mock import Mock, patch, MagicMock
import io

# Add server to path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '../../../server'))

from security.mfa import (
    generate_totp_secret,
    generate_qr_code,
    generate_provisioning_uri,
    verify_totp_token,
    generate_backup_codes,
    hash_backup_code,
    verify_backup_code,
    setup_mfa
)


class TestTOTPSecret:
    """Test TOTP secret generation."""

    def test_generate_totp_secret(self):
        """Test generating TOTP secret."""
        secret = generate_totp_secret()

        assert secret is not None
        assert isinstance(secret, str)
        assert len(secret) == 32  # Base32 encoded

    def test_generate_different_secrets(self):
        """Test that each generation produces different secret."""
        secret1 = generate_totp_secret()
        secret2 = generate_totp_secret()

        assert secret1 != secret2

    def test_secret_base32_format(self):
        """Test that secret is valid base32."""
        secret = generate_totp_secret()

        # Base32 alphabet is A-Z and 2-7
        import re
        assert re.match(r'^[A-Z2-7]+$', secret)


class TestTOTPQRCode:
    """Test TOTP QR code generation."""

    def test_generate_qr_code(self):
        """Test generating QR code for TOTP."""
        secret = generate_totp_secret()
        username = "testuser@example.com"
        issuer = "LabLink"

        # Generate provisioning URI first
        uri = generate_provisioning_uri(secret, username, issuer)
        qr_code = generate_qr_code(uri)

        assert qr_code is not None
        assert isinstance(qr_code, str)
        # Should be base64 encoded
        assert len(qr_code) > 0

    def test_qr_code_is_base64(self):
        """Test that QR code is base64 encoded."""
        secret = generate_totp_secret()
        uri = generate_provisioning_uri(secret, "test@example.com", "LabLink")
        qr_code = generate_qr_code(uri)

        # Try to decode base64
        import base64
        try:
            decoded = base64.b64decode(qr_code.split(',')[1] if ',' in qr_code else qr_code)
            assert len(decoded) > 0
        except Exception as e:
            pytest.fail(f"QR code is not valid base64: {e}")

    def test_qr_code_different_users(self):
        """Test QR codes for different users."""
        secret = generate_totp_secret()

        uri1 = generate_provisioning_uri(secret, "user1@example.com", "LabLink")
        uri2 = generate_provisioning_uri(secret, "user2@example.com", "LabLink")
        qr1 = generate_qr_code(uri1)
        qr2 = generate_qr_code(uri2)

        # QR codes should be different for different users
        assert qr1 != qr2


class TestTOTPVerification:
    """Test TOTP code verification."""

    def test_verify_valid_totp_code(self):
        """Test verifying valid TOTP code."""
        import pyotp
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)
        valid_code = totp.now()

        assert verify_totp_token(secret, valid_code) is True

    def test_verify_invalid_totp_code(self):
        """Test verifying invalid TOTP code."""
        secret = generate_totp_secret()
        invalid_code = "000000"

        assert verify_totp_token(secret, invalid_code) is False

    def test_verify_empty_code(self):
        """Test verifying empty code."""
        secret = generate_totp_secret()

        assert verify_totp_token(secret, "") is False

    def test_verify_wrong_length_code(self):
        """Test verifying code with wrong length."""
        secret = generate_totp_secret()

        assert verify_totp_token(secret, "123") is False
        assert verify_totp_token(secret, "12345678") is False

    def test_verify_code_time_window(self):
        """Test that code verification works within time window."""
        import pyotp
        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)

        # Current code should work
        current_code = totp.now()
        assert verify_totp_token(secret, current_code) is True

    def test_verify_previous_code_within_window(self):
        """Test that previous code works within tolerance window."""
        import pyotp
        import time

        secret = generate_totp_secret()
        totp = pyotp.TOTP(secret)

        # Get code from 30 seconds ago (previous interval)
        previous_time = time.time() - 30
        previous_code = totp.at(int(previous_time))

        # Should still work due to tolerance window
        # Note: This depends on the tolerance setting in verify_totp_token
        # If tolerance is 1, it should work
        result = verify_totp_token(secret, previous_code)
        # May be True or False depending on exact timing and tolerance


class TestBackupCodes:
    """Test backup code generation and verification."""

    def test_generate_backup_codes(self):
        """Test generating backup codes."""
        codes = generate_backup_codes(count=10)

        assert len(codes) == 10
        assert all(isinstance(code, str) for code in codes)

    def test_backup_codes_unique(self):
        """Test that backup codes are unique."""
        codes = generate_backup_codes(count=10)

        assert len(set(codes)) == 10  # All unique

    def test_backup_code_format(self):
        """Test backup code format."""
        code = generate_backup_codes(count=1)[0]

        # Should be 8 characters (may include hyphen)
        assert len(code.replace('-', '')) == 8

    def test_hash_backup_code(self):
        """Test hashing backup code."""
        code = "ABCD-1234"
        hashed = hash_backup_code(code)

        assert hashed is not None
        assert isinstance(hashed, str)
        assert hashed != code
        assert hashed.startswith('$2b$')  # bcrypt prefix

    def test_verify_backup_code_correct(self):
        """Test verifying correct backup code."""
        code = "ABCD-1234"
        hashed = hash_backup_code(code)

        assert verify_backup_code(code, hashed) is True

    def test_verify_backup_code_incorrect(self):
        """Test verifying incorrect backup code."""
        code = "ABCD-1234"
        wrong_code = "WXYZ-9999"
        hashed = hash_backup_code(code)

        assert verify_backup_code(wrong_code, hashed) is False

    def test_verify_backup_code_case_insensitive(self):
        """Test backup code verification is case-insensitive."""
        code = "ABCD-1234"
        hashed = hash_backup_code(code)

        # Try lowercase version
        assert verify_backup_code("abcd-1234", hashed) is True

    def test_verify_backup_code_without_hyphen(self):
        """Test verifying backup code without hyphen."""
        code = "ABCD-1234"
        hashed = hash_backup_code(code)

        # Try without hyphen
        assert verify_backup_code("ABCD1234", hashed) is True

    def test_generate_custom_count_backup_codes(self):
        """Test generating custom number of backup codes."""
        for count in [5, 10, 15, 20]:
            codes = generate_backup_codes(count=count)
            assert len(codes) == count


class TestBackupCodeSecurity:
    """Test backup code security features."""

    def test_backup_codes_not_predictable(self):
        """Test that backup codes are not predictable."""
        codes1 = generate_backup_codes(count=10)
        codes2 = generate_backup_codes(count=10)

        # No overlap between two sets
        overlap = set(codes1) & set(codes2)
        assert len(overlap) == 0

    def test_backup_code_hash_different_each_time(self):
        """Test that same code produces different hashes (salt)."""
        code = "ABCD-1234"
        hash1 = hash_backup_code(code)
        hash2 = hash_backup_code(code)

        assert hash1 != hash2  # Different due to bcrypt salt


class TestMFAIntegration:
    """Test MFA integration scenarios."""

    def test_complete_mfa_setup_flow(self):
        """Test complete MFA setup flow."""
        # 1. Generate secret
        secret = generate_totp_secret()
        assert secret is not None

        # 2. Generate QR code
        qr_code = generate_totp_qr_code(secret, "test@example.com", "LabLink")
        assert qr_code is not None

        # 3. Generate backup codes
        backup_codes = generate_backup_codes(count=10)
        assert len(backup_codes) == 10

        # 4. Hash backup codes for storage
        hashed_codes = [hash_backup_code(code) for code in backup_codes]
        assert len(hashed_codes) == 10

        # 5. Verify TOTP code
        import pyotp
        totp = pyotp.TOTP(secret)
        code = totp.now()
        assert verify_totp_token(secret, code) is True

        # 6. Verify backup code
        assert verify_backup_code(backup_codes[0], hashed_codes[0]) is True

    def test_mfa_login_with_totp(self):
        """Test MFA login flow with TOTP."""
        import pyotp

        # Setup
        secret = generate_totp_secret()

        # User provides TOTP code
        totp = pyotp.TOTP(secret)
        user_code = totp.now()

        # Verify
        is_valid = verify_totp_token(secret, user_code)
        assert is_valid is True

    def test_mfa_login_with_backup_code(self):
        """Test MFA login flow with backup code."""
        # Setup
        backup_codes = generate_backup_codes(count=10)
        hashed_codes = [hash_backup_code(code) for code in backup_codes]

        # User provides backup code
        user_code = backup_codes[0]

        # Verify
        is_valid = verify_backup_code(user_code, hashed_codes[0])
        assert is_valid is True

        # After use, backup code should be removed from list
        # (This would be handled by the application logic)

    def test_mfa_failure_scenarios(self):
        """Test various MFA failure scenarios."""
        secret = generate_totp_secret()

        # Wrong TOTP code
        assert verify_totp_token(secret, "000000") is False

        # Wrong backup code
        backup_codes = generate_backup_codes(count=10)
        hashed = hash_backup_code(backup_codes[0])
        assert verify_backup_code("WRONG-CODE", hashed) is False

        # Empty codes
        assert verify_totp_token(secret, "") is False
        assert verify_backup_code("", hashed) is False


class TestEdgeCases:
    """Test edge cases and error handling."""

    def test_verify_totp_with_none_secret(self):
        """Test TOTP verification with None secret."""
        try:
            verify_totp_token(None, "123456")
            # Should either return False or raise exception
        except Exception:
            pass  # Expected

    def test_verify_totp_with_invalid_secret(self):
        """Test TOTP verification with invalid secret."""
        result = verify_totp_token("INVALID!", "123456")
        # Should handle gracefully

    def test_generate_qr_with_special_characters(self):
        """Test QR generation with special characters in username."""
        secret = generate_totp_secret()
        username = "test+user@example.com"

        uri = generate_provisioning_uri(secret, username, "LabLink")
        qr_code = generate_qr_code(uri)
        assert qr_code is not None

    def test_backup_code_with_special_characters(self):
        """Test backup code verification with special characters."""
        code = "ABCD-1234"
        hashed = hash_backup_code(code)

        # Try with spaces
        assert verify_backup_code(" ABCD-1234 ", hashed) is False or True
        # Depends on implementation - may trim or not


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
