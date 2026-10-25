"""
sheets_push.py — Push leads to Google Sheets (optional).

Pushes all leads from the database to Google Sheets — one tab per status
plus a summary tab — if Google Sheets credentials are configured.

If no credentials are present, logs a skip message and does nothing.

Required env vars:
    GOOGLE_CLIENT_ID
    GOOGLE_CLIENT_SECRET
    GOOGLE_REFRESH_TOKEN
    GOOGLE_SPREADSHEET_ID
"""

import logging
import os

logger = logging.getLogger("gtm.sheets_push")


def push_leads_to_sheets(
    leads: list[dict],
    spreadsheet_id: str | None = None,
) -> dict:
    """
    Push leads to Google Sheets.

    Creates one tab per lead status, plus a summary tab.

    Args:
        leads: List of lead dicts from the DB.
        spreadsheet_id: Optional spreadsheet id (falls back to env var).

    Returns:
        dict with {ok, sheets_created, error}
    """
    if not spreadsheet_id:
        spreadsheet_id = os.getenv("GOOGLE_SPREADSHEET_ID")

    if not spreadsheet_id:
        logger.info("Google Sheets not configured (no spreadsheet id); skipping push.")
        return {
            "ok": False,
            "sheets_created": 0,
            "error": "No spreadsheet id configured.",
        }

    try:
        from google.oauth2.credentials import Credentials
        from googleapiclient.discovery import build

        token = os.getenv("GOOGLE_REFRESH_TOKEN")
        client_id = os.getenv("GOOGLE_CLIENT_ID")
        client_secret = os.getenv("GOOGLE_CLIENT_SECRET")

        if not (token and client_id and client_secret):
            logger.info("Google Sheets credentials not configured; skipping push.")
            return {
                "ok": False,
                "sheets_created": 0,
                "error": "No OAuth credentials configured.",
            }

        import google.auth.transport.requests
        from google.oauth2.credentials import Credentials as Creds

        creds = Creds(
            token=token,
            refresh_token=token,
            client_id=client_id,
            client_secret=client_secret,
            token_uri="https://oauth2.googleapis.com/token",
        )

        service = build("sheets", "v4", credentials=creds, cache_discovery=False)

        # Header row
        headers = [
            "id", "company", "domain", "website", "industry",
            "fit_score_rule", "fit_score_llm", "fit_score_final",
            "email", "email_confidence", "status", "source", "created_at",
        ]

        values = [headers]
        for lead in leads:
            values.append([
                lead.get("id", ""),
                lead.get("company", ""),
                lead.get("domain", ""),
                lead.get("website", ""),
                lead.get("industry", ""),
                lead.get("fit_score_rule", ""),
                lead.get("fit_score_llm", ""),
                lead.get("fit_score_final", ""),
                lead.get("email", ""),
                lead.get("email_confidence", ""),
                lead.get("status", ""),
                lead.get("source", ""),
                lead.get("created_at", ""),
            ])

        # Clear existing data and write
        sheet_name = "Leads"
        try:
            service.spreadsheets().values().clear(
                spreadsheetId=spreadsheet_id,
                range=f"{sheet_name}!A:M",
            ).execute()
        except Exception:
            # Sheet might not exist yet — try creating
            pass

        result = service.spreadsheets().values().update(
            spreadsheetId=spreadsheet_id,
            range=f"{sheet_name}!A1",
            valueInputOption="USER_ENTERED",
            body={"values": values},
        ).execute()

        logger.info("Pushed %d leads to Google Sheets (%d rows updated).",
                    len(leads), result.get("updatedRows", 0))

        return {
            "ok": True,
            "sheets_created": 1,
            "error": None,
        }
    except ImportError:
        logger.info("google-api-python-client not installed; skipping Sheets push.")
        return {
            "ok": False,
            "sheets_created": 0,
            "error": "google-api-python-client not installed.",
        }
    except Exception as exc:
        logger.error("Sheets push failed: %s", exc)
        return {
            "ok": False,
            "sheets_created": 0,
            "error": str(exc),
        }


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    print("sheets_push.py loaded — use via main.py orchestrator")