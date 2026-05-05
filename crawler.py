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
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterable
from urllib.parse import quote_plus

import feedparser
from bs4 import BeautifulSoup
import requests

OUTPUT_FILE = Path(__file__).with_name("data.json")
MAX_ITEMS = 40
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
        published = getattr(entry, "published", "") or getattr(entry, "updated", "")
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
    """Simple fallback for pages without RSS. Conservative: extracts links with news-like titles."""
    headers = {"User-Agent": "Mozilla/5.0 actuarial-dashboard/1.0"}
    try:
        res = requests.get(url, headers=headers, timeout=TIMEOUT_SECONDS)
        res.raise_for_status()
    except Exception:
        return []

    soup = BeautifulSoup(res.text, "html.parser")
    results: list[NewsItem] = []
    seen = set()

    for a in soup.select("a[href]"):
        title = normalize_text(a.get_text(" "))
        href = a.get("href")
        if not title or len(title) < 18 or len(title) > 160:
            continue
        if href.startswith("/"):
            from urllib.parse import urljoin
            href = urljoin(url, href)
        if not href.startswith("http"):
            continue
        key = (title.lower(), href)
        if key in seen:
            continue
        seen.add(key)

        # Keep items with actuarial/insurance relevance.
        text = f"{title} {source_name}".lower()
        if not any(k in text for k in LIFE_TERMS + HEALTH_TERMS + REG_TERMS + CAREER_TERMS):
            continue

        category, priority, why = classify(title, "", source_name)
        results.append(NewsItem(
            title=title,
            source=source_name,
            category=category if category else category_hint,
            priority=priority,
            published="",
            summary="Click through to read the full update.",
            whyItMatters=why,
            url=href,
        ))
        if len(results) >= 8:
            break

    return results

def dedupe(items: Iterable[NewsItem]) -> list[NewsItem]:
    unique = {}
    for item in items:
        key = re.sub(r"\W+", "", item.title.lower())[:90]
        if key not in unique:
            unique[key] = item
    return list(unique.values())

def sort_items(items: list[NewsItem]) -> list[NewsItem]:
    priority_rank = {"High": 0, "Medium": 1, "Low": 2}
    category_rank = {"Health": 0, "Life": 1, "Regulation": 2, "Career": 3}
    return sorted(items, key=lambda x: (priority_rank.get(x.priority, 9), category_rank.get(x.category, 9), x.title.lower()))

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

    items = sort_items(dedupe(all_items))[:MAX_ITEMS]

    data = {
        "generatedAt": datetime.now(timezone.utc).astimezone().isoformat(timespec="seconds"),
        "news": [asdict(item) for item in items],
        "jobs": JOB_LINKS,
        "sources": CURATED_SOURCES,
    }

    OUTPUT_FILE.write_text(json.dumps(data, indent=2, ensure_ascii=False), encoding="utf-8")
    print(f"Wrote {OUTPUT_FILE} with {len(items)} news items.")

if __name__ == "__main__":
    main()
