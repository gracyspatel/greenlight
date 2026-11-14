# Greenlight: Two-Split Execution Plan

Submissions close **Sunday 11:00 AM**. We submit at **10:30 AM**.

The work is split into **two independent halves**. Each split is a pair of people on its own branch, owning its own files (listed in `CLAUDE.md`). The two splits never edit the same file, so merging is just `git merge` with no conflicts.

The repo **already runs end to end** (rules engine, 3 demo events, page shell). Each split fills in its `TODO(Split A)` / `TODO(Split B)` items.

```
              ┌──────────── main (starter, already works) ────────────┐
              │                                                        │
   split-a (A1 + A2)                                         split-b (B1 + B2)
   Plan → Check → Fix                                         Rules · Submit · Track · Review · Deploy
              │                                                        │
              └──────── merge at 8:30 PM · 11:30 PM · 2:00 AM ─────────┘
```

---

## Split A: The officer flow (Plan → Check → Fix)
**This is the demo.** Split A turns event text into a plan and makes the verdict and the fix loop look great.

**Owns:** `routers/intake.py`, `routers/assist.py` (/explain), `components/intake/`, `timeline/`, `verdict/`, `fixloop/`, `data/demo_events.json`

| # | Task | Who | Done when | By |
|---|---|---|---|---|
| A1 | `/extract` prompt: every Event field, one full example, null for unknowns | A1 | The Diwali text gives JSON close to the demo event | 5:00 |
| A2 | Follow-up answers merged into the event; `IntakePanel` shows each question with an answer box and a loading state | A1 | Answering "300 people" fills `attendance` | 7:00 |
| A3 | `/explain` prompt: friendly reason + fix, quoting ONLY `rule_text`, falls back to the engine text | A2 | Never invents a number or rule (test 5 flags) | 5:30 |
| A4 | `VerdictCards`: big verdict, count chips, collapsible cards, *Explain* button, quote + source | A2 | Looks great on Diwali Night | 7:30 |
| A5 | `Timeline`: visual timeline today → event date, red/yellow/green markers, today line, order (venue → UEPA) | A1 | Looks good on all 3 demos | 9:00 |
| A6 | `FixPanel`: edit budget lines (amount, quote attached), *Apply fix* buttons (move date, drop dancing, attach quote) | A2 | Diwali Night goes Will be rejected → Ready live in under 60s | 10:00 |
| A7 | Before/after: highlight the flags that disappeared after a change | A2 | | 11:00 |
| A8 | Plain-text versions of the 3 demos that extract cleanly; edge cases ("next Friday", "$3.5k", off-campus) | A1 | All 3 give the right verdict from text | 11:30 |

## Split B: Rules, submit, track, review, deploy
Split B makes the verdict **trustworthy** (verified rules, tests), adds everything after the check (pack, tracker, reviewer, Q&A), and keeps the live URL up.

**Owns:** `engine.py`, `rules.json`, `calendar.json`, `tests/`, `routers/check.py`, `extras.py`, `pack.py`, `main.py`, `llm.py`, `App.jsx`, `api.js`, `components/tracker/`, `reviewer/`, `ask/`, `pack/` (new), `data/guidelines/`, `.replit`

| # | Task | Who | Done when | By |
|---|---|---|---|---|
| B1 | GitHub repo + collaborators (Setup). Import it into **Replit** and get the public URL live | B1 | The URL shows the app | 4:15 |
| B2 | `llm.py` working with the key; test one call; share a "how to call the LLM" snippet with Split A | B1 | `/extract` stub returns real JSON | 4:30 |
| B3 | Check every rule in `rules.json` and the breaks in `calendar.json` against the sources; fill `verified_on` | B2 | Every rule has a working source | 4:30 |
| B4 | **Find a USG / Campus Activities person at the event**: confirm the rules, get one quote → `docs/usg-notes.md` | B2 | Quote in hand | 5:00 |
| B5 | `Tracker`: status per approval, "blocking now" summary, *Remind advisor* (drafted email text) | B1 | Marking approved turns cards green | 7:30 |
| B6 | Tests: one per rule (pass + fail), the break case; any missing rules USG confirmed | B2 | `pytest` covers every rule id | 8:00 |
| B7 | `/pack` + new `components/pack/PackView.jsx` (add it to `App.jsx`): drafted text per form, copy button, link. Enabled only when the verdict is Ready | B1 | | 10:30 |
| B8 | `data/guidelines/*.md`: public USG/GSG/Campus Activities/TES pages, one file each, source URL at the top | B2 | 6+ files | 9:30 |
| B9 | `/ask`: keyword search → LLM answers ONLY from the chunks, with a citation, else "email usgfunds@usc.edu" | B2 | "Can USG pay for T-shirts?" gives a cited answer | 12:00 AM |
| B10 | `ReviewerView` + `/reviewer/queue`: LLM summary per application, filter by verdict | B1 | | 1:00 AM |
| B11 | Redeploy Replit after every merge into `main` | B1 | | ongoing |

**Split A depends on nothing from Split B, and the other way round.** Every endpoint and component already exists as a working stub, so each split builds against the other's stubs until the merge.

---

## Setup (3:15–3:35 PM)

**B1 first (5 min):**
```bash
unzip greenlight-starter.zip && cd greenlight
git init && git add . && git commit -m "Starter" && git branch -M main
git remote add origin https://github.com/<you>/greenlight.git && git push -u origin main
git checkout -b split-a && git push -u origin split-a
git checkout -b split-b main && git push -u origin split-b
```
GitHub → Settings → Collaborators → add the other three. Share an Anthropic API key in the private group chat.

**Everyone:**
```bash
git clone https://github.com/<B1>/greenlight.git && cd greenlight
git checkout split-a        # or split-b
cp .env.example .env        # paste the key, never commit it
pip install -r backend/requirements.txt
cd frontend && npm install && cd ..
python -m uvicorn backend.app.main:app --reload --port 8000     # terminal 1
cd frontend && npm run dev                                         # terminal 2 → http://localhost:5173
```
Click "Diwali Night" and you should see **Will be rejected**. If you do, you're set up.

**Claude Code** (each person with their **own** Claude account), first message:
> Read CLAUDE.md, PLAN.md and docs/CONTRACTS.md. I am on Split A, task A1 (my partner does A3). Only edit Split A files.

### Working inside a split (2 people, 1 branch)
- Split the tasks so the two of you are in **different folders** at any moment (the "Who" column already does this).
- Commit small and often. Before every push: `git pull --rebase` → `cd backend && python -m pytest -q` → `git push`.
- Pull your partner's work at least every hour.

---

## Merging the two splits

At each merge point, **one person per split** does this. Split B merges first (it owns the shell), then Split A:

```bash
# Split B
git checkout split-b && git pull && cd backend && python -m pytest -q && cd ..
git checkout main && git pull && git merge split-b && git push

# Split A (after B is done)
git checkout split-a && git pull
git checkout main && git pull && git merge split-a
cd backend && python -m pytest -q && cd ..
git push

# Both splits then pick up each other's work
git checkout split-a && git merge main && git push      # (B does the same on split-b)
```
Then all four of you run the full demo on `main` together (15 min), and B1 redeploys Replit.

| Merge | Must work on `main` after merging |
|---|---|
| **8:30 PM** | Text → plan → verdict cards with explanations → timeline. Verified rules, tracker, live URL. **The minimum demo.** |
| **11:30 PM** | Diwali Night goes Will be rejected → Ready live. Pack works. **The safe demo:** `git tag safe-demo && git push --tags` |
| **2:00 AM** | Q&A and reviewer view, or cut. **Last feature merge.** |
| **6:00 AM** | Code freeze. Bug fixes only, made straight on `main` by one person at a time. |

**If behind at 8:30:** Split B cuts Q&A (B9) and the reviewer view (B10), and both splits help finish the fix loop (A6).

## Rules of the road
- Only edit your split's files. If you need something from the other split, post the exact change in the chat and they make it.
- Don't change the shapes in `docs/CONTRACTS.md` without both splits agreeing.
- Hourly status from each split in the chat: `done / next / blocked`.
- Each person uses their own Claude account. If someone hits their usage limit, they pair with their partner.
- Never commit `.env`.

## Sleep shifts (one person per split always awake)
- A1 + B2: 2:00–4:30 AM
- A2 + B1: 4:30–7:00 AM

## Sunday 7:00–10:30 AM: Ship it (no more coding)
| Who | What |
|---|---|
| Split A (A1 + A2) | 3-minute video, using the demo script below |
| B2 | Slide deck (problem, how it works, "AI understands, rules decide", USG quote) |
| B1 | Devpost write-up, screenshots, Replit link, final redeploy. **Submit at 10:30.** |

## The 3-minute demo script
1. "USC clubs lose events because approvals are split across 6 offices with hidden deadlines." (USG quote)
2. Paste the Diwali Night text → *Plan my approvals* → 8 approvals, timeline, **Will be rejected**.
3. *Explain* on the $4,500 venue flag → the rule quoted with its source.
4. Fix live: move the date, cut the venue cost, attach a quote, drop dancing → **Ready**.
5. Submission pack → tracker → USG reviewer view.
6. "The AI only reads and explains. Code decides from USC's written rules. USG still makes the call."
