"""
app.py — Main Streamlit application for the GTM Research Copilot.

This app demonstrates AI-assisted prospect research for GTM (Go-To-Market)
engineers at Hyperleap AI. It combines:
- Rule-based ICP scoring (scoring.py)
- Groq-powered research summaries (ai_generator.py)
- Rule-based outreach drafting
- CSV export via Pandas

Run with: streamlit run app.py
"""

import pandas as pd
import streamlit as st

from research import extract_website_info
from scoring import score_prospect, get_criteria_labels
from ai_generator import generate_research_summary


# ---------------------------------------------------------------------------
# Session state initialization
# ---------------------------------------------------------------------------

def init_session_state():
    """Initialize or reset all session state variables."""
    if "prospects" not in st.session_state:
        st.session_state.prospects = []
    if "summary" not in st.session_state:
        st.session_state.summary = None
    if "summary_source" not in st.session_state:
        st.session_state.summary_source = None
    if "research_result" not in st.session_state:
        st.session_state.research_result = None


init_session_state()


# ---------------------------------------------------------------------------
# Outreach draft generation (no API calls)
# ---------------------------------------------------------------------------

def generate_outreach_draft(business_name: str, industry: str, observation: str = None) -> str:
    """
    Generate a personalized outreach draft using a Python string template.
    No LLM API calls are made here.
    """
    # Use an observed fact or a safe default.
    if not observation or len(observation.strip()) < 10:
        observation = "your services"

    # Template - conversational, concise, factual, and low-pressure.
    template = f"""Hi {business_name},

I noticed you specialize in {industry} services. From your website, I saw you're handling {observation}.

Hyperleap AI helps businesses reduce response time on inbound enquiries with an AI front-desk that can qualify leads and schedule appointments 24/7. It's a straightforward integration that typically saves a few hours of manual work per week.

Would you be open to a quick 15-minute chat about whether this might fit your workflow?

Best,
[Your Name]"""

    return template


# ---------------------------------------------------------------------------
# Main UI
# ---------------------------------------------------------------------------

st.set_page_config(
    page_title="GTM Research Copilot",
    page_icon="🔍",
    layout="centered",
)

st.title("🔍 GTM Research Copilot")
st.caption(
    "AI-assisted prospect research for GTM engineers. "
    "Demo by Ayush for Hyperleap AI."
)

# ---------------------------------------------------------------------------
# Section A: Business Input
# ---------------------------------------------------------------------------

st.header("A. Business Input")

col1, col2 = st.columns(2)
with col1:
    business_name = st.text_input(
        "Business name",
        placeholder="e.g., Sunset Dental Clinic"
    )
with col2:
    website_url = st.text_input(
        "Website URL",
        placeholder="https://example.com"
    )

industry_options = [
    "healthcare", "legal", "real_estate", "automotive", "hospitality",
    "fitness", "education", "home_services", "financial", "technology",
    "retail", "manufacturing", "nonprofit", "professional_services", "other"
]
selected_industry = st.selectbox(
    "Select industry",
    options=industry_options,
    index=0,
    help="Choose the industry that best matches this business."
)

manual_description = st.text_area(
    "Manual business description (optional)",
    placeholder="Add any details you know that weren't on the website..."
)

research_button = st.button("🔬 Research Business", type="primary")

# Track icp_result for use in the prospect table
icp_result = None

# ---------------------------------------------------------------------------
# Run research when button clicked
# ---------------------------------------------------------------------------

if research_button and business_name:
    # Reset previous results
    st.session_state.summary = None
    st.session_state.summary_source = None
    st.session_state.research_result = None

    # Step 1: Extract website info
    with st.spinner("Extracting website information..."):
        web_result = extract_website_info(website_url)

    # Step 2: Build evidence text
    evidence_text_parts = []
    if web_result["success"]:
        evidence_text_parts.append(f"Title: {web_result['title']}")
        evidence_text_parts.append(f"Description: {web_result['description']}")
        evidence_text_parts.append(f"Content excerpt: {web_result['content'][:1500]}")
    if manual_description.strip():
        evidence_text_parts.append(f"Manual description: {manual_description}")

    evidence_text = " ".join(evidence_text_parts)

    # Step 3: Score the prospect
    with st.spinner("Calculating prospect fit score..."):
        icp_result = score_prospect(selected_industry, evidence_text, web_result.get("content", ""))

    # Store scores in research result for later display
    web_result["total_score"] = icp_result

    # Step 4: Generate research summary
    with st.spinner("Generating research summary..."):
        summary = generate_research_summary(
            business_name=business_name,
            industry=selected_industry,
            website_title=web_result.get("title", ""),
            website_description=web_result.get("description", ""),
            extracted_text=web_result.get("content", ""),
            icp_scores=icp_result["scores"],
            icp_total=icp_result["total"],
            icp_category=icp_result["category"],
        )

        # Determine the summary source.
        if summary.startswith("[Groq-"):
            st.session_state.summary_source = "Groq-generated"
        else:
            st.session_state.summary_source = "Rule-based fallback"

        st.session_state.summary = summary
        # Keep the user-entered prospect details with the scraped website data.
        # The outreach section reads from this dictionary after Streamlit reruns.
        web_result["business_name"] = business_name
        web_result["industry"] = selected_industry
        st.session_state.research_result = web_result

    st.success("Research complete!")


# ---------------------------------------------------------------------------
# Section B: Website Findings
# ---------------------------------------------------------------------------

st.header("B. Website Findings")

if st.session_state.research_result:
    result = st.session_state.research_result

    col1, col2 = st.columns(2)
    with col1:
        st.subheader("Page title")
        if result["success"]:
            st.write(result.get("title", "") or "—")
        else:
            st.write("—")
    with col2:
        st.subheader("Meta description")
        if result["success"]:
            desc = result.get("description", "")
            st.write((desc[:200] + "...") if len(desc) > 200 else (desc or "—"))
        else:
            st.write("—")

    st.subheader("Extracted content")
    if result["success"]:
        content = result.get("content", "")
        # Show first 300 chars with expand option.
        short_content = (content[:300] + "...") if len(content) > 300 else content
        st.markdown(f"**{short_content}**")
        if len(content) > 300:
            with st.expander("View more"):
                st.write(content)
    else:
        st.info(f"Could not extract content: {result.get('error', 'Unknown error')}")

    if not result["success"]:
        st.caption(
            "Research limitations: Website extraction failed. "
            "The business will be scored using the manual description only."
        )


# ---------------------------------------------------------------------------
# Section C: ICP Scoring
# ---------------------------------------------------------------------------

st.header("C. ICP Scoring")

if st.session_state.research_result and st.session_state.research_result.get("total_score"):
    result = st.session_state.research_result
    scores = result["total_score"]["scores"]
    total = result["total_score"]["total"]
    category = result["total_score"]["category"]

    # Display total score and category
    col1, col2, col3 = st.columns(3)
    with col1:
        st.metric("ICP Score", total, delta="out of 100")
    with col2:
        if total >= 70:
            st.success(category)
        elif total >= 40:
            st.warning(category)
        else:
            st.info(category)

    # Individual criteria
    st.markdown("#### Criterion breakdown")
    for criterion_key in ["industry_fit", "enquiry_complexity", "booking_fit", "automation_opportunity"]:
        details = scores.get(criterion_key, (0, "N/A", [], "missing"))
        with st.expander(f"{get_criteria_labels().get(criterion_key, criterion_key)}"):
            st.markdown(f"**Score:** {details[0]} points")
            st.markdown(f"**Explanation:** {details[1]}")
            st.markdown(f"**Evidence:** {'; '.join(details[2]) if details[2] else 'N/A'}")


# ---------------------------------------------------------------------------
# Section D: Research Summary
# ---------------------------------------------------------------------------

st.header("D. Research Summary")

if st.session_state.summary:
    source = st.session_state.summary_source or "Unknown"
    st.markdown(f"**Summary source:** {source}")
    st.markdown(st.session_state.summary)
elif research_button:
    st.info("Generate a summary by clicking the Research button above.")


# ---------------------------------------------------------------------------
# Section E: Outreach Draft
# ---------------------------------------------------------------------------

st.header("E. Outreach Draft")

if st.session_state.research_result:
    result = st.session_state.research_result

    # Find one verified observation from the website for personalization.
    observation = None
    if result.get("success") and result.get("title"):
        observation = f"the '{result['title']}' page"
    elif result.get("success") and result.get("description"):
        observation = f"their '{result['description'][:60]}...'"

    # Initialize outreach draft if not present
    if "outreach_draft" not in st.session_state:
        st.session_state.outreach_draft = generate_outreach_draft(
            result.get("business_name", business_name),
            result.get("industry", selected_industry),
            observation,
        )
        st.session_state.draft_approved = False

    st.text_area(
        "Outreach draft",
        value=st.session_state.outreach_draft,
        height=150,
        key="draft_editor"
    )

    # Allow editing: update the stored draft
    st.session_state.outreach_draft = st.session_state.draft_editor

    col1, col2 = st.columns(2)
    with col1:
        if st.button("🔁 Regenerate Draft"):
            st.session_state.outreach_draft = generate_outreach_draft(
                result.get("business_name", business_name),
                result.get("industry", selected_industry),
                observation,
            )
            st.session_state.draft_approved = False
            st.rerun()
    with col2:
        approved = st.checkbox(
            "Mark as approved",
            value=st.session_state.draft_approved,
            key="approve_checkbox"
        )
        st.session_state.draft_approved = approved
        if approved:
            st.success("Draft marked as approved")


# ---------------------------------------------------------------------------
# Section F: Prospect Table
# ---------------------------------------------------------------------------

st.header("F. Prospect Table")

# Prevent duplicate entries
is_duplicate = business_name and st.session_state.prospects and any(
    p.get("business_name") == business_name for p in st.session_state.prospects
)

# Build evidence_text for CSV export
evidence_text_parts = []
rr = st.session_state.research_result
if rr and rr.get("success"):
    evidence_text_parts.append(f"Title: {rr.get('title', '')}")
    evidence_text_parts.append(f"Description: {rr.get('description', '')}")
    evidence_text_parts.append(f"Content excerpt: {rr.get('content', '')[:1000]}")
if manual_description.strip():
    evidence_text_parts.append(f"Manual description: {manual_description}")
evidence_text = " ".join(evidence_text_parts)

if is_duplicate and research_button:
    st.warning("⚠️ This business is already in the prospect list.")
elif research_button and business_name and st.session_state.research_result:
    # Ensure we have the icp_result from the research phase
    scores = st.session_state.research_result["total_score"]["scores"]
    total = st.session_state.research_result["total_score"]["total"]
    category = st.session_state.research_result["total_score"]["category"]

    # Add to prospect list
    new_prospect = {
        "business_name": business_name,
        "website_url": website_url,
        "industry": selected_industry,
        "total_score": total,
        "category": category,
        # Each scoring criterion is returned as a tuple:
        # (points, explanation, evidence, evidence_status).
        "industry_fit_score": scores["industry_fit"][0],
        "enquiry_complexity_score": scores["enquiry_complexity"][0],
        "booking_fit_score": scores["booking_fit"][0],
        "automation_opportunity_score": scores["automation_opportunity"][0],
        "evidence": evidence_text[:500] + "..." if len(evidence_text) > 500 else evidence_text,
        "research_summary": st.session_state.summary or "",
        "summary_source": st.session_state.summary_source or "",
        "outreach_draft": st.session_state.get("outreach_draft", ""),
        "draft_approved": st.session_state.get("draft_approved", False),
    }
    st.session_state.prospects.append(new_prospect)
    st.success("Added to prospect list!")

# Display prospect table
if st.session_state.prospects:
    df_prospects = pd.DataFrame(st.session_state.prospects)

    # Format for display
    display_cols = [
        "business_name", "website_url", "industry", "total_score", "category",
        "outreach_draft"
    ]

    st.dataframe(
        df_prospects[display_cols],
        hide_index=True,
        use_container_width=True,
        column_config={
            "outreach_draft": st.column_config.TextColumn(width=300)
        }
    )

    # CSV download
    csv = df_prospects.to_csv(index=False, quotechar='"')
    st.download_button(
        label="📥 Download CSV",
        data=csv,
        file_name="prospects.csv",
        mime="text/csv"
    )
else:
    st.info("No prospects yet. Research a business and add it to get started.")

# ---------------------------------------------------------------------------
# Footer
# ---------------------------------------------------------------------------

st.markdown("---")
st.caption(
    "GTM Research Copilot — Demo application. "
    "Uses Groq API only for research summary generation."
)
