"""Token storage utility for persisting JWT tokens."""

import json
import logging
from typing import List, Optional, Tuple

from PyQt6.QtCore import QSettings

logger = logging.getLogger(__name__)

# Attempt to import keyring; fall back gracefully on headless systems
try:
    import keyring

    _KEYRING_AVAILABLE = True
except Exception:
    _KEYRING_AVAILABLE = False

_KEYRING_SERVICE = "LabLink"


class TokenStorage:
    """Manages secure storage of authentication tokens."""

    def __init__(self):
        """Initialize token storage."""
        self.settings = QSettings("LabLink", "Client")

    def save_tokens(self, access_token: str, refresh_token: str):
        """Save authentication tokens.

        Stores tokens in the OS keychain when available; falls back to QSettings.

        Args:
            access_token: JWT access token
            refresh_token: JWT refresh token
        """
        if _KEYRING_AVAILABLE:
            try:
                keyring.set_password(_KEYRING_SERVICE, "access_token", access_token)
                keyring.set_password(_KEYRING_SERVICE, "refresh_token", refresh_token)
                # Remove any plaintext copies left from previous installs
                self.settings.remove("access_token")
                self.settings.remove("refresh_token")
                self.settings.sync()
                logger.debug("Tokens saved to keyring")
                return
            except Exception as e:
                logger.warning(f"Keyring save failed, falling back to QSettings: {e}")

        try:
            self.settings.setValue("access_token", access_token)
            self.settings.setValue("refresh_token", refresh_token)
            self.settings.sync()
            logger.debug("Tokens saved to QSettings")
        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")

    def load_tokens(self) -> Tuple[Optional[str], Optional[str]]:
        """Load stored authentication tokens.

        Tries the OS keychain first, then falls back to QSettings for
        compatibility with existing installs.

        Returns:
            Tuple of (access_token, refresh_token), None values if not found
        """
        if _KEYRING_AVAILABLE:
            try:
                access_token = keyring.get_password(_KEYRING_SERVICE, "access_token")
                refresh_token = keyring.get_password(_KEYRING_SERVICE, "refresh_token")
                if access_token and refresh_token:
                    logger.debug("Tokens loaded from keyring")
                    return access_token, refresh_token
            except Exception as e:
                logger.warning(f"Keyring load failed, trying QSettings: {e}")

        try:
            access_token = self.settings.value("access_token", None, type=str)
            refresh_token = self.settings.value("refresh_token", None, type=str)
            if access_token and refresh_token:
                logger.debug("Tokens loaded from QSettings")
                return access_token, refresh_token
        except Exception as e:
            logger.error(f"Failed to load tokens from QSettings: {e}")

        return None, None

    def clear_tokens(self):
        """Clear stored authentication tokens from all backends."""
        if _KEYRING_AVAILABLE:
            try:
                keyring.delete_password(_KEYRING_SERVICE, "access_token")
            except Exception:
                pass
            try:
                keyring.delete_password(_KEYRING_SERVICE, "refresh_token")
            except Exception:
                pass

        try:
            self.settings.remove("access_token")
            self.settings.remove("refresh_token")
            self.settings.sync()
            logger.debug("Tokens cleared successfully")
        except Exception as e:
            logger.error(f"Failed to clear tokens from QSettings: {e}")

    def has_tokens(self) -> bool:
        """Check if tokens are stored.

        Returns:
            True if tokens are available
        """
        access_token, refresh_token = self.load_tokens()
        return bool(access_token and refresh_token)

    def save_user_data(self, user_data: dict):
        """Save user data.

        Args:
            user_data: User information dictionary
        """
        try:
            self.settings.setValue("user_username", user_data.get("username", ""))
            self.settings.setValue("user_email", user_data.get("email", ""))
            self.settings.setValue("user_full_name", user_data.get("full_name", ""))
            self.settings.setValue(
                "user_is_superuser", user_data.get("is_superuser", False)
            )
            self.settings.setValue(
                "user_roles", json.dumps(user_data.get("roles", []))
            )
            self.settings.sync()
            logger.debug("User data saved successfully")
        except Exception as e:
            logger.error(f"Failed to save user data: {e}")

    def load_user_data(self) -> Optional[dict]:
        """Load stored user data.

        Returns:
            User data dictionary or None
        """
        try:
            username = self.settings.value("user_username", "", type=str)
            if not username:
                return None

            roles_raw = self.settings.value("user_roles", "[]", type=str)
            try:
                roles: List[str] = json.loads(roles_raw)
            except (json.JSONDecodeError, TypeError):
                roles = []

            return {
                "username": username,
                "email": self.settings.value("user_email", "", type=str),
                "full_name": self.settings.value("user_full_name", "", type=str),
                "is_superuser": self.settings.value(
                    "user_is_superuser", False, type=bool
                ),
                "roles": roles,
            }

        except Exception as e:
            logger.error(f"Failed to load user data: {e}")
            return None

    def clear_user_data(self):
        """Clear stored user data."""
        try:
            self.settings.remove("user_username")
            self.settings.remove("user_email")
            self.settings.remove("user_full_name")
            self.settings.remove("user_is_superuser")
            self.settings.remove("user_roles")
            self.settings.sync()
            logger.debug("User data cleared successfully")
        except Exception as e:
            logger.error(f"Failed to clear user data: {e}")

    def clear_all(self):
        """Clear all stored authentication data."""
        self.clear_tokens()
        self.clear_user_data()


# Global token storage instance
_token_storage: Optional[TokenStorage] = None


def get_token_storage() -> TokenStorage:
    """Get global token storage instance.

    Returns:
        TokenStorage instance
    """
    global _token_storage
    if _token_storage is None:
        _token_storage = TokenStorage()
    return _token_storage
