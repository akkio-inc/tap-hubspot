"""
Taken from hotglue's implementation of OAuth2Authenticator.
See https://gitlab.com/hotglue/tap-hubspot-beta/-/blob/master/tap_hubspot_beta/auth.py?ref_type=heads
"""

"""hubspot Authentication."""

import json
from datetime import datetime
from typing import Any, Dict, Optional

import requests
from singer_sdk.authenticators import APIAuthenticatorBase
from singer_sdk.streams import Stream as RESTStreamBase

class OAuth2Authenticator(APIAuthenticatorBase):
    """API Authenticator for OAuth 2.0 flows."""

    def __init__(
        self,
        stream: RESTStreamBase
    ) -> None:
        super().__init__(stream=stream)
        self._tap_config = stream.config
        self._tap = stream._tap
        if not hasattr(self._tap, "access_token"):
            self._tap.access_token = None
        if not hasattr(self._tap, "expires_in"):
            self._tap.expires_in = None

        self._auth_endpoint = "https://api.hubapi.com/oauth/v1/token"

    @property
    def auth_headers(self) -> dict:
        """Return a dictionary of auth headers to be applied.

        These will be merged with any `http_headers` specified in the stream.

        Returns:
            HTTP headers for authentication.
        """
        if not self.is_token_valid():
            self.update_access_token()
        result = super().auth_headers
        result["Authorization"] = f"Bearer {self._tap.access_token}"
        return result

    @property
    def auth_endpoint(self) -> str:
        """Get the authorization endpoint.

        Returns:
            The API authorization endpoint if it is set.

        Raises:
            ValueError: If the endpoint is not set.
        """
        if not self._auth_endpoint:
            raise ValueError("Authorization endpoint not set.")
        return self._auth_endpoint

    @property
    def oauth_request_body(self) -> dict:
        """Define the OAuth request body for the hubspot API."""
        return {
            "client_id": self._tap_config["client_id"],
            "client_secret": self._tap_config["client_secret"],
            "redirect_uri": self._tap_config["redirect_uri"],
            "refresh_token": self._tap_config["refresh_token"],
            "grant_type": "refresh_token",
        }

    def is_token_valid(self) -> bool:
        now = round(datetime.utcnow().timestamp())

        # Valid if the token will expire in more than 60 seconds
        return not bool(
            (not self._tap.access_token) or (not self._tap.expires_in) or ((self._tap.expires_in - now) < 60)
        )

    @property
    def oauth_request_payload(self) -> dict:
        """Get request body.

        Returns:
            A plain (OAuth) or encrypted (JWT) request body.
        """
        return self.oauth_request_body

    # Authentication and refresh
    def update_access_token(self) -> None:
        """Update `access_token` along with: `last_refreshed` and `expires_in`.

        Raises:
            RuntimeError: When OAuth login fails.
        """
        request_time = round(datetime.utcnow().timestamp())
        auth_request_payload = self.oauth_request_payload
        token_response = requests.post(self.auth_endpoint, data=auth_request_payload)
        try:
            token_response.raise_for_status()
            self.logger.info("OAuth authorization attempt was successful.")
        except Exception as ex:
            raise RuntimeError(
                f"Failed OAuth login, response was '{token_response.json()}'. {ex}"
            )
        token_json = token_response.json()
        self._tap.access_token = token_json["access_token"]
        self._tap.expires_in = request_time + token_json["expires_in"]

        self.logger.info("Generated new access token")