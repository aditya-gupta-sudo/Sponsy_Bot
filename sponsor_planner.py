
import json
import os
from pathlib import Path

from dotenv import load_dotenv
from google import genai
from ai_usage_tracker import record_usage


# Load environment variables from the project root.
BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")


def _get_client():
    api_key = os.getenv("GEMINI_API_KEY", "").strip()
    if not api_key:
        raise RuntimeError("GEMINI_API_KEY is missing from the project .env file.")
    return genai.Client(api_key=api_key)


def generate_sponsor_plan(event: dict) -> dict:
    """
    Generate audience-aware sponsor categories and search queries.

    This function does not search the web, rank companies, or save data.
    It only creates a search plan from a saved event.
    """

    # Pass only the event information relevant to sponsor discovery.
    event_profile = {
        "event_name": event.get("event_name"),
        "college": event.get("college"),
        "city": event.get("city"),
        "state": event.get("state"),
        "event_date": str(event.get("event_date", "")),
        "expected_participants": event.get("expected_participants"),
        "event_type": event.get("event_type"),
        "description": event.get("description"),
        "sponsorship_requirements": (
            event.get("sponsorship_requirements") or []
        ),
        "age_groups": event.get("age_groups") or [],
        "audience_types": event.get("audience_types") or [],
        "interests": event.get("interests") or [],
        "geographic_reach": event.get("geographic_reach"),
        "spending_profile": event.get("spending_profile") or "unknown",
        "event_format": event.get("event_format"),
    }

    prompt = f"""
You are the sponsor-discovery planning engine for SponsyBot.

Your task is to generate a broad, event-specific web-search plan.
You are NOT being asked to invent a list of sponsor companies.

SAVED EVENT PROFILE:
{json.dumps(event_profile, ensure_ascii=False, default=str, indent=2)}

OBJECTIVES:
1. Match potential sponsors to the actual audience and its interests,
   not merely to the event type.
2. Include relevant local businesses as well as larger brands.
3. Explore less-obvious but defensible opportunities.
4. Produce search queries that a web-search API can execute directly.

Consider categories where relevant, including:
- Cafes, restaurants, bakeries and food providers
- Youth-oriented consumer brands and retailers
- Coaching institutes and education providers
- Technology companies, developer platforms and cloud providers
- Gaming, sports, fitness and entertainment businesses
- Bookstores, stationery, printing and electronics shops
- Banks, coworking spaces, transport and other local businesses

These are examples, not mandatory categories.
Choose categories based on the supplied event profile.
Do not include irrelevant categories merely to fill a list.

RULES:
- Use the supplied city and state for local searches.
- Use the audience profile to explain category relevance.
- Never invent missing demographics, interests, budgets or attendance.
- Treat spending_profile="unknown" as unknown.
- Do not claim that a business sponsors events unless evidence exists.
- Search for previous sponsorships and partnership programs where useful,
  but do not exclude businesses simply because such evidence is unavailable.
- Include both cash and in-kind opportunities when relevant.
- Queries must name a business category or concrete search target.
- Prefer diverse queries over repetitive variations.
- Do not generate company names as if they were verified prospects.
- Generate 5 to 8 useful categories, each with 2 to 3 distinct queries.

Return ONLY valid JSON in this exact structure:
{{
  "event_name": "name of the supplied event",
  "categories": [
    {{
      "name": "Sponsor category",
      "reason": "Why this category may fit this event's audience",
      "possible_contributions": [
        "Cash",
        "Food vouchers"
      ],
      "queries": [
        "Specific web search query 1",
        "Specific web search query 2"
      ]
    }}
  ]
}}
"""

    client = _get_client()
    response = client.models.generate_content(
        model=GEMINI_MODEL,
        contents=prompt,
        config={
            "response_mime_type": "application/json",
        },
    )

    record_usage("gemini", units=1, operation="sponsor planning", model=GEMINI_MODEL)
    response_text = response.text

    if not response_text:
        raise RuntimeError("Gemini returned an empty response.")

    try:
        plan = json.loads(response_text)
    except json.JSONDecodeError as error:
        raise RuntimeError(
            "Gemini did not return valid JSON."
        ) from error

    # Basic validation before this plan is used by another service.
    if not isinstance(plan, dict):
        raise ValueError("The sponsor plan must be a JSON object.")

    categories = plan.get("categories")

    if not isinstance(categories, list) or not categories:
        raise ValueError(
            "The sponsor plan must contain at least one category."
        )

    for category in categories:
        if not isinstance(category, dict):
            raise ValueError("Each category must be a JSON object.")

        for field in ("name", "reason", "possible_contributions", "queries"):
            if field not in category:
                raise ValueError(
                    f"A category is missing the required field: {field}"
                )

        if not isinstance(category["queries"], list):
            raise ValueError("Category queries must be a list.")

        if not category["queries"]:
            raise ValueError(
                f"Category '{category['name']}' has no search queries."
            )

        # TEMPORARY DEBUG OUTPUT: Gemini sponsor plan
    print("\n" + "=" * 65, flush=True)
    print("[GEMINI] Sponsor plan generated successfully", flush=True)
    print(f"Event: {plan.get('event_name')}", flush=True)

    for index, category in enumerate(categories, start=1):
        print(f"\nCategory {index}: {category['name']}", flush=True)
        print(f"Reason: {category['reason']}", flush=True)
        print("Search queries:", flush=True)

        for query in category["queries"]:
            print(f"  - {query}", flush=True)

    print("=" * 65 + "\n", flush=True)

    return plan
