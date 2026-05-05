#!/usr/bin/env python3
"""
Actuarial Life/Health News Crawler

What it does:
- Pulls public RSS feeds and Google News RSS keyword feeds.
- Classifies each item into Life / Health / Regulation / Career.
- Adds an actuarial "why it matters" note.
- Outputs dashboard-ready data.json.

Run:
    pip install -r requirements.txt
    python crawler.py

Then open:
    python -m http.server 8000
    http://localhost:8000

Optional:
- Schedule with Windows Task Scheduler or cron every morning.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass, asdict
from datetime import datetime, timezone, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

import feedparser
from bs4 import BeautifulSoup
import requests
import os
from urllib.parse import urlencode

OUTPUT_FILE = Path(__file__).with_name("data.json")
MAX_ITEMS = 80
DAYS_BACK = 7
TIMEOUT_SECONDS = 20

# Stable public RSS / feed sources.
# Google News RSS is used for market topics because many official sites do not provide clean RSS for every page.
GOOGLE_NEWS_QUERIES = [
    # Life insurance actuarial / regulatory
    "life insurance actuarial valuation annuity reserves NAIC",
    "life insurance reinsurance asset adequacy actuarial guideline NAIC",
    "annuity illustration life insurance actuary NAIC",
    "mortality longevity life insurance actuarial",

    # Health insurance actuarial / regulatory
    "health insurance actuarial rate filing medical cost trend",
    "health insurance claims trend actuary Medicare Advantage",
    "ACA premium rate review actuarial health insurance",
    "risk adjustment health insurance actuarial",

    # Professional actuarial / market
    "Society of Actuaries health insurance actuarial",
    "American Academy of Actuaries health insurance actuarial",
    "American Academy of Actuaries life insurance actuarial",
    "actuarial analyst life insurance health insurance SQL Python",
]

RSS_FEEDS = [
    {
        "name": "SOA Newsroom",
        "url": "https://www.soa.org/resources/newsroom/default/",
        "category_hint": "Career",
        "type": "html"
    },
    {
        "name": "SOA Podcasts RSS",
        "url": "https://soapodcasts.libsyn.com/rssfeed",
        "category_hint": "Career",
        "type": "rss"
    },
    {
        "name": "The Actuary Magazine",
        "url": "https://www.theactuarymagazine.org/feed/",
        "category_hint": "Career",
        "type": "rss"
    },
]

CURATED_SOURCES = [
    {
        "name": "NAIC Life Actuarial Task Force",
        "category": "Life",
        "use": "Life valuation, annuity assumptions, reinsurance, asset adequacy, complex assets, and regulatory development.",
        "url": "https://content.naic.org/committees/a/life-actuarial-tf",
    },
    {
        "name": "NAIC Health Actuarial Task Force",
        "category": "Health",
        "use": "Health actuarial regulation, rate review, claims trend, Medicare/Medicaid, and risk adjustment issues.",
        "url": "https://content.naic.org/committees/b/health-actuarial-tf",
    },
    {
        "name": "American Academy of Actuaries Newsroom",
        "category": "Regulation",
        "use": "Policy-facing actuarial updates, public statements, and practice-area commentary.",
        "url": "https://actuary.org/newsroom/",
    },
    {
        "name": "American Academy of Actuaries - Health",
        "category": "Health",
        "use": "Health practice notes, issue briefs, and health insurance policy topics.",
        "url": "https://actuary.org/practice-area/health/",
    },
    {
        "name": "American Academy of Actuaries - Life",
        "category": "Life",
        "use": "Life insurance, annuity, longevity, valuation, and policy topics.",
        "url": "https://actuary.org/practice-area/life/",
    },
    {
        "name": "SOA Health Section",
        "category": "Health",
        "use": "Health actuarial articles, newsletters, terminology, and applied practice discussion.",
        "url": "https://www.soa.org/sections/health/",
    },
    {
        "name": "SOA Newsroom",
        "category": "Career",
        "use": "SOA research, profession updates, and actuarial industry announcements.",
        "url": "https://www.soa.org/resources/newsroom/default/",
    },
    {
        "name": "The Actuary Magazine",
        "category": "Career",
        "use": "General actuarial profession articles, technology, emerging risks, and practice trends.",
        "url": "https://www.theactuarymagazine.org/",
    },
    {
        "name": "ActuaryList",
        "category": "Career",
        "use": "Actuarial job postings and skill keyword scanning.",
        "url": "https://www.actuarylist.com/",
    },
]

JOB_LINKS = [
    {
        "role": "Actuarial Analyst - Health",
        "market": "Health",
        "searchUrl": "https://www.google.com/search?q=actuarial+analyst+health+insurance+SQL+Python+claims+rate+filing",
        "keywords": ["Excel", "SQL", "Python/R", "Claims Data", "Medical Cost Trend", "Rate Filing", "Power BI"],
        "whatToWatch": "Prioritize postings mentioning claims trend, pricing, rate filing, risk adjustment, ACA, Medicare Advantage, Medicaid, SQL, and dashboarding.",
    },
    {
        "role": "Actuarial Analyst - Life",
        "market": "Life",
        "searchUrl": "https://www.google.com/search?q=actuarial+analyst+life+insurance+valuation+reserves+annuity+Python+SQL",
        "keywords": ["Excel", "Python", "SQL", "Valuation", "Reserves", "Annuities", "Assumption Analysis", "Model Documentation"],
        "whatToWatch": "Prioritize postings mentioning valuation, reserves, annuities, asset adequacy, reinsurance, mortality, assumption governance, and model validation.",
    },
    {
        "role": "Actuarial Data Analyst",
        "market": "Career",
        "searchUrl": "https://www.google.com/search?q=actuarial+data+analyst+insurance+SQL+Python+Power+BI",
        "keywords": ["SQL", "Python", "ETL", "Data Validation", "Power BI", "Insurance Metrics", "Automation"],
        "whatToWatch": "This is likely the easiest transition title for a Python/SQL/data-science profile. Watch for insurance data, reporting automation, and model support tasks.",
    },
    {
        "role": "Pricing / Reserving Analyst",
        "market": "Career",
        "searchUrl": "https://www.google.com/search?q=pricing+reserving+analyst+actuarial+life+health+insurance",
        "keywords": ["Pricing", "Reserving", "Trend Analysis", "Scenario Testing", "Documentation", "Excel Modeling"],
        "whatToWatch": "Watch how job posts describe pricing support, reserve movement, loss ratio, experience study, and management reporting.",
    },
]

LIFE_TERMS = [
    "life insurance", "annuity", "annuities", "mortality", "longevity", "valuation",
    "reserve", "reserves", "asset adequacy", "reinsurance", "indexed universal life",
    "variable annuity", "principle-based reserving", "pbr", "vm-20", "vm-21"
]
HEALTH_TERMS = [
    "health insurance", "medical cost", "claims", "claim", "aca", "medicare", "medicaid",
    "risk adjustment", "rate filing", "premium rate", "utilization", "provider", "pharmacy",
    "ma ", "medicare advantage", "under-65", "hix", "exchange"
]
REG_TERMS = [
    "naic", "regulation", "regulatory", "actuarial standard", "asop", "valuation manual",
    "task force", "academy", "public policy", "rate review", "filing", "guideline"
]
CAREER_TERMS = [
    "actuarial analyst", "actuary", "society of actuaries", "soa", "job", "career",
    "fsa", "asa", "skills", "ai", "modeling", "python", "sql", "power bi"
]


def parse_feed_date(entry) -> datetime | None:
    """Return timezone-aware published/updated datetime, or None if unavailable."""
    # feedparser structured date
    for attr in ("published_parsed", "updated_parsed"):
        value = getattr(entry, attr, None)
        if value:
            try:
                return datetime(*value[:6], tzinfo=timezone.utc)
            except Exception:
                pass

    # raw RFC date string
    for attr in ("published", "updated", "created"):
        value = getattr(entry, attr, None)
        if value:
            try:
                dt = parsedate_to_datetime(value)
                if dt.tzinfo is None:
                    dt = dt.replace(tzinfo=timezone.utc)
                return dt.astimezone(timezone.utc)
            except Exception:
                pass

    return None


def is_recent(dt: datetime | None, days_back: int = DAYS_BACK) -> bool:
    """Keep only items with a reliable publish/update date within the last N days."""
    if dt is None:
        return False
    cutoff = datetime.now(timezone.utc) - timedelta(days=days_back)
    return dt.astimezone(timezone.utc) >= cutoff

@dataclass
class NewsItem:
    title: str
    source: str
    category: str
    priority: str
    published: str
    summary: str
    whyItMatters: str
    url: str

def normalize_text(text: str) -> str:
    return re.sub(r"\s+", " ", BeautifulSoup(text or "", "html.parser").get_text(" ")).strip()

def classify(title: str, summary: str, source: str = "") -> tuple[str, str, str]:
    text = f"{title} {summary} {source}".lower()

    scores = {
        "Life": sum(1 for t in LIFE_TERMS if t in text),
        "Health": sum(1 for t in HEALTH_TERMS if t in text),
        "Regulation": sum(1 for t in REG_TERMS if t in text),
        "Career": sum(1 for t in CAREER_TERMS if t in text),
    }

    # Prefer more specific insurance categories over generic regulation/career.
    if scores["Life"] >= scores["Health"] and scores["Life"] > 0:
        category = "Life"
    elif scores["Health"] > 0:
        category = "Health"
    elif scores["Regulation"] > 0:
        category = "Regulation"
    elif scores["Career"] > 0:
        category = "Career"
    else:
        category = "Career"

    high_words = ["naic", "rate filing", "valuation", "reserve", "reserves", "reinsurance",
                  "medicare", "medicaid", "aca", "risk adjustment", "medical cost trend",
                  "actuarial guideline", "asop", "valuation manual"]
    medium_words = ["soa", "academy", "actuary", "annuity", "mortality", "claims", "pricing"]

    priority = "High" if any(w in text for w in high_words) else ("Medium" if any(w in text for w in medium_words) else "Low")

    why = why_it_matters(category, text)
    return category, priority, why

def why_it_matters(category: str, text: str) -> str:
    if category == "Life":
        if "reinsurance" in text:
            return "Relevant to life valuation, asset adequacy testing, capital, reserve risk, and reinsurance governance."
        if "annuity" in text or "annuities" in text:
            return "Relevant to annuity pricing, illustration assumptions, policyholder behavior, reserves, and product risk."
        if "mortality" in text or "longevity" in text:
            return "Relevant to mortality/longevity assumptions, experience studies, pricing, and reserves."
        return "Relevant to life valuation, reserves, product pricing, assumption setting, and regulatory reporting."
    if category == "Health":
        if "risk adjustment" in text:
            return "Relevant to health risk adjustment, pricing accuracy, premium adequacy, and plan performance measurement."
        if "medicare" in text or "medicaid" in text:
            return "Relevant to government health programs, bid/pricing assumptions, utilization, and reimbursement risk."
        if "medical cost" in text or "claims" in text:
            return "Relevant to claims trend, pricing, reserving, loss ratio analysis, and forecast assumptions."
        return "Relevant to health pricing, claims trend, rate filing, reserving, and utilization monitoring."
    if category == "Regulation":
        return "Relevant to regulatory awareness, actuarial standards, compliance, model governance, and professional judgment."
    return "Relevant to actuarial career awareness, market terminology, analytics skills, and interview talking points."

def google_news_feed(query: str) -> str:
    return "https://news.google.com/rss/search?q=" + quote_plus(query) + "&hl=en-US&gl=US&ceid=US:en"

def parse_rss(url: str, source_name: str) -> list[NewsItem]:
    items: list[NewsItem] = []
    parsed = feedparser.parse(url)
    for entry in parsed.entries[:15]:
        title = normalize_text(getattr(entry, "title", ""))
        summary = normalize_text(getattr(entry, "summary", ""))
        link = getattr(entry, "link", "")
        published_dt = parse_feed_date(entry)
        if not is_recent(published_dt):
            continue

        published = published_dt.astimezone().strftime("%Y-%m-%d %H:%M")
        if not title or not link:
            continue
        category, priority, why = classify(title, summary, source_name)
        items.append(NewsItem(
            title=title,
            source=source_name,
            category=category,
            priority=priority,
            published=published,
            summary=summary[:420] if summary else "Click through to read the full update.",
            whyItMatters=why,
            url=link,
        ))
    return items

def parse_simple_html(url: str, source_name: str, category_hint: str = "Career") -> list[NewsItem]:
    """HTML pages usually do not expose reliable publish dates, so skip them for strict 2-day filtering."""
    return []

def dedupe(items: Iterable[NewsItem]) -> list[NewsItem]:
    unique = {}
    for item in items:
        key = re.sub(r"\W+", "", item.title.lower())[:90]
        if key not in unique:
            unique[key] = item
    return list(unique.values())

def sort_items(items: list[NewsItem]) -> list[NewsItem]:
    priority_rank = {"High": 0, "Medium": 1, "Low": 2}
    category_rank = {"Life": 0, "Health": 1, "Regulation": 2, "Career": 3}
    return sorted(items, key=lambda x: (priority_rank.get(x.priority, 9), category_rank.get(x.category, 9), x.title.lower()))

# -----------------------------
# Job opening crawler
# -----------------------------
# This uses Adzuna if you provide GitHub Secrets:
# ADZUNA_APP_ID and ADZUNA_APP_KEY.
#
# Why Adzuna:
# - It aggregates listings from many job sites.
# - It has a documented job-search API.
# - It avoids brittle scraping of Indeed/LinkedIn, which often block bots.
#
# Limitation:
# No job source can guarantee "all jobs in the U.S." without multiple licensed APIs.
# This crawler collects broad U.S. actuarial openings available through configured APIs
# and filters for likely <=3 years experience.

JOB_SEARCH_QUERIES = [
    "actuarial analyst",
    "entry level actuarial analyst",
    "actuarial data analyst",
    "health actuarial analyst",
    "life actuarial analyst",
    "pricing actuarial analyst",
    "reserving actuarial analyst",
    "actuarial associate analyst",
    "actuarial assistant",
    "actuarial consultant analyst",
]

SENIOR_EXCLUDE_TERMS = [
    "senior", "sr.", "sr ", "manager", "director", "vp", "vice president",
    "principal", "lead", "head of", "chief", "fellow", "fsa", "fcas",
    "credentialed actuary", "consulting actuary", "staff actuary", "valuation actuary",
    "senior associate", "experienced actuary"
]

EARLY_CAREER_INCLUDE_TERMS = [
    "entry level", "entry-level", "junior", "analyst", "assistant", "associate analyst",
    "0-1", "0-2", "0-3", "1-2", "1-3", "2-3", "new grad", "recent graduate",
    "early career", "student program", "development program"
]

THREE_YEAR_PATTERNS = [
    r"0\s*[-–to]+\s*1\s+years?",
    r"0\s*[-–to]+\s*2\s+years?",
    r"0\s*[-–to]+\s*3\s+years?",
    r"1\s*[-–to]+\s*2\s+years?",
    r"1\s*[-–to]+\s*3\s+years?",
    r"2\s*[-–to]+\s*3\s+years?",
    r"up to\s*3\s+years?",
    r"less than\s*3\s+years?",
    r"fewer than\s*3\s+years?",
    r"under\s*3\s+years?",
    r"no more than\s*3\s+years?",
    r"minimum of\s*0\s*[-–to]+\s*3\s+years?",
    r"\b0\+?\s+years?",
    r"\b1\+?\s+years?",
    r"\b2\+?\s+years?",
    r"\b3\+?\s+years?",
]

OVER_THREE_PATTERNS = [
    r"\b4\+?\s+years?",
    r"\b5\+?\s+years?",
    r"\b6\+?\s+years?",
    r"\b7\+?\s+years?",
    r"\b8\+?\s+years?",
    r"\b9\+?\s+years?",
    r"\b10\+?\s+years?",
    r"minimum of\s*[4-9]\s+years?",
    r"at least\s*[4-9]\s+years?",
    r"[4-9]\s*[-–to]+\s*\d+\s+years?",
]

def classify_job_market(text: str) -> str:
    t = text.lower()
    if any(x in t for x in ["health", "medical", "medicare", "medicaid", "aca", "claims", "provider"]):
        return "Health"
    if any(x in t for x in ["life", "annuity", "annuities", "mortality", "valuation", "reinsurance", "reserves"]):
        return "Life"
    if any(x in t for x in ["pricing", "reserving", "reserve"]):
        return "Pricing/Reserving"
    return "Actuarial"

def infer_experience_fit(title: str, description: str) -> tuple[bool, str]:
    text = f"{title} {description}".lower()

    if any(term in text for term in SENIOR_EXCLUDE_TERMS):
        return False, "Excluded: senior/manager/fellow-level wording"

    for pattern in OVER_THREE_PATTERNS:
        if re.search(pattern, text):
            return False, "Excluded: appears to require more than 3 years"

    for pattern in THREE_YEAR_PATTERNS:
        if re.search(pattern, text):
            return True, "Likely <=3 years based on description"

    if any(term in text for term in EARLY_CAREER_INCLUDE_TERMS):
        return True, "Likely early-career based on title/keywords"

    # Keep analyst roles because many actuarial analyst jobs do not state exact years.
    if "actuarial analyst" in text or "analyst, actuarial" in text:
        return True, "Likely early-career analyst role; verify experience in posting"

    return False, "Excluded: not clearly <=3 years"

def extract_skills(text: str) -> list[str]:
    skill_terms = [
        "Excel", "SQL", "Python", "R", "Power BI", "Tableau", "SAS", "VBA",
        "Access", "Prophet", "Moody", "AXIS", "MG-ALFA", "ResQ",
        "Claims", "Pricing", "Reserving", "Valuation", "Rate Filing",
        "Medicare", "Medicaid", "ACA", "Risk Adjustment", "Reinsurance",
        "Annuity", "Mortality", "Experience Study", "Data Validation"
    ]
    lower = text.lower()
    found = []
    for s in skill_terms:
        if s.lower() in lower:
            found.append(s)
    return found[:10]

def parse_adzuna_date(created: str) -> tuple[str, int | None]:
    if not created:
        return "", None
    try:
        dt = datetime.fromisoformat(created.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        age = (datetime.now(timezone.utc) - dt.astimezone(timezone.utc)).days
        return dt.astimezone().strftime("%Y-%m-%d"), max(age, 0)
    except Exception:
        return created[:10], None

def fetch_adzuna_jobs(max_days_old: int = 14, max_pages: int = 4) -> list[dict]:
    app_id = os.getenv("ADZUNA_APP_ID", "").strip()
    app_key = os.getenv("ADZUNA_APP_KEY", "").strip()

    if not app_id or not app_key:
        return [{
            "source": "Setup required",
            "role": "Adzuna API is not configured",
            "company": "",
            "location": "United States",
            "market": "Actuarial",
            "posted": "",
            "postedAgeDays": 999,
            "experienceFit": "Add ADZUNA_APP_ID and ADZUNA_APP_KEY in GitHub Actions Secrets to fetch real job openings.",
            "skills": ["GitHub Secrets", "Adzuna API"],
            "summary": "The dashboard is ready, but real job openings require an API key. After secrets are added, GitHub Actions will fetch U.S. actuarial jobs daily.",
            "url": "https://developer.adzuna.com/"
        }]

    collected = []
    seen = set()

    for query in JOB_SEARCH_QUERIES:
        for page in range(1, max_pages + 1):
            params = {
                "app_id": app_id,
                "app_key": app_key,
                "what": query,
                "where": "United States",
                "content-type": "application/json",
                "results_per_page": 50,
                "max_days_old": max_days_old,
                "sort_by": "date",
            }
            url = f"https://api.adzuna.com/v1/api/jobs/us/search/{page}?" + urlencode(params)

            try:
                response = requests.get(url, timeout=TIMEOUT_SECONDS)
                if response.status_code != 200:
                    continue
                payload = response.json()
            except Exception:
                continue

            for job in payload.get("results", []):
                title = normalize_text(job.get("title", ""))
                description = normalize_text(job.get("description", ""))
                redirect_url = job.get("redirect_url", "")
                company = (job.get("company") or {}).get("display_name", "")
                location = (job.get("location") or {}).get("display_name", "United States")
                posted, age_days = parse_adzuna_date(job.get("created", ""))

                if not title or not redirect_url:
                    continue
                if age_days is not None and age_days > max_days_old:
                    continue

                key = redirect_url or f"{company}-{title}-{location}"
                if key in seen:
                    continue

                keep, fit_reason = infer_experience_fit(title, description)
                if not keep:
                    continue

                combined = f"{title} {description}"
                market = classify_job_market(combined)
                skills = extract_skills(combined)

                collected.append({
                    "source": "Adzuna",
                    "role": title,
                    "company": company,
                    "location": location,
                    "market": market,
                    "posted": posted,
                    "postedAgeDays": age_days if age_days is not None else 999,
                    "experienceFit": fit_reason,
                    "skills": skills,
                    "summary": description[:500] if description else "Open the job posting for full details.",
                    "url": redirect_url,
                })
                seen.add(key)

    collected.sort(key=lambda j: (j.get("postedAgeDays", 999), j.get("market", ""), j.get("role", "")))
    return collected[:200]

def main() -> None:
    all_items: list[NewsItem] = []

    # Google News RSS topic feeds.
    for query in GOOGLE_NEWS_QUERIES:
        all_items.extend(parse_rss(google_news_feed(query), f"Google News: {query[:42]}"))

    # Specific RSS/HTML sources.
    for source in RSS_FEEDS:
        if source.get("type") == "rss":
            all_items.extend(parse_rss(source["url"], source["name"]))
        else:
            all_items.extend(parse_simple_html(source["url"], source["name"], source.get("category_hint", "Career")))

    deduped = sort_items(dedupe(all_items))

    # Balanced selection so Health news does not crowd out Life / Regulation / Career.
    balanced_items = []
    category_limits = {
        "Life": 20,
        "Health": 20,
        "Regulation": 20,
        "Career": 20,
    }

    for category, limit in category_limits.items():
        category_items = [item for item in deduped if item.category == category]
        balanced_items.extend(category_items[:limit])

    seen_urls = {item.url for item in balanced_items}
    for item in deduped:
        if item.url not in seen_urls and len(balanced_items) < MAX_ITEMS:
            balanced_items.append(item)
            seen_urls.add(item.url)

    items = balanced_items[:MAX_ITEMS]

    data = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "news": [asdict(item) for item in items],
        "jobs": fetch_adzuna_jobs(max_days_old=14),
        "jobSearchLinks": JOB_LINKS,
        "sources": CURATED_SOURCES,
    }

    OUTPUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE} with {len(items)} news items.")

if __name__ == "__main__":
    main()
