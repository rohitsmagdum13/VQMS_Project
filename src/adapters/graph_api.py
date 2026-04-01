"""Module: adapters/graph_api.py

Microsoft Graph API adapter for VQMS.

Handles authentication via MSAL (OAuth 2.0 Client Credentials Flow)
and provides methods to fetch emails and attachments from Exchange
Online. This is the only module that talks to Graph API — all other
modules use this adapter.

The adapter supports two email detection modes:
  1. Polling (primary for dev) — queries unread messages every 60s
  2. Webhook (production) — receives push notifications for new emails

Authentication uses application permissions: Mail.Read, Mail.ReadWrite.
Credentials are loaded from environment variables (dev) or AWS Secrets
Manager (production).

Usage:
    from src.adapters.graph_api import GraphAPIAdapter

    graph = GraphAPIAdapter()
    email = await graph.fetch_message(message_id)
    attachments = await graph.fetch_attachments(message_id)
    unread = await graph.list_unread_messages()
"""

from __future__ import annotations

import logging
import os
from typing import Any

import httpx
import msal

logger = logging.getLogger(__name__)


class GraphAPIError(Exception):
    """Raised when a Graph API call fails.

    Covers: auth failure, message not found, throttling (429),
    network errors, and unexpected response formats.
    """


# Graph API base URL — v1.0 is the stable endpoint
GRAPH_API_BASE_URL = "https://graph.microsoft.com/v1.0"

# Scope for application-level mail access
GRAPH_API_SCOPE = "https://graph.microsoft.com/.default"


class GraphAPIAdapter:
    """Adapter for Microsoft Graph API email operations.

    Handles OAuth token acquisition via MSAL and provides typed
    methods for fetching emails and attachments. Tokens are cached
    and refreshed automatically by the MSAL library.

    All methods accept optional correlation_id for log tracing.
    """

    def __init__(self) -> None:
        """Initialize the adapter with credentials from environment.

        Creates an MSAL ConfidentialClientApplication for token management.
        Does not make any API calls until a method is invoked.
        """
        self._tenant_id = os.getenv("GRAPH_API_TENANT_ID", "")
        self._client_id = os.getenv("GRAPH_API_CLIENT_ID", "")
        self._client_secret = os.getenv("GRAPH_API_CLIENT_SECRET", "")
        self._mailbox = os.getenv(
            "GRAPH_API_MAILBOX", "vendorsupport@yourcompany.com"
        )

        # MSAL handles token caching and refresh internally
        self._msal_app = msal.ConfidentialClientApplication(
            client_id=self._client_id,
            client_credential=self._client_secret,
            authority=f"https://login.microsoftonline.com/{self._tenant_id}",
        )

        # Reusable async HTTP client for Graph API calls
        self._http_client = httpx.AsyncClient(timeout=30.0)

    async def _get_access_token(self) -> str:
        """Acquire an OAuth access token from Azure AD.

        Uses MSAL's client credentials flow. Tokens are cached by
        MSAL and only refreshed when they expire.

        Returns:
            A valid access token string.

        Raises:
            GraphAPIError: If token acquisition fails.
        """
        result = self._msal_app.acquire_token_for_client(
            scopes=[GRAPH_API_SCOPE]
        )

        if "access_token" not in result:
            error_desc = result.get("error_description", "Unknown error")
            raise GraphAPIError(
                f"Failed to acquire Graph API access token: {error_desc}"
            )

        return result["access_token"]

    async def _make_request(
        self,
        method: str,
        url: str,
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Make an authenticated request to the Graph API.

        Handles token acquisition, header setting, and error handling
        for all Graph API calls.

        Args:
            method: HTTP method ('GET', 'POST', etc.).
            url: Full Graph API URL.
            correlation_id: Tracing ID for log context.

        Returns:
            Parsed JSON response as a dict.

        Raises:
            GraphAPIError: If the request fails.
        """
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._http_client.request(
                method, url, headers=headers
            )

            # Handle common error codes
            if response.status_code == 404:
                raise GraphAPIError(
                    f"Resource not found: {url}"
                )
            if response.status_code == 429:
                # Graph API throttling — caller should retry with backoff
                raise GraphAPIError(
                    "Graph API rate limit exceeded (429). Retry with backoff."
                )
            if response.status_code >= 400:
                raise GraphAPIError(
                    f"Graph API error {response.status_code}: {response.text}"
                )

            return response.json()
        except httpx.RequestError as exc:
            raise GraphAPIError(
                f"Graph API network error: {exc}"
            ) from exc

    # --------------------------------------------------------
    # Email Operations
    # --------------------------------------------------------

    async def fetch_message(
        self,
        message_id: str,
        *,
        correlation_id: str | None = None,
    ) -> dict[str, Any]:
        """Fetch a single email by its Exchange Online message ID.

        Retrieves the full email including body, headers, and metadata.
        The attachment content is NOT included — use fetch_attachments()
        separately when hasAttachments is True.

        Args:
            message_id: Exchange Online message ID.
            correlation_id: Tracing ID for log context.

        Returns:
            Graph API message resource as a dict with fields:
            id, subject, sender, body, receivedDateTime,
            hasAttachments, conversationId, internetMessageId, etc.

        Raises:
            GraphAPIError: If the fetch fails.
        """
        url = (
            f"{GRAPH_API_BASE_URL}/users/{self._mailbox}"
            f"/messages/{message_id}"
        )

        logger.info(
            "Fetching email from Graph API",
            extra={
                "message_id": message_id,
                "correlation_id": correlation_id,
            },
        )

        return await self._make_request("GET", url, correlation_id=correlation_id)

    async def list_unread_messages(
        self,
        *,
        max_results: int = 50,
        correlation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """List unread messages in the shared mailbox.

        Used for polling-based email detection. Returns messages
        ordered by receivedDateTime descending (newest first).

        Args:
            max_results: Maximum number of messages to return.
            correlation_id: Tracing ID for log context.

        Returns:
            List of Graph API message resource dicts.

        Raises:
            GraphAPIError: If the list operation fails.
        """
        url = (
            f"{GRAPH_API_BASE_URL}/users/{self._mailbox}/messages"
            f"?$filter=isRead eq false"
            f"&$orderby=receivedDateTime desc"
            f"&$top={max_results}"
        )

        logger.info(
            "Listing unread messages from Graph API",
            extra={"max_results": max_results, "correlation_id": correlation_id},
        )

        response = await self._make_request("GET", url, correlation_id=correlation_id)
        return response.get("value", [])

    async def fetch_attachments(
        self,
        message_id: str,
        *,
        correlation_id: str | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch all attachments for a given email.

        Returns metadata and content for each attachment. Called only
        when the email's hasAttachments flag is True.

        Args:
            message_id: Exchange Online message ID.
            correlation_id: Tracing ID for log context.

        Returns:
            List of attachment dicts with fields: name, contentType,
            size, contentBytes (base64 encoded), isInline, contentId.

        Raises:
            GraphAPIError: If the fetch fails.
        """
        url = (
            f"{GRAPH_API_BASE_URL}/users/{self._mailbox}"
            f"/messages/{message_id}/attachments"
        )

        logger.info(
            "Fetching attachments from Graph API",
            extra={
                "message_id": message_id,
                "correlation_id": correlation_id,
            },
        )

        response = await self._make_request("GET", url, correlation_id=correlation_id)
        return response.get("value", [])

    async def mark_as_read(
        self,
        message_id: str,
        *,
        correlation_id: str | None = None,
    ) -> None:
        """Mark an email as read in Exchange Online.

        Called after successful ingestion to prevent the polling
        mechanism from picking up the same email again.

        Args:
            message_id: Exchange Online message ID.
            correlation_id: Tracing ID for log context.

        Raises:
            GraphAPIError: If the update fails.
        """
        url = (
            f"{GRAPH_API_BASE_URL}/users/{self._mailbox}"
            f"/messages/{message_id}"
        )
        token = await self._get_access_token()
        headers = {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json",
        }

        try:
            response = await self._http_client.patch(
                url,
                headers=headers,
                json={"isRead": True},
            )
            if response.status_code >= 400:
                raise GraphAPIError(
                    f"Failed to mark message as read: {response.status_code}"
                )
            logger.info(
                "Email marked as read",
                extra={
                    "message_id": message_id,
                    "correlation_id": correlation_id,
                },
            )
        except httpx.RequestError as exc:
            raise GraphAPIError(
                f"Network error marking message as read: {exc}"
            ) from exc

    async def close(self) -> None:
        """Close the HTTP client connection pool."""
        await self._http_client.aclose()
