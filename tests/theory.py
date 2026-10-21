# # The key idea for SponsyBot is to discover sponsors through audience-to-business matching, not just event-type matching. A café may be a sensible prospect for a college hackathon because of the attendees' age, location and food needs, even though the café has no connection to technology. Event sponsorship guidance similarly emphasizes audience alignment, local businesses and concrete benefits for the sponsor. 
# 1. First, build an audience profile for every event
# Your current event form captures event type, location, expected participants, description and sponsorship requirements. That is a useful start, but it doesn't fully describe the audience.
# I would add these fields to SponsyBot in a later form update:
# - Age groups: e.g. 16–18, 18–22, 23–30, 30+.
# - Audience type: college students, school students, working professionals, entrepreneurs, families, competitive-exam aspirants, etc.
# - Interests: technology, gaming, fitness, food, career development, entertainment, finance, and so on.
# - Geographic reach: attendees from the host college, nearby colleges, across the city, or across India.
# - Spending profile: unknown, low, moderate or high, based on organizer-provided information—not assumptions about individuals.
# - Event format: on-campus, off-campus, online or hybrid.
# Let organizers select multiple audience types and interests. If a field is unknown, store it as unknown rather than letting AI invent demographics.

# 2. Create a sponsor-category discovery matrix
# For each event, SponsyBot should investigate several categories in parallel.

# A. Local food, cafés and restaurants
# Potential support: coupons, refreshments, food vouchers, catering, cash sponsorship.
# Find cafés near the venue, restaurants, bakeries, pizza outlets, snack shops, cloud kitchens and food delivery brands.
# Search signals: proximity to the campus, student discounts, bulk catering, campus partnerships and previous college-event support.

# B. Youth-oriented consumer brands
# Potential support: product sampling, merchandise, coupons, cash sponsorship.
# Investigate energy-drink brands such as Red Bull and Monster Energy, as well as sportswear, gaming accessories, personal-care products and youth-oriented retail brands.
# Search signals: campus activations, youth marketing campaigns, local brand representatives and previous event partnerships. Do not assume a major brand accepts unsolicited sponsorship requests.

# C. Coaching institutes and education businesses
# Potential support: cash, scholarships, fee discounts, learning resources, workshops.
# Find local JEE/NEET coaching centres, UPSC and government-exam institutes, coding bootcamps, test-preparation providers and online learning platforms.
# Search signals: the attendee age group, overlap with their prospective students, branches near the venue, scholarships and student-outreach programs.

# D. Technology and developer businesses
# Potential support: cloud credits, APIs, prizes, equipment, cash.
# Search cloud providers, software companies, hardware manufacturers, cybersecurity firms, developer platforms and startups.
# Search signals: student programs, hackathon grants, educational licenses and sponsorships of similar events.

# E. Other local businesses
# Potential support: cash, gift cards, services, equipment or venue support.
# Include gyms, bookstores, stationery shops, printing services, clothing retailers, electronics shops, banks, coworking spaces and transport providers.
# Search signals: service-area overlap, relevance to the audience, a local decision-maker and a concrete benefit from participating.

# These categories are starting points, not an exhaustive list. SponsyBot should expand them according to the actual audience and event requirements.
# 3. How the discovery engine should search
# For each event, use the following workflow.
# 1. Generate categories from the event profile.
#    Gemini reads the event details and proposes relevant sponsor categories, including less-obvious ones such as cafés and coaching institutes.
# 2. Generate searches for each category.
#    For example, a college event in Surat might generate queries for nearby cafés, student discounts, local coaching centres, youth-brand activations and technology sponsors.
# 3. Search multiple sources.
#    Tavily searches the web. Later, a second search provider can help find additional businesses that the first source missed. Search official company pages, local directories and evidence of prior partnerships.
# 4. Extract companies and evidence.
#    Gemini turns results into structured records: company name, website, industry, location, source URL, evidence snippet, relevant sponsor category and explanation of potential fit.
# 5. Deduplicate, save and review.
#    Store each company once in companies, link it to the event through event_companies, and retain its research evidence in company_research_sources.
# 4. What SponsyBot should store for each candidate

# Your current database already supports the core company and event relationship. The discovery service should additionally retain structured research information, such as:
# Field	Example
# Company	Local café
# Sponsor category	Food and beverage
# Geographic relevance	Near the event venue
# Audience match	Student attendees
# Possible contribution	Food vouchers or refreshments
# Evidence	Source URL and supporting text
# Reason to approach	Can reach students attending the event
# Verification	Evidence found / needs verification
# The reason to approach must be grounded in the evidence. If we only know that a café exists near campus, we can say it is a potential local prospect—not that it has a sponsorship budget.

# 5. The important distinction: discovery versus ranking
# Do not filter out every company that lacks a public sponsorship history. That would exclude many local businesses that may be willing to provide in-kind support.
# Instead, discovery should aim for broad but relevant coverage, and the next ranking stage should evaluate:
# - Audience alignment.
# - Geographic relevance.
# - Relevance to the event's requirements.
# - Evidence of previous sponsorships or partnership programs.
# - Likely type of contribution.
# - Strength and reliability of supporting evidence.
# My recommendation for the current build: implement audience-aware category generation first, then run Tavily searches across those categories. Keep discovery broad enough to find unexpected prospects, but require a source and a defensible reason before saving each candidate. That gives SponsyBot a much stronger foundation than simply asking an AI to list sponsors for a hackathon.