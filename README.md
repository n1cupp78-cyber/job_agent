# Job Search Agent — Nick Cupp

A small local agent that searches for remote-friendly Project/Product
Manager roles in telecom, energy, and AI/cloud-adjacent tech, scores them
against your resume profile, and writes a report you can read or query.

## 1. Install

```bash
cd job_agent
python3 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
cp profile.example.json profile.json   # then edit it (see section 4)
```

## 2. Get API keys (free tiers)

- **Adzuna** (main job aggregator, required): https://developer.adzuna.com/
  → sign up, create an app, copy the App ID and App Key.
- **USAJobs** (optional, gov/federal-adjacent roles): https://developer.usajobs.gov/
- **Anthropic API key** (optional but recommended — gives you real AI-based
  relevance scoring instead of keyword matching): https://console.anthropic.com/

Copy `.env.example` to `.env` and fill in whichever keys you got:

```bash
cp .env.example .env
nano .env
```

## 3. Run it manually

```bash
python3 job_agent.py
```

This writes a dated report to `reports/YYYY-MM-DD.md` and updates
`reports/latest.md`.

To check in later without re-running a search:

```bash
python3 job_agent.py --ask
```

## 4. Tune the search

Open `profile.json` and edit:
- `keywords_for_search` — the actual search queries sent to job APIs. Add or
  remove terms as you see which ones return good results.
- `target_roles` / `target_industries` — used by the AI scorer as context.
- `aspirational_skills` — update this as you complete AWS/cloud/AI training,
  so the agent starts surfacing more AI/cloud-leaning roles over time.

## 5. Schedule it (daily or weekly)

Run `crontab -e` and add one of:

```cron
# Daily at 7:30am
30 7 * * * cd /full/path/to/job_agent && ./venv/bin/python3 job_agent.py >> logs.txt 2>&1

# Weekly, Monday 7:30am
30 7 * * 1 cd /full/path/to/job_agent && ./venv/bin/python3 job_agent.py >> logs.txt 2>&1
```

Replace `/full/path/to/job_agent` with the real path (run `pwd` inside the
folder to get it).

## 6. Checking in via prompt or voice

**Text/prompt check-in** works out of the box:
```bash
python3 job_agent.py --ask
```

**Voice check-in** (optional, fully local): `voice_agent.py` is a push-to-talk
interface. Press Enter, speak a command, and it transcribes with whisper.cpp,
runs the agent, and reads back a short summary with Piper (or espeak-ng).

```bash
python3 voice_agent.py
```

Say "run a search", "any new jobs?", "list reports", or "stop". Setup steps for
whisper.cpp and text-to-speech are in [VOICE_SETUP.md](VOICE_SETUP.md).

A quick alternative without voice input:

```bash
python3 job_agent.py --ask | espeak-ng
```

## Adding specific companies or headhunters

The agent now supports pulling job feeds directly from specific companies, on
top of the general Adzuna/USAJobs search. Two platforms are supported out of
the box — **Greenhouse** and **Lever** — both free, public, no API key
needed.

**To add a company:**
1. Guess or search for their careers page, then check if either of these
   loads real job listings:
   - `https://boards.greenhouse.io/COMPANYNAME`
   - `https://jobs.lever.co/COMPANYNAME`
2. If one does, that URL segment is the "token." Add it to `profile.json`:
   ```json
   "company_sources": {
     "greenhouse_tokens": ["stripe", "figma"],
     "lever_tokens": ["netflix"]
   }
   ```
3. Run `python3 job_agent.py` again — it'll pull every open role at that
   company alongside the keyword search results.

**For headhunters/staffing firms** — most recruiting/staffing agencies don't
expose a public API, and many run on the same job-board platforms as
regular employers (some use Greenhouse/Lever too, worth checking with the
steps above). For firms that don't, the general Adzuna keyword search
already picks up a lot of agency-posted listings, since agencies post to
aggregators to get visibility. If a specific staffing firm needs to be
tracked directly and neither Greenhouse nor Lever works for it, a new source
function would need to be added.

**For other ATS platforms** (Workday, iCIMS, SmartRecruiters, etc.) — these
are less consistently public, but some companies still expose a semi-public
JSON endpoint. To add one, check what its careers page exposes and write a
matching search function following the same pattern as
`search_greenhouse`/`search_lever` in `job_agent.py`.

## Notes / limitations

- This uses **Adzuna** and **USAJobs**, both of which have legitimate,
  ToS-compliant free APIs. It does **not** scrape LinkedIn or Indeed — both
  actively block that, and it would violate their terms of service.
- If you want specific companies covered (e.g. AT&T, Nokia, specific energy
  companies), many use Greenhouse/Lever ATS platforms with public JSON job
  feeds — easy to add as additional sources once you know which companies
  you want tracked.
- The "remote or Oklahoma" filter is currently a simple text match on
  location/description. It's intentionally permissive (better to see an
  extra irrelevant listing than miss a good one) — the AI scorer is what
  does the real filtering by giving each listing a 0–10 fit score.

## License

MIT
