"""
Multi-Factor Authentication (MFA) Module for LabLink

Provides TOTP-based two-factor authentication with:
- TOTP secret generation
- QR code generation for authenticator apps
- TOTP token validation
- Backup codes generation and validation
- Support for popular authenticator apps (Google Authenticator, Authy, etc.)
"""

import secrets
import string
import base64
import io
from typing import List, Tuple, Optional
import logging

# TOTP implementation
import pyotp

# QR code generation
import qrcode
from qrcode.image.pil import PilImage

# Password hashing for backup codes
import bcrypt

logger = logging.getLogger(__name__)


# ============================================================================
# Configuration
# ============================================================================

# TOTP Configuration
TOTP_ISSUER = "LabLink"  # Shown in authenticator apps
TOTP_INTERVAL = 30  # Time step in seconds (standard is 30)
TOTP_DIGITS = 6  # Number of digits in TOTP code (standard is 6)

# Backup Codes Configuration
BACKUP_CODE_COUNT = 10  # Number of backup codes to generate
BACKUP_CODE_LENGTH = 8  # Length of each backup code


# ============================================================================
# TOTP Functions
# ============================================================================

def generate_totp_secret() -> str:
    """
    Generate a new TOTP secret (base32 encoded).

    Returns:
        Base32 encoded secret string
    """
    secret = pyotp.random_base32()
    logger.info("Generated new TOTP secret")
    return secret


def generate_provisioning_uri(secret: str, username: str, issuer: str = TOTP_ISSUER) -> str:
    """
    Generate a provisioning URI for QR code.

    Args:
        secret: Base32 encoded TOTP secret
        username: Username to associate with the secret
        issuer: Issuer name (default: LabLink)

    Returns:
        otpauth:// URI string
    """
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL, digits=TOTP_DIGITS)
    uri = totp.provisioning_uri(name=username, issuer_name=issuer)
    return uri


def generate_qr_code(provisioning_uri: str) -> str:
    """
    Generate a QR code image as a data URI.

    Args:
        provisioning_uri: otpauth:// URI string

    Returns:
        Data URI (base64 encoded PNG image)
    """
    # Create QR code
    qr = qrcode.QRCode(
        version=1,
        error_correction=qrcode.constants.ERROR_CORRECT_L,
        box_size=10,
        border=4,
    )
    qr.add_data(provisioning_uri)
    qr.make(fit=True)

    # Generate image
    img = qr.make_image(fill_color="black", back_color="white", image_factory=PilImage)

    # Convert to data URI
    buffer = io.BytesIO()
    img.save(buffer, format='PNG')
    img_bytes = buffer.getvalue()
    img_base64 = base64.b64encode(img_bytes).decode('utf-8')
    data_uri = f"data:image/png;base64,{img_base64}"

    logger.info("Generated QR code for TOTP setup")
    return data_uri


def verify_totp_token(secret: str, token: str, window: int = 1) -> bool:
    """
    Verify a TOTP token against a secret.

    Args:
        secret: Base32 encoded TOTP secret
        token: 6-digit TOTP token to verify
        window: Number of time steps to check before/after current time
                (default: 1 = ±30 seconds tolerance)

    Returns:
        True if token is valid
    """
    try:
        totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL, digits=TOTP_DIGITS)
        is_valid = totp.verify(token, valid_window=window)

        if is_valid:
            logger.info("TOTP token verification successful")
        else:
            logger.warning("TOTP token verification failed")

        return is_valid
    except Exception as e:
        logger.error(f"TOTP verification error: {e}")
        return False


def get_current_totp_token(secret: str) -> str:
    """
    Get the current TOTP token for a secret (for testing).

    Args:
        secret: Base32 encoded TOTP secret

    Returns:
        Current 6-digit TOTP token
    """
    totp = pyotp.TOTP(secret, interval=TOTP_INTERVAL, digits=TOTP_DIGITS)
    return totp.now()


# ============================================================================
# Backup Codes Functions
# ============================================================================

def generate_backup_codes(count: int = BACKUP_CODE_COUNT) -> List[str]:
    """
    Generate a list of backup codes.

    Args:
        count: Number of backup codes to generate

    Returns:
        List of plain text backup codes
    """
    codes = []
    for _ in range(count):
        # Generate random alphanumeric code
        code = ''.join(secrets.choice(string.ascii_uppercase + string.digits)
                      for _ in range(BACKUP_CODE_LENGTH))
        # Format with hyphen in the middle for readability
        formatted_code = f"{code[:4]}-{code[4:]}"
        codes.append(formatted_code)

    logger.info(f"Generated {count} backup codes")
    return codes


def hash_backup_code(code: str) -> str:
    """
    Hash a backup code for storage.

    Args:
        code: Plain text backup code

    Returns:
        Bcrypt hashed code
    """
    salt = bcrypt.gensalt()
    hashed = bcrypt.hashpw(code.encode('utf-8'), salt)
    return hashed.decode('utf-8')


def verify_backup_code(plain_code: str, hashed_code: str) -> bool:
    """
    Verify a backup code against a hash.

    Args:
        plain_code: Plain text backup code
        hashed_code: Bcrypt hashed backup code

    Returns:
        True if code matches
    """
    try:
        # Remove hyphen if present
        plain_code = plain_code.replace('-', '').upper()

        is_valid = bcrypt.checkpw(
            plain_code.encode('utf-8'),
            hashed_code.encode('utf-8')
        )

        if is_valid:
            logger.info("Backup code verification successful")
        else:
            logger.warning("Backup code verification failed")

        return is_valid
    except Exception as e:
        logger.error(f"Backup code verification error: {e}")
        return False


def hash_backup_codes(codes: List[str]) -> List[str]:
    """
    Hash a list of backup codes.

    Args:
        codes: List of plain text backup codes

    Returns:
        List of hashed codes
    """
    return [hash_backup_code(code) for code in codes]


# ============================================================================
# MFA Setup Functions
# ============================================================================

def setup_mfa(username: str) -> Tuple[str, str, List[str], str]:
    """
    Complete MFA setup for a user.

    Args:
        username: Username to associate with MFA

    Returns:
        Tuple of (secret, qr_code_data_uri, backup_codes, provisioning_uri)
    """
    # Generate TOTP secret
    secret = generate_totp_secret()

    # Generate provisioning URI
    provisioning_uri = generate_provisioning_uri(secret, username)

    # Generate QR code
    qr_code = generate_qr_code(provisioning_uri)

    # Generate backup codes
    backup_codes = generate_backup_codes()

    logger.info(f"MFA setup completed for user: {username}")

    return secret, qr_code, backup_codes, provisioning_uri


# ============================================================================
# MFA Verification Functions
# ============================================================================

def verify_mfa_token(
    secret: str,
    token: str,
    backup_codes: Optional[List[str]] = None
) -> Tuple[bool, bool]:
    """
    Verify an MFA token (TOTP or backup code).

    Args:
        secret: Base32 encoded TOTP secret
        token: Token to verify (TOTP or backup code)
        backup_codes: List of hashed backup codes

    Returns:
        Tuple of (is_valid, used_backup_code)
    """
    # Try TOTP first
    if verify_totp_token(secret, token):
        return True, False

    # Try backup codes if provided
    if backup_codes:
        for hashed_code in backup_codes:
            if verify_backup_code(token, hashed_code):
                logger.info("Backup code used for MFA verification")
                return True, True

    logger.warning("MFA verification failed (neither TOTP nor backup code matched)")
    return False, False


# ============================================================================
# Utility Functions
# ============================================================================

def format_backup_codes_for_display(codes: List[str]) -> str:
    """
    Format backup codes for user-friendly display.

    Args:
        codes: List of backup codes

    Returns:
        Formatted string with numbered codes
    """
    lines = []
    for i, code in enumerate(codes, 1):
        lines.append(f"{i:2d}. {code}")
    return '\n'.join(lines)
