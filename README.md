# Actuarial Life & Health Auto News Dashboard

This is a simplified dashboard with only three sections:

1. **New**
   - Latest automatically collected life/health actuarial news from the last 7 days.
   - Each card includes source, category, priority, summary, why it matters, and read-more link.

2. **Job**
   - Actuarial job-market watch.
   - Includes life, health, actuarial data analyst, and pricing/reserving search links.
   - Tracks common skills to watch in job descriptions.

3. **Source**
   - Curated core sources for a life/health actuarial career transition.

---

## Option A — Run locally on your computer

### First-time setup

1. Install Python 3.
2. Unzip this package.
3. Double-click `run_windows.bat`.

It will:
- Install Python packages.
- Run the crawler.
- Generate `data.json`.
- Start a local server at:

http://localhost:8000

Open that URL in your browser.

### Daily usage

Every morning:
1. Double-click `run_windows.bat`.
2. Open http://localhost:8000.
3. Read the New section.

---

## Option B — Manual run

```bash
pip install -r requirements.txt
python crawler.py
python -m http.server 8000
```

Then open:

http://localhost:8000

---

## Option C — Put it online and auto-update every morning

Best for mobile use.

1. Create a GitHub repository.
2. Upload these files:
   - `index.html`
   - `crawler.py`
   - `requirements.txt`
   - `.github/workflows/daily_news.yml`
3. Enable GitHub Pages.
4. The GitHub Action will run daily and update `data.json`.

Then you can open the GitHub Pages URL on your phone every morning.

---

## Important notes

- The crawler uses public RSS feeds and Google News RSS keyword searches.
- It does not bypass paywalls, logins, or anti-bot systems.
- Some job boards block scraping, so the Job tab uses stable search links and skill themes.
- You can add more RSS feeds or keywords inside `crawler.py`.

---

## What an actuarial life/health professional should monitor

### Life insurance
- Valuation
- Reserves
- Asset adequacy testing
- Annuities
- Mortality and longevity
- Reinsurance
- Assumption governance
- Model risk
- Capital and solvency

### Health insurance
- Medical cost trend
- Claims utilization
- Rate filing
- ACA / exchange markets
- Medicare Advantage
- Medicaid
- Risk adjustment
- Provider reimbursement
- Pharmacy trend

### General actuarial / career
- NAIC updates
- Academy policy updates
- SOA research and profession updates
- ASOP / actuarial standards
- AI/model governance
- SQL/Python/Power BI job-market requirements


## Job opening crawler

This version adds a real job-opening pipeline for the Job tab.

### What it can do

- Search U.S. actuarial-related jobs through the Adzuna API.
- Filter jobs posted within:
  - 1 day
  - 1 week
  - 2 weeks
- Keep likely early-career / <=3 years experience roles.
- Exclude many senior, manager, director, FSA/FCAS, and 4+ years roles.
- Display direct job-posting links.

### Important limitation

No public crawler can truly guarantee **all** U.S. actuarial jobs. Indeed, LinkedIn, and many company sites block or restrict automated scraping. This project uses Adzuna because it provides a documented job-search API and aggregates postings from many job sources.

### Required GitHub Secrets

To enable real job openings, create a free Adzuna developer account and add these repository secrets:

- `ADZUNA_APP_ID`
- `ADZUNA_APP_KEY`

GitHub path:

`Repository → Settings → Secrets and variables → Actions → New repository secret`

After adding both secrets, go to:

`Actions → Daily Actuarial News Update → Run workflow`

The workflow will update `data.json`, and your dashboard Job tab will show real openings.

