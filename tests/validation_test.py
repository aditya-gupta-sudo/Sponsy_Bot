from pydantic import BaseModel


class SponsorAnalysis(BaseModel):
    company_name: str
    industry: str
    past_sponsorship_interest: str
    sponsor_fit: str
    reasons: list[str]


sponsor = SponsorAnalysis(
    company_name="Google",
    industry="Technology",
    past_sponsorship_interest="High",
    sponsor_fit="Excellent",
    reasons="Developer recruitment"
)

print(sponsor)