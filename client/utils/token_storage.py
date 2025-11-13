"""Token storage utility for persisting JWT tokens."""

from PyQt6.QtCore import QSettings
from typing import Optional, Tuple
import logging

logger = logging.getLogger(__name__)


class TokenStorage:
    """Manages secure storage of authentication tokens."""

    def __init__(self):
        """Initialize token storage."""
        self.settings = QSettings("LabLink", "Client")

    def save_tokens(self, access_token: str, refresh_token: str):
        """Save authentication tokens.

        Args:
            access_token: JWT access token
            refresh_token: JWT refresh token
        """
        try:
            self.settings.setValue("access_token", access_token)
            self.settings.setValue("refresh_token", refresh_token)
            self.settings.sync()
            logger.debug("Tokens saved successfully")
        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")

    def load_tokens(self) -> Tuple[Optional[str], Optional[str]]:
        """Load stored authentication tokens.

        Returns:
            Tuple of (access_token, refresh_token), None if not found
        """
        try:
            access_token = self.settings.value("access_token", None, type=str)
            refresh_token = self.settings.value("refresh_token", None, type=str)

            if access_token and refresh_token:
                logger.debug("Tokens loaded successfully")
                return access_token, refresh_token
            else:
                return None, None

        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
            return None, None

    def clear_tokens(self):
        """Clear stored authentication tokens."""
        try:
            self.settings.remove("access_token")
            self.settings.remove("refresh_token")
            self.settings.sync()
            logger.debug("Tokens cleared successfully")
        except Exception as e:
            logger.error(f"Failed to clear tokens: {e}")

    def has_tokens(self) -> bool:
        """Check if tokens are stored.

        Returns:
            True if tokens are available
        """
        access_token = self.settings.value("access_token", None, type=str)
        refresh_token = self.settings.value("refresh_token", None, type=str)
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
            self.settings.setValue("user_is_superuser", user_data.get("is_superuser", False))
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

            return {
                "username": username,
                "email": self.settings.value("user_email", "", type=str),
                "full_name": self.settings.value("user_full_name", "", type=str),
                "is_superuser": self.settings.value("user_is_superuser", False, type=bool),
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
