# FastAPI — creates the web application.
# HTTPException — returns an HTTP error response when something fails.
# Query — configures and validates query parameters in a URL.
# FileResponse — serves your HTML file.
# StaticFiles — serves CSS, JavaScript, and other static assets.
# Error — catches general MySQL Connector errors.
# IntegrityError — catches database integrity violations, such as a foreign-key failure.
# save_event — imports the database function we just examined.
# Event — imports your Pydantic model for event validation
from pathlib import Path
import os
import secrets
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

from fastapi import FastAPI, HTTPException, Query, Depends, Request
from fastapi.responses import FileResponse, RedirectResponse
from starlette.middleware.sessions import SessionMiddleware
from fastapi.staticfiles import StaticFiles
from mysql.connector import Error, IntegrityError
from datetime import date, datetime
from decimal import Decimal
from urllib.parse import urlencode
from contact_ranking import rank_contact, rank_contacts

from database import (
    get_event_by_id,
    get_event_candidates,
    get_event_progress,
    get_events,
    get_sponsor_directory,
    get_sponsor_global_history,
    get_sponsor_history,
    save_company_candidates,
    save_event,
    update_event,
)
from sponsor_planner import generate_sponsor_plan
from sponsor_research import research_sponsor_plan
from company_extractor import extract_companies
from models import Event
from datetime import date, datetime
from decimal import Decimal
from typing import Literal

from pydantic import BaseModel

from contact_finder import (
    ContactDiscoveryError,
    find_company_contacts,
)
from email_generator import (
    EmailGenerationError,
    generate_sponsorship_email,
)
from email_sender import (
    EmailSendError,
    send_email,
    test_smtp_connection,
)

from gmail_reply_tracker import router as gmail_reply_router

from user_email_settings import (
    EmailSettingsError,
    get_user_email_settings,
    save_user_email_settings,
)

from outreach_database import (
    finish_email_send,
    get_all_outreach_history,
    get_outreach_history,
    get_selected_company,
    get_sponsor_contacts,
    save_email_draft,
    save_sponsor_contacts,
    claim_email_for_sending,
    set_sponsor_selection,
    update_email_draft,
    delete_event_sponsor,
    delete_outreach_record as delete_outreach_record_db,
)



from ai_usage_tracker import get_ai_usage_summary
from auth import router as auth_router, authenticated_user_id, page_user

FRONTEND_DIR = BASE_DIR / "frontend"

class SponsorSelectionRequest(BaseModel):
    status: Literal["SELECTED", "REJECTED"]


class SendConfirmation(BaseModel):
    confirm_send: bool
    confirm_recipient: bool = False


class EmailDraftUpdate(BaseModel):
    subject: str
    body: str

class EmailSettingsRequest(BaseModel):
    smtp_host: str
    smtp_port: int
    smtp_security: Literal["STARTTLS", "SSL"]
    smtp_username: str
    smtp_password: str | None = None
    from_email: str
    from_name: str = "SponsyBot User"

# FastAPI(...) creates the application object. 
# Uvicorn uses this object to serve HTTP requests
_is_production = os.getenv("ENVIRONMENT", "development").strip().lower() == "production"
app = FastAPI(
    title="SponsyBot API",
    docs_url=None if _is_production else "/docs",
    redoc_url=None if _is_production else "/redoc",
    openapi_url=None if _is_production else "/openapi.json",
)

# Google OAuth uses Starlette's signed session for its state/nonce handshake.
# Reject the documented sample value and weak secrets in production.
_secret_key = os.getenv("SECRET_KEY", "").strip()
_is_placeholder_secret = not _secret_key or _secret_key.lower().startswith("replace-with")
_is_weak_secret = len(_secret_key) < 32
if _is_production and (_is_placeholder_secret or _is_weak_secret):
    raise RuntimeError("Production requires SECRET_KEY to be a unique random value of at least 32 characters.")
if _is_placeholder_secret or _is_weak_secret:
    _secret_key = secrets.token_urlsafe(48)
app.add_middleware(
    SessionMiddleware,
    secret_key=_secret_key,
    same_site="lax",
    https_only=_is_production,
)
app.include_router(auth_router)

app.include_router(gmail_reply_router)
# everything happens wrt browser
# @app.get("/") -This is a route decorator. It tells FastAPI:
# -When the browser sends an HTTP GET request to /, execute the home() function.

# def home(): This defines the Python function that handles the request. 
# -FastAPI calls this function when the route matches.
# return FileResponse(FRONTEND_DIR / "index.html")
# -This tells FastAPI to send the contents of your index.html file to the browser.
def _workspace_redirect(request: Request):
    if not page_user(request):
        next_path = request.url.path
        if request.url.query:
            next_path += "?" + request.url.query
        return RedirectResponse(
            url="/login?" + urlencode({"next": next_path}),
            status_code=303,
        )
    return None


@app.get("/login")
def login_page(request: Request):
    if page_user(request):
        return RedirectResponse(url="/", status_code=303)
    return FileResponse(FRONTEND_DIR / "login.html")


@app.get("/")
def home(request: Request):
    redirect = _workspace_redirect(request)
    if redirect:
        return redirect
    return FileResponse(FRONTEND_DIR / "index.html")

# event: Event tells FastAPI to validate the incoming JSON 
# -using your Pydantic Event model.
# user_id: int says the query parameter must be an integer.
# Query(..., gt=0) makes the parameter mandatory (...) 
# -and requires it to be greater than zero.
@app.post("/events")
def create_event(
    event: Event,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        event_id = save_event(event, user_id)

        return {
            "message": "Event saved successfully",
            "event_id": event_id,
# event.model_dump(mode="json") converts the Pydantic model into a 
# -dictionary using JSON-compatible representations, including dates.
            "event": event.model_dump(mode="json"),
        }

# An IntegrityError can occur if the referenced user doesn't exist or 
# -a database constraint is violated. The API returns HTTP 400 Bad Request.
    except IntegrityError as error:
        raise HTTPException(
            status_code=400,
            detail=(
                "The user_id must refer to an existing user, "
                "and the submitted event must satisfy the "
                "database constraints."
            ),
        ) from error

#    Other MySQL errors become HTTP 500 Internal Server Error.
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Database operation failed.",
        ) from error


@app.get("/events")
def events_page(request: Request):
    redirect = _workspace_redirect(request)
    if redirect:
        return redirect
    return FileResponse(FRONTEND_DIR / "events.html")


@app.get("/sponsors")
def sponsors_page(request: Request):
    redirect = _workspace_redirect(request)
    if redirect:
        return redirect
    return FileResponse(FRONTEND_DIR / "sponsors.html")


@app.get("/pipeline")
def pipeline_page(request: Request):
    redirect = _workspace_redirect(request)
    if redirect:
        return redirect
    return FileResponse(FRONTEND_DIR / "pipeline.html")


@app.get("/email-studio")
def email_studio_page(request: Request):
    redirect = _workspace_redirect(request)
    if redirect:
        return redirect
    return FileResponse(FRONTEND_DIR / "email-studio.html")

@app.get("/email-settings")
def email_settings_page(request: Request):
    redirect = _workspace_redirect(request)
    if redirect:
        return redirect

    return FileResponse(
        FRONTEND_DIR / "email-settings.html"
    )

@app.get("/outreach")
def outreach_page(request: Request):
    redirect = _workspace_redirect(request)
    if redirect:
        return redirect
    return FileResponse(FRONTEND_DIR / "outreach.html")

@app.delete("/api/outreach/{email_id}")
def delete_outreach_record_api(
    email_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        deleted = delete_outreach_record_db(
            email_id=email_id,
            user_id=user_id,
        )

        if not deleted:
            raise HTTPException(
                status_code=404,
                detail="Outreach record not found.",
            )

        return {
            "message": "Outreach record permanently deleted.",
            "email_id": email_id,
        }

    except HTTPException:
        raise

    except ValueError as error:
        raise HTTPException(
            status_code=409,
            detail=str(error),
        ) from error

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not delete the outreach record.",
        ) from error

@app.get("/api/events")
def list_events(user_id: int = Depends(authenticated_user_id)):
    try:
        events = get_events(user_id)
        return {"events": events}

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve events from the database."
        ) from error



@app.get("/api/events/{event_id}")
def get_event_details(
    event_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        event = get_event_by_id(event_id, user_id)

        if event is None:
            raise HTTPException(
                status_code=404,
                detail="Event not found for this user.",
            )

        # Convert the date to a JSON-compatible string.
        event["event_date"] = event["event_date"].isoformat()

        return {"event": event}

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve event details.",
        ) from error



@app.put("/api/events/{event_id}")
def edit_event(
    event_id: int,
    event: Event,
    user_id: int = Depends(authenticated_user_id),
):
    """Update an existing event belonging to the requested user."""

    try:
        updated = update_event(event_id, user_id, event)

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Event not found for this user.",
            )

        return {
            "message": "Event updated successfully.",
            "event_id": event_id,
            "event": event.model_dump(mode="json"),
        }

    except HTTPException:
        raise

    except IntegrityError as error:
        raise HTTPException(
            status_code=400,
            detail="The event violates a database constraint.",
        ) from error

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not update the event.",
        ) from error



@app.post("/api/events/{event_id}/discover")
def discover_event_sponsors(
    event_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    """Generate, research, extract, and save sponsor candidates."""

    # 1. Confirm that this event belongs to the requested user.
    try:
        event = get_event_by_id(event_id, user_id)
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve the event.",
        ) from error

    if event is None:
        raise HTTPException(
            status_code=404,
            detail="Event not found for this user.",
        )

    # 2. Run the external discovery pipeline.
    try:
        plan = generate_sponsor_plan(event)

        research = research_sponsor_plan(
            plan,
            max_queries=6,
            max_results_per_query=5,
        )

        extraction = extract_companies(research)

    except Exception as error:
        import traceback

        print(f"\nSponsor discovery failed for event {event_id}:")
        traceback.print_exc()

        raise HTTPException(
            status_code=502,
            detail=(
                "Sponsor discovery failed while contacting or "
                "processing an external research service. "
                "Check the server terminal for details."
            ),
        ) from error

    candidates = extraction["candidates"]

    # 3. Save the candidates and their supporting evidence.
    try:
        save_result = save_company_candidates(event_id, candidates)

    except Error as error:
        print(f"Database save failed for event {event_id}: {error}")

        raise HTTPException(
            status_code=500,
            detail="Research completed, but candidates could not be saved.",
        ) from error

    except ValueError as error:
        raise HTTPException(
            status_code=400,
            detail=str(error),
        ) from error

        # TEMPORARY DEBUG OUTPUT: clear only after successful saving.
    if os.name == "nt":
        os.system("cls")
    else:
        os.system("clear")

    print("\nSponsyBot - Sponsor discovery completed", flush=True)
    print(f"Event ID: {event_id}", flush=True)
    print(
        f"Candidates processed: {extraction['candidate_count']}",
        flush=True,
    )
    print(
        f"Candidates saved: {save_result['saved_count']}",
        flush=True,
    )
    print(
        f"Existing or duplicate relationships skipped: "
        f"{save_result['skipped_count']}\n",
        flush=True,
    )

    # 4. Return a summary, not the full research payload.
    return {
        "message": "Sponsor discovery completed.",
        "event_id": event_id,
        "event_name": event["event_name"],
        "searches_run": research["searches_run"],
        "unique_source_count": research["unique_source_count"],
        "candidate_count": extraction["candidate_count"],
        "rejected_candidate_count": extraction[
            "rejected_candidate_count"
        ],
        "saved_count": save_result["saved_count"],
        "skipped_count": save_result["skipped_count"],
        "candidates_url": (
            f"/api/events/{event_id}/candidates"
        ),
    }


@app.get("/api/events/{event_id}/candidates")
def list_event_candidates(
    event_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    """Return saved candidates and their supporting evidence."""

    try:
        event = get_event_by_id(event_id, user_id)

        if event is None:
            raise HTTPException(
                status_code=404,
                detail="Event not found for this user.",
            )

        candidates = get_event_candidates(event_id, user_id)

        # Convert Decimal values into JSON-compatible numbers.
        for candidate in candidates:
            if candidate["ai_score"] is not None:
                candidate["ai_score"] = float(candidate["ai_score"])

        return {
            "event_id": event_id,
            "event_name": event["event_name"],
            "candidate_count": len(candidates),
            "candidates": candidates,
        }

    except HTTPException:
        raise

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve sponsor candidates.",
        ) from error


# ---------- Sponsor selection ----------

@app.put("/api/events/{event_id}/sponsors/{company_id}/selection")
def update_sponsor_selection(
    event_id: int,
    company_id: int,
    request: SponsorSelectionRequest,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        updated = set_sponsor_selection(
            event_id,
            company_id,
            user_id,
            request.status,
        )

        if not updated:
            raise HTTPException(
                status_code=404,
                detail="Sponsor not found for this user's event.",
            )

        return {
            "message": "Sponsor selection updated.",
            "event_id": event_id,
            "company_id": company_id,
            "status": request.status,
        }

    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not update sponsor selection.",
        ) from error


@app.delete("/api/events/{event_id}/sponsors/{company_id}")
def delete_sponsor_from_event(
    event_id: int,
    company_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    """Remove a sponsor from this event, without deleting the global company."""
    try:
        deleted = delete_event_sponsor(event_id, company_id, user_id)
        if not deleted:
            raise HTTPException(status_code=404, detail="Sponsor not found for this event.")
        return {"message": "Sponsor removed from this event.", "event_id": event_id, "company_id": company_id}
    except ValueError as error:
        raise HTTPException(status_code=409, detail=str(error)) from error
    except Error as error:
        raise HTTPException(status_code=500, detail="Could not remove this sponsor from the event.") from error


# ---------- Discover contacts ----------

@app.post(
    "/api/events/{event_id}/sponsors/{company_id}/contacts/discover"
)
def discover_sponsor_contacts(
    event_id: int,
    company_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        company = get_selected_company(event_id, company_id, user_id)

        if company is None:
            raise HTTPException(
                status_code=404,
                detail=(
                    "Selected sponsor not found. Select the sponsor "
                    "before discovering its contacts."
                ),
            )

        result = find_company_contacts(
            company_name=company["company_name"],
            website=company.get("company_website"),
        )

        save_sponsor_contacts(
            event_id=event_id,
            company_id=company_id,
            contacts=result["contacts"],
            domain=result["domain"],
            website=result["website"],
        )

        contacts = get_sponsor_contacts(
            event_id, company_id, user_id
        )

        for contact in contacts:
            for field, value in contact.items():
                if isinstance(value, (datetime, date)):
                    contact[field] = value.isoformat()
                elif isinstance(value, Decimal):
                    contact[field] = float(value)

        return {
            "message": (
                "Contact discovery completed."
                if contacts
                else "No email contacts were found by Hunter."
            ),
            "event_id": event_id,
            "company_id": company_id,
            "company_name": company["company_name"],
            "website": result["website"],
            "domain": result["domain"],
            "contact_count": len(contacts),
            "contacts": contacts,
        }

    except HTTPException:
        raise
    except ContactDiscoveryError as error:
        raise HTTPException(status_code=502, detail=str(error)) from error
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not save or retrieve discovered contacts.",
        ) from error


@app.get(
    "/api/events/{event_id}/sponsors/{company_id}/contacts"
)
def list_sponsor_contacts(
    event_id: int,
    company_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        company = get_selected_company(event_id, company_id, user_id)

        if company is None:
            raise HTTPException(
                status_code=404,
                detail="Selected sponsor not found for this event.",
            )

        contacts = get_sponsor_contacts(
            event_id, company_id, user_id
        )

        contacts = rank_contacts(contacts)

        for contact in contacts:
            for field, value in contact.items():
                if isinstance(value, (datetime, date)):
                    contact[field] = value.isoformat()
                elif isinstance(value, Decimal):
                    contact[field] = float(value)

        return {
            "event_id": event_id,
            "company_id": company_id,
            "contacts": contacts,
        }

    except HTTPException:
        raise
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve sponsor contacts.",
        ) from error


# ---------- Generate an email draft ----------

@app.post(
    "/api/events/{event_id}/sponsors/{company_id}/contacts/"
    "{contact_id}/draft"
)
def create_sponsor_email_draft(
    event_id: int,
    company_id: int,
    contact_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        company = get_selected_company(event_id, company_id, user_id)

        if company is None:
            raise HTTPException(
                status_code=404,
                detail="Select this sponsor before drafting an email.",
            )

        contacts = get_sponsor_contacts(
            event_id, company_id, user_id
        )

        contacts = rank_contacts(contacts)

        contact = next(
            (
                item for item in contacts
                if item["contact_id"] == contact_id
            ),
            None,
        )

        if contact is None:
            raise HTTPException(
                status_code=404,
                detail="Contact not found for this selected sponsor.",
            )

        # Allow draft generation for any discovered contact with an email address.
        # Recommendation status should not prevent creating a draft.
        email_address = str(
            contact.get("email_address") or ""
        ).strip()

        if not email_address:
            raise HTTPException(
                status_code=422,
                detail=(
                    "Cannot generate an email draft because "
                    "this contact has no email address."
                ),
            )

        contact["email_address"] = email_address

        # Keep the ranking metadata for display, but do not block draft generation.
        contact_match = rank_contact(contact)

        event_data = {
            "event_name": company["event_name"],
            "college": company["college"],
            "city": company["event_city"],
            "state": company["event_state"],
            "event_date": company["event_date"],
            "expected_participants": company["expected_participants"],
            "event_type": company["event_type"],
            "description": company["description"],
            "sponsorship_requirements": company[
                "sponsorship_requirements"
            ],
            "audience_types": company["audience_types"],
            "interests": company["interests"],
            "event_format": company["event_format"],
        }

        draft = generate_sponsorship_email(
            event_data,
            company,
            contact,
        )

        email_id = save_email_draft(
            event_id=event_id,
            company_id=company_id,
            contact_id=contact_id,
            user_id=user_id,
            subject=draft["subject"],
            body=draft["body"],
        )

        if email_id is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Could not save draft. Verify the event, sponsor "
                    "selection, and contact."
                ),
            )

        return {
            "message": "Email draft generated and saved.",
            "email_id": email_id,
            "event_id": event_id,
            "company_id": company_id,
            "recipient_email": contact["email_address"],
            "recipient_name": contact.get("full_name"),
            "sender_email": os.getenv("SMTP_FROM_EMAIL", "").strip() or os.getenv("SMTP_USERNAME", "").strip(),
            "subject": draft["subject"],
            "body": draft["body"],
            "status": "DRAFT",

            # Contact-ranking information
            "contact_category": contact_match["contact_category"],
            "priority_rank": contact_match["priority_rank"],
            "selection_reason": contact_match["selection_reason"],
            "verification_warning": contact_match["verification_warning"],

            "send_url": (
                f"/api/events/{event_id}/outreach/{email_id}/send"
                f""
            ),
        }

    except HTTPException:
        raise
    except EmailGenerationError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not save the generated email draft.",
        ) from error



# ---------- Edit a draft before sending ----------

@app.put("/api/events/{event_id}/outreach/{email_id}")
def edit_sponsor_email_draft(
    event_id: int,
    email_id: int,
    request: EmailDraftUpdate,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        updated = update_email_draft(
            email_id=email_id,
            event_id=event_id,
            user_id=user_id,
            subject=request.subject,
            body=request.body,
        )

        if not updated:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Draft not found, no changes were made, or the email "
                    "is no longer editable. Only selected sponsors' "
                    "unsent drafts can be edited."
                ),
            )

        return {
            "message": "Email draft updated.",
            "email_id": email_id,
            "status": "DRAFT",
        }

    except HTTPException:
        raise
    except ValueError as error:
        raise HTTPException(status_code=422, detail=str(error)) from error
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not update email draft.",
        ) from error


# ---------- Send an approved email ----------

@app.post("/api/events/{event_id}/outreach/{email_id}/send")
def send_sponsor_email(
    event_id: int,
    email_id: int,
    request: SendConfirmation,
    user_id: int = Depends(authenticated_user_id),
):
    if not request.confirm_recipient:
        raise HTTPException(
            status_code=400,
            detail="Confirm the recipient address before sending the email.",
        )
    if not request.confirm_send:
        raise HTTPException(
            status_code=400,
            detail="Confirm email delivery only after reviewing the draft.",
        )

    try:
        smtp_config = get_user_email_settings(
            user_id,
            decrypt_password=True,
        )

        if not smtp_config:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Connect your email account in Email Settings "
                    "before sending."
                ),
            )

    except HTTPException:
        raise

    except EmailSettingsError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not load your saved email settings.",
        ) from error

    try:
        draft = claim_email_for_sending(
            email_id=email_id,
            event_id=event_id,
            user_id=user_id,
        )

        if draft is None:
            raise HTTPException(
                status_code=409,
                detail=(
                    "This email cannot be sent. Check that it is still "
                    "a DRAFT, belongs to your event, and its sponsor "
                    "is still selected. Already claimed or sent drafts "
                    "cannot be sent again through this endpoint."
                ),
            )

    except HTTPException:
        raise
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not claim the email draft for sending.",
        ) from error

    try:
        send_email(
            recipient_email=draft["recipient_email"],
            recipient_name=draft.get("recipient_name"),
            subject=draft["subject"],
            body=draft["body"],
            smtp_config=smtp_config,
        )

    except EmailSendError as error:
        try:
            finish_email_send(
                email_id=email_id,
                event_id=event_id,
                company_id=draft["company_id"],
                success=False,
                error=str(error),
            )
        except Error:
            print(
                f"Could not record the SMTP failure for email {email_id}."
            )

        raise HTTPException(
            status_code=502,
            detail=(
                "The SMTP send failed. The system recorded the failure "
                "if the database update succeeded. Check the SMTP "
                "configuration before trying again."
            ),
        ) from error

    try:
        finish_email_send(
            email_id=email_id,
            event_id=event_id,
            company_id=draft["company_id"],
            success=True,
        )

    except Error as error:
        # SMTP has already accepted the message; do not automatically retry.
        print(
            f"Email {email_id} may have been sent, but its database "
            f"status could not be finalized: {error}"
        )
        raise HTTPException(
            status_code=500,
            detail=(
                "The SMTP server accepted the email, but the database "
                "status update failed. Check the email account and "
                "database before attempting any further send."
            ),
        ) from error

    return {
        "message": "Email accepted by the configured SMTP server.",
        "email_id": email_id,
        "event_id": event_id,
        "company_id": draft["company_id"],
        "recipient_email": draft["recipient_email"],
        "status": "SENT",
    }


# ---------- View draft and send history ----------

@app.get("/api/events/{event_id}/outreach")
def list_event_outreach(
    event_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        history = get_outreach_history(event_id, user_id)

        for item in history:
            for field, value in item.items():
                if isinstance(value, (datetime, date)):
                    item[field] = value.isoformat()
                elif isinstance(value, Decimal):
                    item[field] = float(value)

        return {
            "event_id": event_id,
            "count": len(history),
            "outreach": history,
        }

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve outreach history.",
        ) from error



@app.get("/api/events/{event_id}/sponsors/{company_id}/history")
def list_sponsor_history(
    event_id: int,
    company_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        history = get_sponsor_history(
            event_id, company_id, user_id
        )

        if history is None:
            raise HTTPException(
                status_code=404,
                detail="Sponsor not found for this user's event.",
            )

        for section in ("previous_events", "sponsorship_evidence"):
            for item in history[section]:
                for field, value in item.items():
                    if isinstance(value, (datetime, date)):
                        item[field] = value.isoformat()
                    elif isinstance(value, Decimal):
                        item[field] = float(value)

        return {
            "event_id": event_id,
            "company_id": company_id,
            **history,
        }

    except HTTPException:
        raise
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve sponsor history.",
        ) from error



@app.get("/api/sponsors")
def list_sponsor_directory(
    user_id: int = Depends(authenticated_user_id),
    search: str | None = Query(default=None, max_length=200),
    industry: str | None = Query(default=None, max_length=150),
    sort_by: str = Query(default="name"),
):
    try:
        # Obtain industry options independently of active filters.
        all_sponsors = get_sponsor_directory(
            user_id=user_id,
            sort_by="name",
        )

        sponsors = get_sponsor_directory(
            user_id=user_id,
            search=search,
            industry=industry,
            sort_by=sort_by,
        )

        industries = sorted({
            item["industry"].strip()
            for item in all_sponsors
            if item.get("industry") and item["industry"].strip()
        })

        for item in sponsors:
            if item.get("latest_event_date"):
                item["latest_event_date"] = (
                    item["latest_event_date"].isoformat()
                )

            if item.get("event_count") is not None:
                item["event_count"] = int(item["event_count"])

            if item.get("sponsorship_evidence_count") is not None:
                item["sponsorship_evidence_count"] = int(
                    item["sponsorship_evidence_count"]
                )

        return {
            "count": len(sponsors),
            "industries": industries,
            "sponsors": sponsors,
        }

    except Error as error:
        print(f"Sponsor directory database error: {error!r}")

        raise HTTPException(
            status_code=500,
            detail="Could not retrieve the sponsor directory. Check server logs.",
        ) from error


@app.get("/api/sponsors/{company_id}/history")
def sponsor_global_history(
    company_id: int,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        history = get_sponsor_global_history(company_id, user_id)

        if history is None:
            raise HTTPException(
                status_code=404,
                detail="Sponsor not found in this user's events.",
            )

        for section in ("event_history", "sponsorship_evidence"):
            for item in history[section]:
                for field, value in item.items():
                    if isinstance(value, (datetime, date)):
                        item[field] = value.isoformat()
                    elif isinstance(value, Decimal):
                        item[field] = float(value)

        return history

    except HTTPException:
        raise
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve sponsor history.",
        ) from error


@app.get("/api/outreach")
def list_all_outreach(
    user_id: int = Depends(authenticated_user_id),
    search: str | None = Query(default=None, max_length=200),
    status: str | None = Query(default=None, max_length=20),
    sort_by: str = Query(default="newest"),
):
    try:
        records = get_all_outreach_history(
            user_id=user_id,
            search=search,
            status=status,
            sort_by=sort_by,
        )

        for item in records:
            for field, value in item.items():
                if isinstance(value, (datetime, date)):
                    item[field] = value.isoformat()
                elif isinstance(value, Decimal):
                    item[field] = float(value)

        email_settings = get_user_email_settings(user_id)

        sender_email = (
            (email_settings or {}).get("from_email") or ""
        ).strip()

        if not sender_email:
            sender_email = "Email account not configured"
        return {
            "count": len(records),
            "sender_email": sender_email,
            "outreach": records,
        }

    except ValueError as error:
        raise HTTPException(status_code=400, detail=str(error)) from error
    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not retrieve outreach history.",
        ) from error


@app.get("/api/event-progress")
def event_progress_api(user_id: int = Depends(authenticated_user_id)):
    try:
        return {"progress": get_event_progress(user_id)}
    except Error as error:
        raise HTTPException(status_code=500, detail="Could not retrieve event progress.") from error


app.mount(
    "/static",
    StaticFiles(directory=FRONTEND_DIR),
    name="static",
)

# --- SponsyBot AI Usage routes (added by apply_ai_usage_routes.py) ---
@app.get("/ai-usage")
def ai_usage_page(request: Request):
    redirect = _workspace_redirect(request)
    if redirect:
        return redirect
    return FileResponse(FRONTEND_DIR / "ai-usage.html")


@app.get("/api/ai-usage")
def ai_usage_api(user_id: int = Depends(authenticated_user_id)):
    return get_ai_usage_summary()

@app.get("/api/email-settings")
def read_email_settings_api(
    user_id: int = Depends(authenticated_user_id),
):
    try:
        settings = get_user_email_settings(user_id)

        if not settings:
            return {
                "configured": False,
                "settings": None,
            }

        # Never return the saved password or encrypted password.
        public_fields = (
            "from_name",
            "from_email",
            "smtp_host",
            "smtp_port",
            "smtp_security",
            "smtp_username",
            "has_password",
        )

        public_settings = {
            field: settings.get(field)
            for field in public_fields
        }

        return {
            "configured": True,
            "settings": public_settings,
        }

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not load your email settings.",
        ) from error


@app.put("/api/email-settings")
def update_email_settings_api(
    request: EmailSettingsRequest,
    user_id: int = Depends(authenticated_user_id),
):
    try:
        save_user_email_settings(
            user_id,
            request.model_dump(),
        )

        return {
            "message": (
                "Email settings saved. Test your connection "
                "before sending."
            ),
            "configured": True,
        }

    except EmailSettingsError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not save your email settings.",
        ) from error


@app.post("/api/email-settings/test")
def test_email_settings_api(
    user_id: int = Depends(authenticated_user_id),
):
    try:
        settings = get_user_email_settings(
            user_id,
            decrypt_password=True,
        )

        if not settings:
            raise HTTPException(
                status_code=409,
                detail=(
                    "Save your email account in Email Settings "
                    "before testing the connection."
                ),
            )

        test_smtp_connection(settings)

        return {
            "message": (
                "SMTP connection and login succeeded. "
                "No email was sent."
            ),
            "connected": True,
        }

    except HTTPException:
        raise

    except EmailSettingsError as error:
        raise HTTPException(
            status_code=422,
            detail=str(error),
        ) from error

    except EmailSendError as error:
        raise HTTPException(
            status_code=502,
            detail=str(error),
        ) from error

    except Error as error:
        raise HTTPException(
            status_code=500,
            detail="Could not load your saved email settings.",
        ) from error