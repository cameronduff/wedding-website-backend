from fastapi import FastAPI, Query, Request
from fastapi.responses import JSONResponse, PlainTextResponse
from pydantic import BaseModel
from typing import Optional
import json
from datetime import datetime

app = FastAPI()


class RSVPData(BaseModel):
    fullName: str
    dietaryRequirements: Optional[str] = ""
    rehearsalDinner: bool
    ceremony: bool
    brunch: bool
    plus1Name: Optional[str] = ""
    plus1DietaryRequirements: Optional[str] = ""
    plus1RehearsalDinner: Optional[bool] = None
    plus1Ceremony: Optional[bool] = None
    plus1Brunch: Optional[bool] = None
    timestamp: Optional[str] = None


@app.post("/rsvp")
async def receive_rsvp(request: Request):
    """
    Receives RSVP data (sent via JSON or JSONP-compatible GET/POST).
    """
    try:
        # Parse incoming JSON payload
        data = await request.json()
        callback = data.get("callback")

        # Validate full name
        if not data.get("fullName", "").strip():
            response = {"success": False, "error": "Full name is required"}
        else:
            # Create a normalized RSVP entry
            rsvp = RSVPData(**data)
            rsvp.timestamp = rsvp.timestamp or datetime.utcnow().isoformat()

            # TODO: Add persistence (e.g., write to Google Sheets or DB)
            print("📥 Received RSVP:", rsvp.dict())

            response = {"success": True, "message": "RSVP received successfully"}

        # Return JSONP if callback provided
        if callback:
            jsonp_response = f"{callback}({json.dumps(response)})"
            return PlainTextResponse(
                jsonp_response, media_type="application/javascript"
            )

        # Otherwise return normal JSON
        return JSONResponse(response)

    except Exception as e:
        print("❌ Error processing RSVP:", e)
        return JSONResponse(
            {"success": False, "error": "Invalid payload or server error"},
            status_code=400,
        )
