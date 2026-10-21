
# contact_ranking.py
import re


# Tier 1: job titles directly related to sponsorship decisions.
DIRECT_ROLE_TERMS = (
    "sponsorship",
    "sponsor relations",
    "corporate social responsibility",
    "csr",
    "partnership",
    "alliances",
    "corporate affairs",
    "public affairs",
    "community relations",
    "social impact",
    "sustainability",
    "brand partnership",
    "brand marketing",
    "marketing",
    "communications",
    "public relations",
    "external affairs",
    "external relations",
)

# Tier 3: fallback positions with identifiable authority.
SENIOR_ROLE_PATTERNS = (
    r"\bchief executive officer\b",
    r"\bceo\b",
    r"\bmanaging director\b",
    r"\bjoint managing director\b",
    r"\bpresident\b",
    r"\bvice president\b",
    r"\bvp\b",
    r"\bdirector\b",
    r"\bgeneral manager\b",
    r"\bdeputy general manager\b",
    r"\bassistant general manager\b",
    r"\bdepartment head\b",
    r"\bhead of\b",
    r"\bchairman\b",
    r"\bchairperson\b",
    r"\bchief operating officer\b",
    r"\bcoo\b",
    r"\bchief financial officer\b",
    r"\bcfo\b",
)

# Exclude clearly unrelated roles. These should never become fallback
# contacts merely because their title contains "chief" or "director".
UNRELATED_ROLE_TERMS = (
    "information security",
    "cyber security",
    "cybersecurity",
    "software engineer",
    "software developer",
    "network engineer",
    "it support",
    "technical support",
    "self employed",
    "self-employed",
)

DIRECT_INBOX_TERMS = (
    "sponsorship",
    "sponsor",
    "partnership",
    "alliances",
    "csr",
    "marketing",
    "brand",
    "corporateaffairs",
    "community",
    "socialimpact",
    "sustainability",
    "communications",
    "publicrelations",
    "externalaffairs",
)

GENERAL_INBOX_NAMES = {
    "info",
    "contact",
    "enquiry",
    "enquiries",
    "inquiry",
    "inquiries",
    "office",
    "corporate",
}


def _normalize(value):
    return re.sub(
        r"\s+",
        " ",
        str(value or "").strip().lower(),
    )


def _email_local_part(email):
    email = _normalize(email)

    if "@" not in email:
        return ""

    return email.split("@", 1)[0]


def _contains_any(text, terms):
    return any(term in text for term in terms)


def _is_senior_role(title):
    return any(
        re.search(pattern, title)
        for pattern in SENIOR_ROLE_PATTERNS
    )


def rank_contact(contact):
    """
    Rank one saved Hunter contact for sponsorship outreach.

    Priority:
      1 = directly sponsorship-related person or role inbox
      2 = official general corporate contact inbox
      3 = senior-management fallback
      None = not recommended
    """

    title = _normalize(contact.get("job_title"))
    department = _normalize(contact.get("department"))
    email_type = _normalize(contact.get("email_type"))
    email = _normalize(contact.get("email_address"))
    email_local = _email_local_part(email)

    verification = _normalize(
        contact.get("verification_status")
    )

    result = {
        "priority_rank": None,
        "contact_category": "NOT_RECOMMENDED",
        "recommended": False,
        "can_generate_draft": False,
        "selection_reason": (
            "No suitable sponsorship role or designated fallback "
            "position was identified."
        ),
        "verification_warning": None,
    }

    if not email or "@" not in email:
        result["selection_reason"] = "No usable email address."
        return result

    # An explicitly invalid address must not be used.
    if verification == "invalid":
        result["selection_reason"] = (
            "Hunter marks this email as invalid."
        )
        result["verification_warning"] = (
            "Do not use this address."
        )
        return result

    direct_title_match = _contains_any(
        title,
        DIRECT_ROLE_TERMS,
    )

    direct_inbox_match = (
        email_type == "generic"
        and _contains_any(email_local, DIRECT_INBOX_TERMS)
    )

    # Directly relevant roles take priority, unless the title clearly
    # identifies an unrelated function.
    unrelated_role = _contains_any(
        title,
        UNRELATED_ROLE_TERMS,
    )

    if (direct_title_match or direct_inbox_match) and not unrelated_role:
        result.update({
            "priority_rank": 1,
            "contact_category": "DIRECT_SPONSORSHIP_ROLE",
            "recommended": True,
            "can_generate_draft": True,
            "selection_reason": (
                "The title or role-based email is directly related "
                "to sponsorship, CSR, marketing, or partnerships."
            ),
        })

    # General company contact inboxes are a fallback, not a named
    # decision-maker. Use them only when they are role-based addresses.
    elif (
        email_type == "generic"
        and email_local in GENERAL_INBOX_NAMES
    ):
        result.update({
            "priority_rank": 2,
            "contact_category": "GENERAL_CORPORATE_INBOX",
            "recommended": True,
            "can_generate_draft": True,
            "selection_reason": (
                "An official general corporate contact inbox is "
                "available as a fallback."
            ),
        })

    # Do not choose staff from unrelated departments as a fallback.
    elif (
        _is_senior_role(title)
        and not unrelated_role
        and department not in {"it", "support", "hr"}
    ):
        result.update({
            "priority_rank": 3,
            "contact_category": "SENIOR_MANAGEMENT_FALLBACK",
            "recommended": True,
            "can_generate_draft": True,
            "selection_reason": (
                "No direct sponsorship role was identified for this "
                "contact. This is a designated senior-management "
                "fallback and requires human review."
            ),
        })

    if result["recommended"]:
        if verification == "valid":
            result["verification_warning"] = None
        elif verification == "accept_all":
            result["verification_warning"] = (
                "The domain accepts all addresses; individual "
                "deliverability is not confirmed."
            )
        else:
            result["verification_warning"] = (
                "The email is not confirmed as valid. Review or "
                "verify it before sending."
            )

    return result


def rank_contacts(contacts):
    """Return contacts with ranking metadata, best candidates first."""

    ranked = []

    for contact in contacts:
        item = dict(contact)
        item.update(rank_contact(contact))
        ranked.append(item)

    ranked.sort(
        key=lambda contact: (
            contact["priority_rank"] is None,
            contact["priority_rank"] or 999,
            contact.get("verification_status") != "valid",
            -(contact.get("confidence") or 0),
            contact.get("email_address") or "",
        )
    )

    for index, contact in enumerate(ranked, start=1):
        contact["display_order"] = index

    return ranked
