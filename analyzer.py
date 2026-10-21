from google import genai
from pydantic import BaseModel
import os
from dotenv import load_dotenv
from pathlib import Path
from ai_usage_tracker import record_usage

BASE_DIR = Path(__file__).resolve().parent
load_dotenv(BASE_DIR / ".env")

api_key = os.getenv("GEMINI_API_KEY")
if not api_key:
    raise RuntimeError("GEMINI_API_KEY is not configured in .env.")

GEMINI_MODEL = os.getenv("GEMINI_MODEL", "gemini-3.8-flash")
client = genai.Client(api_key=api_key)


# -----------------------------
# 1. Define the AI output format
# -----------------------------

class SponsorAnalysis(BaseModel):
    company_name: str
    industry: str
    local_presence: str
    past_sponsorship_interest: str
    sponsor_fit: str
    reasons: list[str]


# -----------------------------
# 2. Information about our event
# -----------------------------

event_info = {
    "college": "SVNIT",
    "city": "Surat",
    "state": "Gujarat",
    "event_name": "ACM Hackathon",
    "event_date": "2026-10-19",
    "expected_participants": 500,
    "event_type": "College Hackathon",
    "focus": [
        "AI",
        "Software Development",
        "Web Development"
    ]
}


# -----------------------------
# 3. Information about company
# -----------------------------

company_info = {
    "company": "Microsoft",
    "industry": "Technology",

    "known_information": [
        "Microsoft develops software, cloud services, and developer tools.",
        "Microsoft has a large developer ecosystem."
    ],

    "local_presence": "Not provided",

    "past_sponsorships": "Not provided",

    "developer_programs": "Not provided"
}


# -----------------------------
# 4. Ask Gemini to analyze
# -----------------------------

response = client.models.generate_content(
    model=GEMINI_MODEL,

    contents=f"""
Analyze the following company as a potential sponsor for the following college hackathon.

IMPORTANT RULES:
- Use ONLY the information provided below.
- Do not invent facts.
- Do not assume that the company has an office in the event city.
- Do not assume previous sponsorships if they are not provided.
- If information is missing, write "Not provided".
- Consider the college, city, date, participants and technical focus of the event.
- Evaluate whether the company's known information matches the event.

EVENT INFORMATION:

{event_info}


COMPANY INFORMATION:

{company_info}


Return:
- company name
- industry
- local presence
- past sponsorship interest
- sponsor fit
- reasons why the company could be a good sponsor
""",

    config={
        "response_mime_type": "application/json",
        "response_schema": SponsorAnalysis,
    },
)


# Record only a successful provider response. This example is not used by the web app,
# but its API calls are also included in the local SponsyBot usage ledger.
record_usage("gemini", units=1, operation="manual company analysis", model=GEMINI_MODEL)

# -----------------------------
# 5. Get the structured result
# -----------------------------

result = response.parsed


# -----------------------------
# 6. Display the result
# -----------------------------

print(result)

print()

print("Company:", result.company_name)
print("Industry:", result.industry)
print("Local Presence:", result.local_presence)
print("Past Sponsorship Interest:", result.past_sponsorship_interest)
print("Sponsor Fit:", result.sponsor_fit)

print("Reasons:")

for reason in result.reasons:
    print("-", reason)
