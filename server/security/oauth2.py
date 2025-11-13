"""
OAuth2 Authentication Providers

Implements OAuth2 authentication flows for external identity providers:
- Google
- GitHub
- Microsoft
- Custom providers

Supports:
- Authorization code flow
- Token exchange
- User information retrieval
- Account linking
"""

import httpx
from typing import Dict, Any, Optional, Tuple
from datetime import datetime, timedelta
from urllib.parse import urlencode

from .models import OAuth2Provider, OAuth2Config, User
from logging_config import get_logger

logger = get_logger(__name__)


# ============================================================================
# OAuth2 Provider Configurations
# ============================================================================

# Default OAuth2 provider endpoints and scopes
OAUTH2_DEFAULTS = {
    OAuth2Provider.GOOGLE: {
        "authorization_url": "https://accounts.google.com/o/oauth2/v2/auth",
        "token_url": "https://oauth2.googleapis.com/token",
        "user_info_url": "https://www.googleapis.com/oauth2/v3/userinfo",
        "scopes": ["openid", "email", "profile"],
    },
    OAuth2Provider.GITHUB: {
        "authorization_url": "https://github.com/login/oauth/authorize",
        "token_url": "https://github.com/login/oauth/access_token",
        "user_info_url": "https://api.github.com/user",
        "scopes": ["read:user", "user:email"],
    },
    OAuth2Provider.MICROSOFT: {
        "authorization_url": "https://login.microsoftonline.com/common/oauth2/v2.0/authorize",
        "token_url": "https://login.microsoftonline.com/common/oauth2/v2.0/token",
        "user_info_url": "https://graph.microsoft.com/v1.0/me",
        "scopes": ["openid", "email", "profile"],
    },
}


# ============================================================================
# OAuth2 Provider Base Class
# ============================================================================

class OAuth2ProviderBase:
    """Base class for OAuth2 providers."""

    def __init__(self, config: OAuth2Config):
        """
        Initialize OAuth2 provider.

        Args:
            config: Provider configuration
        """
        self.config = config
        self.provider = config.provider

    def get_authorization_url(self, redirect_uri: str, state: Optional[str] = None) -> str:
        """
        Generate authorization URL for OAuth2 flow.

        Args:
            redirect_uri: Redirect URI after authorization
            state: Optional state parameter for CSRF protection

        Returns:
            Authorization URL
        """
        params = {
            "client_id": self.config.client_id,
            "redirect_uri": redirect_uri,
            "response_type": "code",
            "scope": " ".join(self.config.scopes),
        }

        if state:
            params["state"] = state

        return f"{self.config.authorization_url}?{urlencode(params)}"

    async def exchange_code_for_token(
        self, code: str, redirect_uri: str
    ) -> Dict[str, Any]:
        """
        Exchange authorization code for access token.

        Args:
            code: Authorization code from OAuth2 provider
            redirect_uri: Redirect URI used in authorization

        Returns:
            Token response containing access_token and other fields

        Raises:
            Exception: If token exchange fails
        """
        data = {
            "client_id": self.config.client_id,
            "client_secret": self.config.client_secret,
            "code": code,
            "redirect_uri": redirect_uri,
            "grant_type": "authorization_code",
        }

        headers = {"Accept": "application/json"}

        async with httpx.AsyncClient() as client:
            response = await client.post(
                self.config.token_url,
                data=data,
                headers=headers,
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(
                    f"OAuth2 token exchange failed for {self.provider}: {error_text}"
                )
                raise Exception(f"Token exchange failed: {error_text}")

            return response.json()

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """
        Retrieve user information from OAuth2 provider.

        Args:
            access_token: Access token from OAuth2 provider

        Returns:
            User information dictionary

        Raises:
            Exception: If user info retrieval fails
        """
        headers = {
            "Authorization": f"Bearer {access_token}",
            "Accept": "application/json",
        }

        async with httpx.AsyncClient() as client:
            response = await client.get(
                self.config.user_info_url,
                headers=headers,
            )

            if response.status_code != 200:
                error_text = response.text
                logger.error(
                    f"OAuth2 user info failed for {self.provider}: {error_text}"
                )
                raise Exception(f"User info retrieval failed: {error_text}")

            return response.json()

    def extract_user_data(self, user_info: Dict[str, Any]) -> Tuple[str, str, str]:
        """
        Extract standardized user data from provider-specific response.

        Args:
            user_info: Provider-specific user information

        Returns:
            Tuple of (external_id, email, full_name)
        """
        # Default implementation - override in provider-specific classes
        external_id = str(user_info.get("id", user_info.get("sub", "")))
        email = user_info.get("email", "")
        full_name = user_info.get("name", "")

        return external_id, email, full_name


# ============================================================================
# Google OAuth2 Provider
# ============================================================================

class GoogleOAuth2Provider(OAuth2ProviderBase):
    """Google OAuth2 provider implementation."""

    def extract_user_data(self, user_info: Dict[str, Any]) -> Tuple[str, str, str]:
        """Extract user data from Google user info response."""
        external_id = user_info.get("sub", "")  # Google user ID
        email = user_info.get("email", "")
        full_name = user_info.get("name", "")

        return external_id, email, full_name


# ============================================================================
# GitHub OAuth2 Provider
# ============================================================================

class GitHubOAuth2Provider(OAuth2ProviderBase):
    """GitHub OAuth2 provider implementation."""

    async def get_user_info(self, access_token: str) -> Dict[str, Any]:
        """Retrieve user information from GitHub (includes email separately)."""
        # Get user profile
        user_info = await super().get_user_info(access_token)

        # GitHub requires separate API call for email if not public
        if not user_info.get("email"):
            headers = {
                "Authorization": f"Bearer {access_token}",
                "Accept": "application/json",
            }

            async with httpx.AsyncClient() as client:
                email_response = await client.get(
                    "https://api.github.com/user/emails",
                    headers=headers,
                )

                if email_response.status_code == 200:
                    emails = email_response.json()
                    # Get primary email
                    for email_data in emails:
                        if email_data.get("primary") and email_data.get("verified"):
                            user_info["email"] = email_data.get("email")
                            break

        return user_info

    def extract_user_data(self, user_info: Dict[str, Any]) -> Tuple[str, str, str]:
        """Extract user data from GitHub user info response."""
        external_id = str(user_info.get("id", ""))  # GitHub user ID
        email = user_info.get("email", "")
        full_name = user_info.get("name", user_info.get("login", ""))

        return external_id, email, full_name


# ============================================================================
# Microsoft OAuth2 Provider
# ============================================================================

class MicrosoftOAuth2Provider(OAuth2ProviderBase):
    """Microsoft OAuth2 provider implementation."""

    def extract_user_data(self, user_info: Dict[str, Any]) -> Tuple[str, str, str]:
        """Extract user data from Microsoft user info response."""
        external_id = user_info.get("id", "")  # Microsoft user ID
        email = user_info.get("mail", user_info.get("userPrincipalName", ""))
        full_name = user_info.get("displayName", "")

        return external_id, email, full_name


# ============================================================================
# OAuth2 Manager
# ============================================================================

class OAuth2Manager:
    """Manages OAuth2 providers and authentication flows."""

    def __init__(self):
        """Initialize OAuth2 manager."""
        self.providers: Dict[OAuth2Provider, OAuth2ProviderBase] = {}

    def configure_provider(self, config: OAuth2Config):
        """
        Configure an OAuth2 provider.

        Args:
            config: Provider configuration
        """
        # Create provider instance based on type
        if config.provider == OAuth2Provider.GOOGLE:
            provider = GoogleOAuth2Provider(config)
        elif config.provider == OAuth2Provider.GITHUB:
            provider = GitHubOAuth2Provider(config)
        elif config.provider == OAuth2Provider.MICROSOFT:
            provider = MicrosoftOAuth2Provider(config)
        else:
            provider = OAuth2ProviderBase(config)

        self.providers[config.provider] = provider
        logger.info(f"OAuth2 provider configured: {config.provider}")

    def get_provider(self, provider: OAuth2Provider) -> Optional[OAuth2ProviderBase]:
        """
        Get configured OAuth2 provider.

        Args:
            provider: Provider type

        Returns:
            Provider instance or None if not configured
        """
        return self.providers.get(provider)

    def is_provider_enabled(self, provider: OAuth2Provider) -> bool:
        """
        Check if provider is configured and enabled.

        Args:
            provider: Provider type

        Returns:
            True if provider is configured and enabled
        """
        prov = self.providers.get(provider)
        return prov is not None and prov.config.enabled

    def get_enabled_providers(self) -> list[OAuth2Provider]:
        """
        Get list of enabled providers.

        Returns:
            List of enabled provider types
        """
        return [
            provider
            for provider, prov in self.providers.items()
            if prov.config.enabled
        ]

    async def authenticate(
        self, provider: OAuth2Provider, code: str, redirect_uri: str
    ) -> Tuple[str, str, str]:
        """
        Authenticate user with OAuth2 provider.

        Args:
            provider: Provider type
            code: Authorization code
            redirect_uri: Redirect URI used in authorization

        Returns:
            Tuple of (external_id, email, full_name)

        Raises:
            Exception: If authentication fails or provider not configured
        """
        prov = self.get_provider(provider)
        if not prov:
            raise Exception(f"OAuth2 provider not configured: {provider}")

        if not prov.config.enabled:
            raise Exception(f"OAuth2 provider disabled: {provider}")

        # Exchange code for token
        token_response = await prov.exchange_code_for_token(code, redirect_uri)
        access_token = token_response.get("access_token")

        if not access_token:
            raise Exception("No access token received from OAuth2 provider")

        # Get user info
        user_info = await prov.get_user_info(access_token)

        # Extract standardized user data
        external_id, email, full_name = prov.extract_user_data(user_info)

        logger.info(
            f"OAuth2 authentication successful: {provider} - {email} ({external_id})"
        )

        return external_id, email, full_name


# Global OAuth2 manager instance
_oauth2_manager: Optional[OAuth2Manager] = None


def get_oauth2_manager() -> OAuth2Manager:
    """
    Get global OAuth2 manager instance.

    Returns:
        OAuth2 manager instance
    """
    global _oauth2_manager
    if _oauth2_manager is None:
        _oauth2_manager = OAuth2Manager()
    return _oauth2_manager


def init_oauth2_manager(configs: list[OAuth2Config]) -> OAuth2Manager:
    """
    Initialize OAuth2 manager with provider configurations.

    Args:
        configs: List of OAuth2 provider configurations

    Returns:
        Initialized OAuth2 manager
    """
    manager = get_oauth2_manager()

    for config in configs:
        manager.configure_provider(config)

    return manager
