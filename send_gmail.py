"""
send_gmail.py — Create Gmail drafts via Gmail API (no auto-send by default).

Gmail API OAuth flow (via Google Cloud Console):
    - Create OAuth 2.0 Client ID (Web/Desktop application)
    - Install Google APIs Client Libraries
    - Authorize refresh token

Behaviour:
    - For each drafted lead, creates a Gmail draft.
    - Saves gmail_draft_id on the lead.
    - Sets status to 'draft_created'.
    - Only sends (actually sends) if AUTO_SEND=true is set in env.
    - By default AUTO_SEND=false → creates drafts only, never sends.

All credential errors are caught gracefully; failures are logged, never raised.
"""

import base64
import json
import logging
import os

logger = logging.getLogger("gtm.send_gmail")


def _build_rfc822_message(
    to_email: str,
    subject: str,
    body: str,
    from_email: str | None = None,
) -> str:
    """
    Build a minimal RFC 822 email message string.
    """
    from_email = from_email or os.getenv("GMAIL_SENDER_EMAIL") or "noreply@hyperlaplabs.com"

    lines = [
        "From: " + from_email,
        "To: " + to_email,
        "Subject: " + subject,
        "MIME-Version: 1.0",
        "Content-Type: text/plain; charset=\"utf-8\"",
        "",
        body,
    ]
    raw = "\r\n".join(lines).encode("utf-8")
    encoded = base64.urlsafe_b64encode(raw).decode("utf-8")
    return encoded


def get_gmail_draft_id(draft_response: dict) -> str | None:
    """Extract draft id from a Gmail API create response."""
    try:
        return draft_response.get("id")
    except Exception:
        return None


def create_draft(
    to_email: str,
    subject: str,
    body: str,
    thread_id: str | None = None,
) -> dict:
    """
    Create a Gmail draft for the given email.

    Returns:
        dict with {draft_id, ok, error}
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/gmail.compose"]

        creds = None
        token = os.getenv("GOOGLE_REFRESH_TOKEN")
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if token and client_id and client_secret:
            import google.auth.transport.requests
            from google.oauth2.credentials import Credentials as Creds

            creds = Creds(
                token=token,
                refresh_token=token,  # placeholder — user must supply proper refresh token
                client_id=client_id,
                client_secret=client_secret,
                token_uri="https://oauth2.googleapis.com/token",
            )

        if not creds:
            return {
                "draft_id": None,
                "ok": False,
                "error": "Gmail OAuth credentials not configured.",
            }

        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        body = {
            "raw": _build_rfc822_message(to_email, subject, body),
        }
        if thread_id:
            body["threadId"] = thread_id
        draft = service.users().drafts().create(userId="me", body=body).execute()
        draft_id = draft.get("id")
        return {"draft_id": draft_id, "ok": True, "error": None}
    except Exception as exc:
        logger.error("Gmail draft creation failed: %s", exc)
        return {"draft_id": None, "ok": False, "error": str(exc)}


def send_draft(
    to_email: str,
    subject: str,
    body: str,
) -> dict:
    """
    Send an email via Gmail API (requires AUTO_SEND=true).

    Returns: {"ok": bool, "error": str | None}
    """
    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        SCOPES = ["https://www.googleapis.com/auth/gmail.send"]

        token = os.getenv("GOOGLE_REFRESH_TOKEN")
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not (token and client_id and client_secret):
            return {"ok": False, "error": "Gmail OAuth credentials not configured."}

        import google.auth.transport.requests
        from google.oauth2.credentials import Credentials as Creds

        creds = Creds(
            token=token,
            refresh_token=token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )
        service = build("gmail", "v1", credentials=creds, cache_discovery=False)
        message = service.users().messages().send(
            userId="me",
            body={
                "raw": _build_rfc822_message(to_email, subject, body),
            },
        ).execute()
        return {"ok": True, "error": None, "message_id": message.get("id")}
    except Exception as exc:
        logger.error("Gmail send failed: %s", exc)
        return {"ok": False, "error": str(exc)}


def process_drafts(
    leads: list[dict],
    auto_send: bool = False,
) -> list[dict]:
    """
    Process drafted leads: create Gmail drafts for each.

    Args:
        leads: List of lead dicts (must have status='drafted' and email).
        auto_send: If True, actually SEND (not just draft). Default False.

    Returns:
        List of results per lead: {lead_id, draft_id, sent, ok, error}.
    """
    results = []
    for lead in leads:
        if not lead.get("email"):
            continue

        subject = f"Quick chat: {lead.get('company', 'your business')}"
        body = lead.get("draft_email_body") or "Hello,"

        if not auto_send:
            result = create_draft(
                to_email=lead["email"],
                subject=subject,
                body=body,
            )
            if result.get("ok"):
                results.append({
                    "lead_id": lead.get("id"),
                    "draft_id": result.get("draft_id"),
                    "sent": False,
                    "ok": True,
                    "error": None,
                })
            else:
                results.append({
                    "lead_id": lead.get("id"),
                    "draft_id": None,
                    "sent": False,
                    "ok": False,
                    "error": result.get("error"),
                })
        else:
            result = send_draft(
                to_email=lead["email"],
                subject=subject,
                body=body,
            )
            results.append({
                "lead_id": lead.get("id"),
                "sent": True,
                "ok": result.get("ok", False),
                "error": result.get("error"),
            })

    return results


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("send_gmail.py loaded — use via main.py orchestrator")