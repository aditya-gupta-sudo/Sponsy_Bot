from google import genai
from pydantic import BaseModel
import os
from dotenv import load_dotenv

load_dotenv()

api_key = os.getenv("GEMINI_API_KEY")

client = genai.Client(api_key=api_key)


class SponsorAnalysis(BaseModel):
    company_name: str
    industry: str
    past_sponsorship_interest: str
    sponsor_fit: str
    reasons: list[str]


response = client.models.generate_content(
    model="gemini-3.8-flash",
    contents="""
    Analyze Google as a potential sponsor for a college hackathon.

    Give information about:
    - company name
    - industry
    - past sponsorship interest
    - sponsor fit
    - reasons why the company could be a good sponsor
    """,
    config={
        "response_mime_type": "application/json",
        "response_schema": SponsorAnalysis,
    },
)

result = response.parsed

print(result)
print(type(result))
print(result.company_name)
print(result.sponsor_fit)
print(result.reasons)