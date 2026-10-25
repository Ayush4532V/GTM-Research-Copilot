"""
config.py — Declarative target profile for the GTM Research Copilot.

All ICP/industry logic lives here. Change the profile to adjust the Ideal
Customer Profile without touching scoring.py or any other code file.

Structure:
- target_industries: dict of industry categories and their keyword lists
  (moved from scoring.py INDUSTRY_CATEGORIES)
- ideal_signals: cross-industry signals that increase fit regardless of
  vertical (e.g. online booking, quote requests)
- disqualifiers: signals that reduce or negate fit
- target_regions: optional geographic filtering
- your_name / your_one_liner / value_proposition: outreach identity
- FIT_SCORE_THRESHOLD: default threshold used by the qualification stage
"""

# ---------------------------------------------------------------------------
# Target industries
# Moved from scoring.py INDUSTRY_CATEGORIES — keep in sync if you add/remove
# categories in scoring.py.
# ---------------------------------------------------------------------------

target_industries = {
    "healthcare": [
        "clinic", "doctor", "dentist", "dental", "hospital", "medical",
        "physiotherapy", "physio", "chiropractor", "wellness", "therapy",
        "healthcare", "telehealth", "mental health", "counseling", "psychology",
        "optometrist", "optometry", "veterinary", "vet", "lab", "laboratory",
        "pharmacy", "appointment", "patient", "book",
    ],
    "legal": [
        "law", "attorney", "legal", "firm", "litigation", "consultant",
        "paralegal", "court", "claims", "personal injury",
        "immigration", "family law", "criminal", "civil", "notary",
        "appointment", "consultation",
    ],
    "real_estate": [
        "real estate", "realtor", "property", "agent", "brokerage",
        "commercial", "residential", "mortgage", "apartment", "rental",
        "leasing", "development", "construction", "home", "estate agency",
        "book", "viewing", "appointment",
    ],
    "automotive": [
        "car", "auto", "automotive", "dealer", "repair", "mechanic",
        "service center", "body shop", "tyre", "tire", "oil change",
        "diesel", "bus", "fleet", "rental", "motorcycle", "parts",
        "appointment", "book",
    ],
    "hospitality": [
        "hotel", "restaurant", "catering", "cafe",
        "resort", "bar", "pub", "hospitality", "travel", "tourism",
        "booking", "reservation", "hostel", "guest house", "vacation",
        "stay", "event", "venue", "conference",
    ],
    "fitness": [
        "gym", "fitness", "yoga", "pilates", "crossfit", "workout",
        "trainer", "nutrition", "diet", "weight loss", "spa", "massage",
        "wellness", "class", "studio", "training",
    ],
    "education": [
        "school", "university", "college", "academy", "tutor", "training",
        "course", "institute", "educational", "learning", "coaching",
        "kindergarten", "primary school", "secondary school", "language",
        "enrollment", "student",
    ],
    "home_services": [
        "plumbing", "electrician", "hvac", "heating", "air conditioning",
        "cleaning", "cleaner", "pest control", "landscaping", "garden",
        "removalists", "movers", "painting", "roofer", "carpenter",
        "handyman", "locksmith", "appliance repair", "installation",
    ],
    "financial": [
        "accounting", "accountant", "bookkeeping", "tax", "finance",
        "insurance", "broker", "invest", "investment", "wealth",
        "advisory", "adviser", "advisor", "bank", "credit", "mortgage",
        "loan", "pension", "retirement", "super",
    ],
    "technology": [
        "software", "saas", "it", "technology", "tech", "digital",
        "app", "developer", "programming", "api", "cloud", "data",
        "analytics", "cybersecurity", "automation", "ai", "artificial",
        "intelligence", "consulting", "services",
    ],
    "retail": [
        "shop", "store", "retail", "boutique", "e-commerce", "ecommerce",
        "online store", "merchandise", "wholesale", "distribution",
        "subscription", "clothing", "fashion", "beauty", "cosmetics",
        "gift", "jewellery", "jewelry", "accessories",
    ],
    "manufacturing": [
        "manufacturing", "manufacturer", "factory", "production", "industrial",
        "supply", "logistics", "warehouse", "machinery", "equipment",
        "fabrication", "assembly", "parts", "components",
    ],
    "nonprofit": [
        "nonprofit", "non-profit", "charity", "foundation", "ngo",
        "community", "volunteer", "fundraising", "donation", "cause",
        "association", "membership",
    ],
    "professional_services": [
        "consulting", "consultant", "agency", "marketing", "advertising",
        "design", "graphic design", "branding", "pr", "public relations",
        "hr", "human resources", "recruitment", "relocation",
        "facilities", "event management", "catering",
    ],
    "other": [],
}

# ---------------------------------------------------------------------------
# Ideal signals: cross-industry signals that boost fit_score_rule
# ---------------------------------------------------------------------------

ideal_signals = {
    # Booking/enquiry features that show a structured qualification flow.
    "online_booking": [
        "book online", "book now", "booking engine", "booking system",
    ],
    "quote_request": [
        "get a quote", "request a quote", "quote request",
    ],
    "contact_form": [
        "contact form", "enquiry form", "request a callback",
    ],
    "consultation_offer": [
        "free consultation", "book an appointment",
    ],
    "live_chat": [
        "live chat", "chatbot",
    ],
}

# ---------------------------------------------------------------------------
# Disqualifiers: signals that reduce or negate fit regardless of industry
# ---------------------------------------------------------------------------

disqualifiers = {
    # Non-business / personal sites.
    "personal_blog": [
        "blog", "personal blog", "medium", "substack",
    ],
    # Public sector / government (typically outside SMB scope).
    "public_sector": [
        "government", "city hall", "municipal", "council",
        "public sector", "ministry",
    ],
    # Non-profit / advocacy that doesn't have structured enquiry flows.
    "pure_advocacy": [
        "justice", "rights", "equality", "protest", "demonstration",
    ],
}

# ---------------------------------------------------------------------------
# Target regions (optional — leave empty for global)
# ---------------------------------------------------------------------------

target_regions = []  # e.g. ["us", "ca", "uk", "au"]

# ---------------------------------------------------------------------------
# Outreach identity: used by draft_email.py for personalized intros
# ---------------------------------------------------------------------------

your_name = "Ayush"
your_one_liner = "I help service businesses reduce response time on inbound enquiries with an AI front-desk."
value_proposition = "Our AI front-desk qualifies leads and schedules appointments 24/7, saving 5–10 hours of manual work per week."

# ---------------------------------------------------------------------------
# Default qualification threshold (can be overridden per-run)
# ---------------------------------------------------------------------------

FIT_SCORE_THRESHOLD = 70

# Pipeline limits — read from environment or use defaults.
MAX_ACTIONS_PER_RUN = 25
DISCOVERY_QUERIES_PER_RUN = 25

# Auto-send flag: false = create Gmail drafts only, true = actually send.
AUTO_SEND = False

# Database path (SQLite)
DB_PATH = "leads.db"

# Exported aliases so scoring.py can read keyword lists directly from config
# without changing how callers use the module.
INDUSTRY_CATEGORIES = target_industries

COMPLEXITY_KEYWORDS = [
    "quote", "quotation", "get a quote", "free quote", "request a quote",
    "custom", "customised", "customized", "tailored", "bespoke",
    "multiple", "multi", "bulk", "enterprise", "corporate",
    "complex", "complicated", "configuration", "specification",
    "estimate", "proposal", "package", "bundled",
]

BOOKING_KEYWORDS = [
    "book online", "book now", "booking", "book an appointment",
    "schedule", "appointment", "reserve", "enquire", "enquiry", "contact us",
    "request a callback", "callback", "free consultation", "chat with us",
    "live chat", "chatbot", "faq", "frequently asked questions",
    "form", "contact form", "apply", "register", "signup", "sign up",
    "quote request", "lead", "inquiry", "inquiry form",
]

AUTOMATION_KEYWORDS = [
    "appointment booking", "online booking", "self-service", "24/7",
    "round the clock", "open 24 hours", "instant", "same day", "quick quote",
    "automated", "schedule", "calendar", "availability", "slot", "timeslot",
    "booking engine", "booking system", "reservation system", "self booking",
]

QUOTE_INVITE_PHRASES = [
    "get a quote", "request a quote", "request quote", "quote request",
    "enquire now", "enquire today", "contact us", "contact us today",
    "book now", "book today", "book an appointment", "free consultation",
    "chat to us", "chat with us", "speak to us", "get in touch",
]