# Life OS — Master Architecture

**This document is the canonical reference.** It consolidates and supersedes: `life_os_job_and_people_discovery_guide.md`, `life_os_project_handover.md`, and `life_os_browser_use_design.md`. Where this document differs from those (specifically: Browser Use is now read-only research, not an autonomous actor), this document governs.

---

## 0. Mental model

Life OS has three workstreams and one non-negotiable boundary:

```
                              LIFE OS
        ┌───────────────┬───────────────┬───────────────┐
        ▼               ▼               ▼               │
     JOB OS       PEOPLE DISCOVERY  CAREER INTELLIGENCE   │
   (find + screen   (find relevant    (research + strategy│
    opportunities)   professors)       for a specific job  │
                                        or person)          │
        └───────────────┴───────────────┘                  │
                         ▼                                  │
                  EVIDENCE / PROVENANCE LAYER                │
              (every claim traces to a real source)          │
                         ▼                                    │
                    DRAFTS / RECOMMENDATIONS                   │
                         ▼                                      │
        ══════════════════════════════════════════════════════
                    THE USER — sole final actor
        (submits applications, sends messages — Life OS never does)
        ══════════════════════════════════════════════════════
```

**The boundary above the line never moves without a separate, explicit decision.** Life OS discovers, reads, analyzes, matches, and drafts. It does not submit, send, click "apply," or act on any third-party system on the user's behalf. This is a deliberate, revised decision (see §5) — earlier design work explored an auto-apply state machine with an approval gate; that has been replaced by this simpler, lower-risk model. The user is the only actor that ever performs a consequential external action.

---

## 1. Cross-cutting principles (apply everywhere in this document)

1. **No hallucination.** Every fact in every record traces to something literally present in a fetched source. Unknown facts are marked unknown, never inferred.
2. **Source-of-truth hierarchy.** An index (GitHub list, directory site, CSRankings) is never proof of current state. The actual employer posting / actual lab page / actual company page is the source of truth.
3. **Deterministic-first.** Discovery, extraction of explicit fields, and rule-based matching use plain HTTP/parsing/APIs wherever possible. LLMs are used for reasoning, ranking, synthesis, and drafting — never as the mechanism that determines whether something exists or is true.
4. **One new source at a time.** Every new data source (job board, lab directory, API, research target) passes its own fetchability/verification check before being added to any registry.
5. **Stop-after-phase discipline.** Every phase in every workstream ends with an explicit stop for user review. No phase proceeds, and nothing is committed or pushed, without approval of the prior phase.
6. **No automated outreach or submission, ever, by default.** Every workstream produces drafts and recommendations. The user personally sends, applies, or submits. This applies even if a future revision reconsiders it — that would require a new, explicit, separately-approved design, not a quiet extension of this one.
7. **Empty/incomplete beats invented.** If nothing qualifies, or a fact can't be verified, say so plainly. Never manufacture a fact, a person, a job, or a claim about the user's own experience to fill a gap or hit a quota.
8. **Evidence/provenance is mandatory, not optional polish.** Every recommendation (a keyword to add, a project to emphasize, an outreach angle) must be traceable to: the specific source text it came from, and the specific profile evidence that supports it.

---

## 2. WORKSTREAM 1 — JOB OS

*(Status as of last update — see the checklist in §6 for exact current position.)*

### 2.1 Purpose
Reliable, verifiable job discovery and eligibility screening, decoupled from LLM search-grounding availability.

### 2.2 Pipeline
```
Source registry (SpeedyApply, later: JobDataLake, Adzuna, AI Dev Jobs)
        ↓
Extract job URLs / index entries
        ↓
Fetch actual employer posting (plain HTTP first; Jina AI Reader as fallback
        for the ~12.5% requiring JS rendering — NOT Browser Use, NOT Playwright/Apify
        unless Jina proves insufficient)
        ↓
Extract structured fields (14-field schema — see §2.4)
        ↓
Deadline status computation (live, at generation time — never cached as final)
        ↓
Eligibility classification vs. real Career Profile (ELIGIBLE / LIKELY /
        NEEDS VERIFICATION / NOT ELIGIBLE — eligibility criteria only,
        never mixed with relevance)
        ↓
Relevance ranking (separate step — career-direction fit, does not affect
        the eligibility label)
        ↓
Shortlist (5-10 items, fewer if fewer qualify, never padded)
        ↓
[Hands off to Career Intelligence, §4, for jobs the user selects to pursue]
```

### 2.3 Phase discipline
- **Phase 1 — Fetchability testing.** Sample a representative set of URLs from a new source; classify plain-HTTP-parseable vs. browser-required vs. stale/closed vs. fetch-failed as four *mutually exclusive* categories that must sum to the sample size exactly. Stop if browser-required exceeds 30%.
- **Phase 2 — Eligibility classification.** Extract the 14-field schema (§2.4) per posting; classify against the Career Profile using eligibility criteria only; cite evidence; mark unknowns explicitly rather than guessing.
- **Phase 3 — Classification audit.** Re-verify Phase 2's labels with explicit evidence/unknowns in a structured table, specifically to catch relevance-vs-eligibility conflation and missing-field errors before they reach the user.
- **Phase 4 — Full dry run.** Run against the entire index (not a sample). Report full funnel counts (indexed → fetched → parseable → eligible/likely/needs-verification/not-eligible), grouped fetch-failure breakdown by domain, and the final shortlist with mandatory deadline status.

### 2.4 Required 14-field extraction schema
`company, title, location, remote/hybrid/onsite, country, experience requirement, degree requirement, graduation requirement, work-authorization requirement, sponsorship requirement, deadline, required skills, preferred skills, new-grad status` — plus the derived `eligibility label` and `unknowns` list. Always as actual structured fields/columns, never collapsed into prose.

### 2.5 Deadline status (mandatory, previously unimplemented — must be fixed)
Every shortlisted item carries `OPEN` / `CLOSING SOON` (≤7 days) / `CLOSED`, computed against the current date at generation time. **A `CLOSED` posting never appears in the main actionable shortlist**, even with a strong eligibility label. Closed-but-possibly-recurring roles go in a separate "recently closed" note; never guess a reopen date without evidence.

### 2.6 Source registry
One entry per verified source, with a `verified: true/false` and `last_verified` field. Approved for addition, in priority order, each requiring its own fetchability pass before being marked `verified: true`: JobDataLake (already connected, no new integration needed) → Adzuna → AI Dev Jobs. Deferred: Open Skills (future skill-gap layer, not discovery), Groq/Hugging Face (no current gap). Explicitly excluded: JobSpy (violates LinkedIn/Indeed/Glassdoor/ZipRecruiter ToS, real account-ban risk — left as a standing human decision, not silently added or rejected), WolframAlpha (no architectural tie).

---

## 3. WORKSTREAM 2 — PEOPLE DISCOVERY

### 3.1 Purpose
Read-only discovery of professors/researchers genuinely relevant to the user's actual work, explicitly scoped down from an earlier, much larger "network graph" proposal.

### 3.2 Approved sources (exactly these three; no others without separate approval)
1. `nlpbharat.github.io` — community-maintained directory of NLP professors across major Indian institutes.
2. IIT Hyderabad NLIP lab page — added separately since the directory's entry for this institute was blank.
3. CSRankings (`github.com/emeryberger/CSrankings`) — global faculty-affiliation dataset, filtered to NLP/AI subfields. Approved as an exception to "India only" because it's one already-structured dataset, not an open crawl.

### 3.3 Data model
```
name, institution, lab_name, lab_or_personal_page_url (source of truth),
google_scholar_url (if present), research_areas (only if explicitly stated —
left blank otherwise), source_url, date_fetched
```
No inference from lab name, paper titles, or reputation. Records from different sources stay labeled by source, never silently merged.

### 3.4 Explicitly out of scope (until separately approved)
Automated outreach/message drafting at this stage, relevance scoring against the user's profile, "network alert"/trigger detection, startup founders, PhD students, conference speakers, LinkedIn-based discovery, Discord/Telegram monitoring, worldwide open-ended lab-page crawling beyond the three sources above.

*(Note: once Career Intelligence's outreach-strategy layer, §4.5, is active, it consumes People Discovery's verified person records as an input — but People Discovery itself still does not draft or score anything on its own.)*

---

## 4. WORKSTREAM 3 — CAREER INTELLIGENCE (revised; supersedes prior Browser Use auto-apply design)

### 4.1 Purpose and boundary
For a specific job (from Job OS) or person (from People Discovery) the user has chosen to pursue, research it thoroughly and produce a resume/cover-letter/outreach *strategy* — never a submission, never an auto-sent message. **Browser Use's role is narrowed to read-only web research**: open a page, read it, extract information. It has no fill/click/upload/submit capability in this design. Any future reconsideration of that requires a new, separately-approved design — not a silent extension of this one.

### 4.2 Pipeline
```
JOB (or PERSON) SELECTED by user
        ↓
WEB RESEARCH (Browser Use: read-only navigate + extract;
        APIs where structured data exists instead of browsing)
        ↓
JOB/COMPANY INTELLIGENCE (what the posting says, what the company/team
        page says — with source URLs retained for every fact)
        ↓
CAREER PROFILE MATCH (deterministic comparison against the user's
        actual profile — see §4.3)
        ↓
FIT ANALYSIS (per-requirement: MATCH / UNDERREPRESENTED / ADJACENT / MISSING)
        ↓
RESUME STRATEGY (§4.4)
        ↓
COVER LETTER STRATEGY → DRAFT (§4.5)
        ↓
OUTREACH STRATEGY → DRAFT (recruiter or professor, §4.6)
        ↓
EVIDENCE/PROVENANCE PACKAGE attached to every recommendation above (§4.7)
        ↓
PRESENTED TO USER FOR REVIEW
        ↓
USER personally applies / sends — Life OS's involvement ends here
```

### 4.3 Career Profile (data model, reused from earlier design, still valid)
```
CareerProfile:
  identity: {name, email, phone, github, linkedin, portfolio}
  education: {degree, institution, gpa/percentage, graduation_year}
  skills: {languages, frameworks, tools}
  experience: [{role, org, dates, description}]
  projects: [{name, description, tech, relevance_tags}]
  preferences: {roles, locations, remote_ok, salary_expectations}
  work_authorization: {country: status}   # explicit, per-country, never inferred
  resume_variants: [{name, file_ref, tags}]
```
No `question_bank`/auto-fill fields are needed in this revised design — there's no form-filling to support.

### 4.4 Resume strategy — the four-tier rule (mandatory, exact wording matters)
For every requirement detected in the posting, classify against the Career Profile as exactly one of:
- **MATCH** — user has direct evidence (a project, a skill, an experience) — recommend emphasizing it, with the specific project/experience named.
- **UNDERREPRESENTED** — user has it, but it's buried/not prominent in current resume — recommend surfacing it, citing where it already exists.
- **ADJACENT** — user has related-but-not-identical experience — output exactly: *"ADJACENT — potentially mention only if truthful,"* and name the specific related experience.
- **MISSING** — no evidence exists — output exactly: *"MISSING — do not claim this."* Never suggest wording that implies possession of a skill/technology/years of experience the user doesn't have. This rule has no exceptions, regardless of how close a "creative rewording" might get to technically true.

### 4.5 Cover letter strategy and draft
- Strategy: identify one specific, factual, current detail from the actual company/job page — never a generic opener — and connect it to a specific real experience of the user's.
- Draft: written from that strategy, using only MATCH/UNDERREPRESENTED evidence (never ADJACENT or MISSING claims). Presented as a strong starting draft for the user to personalize and finalize, not a disguised final artifact assumed to be sent as-is.

### 4.6 Outreach strategy and draft (recruiters and professors)
Same pipeline shape for both:
```
PERSON (from People Discovery, or a recruiter/team-member found during
        job/company research)
        ↓
Read their actual public research/work (papers, projects, team page)
        ↓
Identify a genuine, specific overlap with the user's real profile
        ↓
Outreach strategy: what angle, why now
        ↓
Draft: references the specific real detail found — never
        "Dear Professor, I am interested in your research..."
        ↓
Presented to user — user sends
```
No automated sending under any circumstance in this design.

### 4.7 Evidence/provenance package (attached to every recommendation)
For every keyword, project recommendation, cover-letter angle, or outreach angle, retain: the exact source URL and quoted/paraphrased text the claim is based on, the specific requirement it responds to, and the specific Career Profile evidence supporting it. This is what lets the user (or a later audit) check "why did it suggest this" without re-deriving it from scratch.

### 4.8 Residual security note
Browser Use still reads untrusted web content (job/company pages), so indirect prompt injection remains a theoretical risk — but with no fill/click/upload/submit capability available to hijack, the practical worst case is a bad recommendation, which the user catches on review, not an unauthorized real-world action. No session/credential storage is needed for this design, since nothing requires being logged in to research public pages. If a future version needs authenticated browsing (e.g., a job board requiring login to view full postings), that reintroduces session-security considerations from the earlier design and should be scoped separately.

---

## 5. What changed from the earlier Browser Use design (for the record)

The original design included: an application state machine with SUBMITTING/SUBMITTED states, a hard-coded approval gate specifically for submission, session/credential isolation for logged-in automation, and an outreach-sending pathway gated the same way. **All of that is removed in this revision.** Browser Use now has no write capability at all in the architecture — no `fill_field`, `click`, `upload_file`, or `submit` methods exposed anywhere. This isn't a simplification of the approval gate; it's the removal of the entire category of action the gate existed to control. If autonomous submission is ever reconsidered, treat it as a new proposal requiring the same scrutiny the original received, not a restoration of old code.

---

## 6. Master sequencing checklist (all three workstreams)

- [ ] Job OS Phase 2 corrected (Beghou eligibility/relevance conflation fixed, deadline extraction diagnosed) — **awaiting return/review**
- [ ] Job OS Phase 3 (classification audit) run and approved
- [ ] Job OS Phase 4 (full dry run, deadline-status logic implemented) run and approved
- [ ] JobDataLake, then Adzuna, then AI Dev Jobs added one at a time, each fetch-verified first
- [ ] People Discovery fetchability check (all 3 sources) completed and reported
- [ ] People Discovery dry-run person list produced and reviewed
- [ ] Career Intelligence pipeline (§4) built against a small number of already-tested jobs (e.g., Clera, Relay) as a pilot, output reviewed before any broader rollout
- [ ] Only after all of the above: discuss whether/how any of this feeds into the daily AI Edge briefing format

No step above may be skipped or reordered without the user explicitly saying so. This checklist replaces the one in the earlier build-guide file.

---

## 7. Explicit permanent exclusions (not just "later" — genuinely out of this architecture unless a new design is separately approved)

- Autonomous application submission or message sending of any kind.
- Storage/reuse of logged-in browser sessions or credentials.
- LinkedIn/Indeed/Glassdoor/ZipRecruiter scraping via JobSpy or similar (ToS/ban risk).
- Any feature that fabricates a skill, experience, achievement, or claim on the user's behalf — this is absolute, with no "creative wording" exception.
- "Worldwide" open-ended crawling beyond explicitly verified, named sources.
