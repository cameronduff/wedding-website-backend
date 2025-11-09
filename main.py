# main.py
from fastapi import FastAPI, APIRouter, HTTPException, Depends, status, Query
from pydantic import BaseModel, Field
import gspread
from typing import Optional
import logging
from datetime import datetime
import os

# ----------------------------
# App & Router Setup
# ----------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

app = FastAPI(title="Wedding RSVP Microservice", version="1.0.0")
router = APIRouter(prefix="/wedding")

# ----------------------------
# Google Sheets Configuration
# ----------------------------
# IMPORTANT: You’ve chosen to store the service account file in the repo root.
SERVICE_ACCOUNT_FILE_PATH = "service_account_rsvp.json"

# Default/fallback names if you want to support name-based opening.
# (We will prefer opening by spreadsheetId from the JSONP payload.)
DEFAULT_SPREADSHEET_NAME = "RSVP Responses"
WORKSHEET_NAME = "Responses"


# ----------------------------
# Pydantic model (for internal struct + response details)
# ----------------------------
class RSVPDetails(BaseModel):
    full_name: str = Field(..., description="Primary attendee full name")
    dietary_requirements: Optional[str] = None
    rehearsal_dinner: Optional[bool] = None
    ceremony: Optional[bool] = None
    brunch: Optional[bool] = None
    plus_one_name: Optional[str] = None
    plus_one_dietary_requirements: Optional[str] = None
    plus_one_rehearsal_dinner: Optional[bool] = None
    plus_one_ceremony: Optional[bool] = None
    plus_one_brunch: Optional[bool] = None
    timestamp: Optional[str] = None


# ----------------------------
# Dependency: Google Sheets client
# ----------------------------
def get_google_sheet_client() -> gspread.Client:
    try:
        gc = gspread.service_account(filename=SERVICE_ACCOUNT_FILE_PATH)
        logging.info(
            f"Authenticated with Google Sheets using file: {SERVICE_ACCOUNT_FILE_PATH}"
        )
        return gc
    except Exception as e:
        logging.error(f"Failed to authenticate with Google Sheets: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Could not authenticate with Google Sheets. "
            f"Check credentials and permissions. Error: {e}",
        )


# ----------------------------
# Helpers
# ----------------------------
def flag_to_bool(v: Optional[str]) -> Optional[bool]:
    """
    Convert JSONP flags:
      '1' -> True
      '0' -> False
      '' or None -> None
    """
    if v is None or v == "":
        return None
    return v == "1"


def bool_to_yes_no(v: Optional[bool]) -> str:
    if v is True:
        return "Yes"
    if v is False:
        return "No"
    return ""


def jsonp_wrap(callback: Optional[str], payload: dict):
    """
    If callback provided, return JS string "<callback>(<json>)",
    else return the plain dict (FastAPI will serialize as JSON).
    """
    if callback:
        from fastapi.responses import PlainTextResponse
        import json as _json

        return PlainTextResponse(
            f"{callback}({_json.dumps(payload)})",
            media_type="application/javascript",
        )
    return payload


# ----------------------------
# JSONP GET Endpoint
# ----------------------------
@router.get("/rsvp", summary="Submit RSVP via JSONP and append to Google Sheet")
async def rsvp_jsonp(
    # From RSVPForm.tsx (required by the client)
    spreadsheetId: str = Query(..., description="Google Sheets spreadsheet ID"),
    fullName: str = Query(..., description="Primary attendee full name"),
    dietaryRequirements: Optional[str] = Query("", description="Primary dietary reqs"),
    rehearsalDinner: Optional[str] = Query("", description="'1' or '0' (primary)"),
    ceremony: Optional[str] = Query("", description="'1' or '0' (primary)"),
    brunch: Optional[str] = Query("", description="'1' or '0' (primary)"),
    plus1Name: Optional[str] = Query("", description="Plus one full name"),
    plus1DietaryRequirements: Optional[str] = Query("", description="Plus one dietary"),
    plus1RehearsalDinner: Optional[str] = Query(
        "", description="'1' or '0' (plus one)"
    ),
    plus1Ceremony: Optional[str] = Query("", description="'1' or '0' (plus one)"),
    plus1Brunch: Optional[str] = Query("", description="'1' or '0' (plus one)"),
    timestamp: Optional[str] = Query(None, description="ISO timestamp from client"),
    callback: Optional[str] = Query(None, description="JSONP callback name"),
    gc: gspread.Client = Depends(get_google_sheet_client),
):
    """
    Receives RSVP data (via JSONP GET) and appends as a row to the target Google Sheet.
    Returns JSONP if `callback` is provided; otherwise returns plain JSON.
    """
    # Basic validation mirroring the frontend
    if not fullName.strip():
        return jsonp_wrap(
            callback, {"success": False, "error": "Full name is required"}
        )

    try:
        # Open by spreadsheet ID (from the client), then select worksheet
        try:
            spreadsheet = gc.open_by_key(spreadsheetId)
        except Exception:
            # Optional fallback to the default name if needed (comment out if not wanted)
            spreadsheet = gc.open(DEFAULT_SPREADSHEET_NAME)

        worksheet = spreadsheet.worksheet(WORKSHEET_NAME)
        logging.info(
            f"Opened spreadsheet '{spreadsheet.title}', worksheet '{WORKSHEET_NAME}'"
        )

        # Normalize + map fields
        details = RSVPDetails(
            full_name=fullName.strip(),
            dietary_requirements=(dietaryRequirements or "").strip() or None,
            rehearsal_dinner=flag_to_bool(rehearsalDinner),
            ceremony=flag_to_bool(ceremony),
            brunch=flag_to_bool(brunch),
            plus_one_name=(plus1Name or "").strip() or None,
            plus_one_dietary_requirements=(plus1DietaryRequirements or "").strip()
            or None,
            plus_one_rehearsal_dinner=flag_to_bool(plus1RehearsalDinner),
            plus_one_ceremony=flag_to_bool(plus1Ceremony),
            plus_one_brunch=flag_to_bool(plus1Brunch),
            timestamp=timestamp or datetime.utcnow().isoformat(),
        )

        # Prepare row in the same style as your working POST endpoint
        row = [
            details.full_name,
            details.dietary_requirements or "",
            bool_to_yes_no(details.rehearsal_dinner),
            bool_to_yes_no(details.ceremony),
            bool_to_yes_no(details.brunch),
            details.plus_one_name or "",
            details.plus_one_dietary_requirements or "",
            bool_to_yes_no(details.plus_one_rehearsal_dinner),
            bool_to_yes_no(details.plus_one_ceremony),
            bool_to_yes_no(details.plus_one_brunch),
            # If you want to store timestamp as well, uncomment:
            # details.timestamp or "",
        ]

        worksheet.append_row(row)
        logging.info(f"Successfully appended row for: {details.full_name}")

        response = {
            "success": True,
            "message": "RSVP submitted successfully!",
            "details": details.model_dump(),
        }
        return jsonp_wrap(callback, response)

    except gspread.exceptions.SpreadsheetNotFound:
        msg = "Google Sheet not found. Check spreadsheetId and sharing permissions."
        logging.error(msg)
        return jsonp_wrap(callback, {"success": False, "error": msg})

    except gspread.exceptions.WorksheetNotFound:
        msg = f"Worksheet '{WORKSHEET_NAME}' not found. Check the worksheet name."
        logging.error(msg)
        return jsonp_wrap(callback, {"success": False, "error": msg})

    except Exception as e:
        logging.error(f"Unexpected error while submitting RSVP: {e}", exc_info=True)
        return jsonp_wrap(
            callback,
            {
                "success": False,
                "error": f"An error occurred while submitting your RSVP: {e}",
            },
        )


# Mount the router on the app
app.include_router(router)

# If running directly:
#   uvicorn main:app --host 0.0.0.0 --port 8000
