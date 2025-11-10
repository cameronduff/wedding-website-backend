import os
import logging
from datetime import datetime
from typing import Optional

import gspread
from fastapi import FastAPI, HTTPException, Security, Depends, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.security import APIKeyHeader
from pydantic import BaseModel, Field

# NEW: for ADC fallback
from google.auth import default as google_auth_default
from google.auth.exceptions import DefaultCredentialsError

# --------------------------------------------------
# Logging
# --------------------------------------------------
logging.basicConfig(
    level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s"
)

# --------------------------------------------------
# App Setup
# --------------------------------------------------
app = FastAPI(
    title="Wedding RSVP API",
    description="FastAPI microservice for handling RSVPs via Google Sheets",
    version="1.0.0",
)

origins = [
    "http://localhost:3000",  # Local React dev
    "https://camandelisha.com",  # Production
]

# Allow all CORS origins (adjust for production)
app.add_middleware(
    CORSMiddleware,
    allow_origins=origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["Content-Type", "X-API-Key"],
)

# --------------------------------------------------
# Security
# --------------------------------------------------
API_KEY_NAME = "X-API-Key"
api_key_header = APIKeyHeader(name=API_KEY_NAME, auto_error=True)
VALID_API_KEY = os.getenv("VALID_API_KEY")

if not VALID_API_KEY:
    logging.warning("⚠️ No VALID_API_KEY set. The API is currently unprotected!")


async def verify_api_key(api_key: str = Security(api_key_header)):
    if VALID_API_KEY is None:
        logging.debug("API key check disabled.")
        return
    if api_key != VALID_API_KEY:
        logging.warning(f"Invalid API key attempted: {api_key[:6]}...")
        raise HTTPException(status_code=403, detail="Invalid API key")
    logging.debug("✅ Valid API key")
    return api_key


# --------------------------------------------------
# Google Sheets Config
# --------------------------------------------------
# Defaults (can be overridden via env)
DEFAULT_SERVICE_ACCOUNT_FILE = "service_account_rsvp.json"
SPREADSHEET_NAME = os.getenv("SPREADSHEET_NAME", "RSVP Responses")
WORKSHEET_NAME = os.getenv("WORKSHEET_NAME", "Responses")

# Helpful scopes (Sheets + Drive to open by name)
GOOGLE_SCOPES = [
    "https://www.googleapis.com/auth/spreadsheets",
    "https://www.googleapis.com/auth/drive",
]


def _in_cloud_run() -> bool:
    # Cloud Run sets K_SERVICE / K_REVISION / K_CONFIGURATION
    return bool(
        os.getenv("K_SERVICE")
        or os.getenv("K_REVISION")
        or os.getenv("K_CONFIGURATION")
    )


def _resolve_credentials_path() -> Optional[str]:
    """
    Resolve where the credentials file should be:
    - In Cloud Run (prod): GOOGLE_APPLICATION_CREDENTIALS (mounted secret path)
    - Else: local file 'service_account_rsvp.json' (dev)
    """
    # If user provided explicit path (e.g., mounted secret)
    env_path = os.getenv("GOOGLE_APPLICATION_CREDENTIALS") or os.getenv(
        "SERVICE_ACCOUNT_FILE"
    )
    if env_path and os.path.isfile(env_path):
        logging.info(f"Using credentials file from env path: {env_path}")
        return env_path

    # Dev default
    if os.path.isfile(DEFAULT_SERVICE_ACCOUNT_FILE):
        logging.info(f"Using local credentials file: {DEFAULT_SERVICE_ACCOUNT_FILE}")
        return DEFAULT_SERVICE_ACCOUNT_FILE

    # Nothing found
    return None


def get_google_client() -> gspread.Client:
    """
    Obtain an authenticated gspread client with robust fallbacks:
    1) If a credentials file exists (mounted secret or local), use it.
    2) Otherwise, try Application Default Credentials (Workload Identity).
    """
    creds_path = _resolve_credentials_path()

    # 1) Service account file path (mounted secret in prod or local in dev)
    if creds_path:
        try:
            client = gspread.service_account(filename=creds_path, scopes=GOOGLE_SCOPES)
            logging.info("Authenticated with Google Sheets via service account file.")
            return client
        except Exception as e:
            logging.error(f"Service account file auth failed: {e}")

    # 2) ADC fallback (works if Cloud Run service account has access to the Sheet)
    try:
        creds, _ = google_auth_default(scopes=GOOGLE_SCOPES)
        client = gspread.authorize(creds)
        logging.info(
            "Authenticated with Google Sheets via Application Default Credentials."
        )
        return client
    except DefaultCredentialsError as e:
        logging.error(f"ADC auth failed (no default credentials): {e}")
    except Exception as e:
        logging.error(f"ADC auth unexpected error: {e}")

    # If we’re here, both methods failed
    hint = (
        "No credentials file found and ADC failed. In Cloud Run, mount your Secret at "
        "e.g. /secrets/rsvp/service_account_rsvp.json and set "
        "GOOGLE_APPLICATION_CREDENTIALS=/secrets/rsvp/service_account_rsvp.json. "
        "Locally, keep service_account_rsvp.json in the project root."
    )
    raise HTTPException(
        status_code=500,
        detail=f"Google Sheets authentication failed. {hint}",
    )


# --------------------------------------------------
# Data Model
# --------------------------------------------------
class RSVPData(BaseModel):
    full_name: str = Field(..., description="Primary guest full name")
    dietary_requirements: Optional[str] = Field(
        None, description="Primary dietary needs"
    )
    rehearsal_dinner: Optional[bool] = Field(
        None, description="Attending rehearsal dinner"
    )
    ceremony: Optional[bool] = Field(None, description="Attending ceremony")
    brunch: Optional[bool] = Field(None, description="Attending brunch")
    plus_one_name: Optional[str] = Field(None, description="Plus one full name")
    plus_one_dietary_requirements: Optional[str] = Field(
        None, description="Plus one dietary needs"
    )
    plus_one_rehearsal_dinner: Optional[bool] = Field(
        None, description="Plus one attending rehearsal dinner"
    )
    plus_one_ceremony: Optional[bool] = Field(
        None, description="Plus one attending ceremony"
    )
    plus_one_brunch: Optional[bool] = Field(
        None, description="Plus one attending brunch"
    )


# --------------------------------------------------
# Endpoint
# --------------------------------------------------
@app.post("/rsvp", summary="Submit RSVP", dependencies=[Depends(verify_api_key)])
async def submit_rsvp(data: RSVPData):
    """
    Accepts RSVP data and appends it to a Google Sheet.
    """
    try:
        client = get_google_client()
        sheet = client.open(SPREADSHEET_NAME)
        worksheet = sheet.worksheet(WORKSHEET_NAME)
        logging.info(f"Opened worksheet '{WORKSHEET_NAME}' in '{SPREADSHEET_NAME}'.")

        # Convert booleans to Yes/No/blank
        def yes_no(val: Optional[bool]) -> str:
            if val is True:
                return "Yes"
            elif val is False:
                return "No"
            return ""

        row = [
            data.full_name,
            data.dietary_requirements or "",
            yes_no(data.rehearsal_dinner),
            yes_no(data.ceremony),
            yes_no(data.brunch),
            data.plus_one_name or "",
            data.plus_one_dietary_requirements or "",
            yes_no(data.plus_one_rehearsal_dinner),
            yes_no(data.plus_one_ceremony),
            yes_no(data.plus_one_brunch),
            datetime.utcnow().isoformat(),
        ]

        worksheet.append_row(row)
        logging.info(f"RSVP recorded for {data.full_name}")

        return {
            "success": True,
            "message": "RSVP submitted successfully!",
            "details": data.model_dump(),
        }

    except gspread.exceptions.SpreadsheetNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Spreadsheet '{SPREADSHEET_NAME}' not found. Check sharing and name.",
        )
    except gspread.exceptions.WorksheetNotFound:
        raise HTTPException(
            status_code=404,
            detail=f"Worksheet '{WORKSHEET_NAME}' not found in spreadsheet.",
        )
    except Exception as e:
        logging.error(f"Unexpected error: {e}", exc_info=True)
        raise HTTPException(status_code=500, detail=str(e))


# --------------------------------------------------
# Run with: uvicorn main:app --reload
# --------------------------------------------------
