
# email_generator.py

import json
import os

from dotenv import load_dotenv
from groq import Groq
from pathlib import Path
from ai_usage_tracker import record_usage

load_dotenv(Path(__file__).resolve().parent / ".env")


class EmailGenerationError(Exception):
    """Raised when email generation fails."""


def generate_sponsorship_email(event, company, contact):
    api_key = os.getenv("GROQ_API_KEY")
    model = os.getenv(
        "GROQ_EMAIL_MODEL",
        os.getenv("GROQ_MODEL", "openai/gpt-oss-20b"),
    )

    if not api_key:
        raise EmailGenerationError(
            "GROQ_API_KEY is not configured in .env."
        )

    event_information = {
        "name": event.get("event_name"),
        "organizer": event.get("college"),
        "city": event.get("city"),
        "state": event.get("state"),
        "date": str(event.get("event_date") or ""),
        "expected_participants": event.get("expected_participants"),
        "event_type": event.get("event_type"),
        "description": event.get("description"),
        "sponsorship_requirements": event.get(
            "sponsorship_requirements", []
        ),
        "audience_types": event.get("audience_types", []),
        "interests": event.get("interests", []),
        "format": event.get("event_format"),
    }

    company_information = {
        "name": company.get("company_name"),
        "industry": company.get("industry"),
        "website": company.get("company_website"),
        "research_title": company.get("source_title"),
        "research_evidence": company.get("evidence_snippet"),
        "research_source": company.get("source_url"),
    }

    contact_information = {
        "name": contact.get("full_name"),
        "job_title": contact.get("job_title"),
        "department": contact.get("department"),
        "email": contact.get("email_address"),
    }

    prompt = f"""
Write a professional, personalized sponsorship outreach email.

EVENT DATA:
{json.dumps(event_information, ensure_ascii=False, default=str)}

COMPANY DATA:
{json.dumps(company_information, ensure_ascii=False, default=str)}

CONTACT DATA:
{json.dumps(contact_information, ensure_ascii=False, default=str)}

Rules:
- Use only the facts supplied above.
- Never invent attendance figures, prior relationships, benefits,
  sponsorship commitments, company contacts, or event achievements.
- Do not claim that the recipient is responsible for sponsorship unless
  their supplied job title or department supports that claim.
- Explain briefly why the company may be relevant to this event.
- Refer to the actual event date, but do not imply the date is confirmed
  beyond the supplied event data.
- Ask for a short conversation about possible sponsorship.
- Be professional, specific, concise, and not pushy.
- Do not include fake sender names, fake phone numbers, or fake links.
- Return valid JSON only, with exactly these string fields:
  {{
    "subject": "email subject",
    "body": "complete email body"
  }}
"""

    try:
        client = Groq(api_key=api_key)

        response = client.chat.completions.create(
            model=model,
            temperature=0.3,
            messages=[
                {
                    "role": "system",
                    "content": (
                        "You write accurate, personalized business "
                        "emails. Never invent facts. Output valid JSON."
                    ),
                },
                {"role": "user", "content": prompt},
            ],
        )

        record_usage("groq", units=1, operation="email draft generation", model=model)
        content = response.choices[0].message.content or ""

        # Handle a model response that includes text around the JSON.
        start = content.find("{")
        end = content.rfind("}")

        if start < 0 or end < start:
            raise ValueError("No JSON object found.")

        result = json.loads(content[start:end + 1])

        subject = result.get("subject")
        body = result.get("body")

        if not isinstance(subject, str) or not subject.strip():
            raise ValueError("The generated subject is empty.")

        if not isinstance(body, str) or not body.strip():
            raise ValueError("The generated body is empty.")

        return {
            "subject": subject.strip(),
            "body": body.strip(),
        }

    except Exception as error:
        raise EmailGenerationError(
            "Could not generate an email draft. Check the Groq model, "
            "API quota, and server logs."
        ) from error
