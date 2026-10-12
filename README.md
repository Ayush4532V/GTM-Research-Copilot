# GTM Research Copilot

A simple, functional AI-assisted GTM research application for demonstrating prospect research and lead qualification concepts during a GTM Engineer Intern interview with Hyperleap AI.

## Purpose

This application demonstrates how AI can assist GTM (Go-To-Market) teams with:
- Automated website research and information extraction
- Rule-based Ideal Customer Profile (ICP) scoring
- AI-generated research summaries (Groq-powered)
- Personalized outreach draft generation
- Prospect tracking and CSV export

## Architecture

```
gtm-research-copilot/
├── app.py                 # Main Streamlit application
├── research.py            # Website extraction utilities
├── scoring.py             # Rule-based ICP scoring engine
├── ai_generator.py        # Groq API integration (research summaries only)
├── requirements.txt       # Python dependencies
├── .env.example          # Environment variable template
├── .gitignore            # Git ignore rules
└── README.md             # This file
```

### Core Components

1. **Website Extraction** (`research.py`)
   - Uses `requests` and `BeautifulSoup` to fetch public website data
   - Extracts title, meta description, and visible text content
   - Handles timeouts, HTTP errors, and inaccessible sites gracefully

2. **ICP Scoring** (`scoring.py`)
   - Rule-based scoring system (0-100 points)
   - Four criteria:
     - Industry fit (max 30 points)
     - Enquiry complexity (max 25 points)
     - Booking/lead-qualification fit (max 25 points)
     - Potential automation opportunity (max 20 points)
   - Completely offline - no API calls

3. **Research Summary** (`ai_generator.py`)
   - Groq API integration for generating concise research summaries
   - **Only** function that makes LLM API calls
   - Falls back to rule-based summary if API key missing or request fails
   - Generates sections: Business overview, Observed evidence, Relevance, Use cases, Assumptions, Next steps

4. **Outreach Draft** (`app.py`)
   - Rule-based personalized message generation
   - No LLM API calls
   - Uses business name, industry, and one verified observation

5. **Prospect Tracking & Export** (`app.py`)
   - Streamlit session state for storing researched businesses
   - Prevents duplicate entries
   - CSV export with Pandas (includes all prospect data)

## Installation

1. Clone or download this repository
2. Create a virtual environment (optional but recommended):
   ```bash
   python -m venv venv
   venv\Scripts\activate  # Windows
   source venv/bin/activate  # macOS/Linux
   ```
3. Install dependencies:
   ```bash
   pip install -r requirements.txt
   ```
4. Configure environment variables:
   - Copy `.env.example` to `.env`
   - Add your Groq API key to `.env`
   - Optionally change the Groq model if needed

## Usage

Run the application:
```bash
streamlit run app.py
```

### Workflow

1. **Enter business details**:
   - Business name
   - Website URL
   - Select industry
   - Optional manual description

2. **Click "Research Business"**:
   - Extracts website information
   - Calculates ICP score (0-100)
   - Generates research summary (Groq or fallback)
   - Creates personalized outreach draft

3. **Review results**:
   - Section B: Website findings (title, description, content)
   - Section C: ICP scoring breakdown
   - Section D: Research summary (shows source)
   - Section E: Outreach draft (editable, approvable)
   - Section F: Prospect table (adds to list)

4. **Export data**:
   - Click "Download CSV" to export all researched prospects

## Scoring System Details

The ICP scoring uses transparent, observable signals only:

### Industry Fit (0-30 pts)
- Matches selected industry keywords in website content
- Bonuses for service patterns and booking signals

### Enquiry Complexity (0-25 pts)
- Keywords: quote, custom, bespoke, multiple, enterprise
- Detects multi-step or custom enquiry processes

### Booking Fit (0-25 pts)
- Keywords: book, appointment, schedule, enquiry, contact form
- Detects existing lead qualification flows

### Automation Opportunity (0-20 pts)
- Keywords: 24/7, instant, self-service, scheduling
- Identifies where AI front-desk could help

### Categories
- 70-100: High priority ✅
- 40-69: Medium priority ⚠️
- 0-39: Low priority ℹ️

## Key Design Decisions

1. **Single LLM Usage**: Only `generate_research_summary()` calls Groq
2. **Rule-Based Fallback**: Works completely offline if API missing
3. **No Fabricated Data**: Never invents lead volumes, revenue, etc.
4. **Privacy-Focused**: API keys never exposed in UI, logs, or exports
5. **Simple Dependencies**: Streamlit, Pandas, Requests, BeautifulSoup, Groq
6. **Editable & Approval Workflow**: Outreach drafts can be reviewed and marked approved

## Limitations & Future Improvements

### Current Limitations
- Only analyzes homepage content (no deep crawling)
- Simple keyword-based scoring (no NLP models)
- Groq dependency for AI summaries (fallback available)
- No authentication or user management
- Basic deduplication (by business name only)

### Potential Enhancements
- Multi-page website analysis
- More sophisticated scoring with weighted signals
- Integration with actual CRM systems
- Advanced NLP for better observation extraction
- Team collaboration features
- Scheduled research jobs

## Verification Checklist

✅ Website extraction works on accessible pages  
✅ Manual input works when extraction fails  
✅ ICP scoring works without network access  
✅ Outreach generation works without API calls  
✅ CSV export works without API calls  
✅ Research summary uses Groq when configured  
✅ Fallback summary works without API key  
✅ API errors don't crash the application  
✅ Summary not repeatedly regenerated on reruns  
✅ CSV contains all expected fields  
✅ No secrets exposed in logs, UI, or exports  

## Interview Talking Points

- **AI Role**: Augments GTM research, doesn't replace human judgment
- **Transparency**: Rule-based scoring shows exactly how decisions are made
- **Privacy**: Strict separation of LLM usage to one function only
- **Practicality**: Focuses on observable signals, not speculation
- **Efficiency**: Saves research time while maintaining data integrity
- **Flexibility**: Works offline, degrades gracefully when APIs unavailable
- **GTM Alignment**: Outputs are immediately useful for outreach and qualification

## Running the Demo

1. Set up your Groq API key in `.env`
2. Run: `streamlit run app.py`
3. Try researching a local business (dentist, lawyer, restaurant, etc.)
4. Observe how the ICP score changes with different inputs
5. Test the fallback by temporarily removing the API key
6. Export prospects to CSV and verify the data structure

---

**Note**: This is a demonstration application focused on clarity and educational value. For production use, additional error handling, logging, and security measures would be recommended.