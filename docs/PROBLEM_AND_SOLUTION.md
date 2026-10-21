# Problem & Solution: AI Due Diligence Copilot

Status: Draft v0.2 — reviewed and revised per your inputs (weighting applied, persona confirmed, targets set, sourcing verified)
Last updated: 2026-09-20

## Executive Summary

Financial due diligence requires analysts to extract precise, defensible facts from long, table-heavy SEC filings under time pressure. Existing generative-AI tools accelerate this work but introduce a documented, measurable hallucination risk that is worse than the slow status quo when the output is trusted at face value. This document evaluates three candidate problem framings in this space, shortlists "ungrounded AI answers in high-stakes financial review" as the true problem worth solving, and defines a solution: a retrieval-augmented copilot over 10-K filings that treats citation verification and explicit refusal as first-class product behavior rather than an afterthought.

---

# PART A — PROBLEM

## 1. Problem Discovery

The discovery process started from this portfolio project's stated goal — proving competence in "data reliability and groundedness" for AI products — and worked backward through the financial-document-review space to find where that competence actually matters. Three research threads fed this:

- How due diligence analysts currently work and where they lose time ([Hebbia, 2026](https://www.hebbia.com/resources/ai-solutions-for-due-diligence))
- How filings themselves have grown in length and complexity over time ([Dyer, Lang & Stice-Lawrence, *Accounting Horizons*, via CLS Blue Sky Blog, 2016](https://clsbluesky.law.columbia.edu/2016/05/05/the-ever-expanding-10-k-why-are-10-ks-getting-so-much-longer-and-does-it-matter/))
- Documented cases of AI-driven errors in financial and legal document work ([Development Corporate, 2026](https://developmentcorporate.com/corporate-development/ai-hallucination-rates-are-a-due-diligence-crisis/); [Scientific American, 2026](https://www.scientificamerican.com/article/why-lawyers-keep-citing-fake-cases-invented-by-ai/))

This surfaced three distinct problem archetypes, each a plausible product to build, evaluated below:

- **Archetype A — Retrieval Speed Bottleneck:** Analysts spend excessive time manually locating specific facts within dense, lengthy filings and data rooms.
- **Archetype B — AI Groundedness & Trust Deficit:** When AI is used to accelerate financial document review, it introduces hallucination risk that is measurably dangerous in high-stakes, low-error-tolerance decisions.
- **Archetype C — Structured/Tabular Data Fragmentation:** Standard document parsing breaks financial tables (segment revenue, balance sheet line items) into fragments that lose row/column meaning, producing systematically wrong numbers independent of the language model used.

## 2. Problem Evaluation

### 2.1 Evaluation Criteria

| Criterion | Weight | Definition | Why it matters for this project |
|---|---|---|---|
| Stakes / severity | 0.25 | Cost of getting it wrong, in dollars, time, or reputational terms | Distinguishes "annoying" from "genuinely dangerous" problems |
| Evidence of active demand | 0.25 | Are real teams and vendors already spending money/effort here | Confirms this isn't an invented problem |
| Whitespace / differentiation | 0.25 | Is this already well-solved by existing commercial tools | A portfolio project solving an already-solved problem proves less |
| Technical feasibility (free-tool constraint) | 0.15 | Can this be meaningfully demonstrated with open/free tools in a reasonable timeframe | This is a portfolio project, not a funded startup |
| Fit with target skill signal | 0.10 | Does solving this specifically demonstrate "data reliability & trust," the stated goal of this project | The project's purpose is to prove this exact competency to employers |

*Weighting confirmed by Nish, 2026-09-20.*

### 2.2 Evaluation Matrix & Justification

Scored 1 (Low) – 2 (Medium) – 3 (High) per criterion, weighted by Section 2.1. Cell format: raw score (weighted contribution).

| Criterion | Weight | A. Retrieval Speed Bottleneck | B. Groundedness & Trust Deficit | C. Tabular Data Fragmentation |
|---|---|---|---|---|
| Stakes / severity | 0.25 | 2 (0.50) | 3 (0.75) | 2 (0.50) |
| Active demand | 0.25 | 3 (0.75) | 3 (0.75) | 2 (0.50) |
| Whitespace | 0.25 | 1 (0.25) | 2 (0.50) | 2 (0.50) |
| Feasibility (free tools) | 0.15 | 3 (0.45) | 2 (0.30) | 2 (0.30) |
| Skill-signal fit | 0.10 | 1 (0.10) | 3 (0.30) | 2 (0.20) |
| **Weighted Total** | | **2.05** | **2.60** | **2.00** |
| **Verdict** | | Not shortlisted | **Shortlisted** | Folded into B as root cause |

Archetype B wins decisively on the two highest-weighted criteria it scores best on (stakes and demand tie for top weight; it leads or ties on both), and its only weakness — feasibility — is a 0.15-weight criterion, so it doesn't swing the outcome.

### 2.3 Detailed justification for each archetype

**Archetype A — Retrieval Speed Bottleneck**
- Real pain: mid-market deal teams report being "buried under thousands of documents and weeks of manual review," and AI tools already save 63% of users six or more hours per week ([Hebbia, 2026](https://www.hebbia.com/resources/ai-solutions-for-due-diligence))
- Filings have objectively gotten longer: median 10-K word count more than doubled from ~23,000 words (1996) to over 49,000 (2013), with text now estimated to require 21.6 years of formal education to fully comprehend ([Dyer, Lang & Stice-Lawrence via CLS Blue Sky Blog, 2016](https://clsbluesky.law.columbia.edu/2016/05/05/the-ever-expanding-10-k-why-are-10-ks-getting-so-much-longer-and-does-it-matter/))
- But whitespace is low: this is exactly what Hebbia and AlphaSense already sell against ([Hebbia, 2026](https://www.hebbia.com/resources/financial-research-platforms); [AlphaSense, 2026](https://www.alpha-sense.com/resources/research-articles/ai-tools-for-financial-research/)), so a naive retrieval demo wouldn't differentiate this portfolio, and it doesn't showcase groundedness engineering — it's a search UX problem, not a reliability one

**Archetype B — AI Groundedness & Trust Deficit**
- Independent benchmark research shows GPT-4 answers ~89% of FinanceBench questions correctly under perfect (hand-curated) retrieval, but accuracy collapses to under 20% correct (over 80% failure) under realistic enterprise RAG conditions — "the 70-point retrieval problem" ([Presenc AI's analysis of the FinanceBench benchmark, 2026](https://presenc.ai/research/financial-ai-hallucination-rates-2026))
- The consequences are concrete, not hypothetical: one reported case had an AI tool fabricate a nonexistent tax document during an acquisition, undetected until a $1.5 million liability surfaced post-close, cutting the deal's value by 10% ([Development Corporate, 2026](https://developmentcorporate.com/corporate-development/ai-hallucination-rates-are-a-due-diligence-crisis/))
- This isn't finance-specific — it's a general failure mode of ungrounded LLM use on any high-stakes factual task: Stanford's RegLab found general-purpose LLMs hallucinate on a majority of specific, verifiable legal questions about random federal court cases — 69% of the time for GPT-3.5 and 88% for Llama 2 ([Stanford RegLab, "Large Legal Fictions," 2024](https://reglab.stanford.edu/publications/hlarge-legal-fictions-profiling-legal-hallucinations-in-large-language-models/))
- Buyers confirm this as their top concern directly: in McKinsey's 2026 State of AI Trust survey, 74% of respondents name inaccuracy a highly relevant AI risk — tied for the single top concern — and close to 67% cite security/risk concerns as the top barrier to scaling agentic AI adoption ([McKinsey, 2026](https://www.mckinsey.com/capabilities/tech-and-ai/our-insights/tech-forward/state-of-ai-trust-in-2026-shifting-to-the-agentic-era))
- Whitespace is only medium — commercial tools exist — but almost none publish their groundedness engineering or eval methodology publicly, which is the gap this portfolio project fills by being transparent about it

**Archetype C — Structured/Tabular Data Fragmentation**
- Real, well-documented technical failure mode: naive chunking of text-and-table documents is a known weak point for retrieval quality, which is why recent benchmarking work specifically evaluates retrieval strategies for text-and-table documents ([alphaXiv, "From BM25 to Corrective RAG," 2026](https://www.alphaxiv.org/abs/2604.01733v1))
- Better understood as a *root cause* of Archetype B than an independent product problem — no user wants "better table parsing" for its own sake, they want "an answer I can trust," and bad table parsing is one reason they can't currently get that
- Folded into Archetype B's scope as the primary technical driver of ungroundedness on numeric questions, rather than evaluated as a separate shortlist candidate

## 3. Problem Statement (Shortlisted)

### 3.1 What is the true problem?

Analysts and deal teams need to extract specific, high-stakes facts from SEC filings quickly, but AI tools fast enough to help are not, by default, trustworthy enough to rely on for that purpose — and the gap between "sounds right" and "is right" is largest precisely on the numeric, tabular, and footnoted content that due diligence cares about most.

### 3.2 How do we know it is a true problem?

Three independent lines of evidence converge:

- **Benchmark evidence:** real-world RAG accuracy on financial questions collapses from ~89% (ideal retrieval) to under 20% (realistic retrieval) ([Presenc AI / FinanceBench analysis, 2026](https://presenc.ai/research/financial-ai-hallucination-rates-2026)), and this generalizes beyond finance — Stanford RegLab found 69-88% hallucination rates on verifiable legal fact-lookup tasks, structurally the same kind of task as filing-based fact lookups ([Stanford RegLab, 2024](https://reglab.stanford.edu/publications/hlarge-legal-fictions-profiling-legal-hallucinations-in-large-language-models/))
- **Incident evidence:** this isn't theoretical — over 1,400 U.S. court cases have addressed AI-generated errors in the past three years, at a current pace of roughly 350-400 per quarter, despite judges repeatedly sanctioning the practice ([Scientific American, 2026](https://www.scientificamerican.com/article/why-lawyers-keep-citing-fake-cases-invented-by-ai/))
- **Demand-side evidence:** buyers confirm it as their top concern directly — 74% of enterprises name inaccuracy their most relevant AI risk ([McKinsey, 2026](https://www.mckinsey.com/capabilities/tech-and-ai/our-insights/tech-forward/state-of-ai-trust-in-2026-shifting-to-the-agentic-era))

### 3.3 Why should we solve this problem now?

Two forces are converging in 2026:

- Filings keep growing in length and complexity, pushing teams toward AI assistance whether or not that assistance is trustworthy ([CLS Blue Sky Blog, 2016](https://clsbluesky.law.columbia.edu/2016/05/05/the-ever-expanding-10-k-why-are-10-ks-getting-so-much-longer-and-does-it-matter/))
- Adoption pressure is rising faster than governance maturity: among enterprises not yet leading on gen AI, only 16% feel prepared on risk and governance and only 20% on technology infrastructure ([Deloitte, 2026](https://www.deloitte.com/us/en/insights/industry/financial-services/generative-ai-financial-services-pioneers.html))

That combination — rising reliance, low governance readiness — is exactly the window in which a well-designed trust architecture has the most to prove.

### 3.4 Impact of not solving this problem?

- **Deal level:** undetected fabrications can materially change deal economics, as in the $1.5M post-close liability example above ([Development Corporate, 2026](https://developmentcorporate.com/corporate-development/ai-hallucination-rates-are-a-due-diligence-crisis/))
- **Workforce level:** knowledge workers already spend an estimated 4.3 hours a week just verifying AI output — roughly $14,200/year per employee — which erodes the productivity gain AI was supposed to deliver in the first place (same source)
- **Trust level:** the problem compounds over time — among organizations that have already had an AI incident, nearly 60% rate their own response to it as unsatisfactory, per McKinsey, suggesting this gets harder to manage the longer it goes unaddressed, not easier ([McKinsey, 2026](https://www.mckinsey.com/capabilities/tech-and-ai/our-insights/tech-forward/state-of-ai-trust-in-2026-shifting-to-the-agentic-era))

### 3.5 What is the value generated by solving this problem?

- **For the business/employer evaluating this portfolio:** demonstrates the specific, hire-relevant skill of designing AI systems that fail safely and explicitly rather than confidently and silently — the exact competency gap Section 3.3's governance-readiness statistics show most organizations currently have
- **For the end user** (the analyst persona in Part B): a tool that says "not disclosed in this filing" instead of guessing turns AI from a source of new risk into a genuine first-pass triage aid — the difference between a tool analysts are allowed to rely on and one they have to double-check line by line anyway

---

# PART B — SOLUTION

## 1. Solution Overview

The AI Due Diligence Copilot is a retrieval-augmented question-answering system over a small set of SEC 10-K filings (Apple, Microsoft, NVIDIA for v1).

How it works:
1. A user asks a natural-language question about a filing
2. The system retrieves relevant passages using a hybrid of keyword (BM25) and vector similarity search — chosen because pure embedding similarity underperforms on exact numeric and defined-term lookups, which financial questions are full of
3. It generates an answer strictly grounded in what was retrieved, with an inline citation to the source page/section
4. It explicitly refuses to answer, rather than guessing, when retrieval confidence is low or the question asks about something the filing doesn't disclose

The refusal behavior (step 4) is a designed, tested feature with its own evaluation metric (refusal accuracy) — not a fallback bolted on afterward.

## 2. Key Features & Benefits

| Feature | Benefit |
|---|---|
| Table-aware document parsing | Numeric answers (segment revenue, margins) stay accurate instead of being silently corrupted by naive text chunking |
| Hybrid retrieval (BM25 + vector) | Catches exact-match numeric/defined-term queries that pure semantic search misses |
| Inline citation on every claim | Lets the analyst verify in seconds instead of re-reading the filing from scratch |
| Explicit refusal policy | Converts "confidently wrong" into "honestly uncertain," which is what makes the tool safe to rely on for first-pass triage |
| Public eval report (Faithfulness, Context Precision, Answer Relevance, Refusal Accuracy) | Makes the tool's reliability legible and auditable rather than a black-box claim |

## 3. Value Proposition

- **For the business** (a firm evaluating or deploying a tool like this): faster first-pass diligence without inheriting the undisclosed-fabrication risk documented in Section 3.4 — explicitly scoped to reduce analyst verification burden (the 4.3 hrs/week, ~$14,200/year figure from Section 3.4) rather than to replace judgment entirely
- **For the user** (the analyst, detailed in Section 6): a fast, source-linked first answer to a specific factual question, with an honest signal on the (frequent) cases where the filing doesn't actually say — turning hours of manual page-hunting into a verifiable few minutes, consistent with the 63%-of-users-save-6+-hours/week pattern reported for similar tools ([Hebbia, 2026](https://www.hebbia.com/resources/ai-solutions-for-due-diligence))

## 4. Business Outcomes & Product Outcomes

**Business outcomes:**
- Demonstrated, portfolio-visible competence in AI trust/groundedness engineering — the direct goal of this project
- A defensible answer to "how do you know this doesn't hallucinate," backed by a published eval methodology, not just a claim

**Product outcomes:**
- High faithfulness and context precision on the golden eval set (targets in Section 8)
- High refusal accuracy specifically on the deliberately-unanswerable subset of eval questions
- Every factual claim traceable to a specific filing location

## 5. Target Users

Three candidate user groups:

| User group | Description | Why relevant |
|---|---|---|
| **PE/VC deal-team associates** | Junior-to-mid analysts running first-pass diligence on acquisition targets under deal-timeline pressure | Highest stakes (Section 3.4's cost-of-error evidence is drawn largely from this context); highest existing tool spend (Hebbia, AlphaSense target this segment directly) |
| Sell-side equity research associates | Analysts producing recurring coverage notes on public companies, referencing filings every earnings cycle | High frequency of the underlying task, but lower single-instance stakes than a live deal |
| Corporate development / competitive-intelligence analysts | In-house analysts benchmarking competitors' filings for strategy or M&A screening | Real need, but smaller and less evidenced market than the other two |

Prioritization criteria: severity of consequence if wrong (deal-breaking vs. inconvenient), frequency of the underlying task, and strength of existing market evidence that this group already pays for adjacent tools.

**Recommendation (confirmed by Nish, 2026-09-20): PE/VC deal-team associates** — highest severity (real, cited $ impact of errors) and strongest market evidence (the exact segment Hebbia and AlphaSense already sell to).

## 6. Target User Persona

*(Illustrative composite persona, not a real individual — built from the analyst-workflow research cited above, standard practice for a portfolio project at this stage.)*

**Priya Menon, 27 — "the associate who has to be right by 6pm"**

| Attribute | Detail |
|---|---|
| Role | Associate, mid-market private equity fund |
| Experience | 3 years post-MBA; works 2-3 live deals concurrently |
| Behaviors | Reads filings under deadline pressure as part of a team dividing a data room; cross-checks anything she'll put her name on in an IC memo; currently uses Ctrl+F, informal ChatGPT drafting help (never for citable numbers), and senior-analyst tribal knowledge |
| Needs | A fast first answer to a specific question (e.g. "what's the customer concentration risk disclosed here") verifiable in seconds; an explicit signal when the answer isn't in the document, since guessing wrong in an IC memo is a career risk |
| Frustrations | General-purpose AI tools that answer confidently regardless of whether they actually found the fact; manual search working but not scaling across three simultaneous live deals |

## 7. Target User Journey

| Stage | Actions | Thoughts | Needs |
|---|---|---|---|
| Deal kickoff | Gets data room access, filing list assigned by deal lead | "How much of this can I actually get through before the IC deadline?" | Fast orientation to what's in scope |
| Initial screening | Skims filings for obvious red flags | "Where do I even start on a 200-page document?" | A way to ask targeted questions instead of reading linearly |
| Deep-dive diligence | Asks specific factual questions (revenue by segment, litigation exposure, debt covenants) | "Is this number actually right, and where did it come from?" | Grounded answers with verifiable citations |
| Verification | Spot-checks AI-surfaced answers against source pages | "I need to be able to defend this in the IC memo." | Inline citations that make spot-checking fast, not a research project of its own |
| Synthesis | Writes findings into IC memo / diligence report | "What am I confident enough to put my name on?" | Clear signal on what's confirmed vs. uncertain vs. not disclosed |
| Post-mortem (if a deal goes wrong) | Reviews what was missed | "Did we miss something that was actually in the filing?" | An audit trail of what was asked and what the system did/didn't find |

## 8. Goals & Success Metrics

Numeric targets below are provisional defaults grounded in the general risk-tiering principle that high-stakes, low-error-tolerance use cases (this one, per Section 3) warrant stricter thresholds than a typical RAG deployment ([Ragas evaluation methodology guidance, 2026](https://saulius.io/blog/ragas-rag-evaluation-metrics-llm-judge)). No universal published "industry standard" number exists for these metrics — that same guidance explicitly warns against treating any fixed score as a universal pass/fail bar — so treat these as a starting hypothesis to be validated and adjusted once the actual baseline eval run (`EVALS_AND_BENCHMARKS.md`) is in hand, not as an external benchmark you're being held to.

| Goal | Metric | Provisional Target | Rationale |
|---|---|---|---|
| Answers are trustworthy | Faithfulness (RAGAS/DeepEval) | ≥ 0.90 | High-stakes tier: unsupported claims here risk real financial decisions, not just minor UX friction |
| Retrieval quality | Context Precision | ≥ 0.85 | Retrieved chunks should be mostly relevant; some noise tolerance is reasonable pre-optimization |
| Answers address the question asked | Answer Relevance | ≥ 0.85 | Standard bar for a usable, on-topic QA system |
| The system knows what it doesn't know | Refusal Accuracy (on deliberately-unanswerable questions) | ≥ 0.90 | This is the core trust mechanic (Section 5, PRD.md) — it should fail closed, not open |
| The system doesn't over-refuse | False-Refusal Rate (on answerable questions) | ≤ 10% | A system that refuses everything to game refusal accuracy is not useful; this caps that failure mode |
| Numeric answers are structurally correct | Exact-match rate, table-derived numeric answers vs. source | ≥ 0.95 | These are the most verifiable, highest-stakes claim type — the bar should be near-perfect |
| Portfolio credibility | Public, reproducible eval report a hiring manager can inspect | Published in `EVALS_AND_BENCHMARKS.md` | You — this is the differentiator per Section 2.3 |

---

## References

- [Hebbia — The Top 10 AI Solutions for Due Diligence (2026)](https://www.hebbia.com/resources/ai-solutions-for-due-diligence)
- [Hebbia — Top 12 AI Financial Research Platforms (2026)](https://www.hebbia.com/resources/financial-research-platforms)
- [AlphaSense — Top 10 AI Tools for Financial Analysis (2026)](https://www.alpha-sense.com/resources/research-articles/ai-tools-for-financial-research/)
- [CLS Blue Sky Blog — The Ever-Expanding 10-K (2016), summarizing Dyer, Lang & Stice-Lawrence, *Accounting Horizons*](https://clsbluesky.law.columbia.edu/2016/05/05/the-ever-expanding-10-k-why-are-10-ks-getting-so-much-longer-and-does-it-matter/)
- [Development Corporate — AI Hallucination Rates Are a Due Diligence Crisis (2026)](https://developmentcorporate.com/corporate-development/ai-hallucination-rates-are-a-due-diligence-crisis/)
- [Scientific American — Why Lawyers Keep Citing Fake Cases Invented by AI (2026)](https://www.scientificamerican.com/article/why-lawyers-keep-citing-fake-cases-invented-by-ai/)
- [Stanford RegLab — Large Legal Fictions: Profiling Legal Hallucinations in Large Language Models (2024)](https://reglab.stanford.edu/publications/hlarge-legal-fictions-profiling-legal-hallucinations-in-large-language-models/)
- [McKinsey — State of AI Trust in 2026: Shifting to the Agentic Era](https://www.mckinsey.com/capabilities/tech-and-ai/our-insights/tech-forward/state-of-ai-trust-in-2026-shifting-to-the-agentic-era)
- [Deloitte — Harnessing Gen AI in Financial Services: Why Pioneers Lead the Way (2026)](https://www.deloitte.com/us/en/insights/industry/financial-services/generative-ai-financial-services-pioneers.html)
- [Presenc AI — Financial AI Hallucination Rates 2026: FinanceBench, BloombergGPT, RAG Realities](https://presenc.ai/research/financial-ai-hallucination-rates-2026)
- [MarketsandMarkets via PR Newswire — Document AI Market Worth $35.34 Billion by 2031](https://www.prnewswire.co.uk/news-releases/document-ai-market-worth-35-34-billion-by-2031--report-by-marketsandmarkets-302883042.html)
- [alphaXiv — From BM25 to Corrective RAG: Benchmarking Retrieval Strategies for Text-and-Table Documents (2026)](https://www.alphaxiv.org/abs/2604.01733v1)
- [Ragas evaluation metrics explained — Saulius blog (2026)](https://saulius.io/blog/ragas-rag-evaluation-metrics-llm-judge)

### Sourcing verification note

Per your request, I checked the Stanford RegLab and Deloitte statistics against primary sources:

- **Stanford RegLab — verified and corrected.** The primary paper ("Large Legal Fictions") reports GPT-3.5 hallucinating on 69% of specific, verifiable questions about random federal court cases, and Llama 2 on 88% — under those exact conditions. This is now cited directly above with the precise figures and task context. I could not verify the "78% for M&A-specific legal work" or "70-170x vendor benchmark" figures from my earlier draft against any primary source, so **I removed both** rather than publish them unverified.
- **Deloitte "47% of enterprise AI users made a decision based on hallucinated content" — could not verify, removed.** I checked Deloitte's 2026 State of AI in the Enterprise press release and their Q4 State of Generative AI press release directly; neither contains this statistic or anything close to it. The same applies to the earlier "0.5% error rate = millions in lost deal value, per Deloitte" claim. Both were removed from the document rather than left in on secondhand authority. The remaining Deloitte citation (governance/infrastructure preparedness percentages, Sections 3.3) is drawn from a Deloitte report I did fetch and verify directly, so it stays.

If you want the removed claims restored, the original secondary source (Development Corporate) is still listed in the earlier draft you have, but I'd recommend leaving them out of a public repo unless you can trace them to Deloitte's actual publication yourself.
