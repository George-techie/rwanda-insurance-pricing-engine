# ASSAR Insurance Pricing & Information Engine

## Technical Report: Architecture, Data Design, Retrieval, and Audit

This report documents the ASSAR pricing-and-information system end to end: what
it does, how it is built, the design choices behind the data and retrieval
layers, and a full audit table mapping every SQL table back to its source table
and page in the manual. The source throughout is the Association of Insurers of
Rwanda (ASSAR) Approved General Business Pricing Manual for the Rwandan
Insurance Industry, Version 3, effective 25 January 2021 (81 pages).

---

## 1. Introduction

Insurance pricing manuals are written for people to read, not for machines to
query. The ASSAR manual interleaves dense numeric rate tables, a 104-row fire
grid, transit and marine commodity grids, liability and engineering rates,
bonds, political-violence rates, and registers of large risks, with paragraphs
of underwriting prose: definitions, conditions, warranties, exclusions, and
guidance. A reader who wants a single number has to find the right page; a
reader who wants to understand a clause has to read several.

This system turns that manual into something a client or underwriter can query
in plain language. It answers two distinct kinds of question. The first is
quantitative and exact: what minimum rate applies to a risk, what multiplier
applies for an indemnity period, what the mandatory excess is, what premium a
given cover costs. The second is qualitative: what a term means, what is
excluded, which warranty must be incorporated. The system is deliberately built
so that the exact numbers are served exactly and deterministically, while the
open-ended questions are answered fluently and with citations.

The result is a conversational assistant with three faces: a chat that holds a
multi-turn conversation, a structured quote calculator, and a browsable
database. All of it is grounded in the manual, and every premium is computed by
tested code rather than guessed by a language model.

---

## 2. System Architecture

The architecture follows one principle: numbers and prose are stored and
retrieved differently, and a language model orchestrates but never computes.

A free-text question first reaches a Manager/router that classifies it. If it
is a pricing or number request, it is sent to the Quant layer: typed Python
calculators that read exact rates from SQLite and compose the premium, plus
text-to-SQL lookups against the per-table information database. If it is a
concept question, it is sent to the Retriever, which performs semantic search
over the manual's prose. The language model then composes a final answer,
citing manual pages and showing the exact rates used; a Verifier step checks
the unit of each figure (percent vs per-mille vs franc amount) and that prose
claims are grounded in retrieved passages.

```
                          +-----------------------------+
        user question --> |      Manager / Router       |
                          | (classify: number vs prose) |
                          +--------------+--------------+
                            |                          |
                   number / quote                  concept / definition
                            |                          |
                            v                          v
              +----------------------------+  +----------------------------+
              |   Quant  (typed Python)    |  |   Retriever  (ChromaDB)    |
              |  pricing calculators +     |  |  semantic search over the  |
              |  read-only text-to-SQL     |  |  manual prose (embeddings) |
              +-------------+--------------+  +-------------+--------------+
                            |                               |
                            v                               v
              +----------------------------+  +----------------------------+
              | SQLite rate tables         |  | corpus.md section chunks   |
              | assar.db / assar_info.db   |  | + page citations           |
              +-------------+--------------+  +-------------+--------------+
                             \                             /
                              v                           v
                          +----------------------------------+
                          |  LLM composes a cited answer;    |
                          |  Verifier checks units & sources |
                          +----------------------------------+
```

The deliberate trade-off is determinism and auditability over end-to-end neural
generation. A purely generative system would be simpler but impossible to trust
for binding figures, because embeddings blur exact values and a model reading a
rate out of retrieved text can round or transcribe it wrong. By confining the
model to understanding the request, selecting a tool, and phrasing the result,
the financially sensitive arithmetic stays under tested, reproducible control.
A separate quote path bypasses the model entirely and calls the calculators
directly, so pricing works even with no language-model key configured.

The language model is pluggable (Groq, Ollama, or Hugging Face via one
OpenAI-compatible client). Embeddings always run locally. Premiums are produced
by typed functions covered by 39 deterministic tests.

---

## 3. Data Design Choices

The system keeps two SQLite databases, both built from the same manual but
shaped for different consumers. This is the central data decision.

The first, assar.db, uses four generic tables. A single rate table holds most
per-category rates, namespaced by a scheme column (fire, public_liability,
aviation, bond, pvt, and so on). Separate tables hold the two-dimensional
transit commodity grids, the ordered discount and multiplier schedules, and
per-product constants such as minimum premiums and mandatory excesses. This
compact, normalized shape is convenient for the pricing calculators to join and
iterate in code, and it is what the 39 tests pin.

The second, assar_info.db, inverts the design: one cleanly named SQL table per
table in the manual, 45 in total. A question such as "what is the fire rate for
a bank" maps naturally to a query against a fire_allied_perils table with a
risk_category column, so a text-to-SQL agent does not need to know an internal
namespacing convention. Descriptive table and column names are, in effect, the
schema documentation the model reads to ground its query.

Three further choices shape the data. First, numbers were verified before being
reused: the rate values were spot-checked cell by cell against the source PDF,
and the information database reuses those verified values rather than
re-transcribing them, confining new manual transcription to the large-risk
registers. Second, labels in the information database are exact verbatim strings
from the manual, including punctuation, so an agent's text matching lines up
with the source wording; a build-time guard fails if any label list drifts out
of alignment with its verified values. Third, units are made explicit: most
columns carry their unit in the column name (rate_pct, rate_per_mille,
insured_value_rwf), and a data_dictionary table documents the unit of every
column, so a percentage is never mistaken for a per-mille rate, the easiest
order-of-magnitude error in this manual.

---

## 4. Chunking Strategy

The prose corpus is chunked for retrieval with a structure-aware,
section-based strategy rather than a fixed page or character window, because
the manual is a long, structured document whose logical units are sections that
often span page breaks.

The corpus builder extracts page text into a Markdown corpus, tagging each page
so chunks can be cited. The chunker then detects heading runs, the manual's
section titles such as "PRICING OF CONSEQUENTIAL LOSS" or "FULL VALUE BASIS",
including titles that wrap onto a second line, and groups each section's body
together even across page boundaries. Long sections are sub-split on sentence
boundaries at roughly 1,600 characters with 200 characters of overlap. Every
chunk is prefixed with its section title, which gives the embedding model
context about what the chunk is, and carries its page anchor for citation plus
the section name in metadata. Front-matter such as the cover page and table of
contents is dropped, and stray PDF bullet glyphs are stripped.

The most important chunking decision is what is excluded: the numeric rate
tables are not embedded at all. They live in SQLite and are served exactly.
This removes the single biggest failure mode for a financial document, an
embedding fuzzing a value like 0.3144 percent, and it is why the corpus holds
only definitions, conditions, warranties, and guidance.

---

## 5. Retrieval Strategy

Concept questions are answered by retrieval-augmented generation over the prose
corpus. Chunks are embedded locally with a sentence-transformers model
(BAAI/bge-small-en-v1.5; a multilingual model is a drop-in for Kinyarwanda or
French) and stored in a persistent ChromaDB collection using cosine similarity.
At query time the same model embeds the question, the top matches are fetched,
and the language model composes an answer grounded in those passages with page
citations. The retrieved section title and page travel with each result, so an
answer can point the reader to the exact place in the manual.

The router is hybrid. Number and quote questions are routed to the Quant layer,
which either calls a typed pricing calculator or runs a read-only SQL lookup
against the information database; concept questions are routed to the retriever.
Lookups are made robust with scheme-scoped fuzzy matching, so an approximate
category such as "hotel" resolves to the valid key, and the dispatcher coerces
string numbers and drops arguments a calculator does not accept. The model is
restricted to general (non-life) business and declines motor, life, or medical
questions rather than inventing a quote. The conversation is multi-turn: prior
turns are passed back so a follow-up like "and for a bank?" keeps context.

---

## 6. Audit: SQL Tables Mapped to the Source Manual

The table below maps every table in the information database (assar_info.db) to
the table or section it was built from in the ASSAR manual and the page(s) where
that source appears, so the data can be verified against the PDF. SQL names are
exactly as they appear in the database.

{{AUDIT_TABLE}}

Audit notes. Pricing values are reused from the verified seed used by the
calculators; the information database adds verbatim labels and the large-risk
registers. Three tables are derived rather than transcribed from a single table:
market_parameters gathers scattered market-wide figures, minimum_premiums
gathers per-class minimums, and data_dictionary is engine metadata documenting
units. PVT rates are stored in per mille; every other class is percent.

---

## 7. Deployment and User Interface

The system runs as a Streamlit web application launched with a single command,
backed by the two SQLite files and a local ChromaDB store. Setup installs the
requirements, copies the environment template, and adds a language-model key
(Groq by default; the key lives in a gitignored .env). The data is built in
three steps: the pricing database from the transcribed tables, the information
database (one table per manual table), and the prose corpus plus its vector
store, after which the app is started. The embedding model is pre-warmed at
startup so the first chat message is not a silent wait. The databases are
committed so the project runs out of the box.

The interface is a wide layout with a themed banner and a sidebar that shows
live status: the rate database and its row count, the information engine and its
45 tables, the language-model backend and whether a key is set, and whether the
vector store is built. A standing caution reminds users to verify rates against
the source manual before binding cover.

---

## 8. What It Does, Section by Section

Chat. The primary, client-facing surface is a multi-turn chat with conversation
memory and a strip of product tiles showing the classes covered. A question is
classified and routed; quote answers show a card with the product, the exact
rate and unit, and the final premium, with a collapsible breakdown and a panel
of cited manual passages. Because it remembers the conversation, follow-up
questions work naturally. It can quote every class in the manual that has a
calculator, twenty-one tools in all, and answers concept questions from the
prose with page citations; out-of-scope questions are politely declined.

Get a Quote. A deterministic calculator with dropdowns for the main products. It
bypasses the language model entirely and calls the typed calculators directly,
so it always works and always returns exact figures with a full breakdown and
the applicable excess. This is the reliable path for a precise quote.

Database. A transparency surface that lets a user browse and run read-only SQL
against either database: the four-table pricing engine, or the 45-table
information engine with its example queries and the data_dictionary of units.
Results can be filtered, searched, and downloaded as CSV. Only SELECT and WITH
queries are allowed, on a genuinely read-only connection.

Underneath all three, the pricing calculators read exact rates from SQLite and
compose premiums with minimum-premium floors, mandatory excesses, short-period
factors, and policy fees as the manual specifies, and they are covered by
deterministic tests so a wrong cell or a broken composition is caught
immediately. The whole system is designed to be deterministic where the numbers
must be exact, fluent where the questions are open-ended, and auditable
throughout. As always, the figures should be verified against the source manual
before binding cover.

---

## 9. Pricing Models for the Main Products (Get a Quote)

Every premium on the Get a Quote tab is produced by a typed Python calculator
that reads exact rates from SQLite; no language model is involved. The
calculators share a common skeleton, then each product applies its own
loadings, discounts, and floors as the manual specifies.

```
premium = sum_insured x rate            (rate /100 for percent, /1000 for per mille)
        + loadings (e.g. industrial process load)
        - discounts (FEA, voluntary deductible, security, clause/mode, stock)
        x multipliers (first-loss, multi-trip, indemnity period, duration load)
        x short-period factor            (fraction of annual premium)
        floored at the class minimum premium
        + policy fee (Rwf5,000, where the class charges one)
        = final premium (net of taxes)
```

### Fire and Allied Perils

The base rate is the occupancy rate from the fire grid: the standard-fire column
(fire, lightning, explosion) or the fire-and-all-special-perils column. The fire
portion is sum insured times that rate. Industrial risks add a 0.025 percent
process loading plus a flat Rwf25,000 extensions loading, neither of which
enjoys the FEA discount. A 15 percent Fire Extinguishing Appliances discount
applies to the fire portion only. A voluntary deductible then earns a banded
discount (capped at 33.33 percent of the excess amount). A short-period factor
and the policy fee complete the premium. All fire material-damage cover is
subject to the Condition of Average.

### Public, Employers, Product, and Professional Liability

Premium is the selected limit of indemnity times the occupation rate, adjusted
by a short-period factor and floored at the class minimum premium (Rwf100,000
for public, employers, and product; Rwf200,000 for professional indemnity, or
Rwf25,000 for insurance agents). Professional indemnity carries a 5 percent
mandatory excess (minimum Rwf200,000).

### Goods in Transit and Transporters Liability

The base rate comes from the commodity grid, selected by cover type (all-risks
or road-accident-only) and whether the cargo is containerized. Transporters
liability outside Rwanda loads the rate by 30 percent. For multiple trips the
annual premium is scaled by trip period (30 percent up to 3 months, 60 percent
up to 6, 90 percent up to 9, 100 percent up to 12). A policy fee is added.

### Marine Cargo

The base is the Institute Cargo Clause A rate for the commodity and packing. A
transit-mode discount is applied first (road minus 10 percent, sea minus 20
percent, air minus 30 percent, combined none), then a clause discount (Clause B
minus 25 percent, Clause C minus 35 percent, Clause A none). A policy fee is
added.

### Personal Accident and Group Personal Accident

Each benefit is priced off the class base rate: death and total permanent
disability at the base rate, total temporary disability at 15 percent of it, and
medical and funeral expenses at ten times it. The selected benefits are summed
against the capital sum, a short-period factor is applied, and the result is
floored at the minimum premium (PA Rwf25,000, or Rwf15,000 for an interning
student; GPA Rwf50,000, or Rwf30,000 for a student).

### Bonds and Guarantees

Premium is the bond value times the bond-type rate. Providing 100 percent cash
collateral reduces the rate to 3 percent. The premium is floored at Rwf10,000
for a bid bond and Rwf30,000 for other bonds. Bonds carry the full annual rate
for any period: no short-period or pro-rata reduction applies.

### Political Violence and Terrorism (PVT)

PVT rates are quoted per mille, not percent, so the premium is sum insured times
the rate divided by one thousand. Approved security features can earn a discount
of up to 10 percent. The mandatory deductible is 5 percent of each loss, minimum
0.5 percent of the sum insured, with a floor of Rwf50,000.

### Engineering: Contractors All Risks and Erection All Risks

Premium is the contract value times the project-type rate. Projects running
beyond twelve months are loaded by 25 percent for each additional six-month
block. Third-party liability is included while its limit stays within 15 percent
of the contract value; above that it is rated separately at 0.2 percent. A
policy fee is added.

### Machinery Breakdown

Premium is the sum insured times the machine or industry rate, plus a policy
fee. The mandatory excess is 10 percent of each loss (minimum Rwf500,000) for
sums insured above Rwf5,000,000, otherwise 5 percent (minimum Rwf250,000).

### Contractors Plant and Machinery (CPM)

The rate is read from the hazard-class by plant-group matrix: plant groups are
cranes (1), mobile plant (2), and non-mobile plant (3); hazard classes A, B, and
C reflect terrain and exposure. A CPM-specific short-period scale and a policy
fee apply. The mandatory excess is 10 percent of claim, minimum Rwf500,000.

### Burglary and Theft

The full-value rate is 0.3 percent for ordinary goods and 0.5 percent for
high-value goods. On a first-loss basis a multiplier from the first-loss
schedule is applied according to the ratio of first-loss sum insured to full
value. A stock-declaration basis earns a 10 percent discount. A short-period
factor and policy fee apply; the mandatory excess is 10 percent of each loss,
minimum Rwf50,000.

### Source anchors for the pricing rules

Each rule above is taken from a specific point in the manual; the page(s) are
listed below so the methodology can be verified against the ASSAR document.
This covers the pricing rules and loadings; the underlying rate values are
spot-checked against the manual and should be confirmed cell by cell before
binding cover.

{{SECTION9_SOURCES}}

---

End of report.
