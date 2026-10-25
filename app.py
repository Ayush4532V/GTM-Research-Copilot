"""
app.py — Streamlit dashboard for the GTM Research Copilot.

Tabs:
  1. Dashboard  — funnel metrics, lead table, detail view, pipeline controls
  2. Manual Research — single-business lookup (preserving the original flow)
  3. Discovery  — run the discovery pipeline and review results

The app reads/writes from SQLite (DB), NOT session_state. Lead data
persists across restarts.
"""

import pandas as pd
import streamlit as st

from db import (
    get_conn, upsert_lead, get_lead, query_leads, count_by_status,
    is_suppressed, add_to_suppression,
)
from config import FIT_SCORE_THRESHOLD


def _get_db_path() -> str:
    try:
        return st.secrets.get("DB_PATH", "leads.db")
    except Exception:
        return "leads.db"


def _normalize_url(url: str) -> str:
    if not url:
        return ""
    if not url.startswith(("http://", "https://")):
        url = "https://" + url
    if url.endswith("/") and url.count("/") > 2:
        url = url.rstrip("/")
    return url


def _status_color(status: str) -> str:
    colors = {
        "new": "gray",
        "qualified": "blue",
        "enriched": "orange",
        "drafted": "purple",
        "draft_created": "green",
        "sent": "teal",
        "replied": "#ff6b6b",
        "rejected": "#ff0000",
        "skipped": "gray",
    }
    return colors.get(status, "gray")


st.set_page_config(
    page_title="GTM Research Copilot",
    page_icon="🔍",
    layout="wide",
)

st.title("🔍 GTM Research Copilot")
st.caption(
    "AI-assisted prospect research for GTM engineers. "
    "Demo by Ayush for Hyperleap AI."
)

tab_dashboard, tab_manual, tab_discovery = st.tabs(
    ["📊 Dashboard", "🔬 Manual Research", "🔍 Discovery"]
)


def show_funnel(conn):
    st.subheader("📈 Funnel Metrics")
    status_counts = count_by_status(conn)
    funnel_stages = [
        ("new", "New (Discovered)"),
        ("qualified", "Qualified"),
        ("enriched", "Enriched"),
        ("drafted", "Drafted"),
        ("draft_created", "Gmail Draft"),
        ("sent", "Sent"),
        ("replied", "Replied"),
        ("rejected", "Rejected"),
        ("skipped", "Skipped"),
    ]
    cols = st.columns(len(funnel_stages))
    for i, (status, label) in enumerate(funnel_stages):
        count = status_counts.get(status, 0)
        color = _status_color(status)
        with cols[i]:
            st.markdown(
                f"<div style='text-align:center'>"
                f"<span style='color:{color};font-size:28px'>{count}</span>"
                f"<br/><small>{label}</small>"
                f"</div>",
                unsafe_allow_html=True,
            )
    st.markdown("---")


def show_pipeline_controls(conn, db_path):
    st.subheader("🚀 Pipeline Controls")
    btn_cols = st.columns(6)

    with btn_cols[0]:
        if st.button("🔍 Run Discovery", use_container_width=True):
            with st.spinner("Running discovery..."):
                from discover import discover_leads
                leads = discover_leads(db_path=db_path)
                st.success(f"Discovered {len(leads)} new leads")
                st.rerun()

    with btn_cols[1]:
        if st.button("🌐 Deep Research", use_container_width=True):
            with st.spinner("Researching websites..."):
                from research import extract_website_info
                new_leads = query_leads(conn, filters={"status": "new"})
                for lead in new_leads:
                    result = extract_website_info(lead["website"])
                    if result["success"]:
                        upsert_lead(conn, domain=lead["domain"],
                                    posting_text=result.get("content", ""),
                                    company_context=result.get("content", ""))
                st.success("Research complete!")
                st.rerun()

    with btn_cols[2]:
        if st.button("🎯 Qualify Leads", use_container_width=True):
            with st.spinner("Qualifying..."):
                from qualify import qualify_lead
                leads = query_leads(conn, filters={"status": "new"})
                qualified = 0
                for lead in leads:
                    result = qualify_lead(
                        conn,
                        domain=lead["domain"],
                        business_name=lead["company"],
                        industry=lead.get("industry", "other"),
                        website_title=lead.get("description", ""),
                        website_description=lead.get("description", ""),
                        extracted_text=lead.get("posting_text", ""),
                    )
                    if result.get("is_qualified"):
                        qualified += 1
                st.success(f"Qualified {qualified} leads (threshold: {FIT_SCORE_THRESHOLD})")
                st.rerun()

    with btn_cols[3]:
        if st.button("📧 Enrich Emails", use_container_width=True):
            with st.spinner("Enriching emails..."):
                from enrich_email import enrich_lead
                leads = query_leads(conn, filters={"status": "qualified"})
                enriched = 0
                for lead in leads:
                    result = enrich_lead(
                        domain=lead["domain"],
                        company_name=lead["company"],
                        website_emails=[],
                    )
                    if result.get("email"):
                        enriched += 1
                st.success(f"Enriched {enriched} leads")
                st.rerun()

    with btn_cols[4]:
        if st.button("✍️ Draft Outreach", use_container_width=True):
            with st.spinner("Drafting outreach..."):
                from draft_email import draft_lead
                leads = query_leads(conn, filters={"status": "enriched"})
                drafted = 0
                for lead in leads:
                    result = draft_lead(
                        domain=lead["domain"],
                        company_name=lead["company"],
                        industry=lead.get("industry", "other"),
                        observed_signal=lead.get("posting_text", "")[:200]
                            or "their business services",
                        email=lead.get("email"),
                    )
                    if result.get("status") == "drafted":
                        drafted += 1
                st.success(f"Drafted {drafted} leads")
                st.rerun()

    with btn_cols[5]:
        if st.button("📤 Deliver (Gmail)", use_container_width=True):
            with st.spinner("Creating Gmail drafts..."):
                from send_gmail import process_drafts
                leads = query_leads(conn, filters={"status": "drafted"})
                results = process_drafts(leads, auto_send=False)
                ok_count = sum(1 for r in results if r.get("ok"))
                st.success(f"Processed {ok_count} Gmail drafts")
                st.rerun()


def show_lead_table(db_path):
    st.subheader("📋 Lead Table")
    conn = get_conn(db_path)
    filters = {}

    col1, col2, col3, col4 = st.columns(4)
    with col1:
        status_options = ["all", "new", "qualified", "enriched",
                          "drafted", "draft_created", "sent",
                          "replied", "rejected", "skipped"]
        filter_status = st.selectbox("Status", status_options, index=0)
    with col2:
        min_score = st.number_input(
            "Min Fit Score", min_value=0, max_value=100, value=0)
    with col3:
        search_term = st.text_input(
            "Search company/domain", placeholder="e.g., Dental")
    with col4:
        if st.button("🔄 Refresh"):
            st.rerun()

    if filter_status != "all":
        filters["status"] = filter_status
    if min_score > 0:
        filters["min_fit_score"] = min_score
    if search_term:
        filters["search"] = search_term

    leads = query_leads(conn, filters=filters,
                        order_by="created_at DESC", limit=100)
    conn.close()

    if leads:
        df = pd.DataFrame(leads)
        display_cols = [
            "company", "domain", "industry", "fit_score_final",
            "fit_score_rule", "email", "email_confidence", "status",
        ]
        available_cols = [c for c in display_cols if c in df.columns]
        display_df = df[available_cols].copy()
        if "fit_score_final" in display_df.columns:
            display_df["fit_score_final"] = display_df["fit_score_final"].fillna("-")
        if "fit_score_rule" in display_df.columns:
            display_df["fit_score_rule"] = display_df["fit_score_rule"].fillna("-")

        st.dataframe(
            display_df,
            hide_index=True,
            use_container_width=True,
            column_config={
                "fit_score_final": st.column_config.NumberColumn(
                    "Final Score", min_value=0, max_value=100),
                "fit_score_rule": st.column_config.NumberColumn(
                    "Rule Score", min_value=0, max_value=100),
                "email_confidence": st.column_config.TextColumn(),
                "status": st.column_config.TextColumn(),
            },
            key="lead_table",
        )

        # --- Lead detail view ---
        if "selected_lead_id" not in st.session_state:
            st.session_state.selected_lead_id = None

        # Row selector
        st.markdown("### Lead Detail View")
        lead_options = {f"{l['company']} ({l['domain']})": l["id"] for l in leads}
        selected_label = st.selectbox(
            "Select a lead to view details",
            options=list(lead_options.keys()),
            index=None,
            placeholder="Choose a lead..."
        )
        if selected_label:
            st.session_state.selected_lead_id = lead_options[selected_label]

        if st.session_state.selected_lead_id:
            conn2 = get_conn(db_path)
            lead = get_lead(conn2, st.session_state.selected_lead_id)
            conn2.close()
            if lead:
                st.markdown("---")
                st.subheader(f"🔍 Lead Detail: {lead['company']}")
                col1, col2 = st.columns(2)
                with col1:
                    st.write(f"**Company:** {lead.get('company', '')}")
                    st.write(f"**Domain:** {lead.get('domain', '')}")
                    st.write(f"**Website:** {lead.get('website', '')}")
                    st.write(f"**Industry:** {lead.get('industry', '')}")
                    st.write(f"**Source:** {lead.get('source', '')}")
                    st.write(f"**Status:** {lead.get('status', '')}")
                with col2:
                    st.write(f"**Rule Score:** {lead.get('fit_score_rule', '')}")
                    st.write(f"**LLM Score:** {lead.get('fit_score_llm', '')}")
                    st.write(f"**Final Score:** {lead.get('fit_score_final', '')}")
                    st.write(f"**Email:** {lead.get('email', '')}")
                    st.write(f"**Email Confidence:** {lead.get('email_confidence', '')}")
                    st.write(f"**LinkedIn:** {lead.get('linkedin_url', '')}")

                if lead.get("fit_reason"):
                    st.info(lead["fit_reason"])

                if lead.get("draft_email_body"):
                    st.subheader("📧 Outreach Draft")
                    draft_val = st.text_area(
                        "Draft email",
                        value=lead["draft_email_body"],
                        height=150,
                        key=f"draft_{lead['id']}",
                    )
                    if st.button("💾 Save Draft", key=f"save_draft_{lead['id']}"):
                        conn3 = get_conn(db_path)
                        upsert_lead(conn3, domain=lead["domain"],
                                    draft_email_body=draft_val)
                        conn3.close()
                        st.success("Draft saved")

                    col_approve, col_suppress = st.columns(2)
                    with col_approve:
                        if st.button(
                            "✅ Approve & Create Draft",
                            key=f"approve_{lead['id']}"
                        ):
                            from send_gmail import process_drafts
                            results = process_drafts([lead], auto_send=False)
                            conn4 = get_conn(db_path)
                            for r in results:
                                if r.get("draft_id"):
                                    upsert_lead(conn4, domain=lead["domain"],
                                               gmail_draft_id=r["draft_id"],
                                               status="draft_created")
                            conn4.close()
                            st.success(f"Gmail draft created")
                            st.rerun()
                    with col_suppress:
                        if st.button("🚫 Suppress Lead",
                                     key=f"suppress_{lead['id']}"):
                            conn5 = get_conn(db_path)
                            add_to_suppression(conn5, lead["domain"],
                                               "Manually suppressed")
                            upsert_lead(conn5, domain=lead["domain"],
                                        status="rejected")
                            conn5.close()
                            st.session_state.selected_lead_id = None
                            st.success("Lead suppressed")
                            st.rerun()

        st.markdown("---")
        if st.button("📥 Download All Leads CSV", key="export_all"):
            conn6 = get_conn(db_path)
            all_leads = query_leads(conn6, limit=500)
            conn6.close()
            df_export = pd.DataFrame(all_leads)
            csv = df_export.to_csv(index=False, quotechar='"')
            st.download_button(
                label="Confirm Download",
                data=csv,
                file_name="all_leads.csv",
                mime="text/csv",
                key="download_csv",
            )
    else:
        st.info("No leads found. Run Discovery to get started.")


def show_manual_research(db_path):
    st.header("🔬 Manual Research")
    st.write("Enter a single business to research manually.")

    from config import target_industries

    col1, col2 = st.columns(2)
    with col1:
        business_name = st.text_input(
            "Business name", placeholder="e.g. Sunset Dental Clinic")
    with col2:
        website_url = st.text_input(
            "Website URL", placeholder="https://example.com")

    industry_options = list(target_industries.keys())
    selected_industry = st.selectbox(
        "Select industry", options=industry_options, index=0)

    manual_description = st.text_area(
        "Manual business description (optional)",
        placeholder="Add any details you know..."
    )

    if st.button("🔬 Research Business", type="primary"):
        if not business_name or not website_url:
            st.warning("Please enter business name and website URL.")
        else:
            with st.spinner("Extracting website information..."):
                from research import extract_website_info
                web_result = extract_website_info(website_url)

            evidence_parts = []
            if web_result["success"]:
                evidence_parts.append(f"Title: {web_result['title']}")
                evidence_parts.append(f"Description: {web_result['description']}")
                evidence_parts.append(f"Content: {web_result['content'][:1500]}")
            if manual_description.strip():
                evidence_parts.append(f"Manual: {manual_description}")
            evidence_text = " ".join(evidence_parts)

            with st.spinner("Calculating fit score..."):
                from scoring import score_prospect, get_criteria_labels
                icp_result = score_prospect(
                    selected_industry, evidence_text,
                    web_result.get("content", "")
                )

            domain = urlparse_domain(_normalize_url(website_url))

            conn = get_conn(db_path)
            lead_id = upsert_lead(
                conn,
                domain=domain,
                company=business_name,
                website=website_url,
                industry=selected_industry,
                description=web_result.get("description", ""),
                posting_text=web_result.get("content", ""),
                company_context=web_result.get("content", ""),
                fit_score_rule=icp_result["total"],
                fit_score_final=icp_result["total"],
                fit_reason=icp_result["category"],
                source="manual_research",
                status="new",
            )
            conn.close()

            st.success(f"Research complete! Lead #{lead_id} added to database.")

            with st.expander("Show Results", expanded=True):
                st.subheader("Website Findings")
                if web_result["success"]:
                    st.write(f"**Title:** {web_result['title']}")
                    st.write(f"**Description:** {web_result['description']}")
                    if web_result.get("emails"):
                        st.write(f"**Emails found:** {web_result['emails']}")
                    if web_result.get("phones"):
                        st.write(f"**Phones found:** {web_result['phones']}")
                    if web_result.get("linkedin_urls"):
                        st.write(f"**LinkedIn URLs:** {web_result['linkedin_urls']}")
                    if web_result.get("booking_signals"):
                        st.write(f"**Booking signals:** {web_result['booking_signals']}")
                    st.markdown(f"**Content:** {web_result['content'][:500]}...")
                else:
                    st.info(f"Extraction failed: {web_result.get('error')}")

                st.subheader("ICP Scoring")
                col_a, col_b = st.columns(2)
                with col_a:
                    st.metric("ICP Score", icp_result["total"], delta="out of 100")
                with col_b:
                    st.write(f"**Category:** {icp_result['category']}")
                for criterion_key in ["industry_fit", "enquiry_complexity",
                                       "booking_fit", "automation_opportunity"]:
                    details = icp_result["scores"].get(
                        criterion_key, (0, "N/A", [], "missing"))
                    with st.expander(
                        f"{get_criteria_labels().get(criterion_key, criterion_key)}"):
                        st.markdown(f"**Score:** {details[0]} points")
                        st.markdown(f"**Explanation:** {details[1]}")
                        st.markdown(
                            f"**Evidence:** {'; '.join(details[2]) if details[2] else 'N/A'}")


def show_discovery(db_path):
    st.header("🔍 Discovery Pipeline")
    st.write("Run the discovery engine to find new leads from search engines.")

    max_actions = st.number_input(
        "Max leads to add", min_value=1, max_value=100, value=10)
    max_queries = st.number_input(
        "Max queries to run", min_value=1, max_value=50, value=15)

    if st.button("🚀 Run Discovery", type="primary"):
        with st.spinner(f"Searching up to {max_queries} queries..."):
            from discover import discover_leads
            leads = discover_leads(
                db_path=db_path,
                max_actions=max_actions,
                max_queries=max_queries,
            )
        st.success(f"Discovered {len(leads)} new leads!")
        if leads:
            st.dataframe(
                pd.DataFrame(leads)[["company", "domain", "source"]],
                hide_index=True,
                use_container_width=True,
            )
        st.rerun()


def urlparse_domain(url):
    from urllib.parse import urlparse
    parsed = urlparse(url)
    host = parsed.netloc.lower()
    if host.startswith("www."):
        host = host[4:]
    return host


def get_criteria_labels():
    return {
        "industry_fit": "Industry fit (max 30)",
        "enquiry_complexity": "Enquiry complexity (max 25)",
        "booking_fit": "Booking / lead-qualification fit (max 25)",
        "automation_opportunity": "Potential automation opportunity (max 20)",
    }


# ---------------- Main UI ----------------

db_path = _get_db_path()

with tab_dashboard:
    conn = get_conn(db_path)
    show_funnel(conn)
    show_pipeline_controls(conn, db_path)
    show_lead_table(db_path)
    conn.close()

with tab_manual:
    show_manual_research(db_path)

with tab_discovery:
    show_discovery(db_path)

# Footer
st.markdown("---")
st.caption(
    "GTM Research Copilot — Persistent via SQLite. "
    "Uses Groq API only for research summaries and fit scoring."
)