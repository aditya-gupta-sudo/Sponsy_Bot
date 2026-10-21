
# contact_finder.py

import os
import re
from urllib.parse import urlparse

import requests
from ai_usage_tracker import record_usage
from pathlib import Path
from dotenv import load_dotenv

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")


HUNTER_DOMAIN_SEARCH_URL = "https://api.hunter.io/v2/domain-search"

EMAIL_PATTERN = re.compile(
    r"^[^@\s]+@[^@\s]+\.[^@\s]+$"
)


class ContactDiscoveryError(Exception):
    """Raised when Hunter contact discovery fails."""


def extract_domain(website):
    """Extract a domain from a saved company website."""
    if not website:
        return None

    value = website.strip()

    if "://" not in value:
        value = "https://" + value

    try:
        hostname = urlparse(value).hostname
    except ValueError:
        return None

    if not hostname:
        return None

    hostname = hostname.lower().rstrip(".")

    if hostname.startswith("www."):
        hostname = hostname[4:]

    # Avoid sending obviously invalid hostnames to Hunter.
    if "." not in hostname or " " in hostname:
        return None

    return hostname


def find_company_contacts(company_name, website=None):
    """
    Search Hunter Domain Search by domain, or by company name
    if no usable domain is available.

    Returns:
        {
            "domain": str | None,
            "website": str | None,
            "contacts": [...]
        }
    """
    api_key = os.getenv("HUNTER_API_KEY")

    if not api_key:
        raise ContactDiscoveryError(
            "HUNTER_API_KEY is not configured in .env."
        )

    domain = extract_domain(website)

    params = {
        "api_key": api_key,
        "limit": 10,
    }

    if domain:
        params["domain"] = domain
    else:
        params["company"] = company_name

    try:
        response = requests.get(
            HUNTER_DOMAIN_SEARCH_URL,
            params=params,
            timeout=25,
        )
    except requests.RequestException as error:
        raise ContactDiscoveryError(
            "Could not connect to Hunter."
        ) from error

    if response.status_code != 200:
        # Do not print response URLs; the query URL may contain the API key.
        raise ContactDiscoveryError(
            f"Hunter returned HTTP {response.status_code}."
        )

    try:
        payload = response.json()
    except ValueError as error:
        raise ContactDiscoveryError(
            "Hunter returned an invalid JSON response."
        ) from error

    if payload.get("errors"):
        raise ContactDiscoveryError(
            "Hunter rejected the contact search. Check the API key, "
            "request parameters, and remaining quota."
        )

    record_usage("hunter", units=1, operation="contact discovery")
    data = payload.get("data") or {}

    returned_domain = extract_domain(data.get("domain")) or domain

    returned_website = (
        website.strip()
        if website and website.strip()
        else f"https://{returned_domain}"
        if returned_domain
        else None
    )

    contacts = []
    seen_emails = set()

    for item in data.get("emails", []):
        email = (item.get("value") or "").strip().lower()

        if not email or not EMAIL_PATTERN.fullmatch(email):
            continue

        if email in seen_emails:
            continue

        seen_emails.add(email)

        first_name = (item.get("first_name") or "").strip()
        last_name = (item.get("last_name") or "").strip()

        full_name = " ".join(
            part for part in (first_name, last_name) if part
        ).strip()

        sources = item.get("sources") or []
        source_url = next(
            (
                source.get("uri")
                for source in sources
                if source.get("uri")
                and source["uri"].startswith(("https://", "http://"))
            ),
            None,
        )

        confidence = item.get("confidence")

        try:
            confidence = int(confidence) if confidence is not None else None
        except (TypeError, ValueError):
            confidence = None

        verification = item.get("verification") or {}
        verification_status = (
            verification.get("status")
            if isinstance(verification, dict)
            else None
        )

        contacts.append({
            "email_address": email,
            "full_name": full_name or None,
            "job_title": item.get("position"),
            "department": item.get("department"),
            "email_type": item.get("type"),
            "confidence": confidence,
            "verification_status": verification_status,
            "source_url": source_url,
            "found_via": "hunter",
        })

    return {
        "domain": returned_domain,
        "website": returned_website,
        "contacts": contacts,
    }
