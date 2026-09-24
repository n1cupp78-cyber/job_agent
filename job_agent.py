#!/usr/bin/env python3
"""
Job Search Agent
=================
Searches remote-friendly Project/Product Manager roles in telecom, energy,
and AI/cloud-adjacent tech, scores them against a resume profile, and writes
a dated report you can read, grep, or have read back to you.

Data sources (free, ToS-friendly APIs — no scraping of LinkedIn/Indeed):
  - Adzuna Jobs API      (https://developer.adzuna.com/)  -> general aggregator
  - USAJobs API          (https://developer.usajobs.gov/) -> federal/federal-adjacent

Usage:
    python3 job_agent.py                 # run a search + write today's report
    python3 job_agent.py --ask           # print latest report to stdout
    python3 job_agent.py --list-reports  # list saved reports

Setup:
    1. pip install -r requirements.txt
    2. Get free API keys:
         Adzuna:   https://developer.adzuna.com/  -> ADZUNA_APP_ID / ADZUNA_APP_KEY
         USAJobs:  https://developer.usajobs.gov/  -> USAJOBS_API_KEY / USAJOBS_EMAIL
    3. (Optional but recommended) Get an Anthropic API key for AI-based
       relevance scoring: https://console.anthropic.com/
         export ANTHROPIC_API_KEY=sk-ant-...
       Without it, the script falls back to keyword-based scoring — still
       useful, just less nuanced.
    4. export the keys as environment variables (or put them in a .env file
       in this directory — see .env.example).
    5. Test it:  python3 job_agent.py
    6. Schedule it with cron (see README.md).
"""

import os
import sys
import json
import re
import argparse
from datetime import datetime, timezone
from pathlib import Path

import requests

BASE_DIR = Path(__file__).resolve().parent
REPORTS_DIR = BASE_DIR / "reports"
REPORTS_DIR.mkdir(exist_ok=True)
PROFILE_PATH = BASE_DIR / "profile.json"

# Load .env if present (very small, no extra dependency)
env_file = BASE_DIR / ".env"
if env_file.exists():
    for line in env_file.read_text().splitlines():
        line = line.strip()
        if line and not line.startswith("#") and "=" in line:
            k, v = line.split("=", 1)
            os.environ.setdefault(k.strip(), v.strip())

ADZUNA_APP_ID = os.environ.get("ADZUNA_APP_ID")
ADZUNA_APP_KEY = os.environ.get("ADZUNA_APP_KEY")
USAJOBS_API_KEY = os.environ.get("USAJOBS_API_KEY")
USAJOBS_EMAIL = os.environ.get("USAJOBS_EMAIL")
ANTHROPIC_API_KEY = os.environ.get("ANTHROPIC_API_KEY")

REMOTE_HINTS = ["remote", "work from home", "wfh", "anywhere"]
OK_HINTS = ["oklahoma", " ok ", "ok,", "okc", "tulsa"]


def load_profile():
    with open(PROFILE_PATH) as f:
        return json.load(f)


def search_adzuna(query, results=25):
    """Query Adzuna's US jobs endpoint."""
    if not (ADZUNA_APP_ID and ADZUNA_APP_KEY):
        return []
    url = "https://api.adzuna.com/v1/api/jobs/us/search/1"
    params = {
        "app_id": ADZUNA_APP_ID,
        "app_key": ADZUNA_APP_KEY,
        "results_per_page": results,
        "what": query,
        "content-type": "application/json",
    }
    try:
        r = requests.get(url, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[adzuna] error for '{query}': {e}", file=sys.stderr)
        return []

    jobs = []
    for item in data.get("results", []):
        jobs.append({
            "source": "adzuna",
            "title": item.get("title", "").strip(),
            "company": (item.get("company") or {}).get("display_name", "Unknown"),
            "location": (item.get("location") or {}).get("display_name", ""),
            "description": item.get("description", ""),
            "url": item.get("redirect_url", ""),
            "posted": item.get("created", ""),
        })
    return jobs


def search_usajobs(query, results=25):
    """Query USAJobs (useful for federal / federal-contractor-adjacent PM roles)."""
    if not (USAJOBS_API_KEY and USAJOBS_EMAIL):
        return []
    url = "https://data.usajobs.gov/api/search"
    headers = {
        "Host": "data.usajobs.gov",
        "User-Agent": USAJOBS_EMAIL,
        "Authorization-Key": USAJOBS_API_KEY,
    }
    params = {"Keyword": query, "ResultsPerPage": results, "RemoteIndicator": "True"}
    try:
        r = requests.get(url, headers=headers, params=params, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[usajobs] error for '{query}': {e}", file=sys.stderr)
        return []

    jobs = []
    for item in data.get("SearchResult", {}).get("SearchResultItems", []):
        d = item.get("MatchedObjectDescriptor", {})
        locs = ", ".join(l.get("LocationName", "") for l in d.get("PositionLocation", []))
        jobs.append({
            "source": "usajobs",
            "title": d.get("PositionTitle", ""),
            "company": d.get("OrganizationName", ""),
            "location": locs,
            "description": d.get("UserArea", {}).get("Details", {}).get("JobSummary", ""),
            "url": d.get("PositionURI", ""),
            "posted": d.get("PublicationStartDate", ""),
        })
    return jobs


def search_greenhouse(token, results=50):
    """Pull all open jobs from a company's public Greenhouse board."""
    url = f"https://boards-api.greenhouse.io/v1/boards/{token}/jobs"
    try:
        r = requests.get(url, params={"content": "true"}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[greenhouse:{token}] error: {e}", file=sys.stderr)
        return []

    jobs = []
    for item in data.get("jobs", [])[:results]:
        jobs.append({
            "source": f"greenhouse:{token}",
            "title": item.get("title", "").strip(),
            "company": token,
            "location": (item.get("location") or {}).get("name", ""),
            "description": item.get("content", ""),
            "url": item.get("absolute_url", ""),
            "posted": item.get("updated_at", ""),
        })
    return jobs


def search_lever(token, results=50):
    """Pull all open jobs from a company's public Lever board."""
    url = f"https://api.lever.co/v0/postings/{token}"
    try:
        r = requests.get(url, params={"mode": "json"}, timeout=20)
        r.raise_for_status()
        data = r.json()
    except Exception as e:
        print(f"[lever:{token}] error: {e}", file=sys.stderr)
        return []

    jobs = []
    for item in data[:results]:
        cat = item.get("categories", {})
        jobs.append({
            "source": f"lever:{token}",
            "title": item.get("text", "").strip(),
            "company": token,
            "location": cat.get("location", ""),
            "description": item.get("descriptionPlain", "") or item.get("description", ""),
            "url": item.get("hostedUrl", ""),
            "posted": "",
        })
    return jobs


def looks_remote_or_ok(job):
    text = f"{job.get('location','')} {job.get('description','')}".lower()
    return any(h in text for h in REMOTE_HINTS) or any(h in text for h in OK_HINTS)


def dedupe(jobs):
    seen = set()
    out = []
    for j in jobs:
        key = (j["title"].lower().strip(), j["company"].lower().strip())
        if key not in seen:
            seen.add(key)
            out.append(j)
    return out


def keyword_score(job, profile):
    """Fallback scorer if no Anthropic API key is set. 0-10 scale."""
    text = f"{job['title']} {job['description']}".lower()
    score = 0
    reasons = []

    role_words = ["project manager", "program manager", "product manager",
                  "technical project manager", "delivery manager", "implementation manager"]
    if any(w in text for w in role_words):
        score += 4
        reasons.append("matches target role")

    industry_words = ["telecom", "telecommunications", "energy", "oil", "gas",
                       "pipeline", "utilities", "wireless", "network"]
    hits = [w for w in industry_words if w in text]
    if hits:
        score += 3
        reasons.append(f"industry match: {', '.join(hits[:3])}")

    ai_cloud_words = ["aws", "cloud", "artificial intelligence", " ai ", "machine learning"]
    if any(w in text for w in ai_cloud_words):
        score += 2
        reasons.append("AI/cloud angle")

    if looks_remote_or_ok(job):
        score += 1
        reasons.append("remote/OK friendly")

    return min(score, 10), "; ".join(reasons) if reasons else "general keyword overlap only"


def ai_score_batch(jobs, profile):
    """Use Claude to score + explain fit for a batch of jobs. Falls back gracefully."""
    if not ANTHROPIC_API_KEY or not jobs:
        return None
    try:
        import anthropic
    except ImportError:
        print("[ai_score] `anthropic` package not installed, falling back to keyword scoring.",
              file=sys.stderr)
        return None

    client = anthropic.Anthropic(api_key=ANTHROPIC_API_KEY)
    listing_block = "\n\n".join(
        f"[{i}] TITLE: {j['title']}\nCOMPANY: {j['company']}\nLOCATION: {j['location']}\n"
        f"DESCRIPTION: {j['description'][:800]}"
        for i, j in enumerate(jobs)
    )

    prompt = f"""You are screening job listings for this candidate profile:

{json.dumps(profile, indent=2)}

Score each listing below from 0-10 for fit (role match, industry match,
remote/Oklahoma eligibility, and any AI/cloud growth angle count in favor).
Respond ONLY with a JSON array, no other text, like:
[{{"index": 0, "score": 7, "reason": "short reason under 20 words"}}, ...]

Listings:
{listing_block}
"""
    try:
        resp = client.messages.create(
            model="claude-sonnet-4-6",
            max_tokens=2000,
            messages=[{"role": "user", "content": prompt}],
        )
        text = "".join(b.text for b in resp.content if hasattr(b, "text"))
        text = re.sub(r"^```json|```$", "", text.strip(), flags=re.MULTILINE).strip()
        scores = json.loads(text)
        for s in scores:
            i = s["index"]
            if 0 <= i < len(jobs):
                jobs[i]["score"] = s["score"]
                jobs[i]["reason"] = s["reason"]
        return jobs
    except Exception as e:
        print(f"[ai_score] error, falling back to keyword scoring: {e}", file=sys.stderr)
        return None


def run_search():
    profile = load_profile()
    all_jobs = []

    for q in profile["keywords_for_search"]:
        all_jobs.extend(search_adzuna(q))
        all_jobs.extend(search_usajobs(q))

    company_sources = profile.get("company_sources", {})
    for token in company_sources.get("greenhouse_tokens", []):
        all_jobs.extend(search_greenhouse(token))
    for token in company_sources.get("lever_tokens", []):
        all_jobs.extend(search_lever(token))

    if not all_jobs:
        print("No results — check that ADZUNA_APP_ID/ADZUNA_APP_KEY (and optionally "
              "USAJOBS_API_KEY/USAJOBS_EMAIL) are set. See README.md.", file=sys.stderr)

    all_jobs = dedupe(all_jobs)
    candidates = [j for j in all_jobs if looks_remote_or_ok(j)]

    scored = ai_score_batch(candidates, profile)
    if scored is None:
        scored = []
        for j in candidates:
            s, reason = keyword_score(j, profile)
            j["score"] = s
            j["reason"] = reason
            scored.append(j)

    scored.sort(key=lambda j: j.get("score", 0), reverse=True)
    write_report(scored, profile)
    return scored


def write_report(jobs, profile):
    today = datetime.now(timezone.utc).strftime("%Y-%m-%d")
    path = REPORTS_DIR / f"{today}.md"
    lines = [f"# Job Search Report — {today}", ""]
    if not jobs:
        lines.append("No matching remote/Oklahoma-eligible PM/Product roles found today.")
    else:
        lines.append(f"{len(jobs)} candidate matches, sorted by fit score.\n")
        for j in jobs:
            lines.append(f"## {j['title']} — {j['company']} ({j.get('score','?')}/10)")
            lines.append(f"- Location: {j.get('location','n/a')}")
            lines.append(f"- Source: {j.get('source')}")
            if j.get("url"):
                lines.append(f"- Link: {j['url']}")
            lines.append(f"- Why: {j.get('reason','')}")
            lines.append("")
    path.write_text("\n".join(lines))
    # also keep a rolling "latest.md" for the --ask flag
    (REPORTS_DIR / "latest.md").write_text("\n".join(lines))
    print(f"Report written to {path}")


def cmd_ask():
    latest = REPORTS_DIR / "latest.md"
    if not latest.exists():
        print("No report yet — run `python3 job_agent.py` first.")
        return
    print(latest.read_text())


def cmd_list_reports():
    for f in sorted(REPORTS_DIR.glob("*.md")):
        print(f.name)


if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--ask", action="store_true", help="Print the latest report")
    parser.add_argument("--list-reports", action="store_true", help="List saved reports")
    args = parser.parse_args()

    if args.ask:
        cmd_ask()
    elif args.list_reports:
        cmd_list_reports()
    else:
        run_search()
