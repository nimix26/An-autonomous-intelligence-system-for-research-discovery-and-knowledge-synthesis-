<p align="center">
  <h1 align="center">🧠 CogniView.AI</h1>
  <p align="center">
    <strong>AI-Powered Research Paper Discovery, Summarization & Analysis Platform</strong>
  </p>
  <p align="center">
    <em>Discover the most relevant papers on any topic using a 7-stage hybrid intelligence pipeline — then summarize, compare, or implement them with one click.</em>
  </p>
</p>

<p align="center">
  <img src="https://img.shields.io/badge/Python-3.10+-3776AB?logo=python&logoColor=white" />
  <img src="https://img.shields.io/badge/React-19-61DAFB?logo=react&logoColor=black" />
  <img src="https://img.shields.io/badge/FastAPI-0.110+-009688?logo=fastapi&logoColor=white" />
  <img src="https://img.shields.io/badge/Vite-8-646CFF?logo=vite&logoColor=white" />
  <img src="https://img.shields.io/badge/Three.js-r183-000000?logo=three.js" />
  <img src="https://img.shields.io/badge/SPECTER_2.0-Semantic_Ranking-orange" />
</p>

---

## 📋 Table of Contents

- [Overview](#-overview)
- [Key Features](#-key-features)
- [Architecture](#-architecture)
- [7-Stage Discovery Pipeline](#-7-stage-discovery-pipeline)
- [Analysis Modes](#-analysis-modes)
- [Tech Stack](#-tech-stack)
- [Project Structure](#-project-structure)
- [Setup & Installation](#-setup--installation)
- [Configuration](#-configuration)
- [API Reference](#-api-reference)
- [Frontend](#-frontend)
- [Core Modules](#-core-modules)
- [License](#-license)

---

## 🔭 Overview

**CogniView.AI** is a full-stack research intelligence platform that automates the process of discovering, understanding, and analyzing academic papers. Given any research topic, it:

1. **Discovers** the most relevant papers across Semantic Scholar, OpenAlex, and ArXiv using a sophisticated 7-stage pipeline with SPECTER 2.0 semantic ranking.
2. **Downloads & parses** full-text PDFs, splitting them into page-level chunks for deep analysis.
3. **Summarizes** papers with role-adapted, depth-aware LLM analysis — extracting methodology, results, limitations, key insights, and all visual elements (figures, tables, equations).
4. **Compares** up to 5 papers side-by-side with structured contribution analysis and research gap identification.
5. **Generates implementation code** by extracting techniques, parameters, and code snippets from up to 10 papers.

The frontend features a **cinematic 3D scroll-driven landing page** (Three.js + React Three Fiber) and a **premium analysis dashboard** with split-pane PDF viewing, tabbed sections, and inline markdown rendering.

---

## ✨ Key Features

| Feature | Description |
|---|---|
| **7-Stage Discovery Pipeline** | Query profiling → Adaptive seeding → Lexical + Citation graph + Semantic retrieval → Quality filter → Multi-signal scoring → MMR diversification → LLM curation |
| **SPECTER 2.0 Ranking** | Papers ranked by cosine similarity against multi-anchor embeddings (query + seeds + concepts + alternative phrasings) |
| **Hybrid Keyword Extraction** | KeyBERT per-paper extraction + spaCy POS filtering + SentenceTransformer similarity ranking + LLM selection |
| **Chunked PDF Analysis** | Full-text PDFs split into 2–3 page chunks with rolling context for comprehensive LLM summarization |
| **Visual Element Grouping** | Figures, tables, and equations extracted, grouped by semantic similarity, and explained in plain language |
| **Role-Based Adaptation** | Content adapted for Learner, Educator, or Researcher personas with configurable depth and format |
| **PDF Upload & Direct Analysis** | Upload your own PDFs to bypass discovery and go straight to summarization |
| **Interactive PDF Viewer** | Click any visual element in the dashboard to jump to its exact page in a split-pane PDF viewer |
| **3D Landing Page** | Cinematic scroll-driven animation: paper stacks → cloud cover → neural network processing → output generation |
| **Multi-LLM Architecture** | Separate LLM endpoints for text, discovery, judging, code, image, graph, and equation analysis |

---

## 🏗 Architecture

```
┌─────────────────────────────────────────────────────────────────┐
│                      FRONTEND (Vite + React 19)                 │
│                                                                 │
│  ┌──────────────┐  ┌───────────────┐  ┌───────────────────────┐ │
│  │  App.jsx     │  │  Dashboard    │  │  Dashboard-2          │ │
│  │  3D Landing  │──│  Search +     │──│  Analysis Results     │ │
│  │  Three.js    │  │  Discovery    │  │  PDF Viewer           │ │
│  └──────────────┘  └───────────────┘  └───────────────────────┘ │
└──────────────────────────┬──────────────────────────────────────┘
                           │ HTTP (localhost:5173 → :8000)
┌──────────────────────────▼──────────────────────────────────────┐
│                    BACKEND (FastAPI + Uvicorn)                   │
│                                                                 │
│  ┌─────────┐  ┌──────────────┐  ┌──────────────────────────┐   │
│  │ api.py  │──│ orchestrator │──│ core/                    │   │
│  │ Routes  │  │ .py          │  │  ├── llm_service.py      │   │
│  │         │  │ 7-Stage      │  │  ├── database_searcher   │   │
│  │         │  │ Pipeline     │  │  ├── specter_ranker      │   │
│  │         │  │              │  │  ├── keyword_generator   │   │
│  │         │  │              │  │  ├── chunked_processor   │   │
│  │         │  │              │  │  ├── query_profiler      │   │
│  │         │  │              │  │  ├── citation_graph      │   │
│  │         │  │              │  │  ├── semantic_retriever  │   │
│  │         │  │              │  │  ├── quality_filter      │   │
│  │         │  │              │  │  ├── mmr_diversifier     │   │
│  │         │  │              │  │  ├── scoring.py          │   │
│  │         │  │              │  │  ├── pdf_downloader      │   │
│  │         │  │              │  │  ├── pdf_parser          │   │
│  │         │  │              │  │  └── visual_grouper      │   │
│  └─────────┘  └──────────────┘  └──────────────────────────┘   │
└─────────────────────────────────────────────────────────────────┘
       │                    │                    │
       ▼                    ▼                    ▼
 ┌───────────┐     ┌──────────────┐     ┌──────────────┐
 │ LLM APIs  │     │ Paper APIs   │     │ NLP Models   │
 │ SambaNova │     │ Semantic S.  │     │ SPECTER 2.0  │
 │ DeepSeek  │     │ OpenAlex     │     │ KeyBERT      │
 │ Gemma     │     │ ArXiv        │     │ spaCy        │
 │ GPT-OSS   │     │ Unpaywall    │     │ MiniLM-L6    │
 └───────────┘     └──────────────┘     └──────────────┘
```

---

## 🔬 7-Stage Discovery Pipeline

The heart of CogniView.AI is a **universal 7-stage research discovery pipeline** (`orchestrator.py`) that finds the most relevant papers for any topic across any academic domain.

### Stage 0 — Query Profiling
> *Adaptive thresholds per query*

An LLM classifies the query across multiple dimensions:
- **Primary/sub domain**, **query type** (broad field, specific method, application, phenomenon, open problem)
- **Breadth** (0–1 scale), **temporal focus**, **interdisciplinary** flag
- **Alternative phrasings**, **paradigms**, **adjacent domains**

These drive all downstream thresholds: quality percentile, MMR lambda, seed count, recency weights.

### Stage 1 — Adaptive Seeding
> *2–6 seeds, paradigm-aware, API-verified*

An LLM suggests foundational/high-impact seed papers covering different paradigms of the topic. Each suggestion is verified against Semantic Scholar and OpenAlex to ensure they are real, published papers. If no seeds verify, the system falls back to pure keyword search.

### Stage 2A — Lexical Retrieval + Concept Expansion
> *Keywords + concepts + alternative phrasings*

A **3-stage hybrid keyword pipeline** generates search terms:
1. **KeyBERT** extracts 10 keywords per seed paper (30 total) with spaCy POS filtering
2. **LLM** selects the best 5 search keywords from all candidates
3. **Post-validation** removes off-topic, duplicate, and generic terms

Additionally, the LLM generates 5 **adjacent research concepts** with different vocabulary to cover blind spots. All terms are used to query Semantic Scholar and OpenAlex.

### Stage 2B — Citation Graph Expansion
> *References + citations + co-citations*

Traverses the citation network of seed papers via the Semantic Scholar API:
- Outgoing references (papers the seeds cite)
- Incoming citations (papers that cite the seeds)
- Co-citations (papers frequently cited alongside the seeds)

### Stage 2C — Semantic Retrieval
> *Semantic Scholar Recommendations API*

Uses the Semantic Scholar Recommendations API with seed paper IDs as positive examples to find semantically similar papers that may have been missed by lexical search and citation traversal.

### Stage 3 — Merge + Deduplicate + Quality Filter
> *Percentile-based, pool-relative*

All papers from channels A, B, and C are merged and deduplicated by normalized title. A **relative quality filter** removes papers below a configurable citation percentile threshold (adapts to query breadth). Seeds are always preserved.

### Stage 4 — Multi-Signal Scoring
> *Pool-normalized, SPECTER 2.0 embeddings*

Each paper is scored using a weighted combination of signals:
- **SPECTER 2.0 semantic similarity** to a multi-anchor query embedding (query + seeds + concepts + alt phrasings + domain)
- **LLM relevance judgement** (batch scoring with DeepSeek)
- **Citation velocity**, **venue quality**, **channel overlap** (papers found by multiple channels score higher)

### Stage 5 — MMR Diversification
> *Maximal Marginal Relevance*

Applies MMR-based selection to ensure the final set covers diverse aspects of the topic rather than clustering around a single sub-area. The lambda parameter is derived from the query's breadth score.

### Stage 6 — Constrained LLM Curator
> *Final selection with fallback*

An LLM reviews the top candidates and selects the final set, ensuring coverage, quality, and diversity. Falls back to score-ordered selection if the LLM call fails.

**Post-processing:** PDF URLs are resolved via multi-source fallback (ArXiv, Unpaywall, OpenAlex OA), and relevance scores are attached.

---

## 📊 Analysis Modes

### 1. Summarize (Single Paper)
Full-text PDF is downloaded, parsed page-by-page using PyMuPDF, and split into 2–3 page chunks. Each chunk is analyzed by the LLM with rolling context from previous chunks. Results are combined into:

| Section | Description |
|---|---|
| **Summary** | Unified narrative summary adapted to persona and depth |
| **Key Insights** | 5–10 extracted insights |
| **Methodology** | Detailed methodology breakdown |
| **Results** | Key findings and statistical results |
| **Limitations** | Identified limitations and future work |
| **Visual Groups** | Figures, tables, and equations — grouped by semantic similarity with plain-language explanations |

### 2. Compare (Up to 5 Papers)
Each paper is individually summarized, then an LLM generates:
- **Paper contributions** — unique contribution of each paper
- **Detailed comparison** (≥2000 chars) — methods, datasets, results, strengths, weaknesses
- **Research gaps** — actionable future research directions

### 3. Implement (Up to 10 Papers)
Extracts implementation details from papers:
- **Code snippets** with page references
- **Parameters** and hyperparameters from literature
- **Key techniques** used across papers
- **Generated Python implementation** synthesized from all extractions

### 4. Analyze (Full Pipeline)
Runs discovery → then auto-selects mode based on context:
- Default: summarize the top paper
- Compare mode: compare top 5 papers
- Implement mode: extract from top 10 papers

---

## 🛠 Tech Stack

### Backend
| Component | Technology |
|---|---|
| **API Framework** | FastAPI 0.110+ with Uvicorn |
| **LLM Integration** | Multi-endpoint architecture via SambaNova Cloud (GPT-OSS-120B, DeepSeek-V3, Gemma-3-12B) |
| **Paper Search** | Semantic Scholar API, OpenAlex API, ArXiv API |
| **PDF Processing** | PyMuPDF (fitz) — page-level text extraction + image extraction |
| **Semantic Ranking** | SPECTER 2.0 (allenai/specter2_base) with proximity adapter |
| **Keyword Extraction** | KeyBERT + spaCy (en_core_web_sm) + SentenceTransformer (all-MiniLM-L6-v2) |
| **HTTP Client** | httpx (async) + requests (sync) |
| **Validation** | Pydantic v2 schemas |
| **Retry Logic** | Exponential backoff with rate-limit handling |

### Frontend
| Component | Technology |
|---|---|
| **Framework** | React 19 with Vite 8 |
| **3D Rendering** | Three.js r183 + React Three Fiber + Drei |
| **Post-processing** | React Three Postprocessing (Bloom, Vignette) |
| **Animations** | GSAP with ScrollTrigger |
| **Styling** | Vanilla CSS with custom design system |

---

## 📁 Project Structure

```
CogniView.AI/
├── index.html                    # Vite entry point
├── package.json                  # Node.js dependencies
├── requirements.txt              # Python dependencies
├── vite.config.js                # Vite configuration
│
├── src/
│   ├── .env                      # Environment variables (API keys, model configs)
│   ├── main.jsx                  # React entry point
│   │
│   ├── App.jsx                   # 3D scroll-driven landing page (Three.js)
│   ├── App.css                   # Landing page styles
│   ├── App_sphere.jsx            # Alternative sphere-based landing
│   ├── App_Sphere.css
│   │
│   ├── Dashboard.jsx             # Main search + discovery interface
│   ├── Dashboard.css
│   │
│   ├── Dashboard-2.jsx           # Analysis results dashboard
│   ├── Dashboard-2.css           # Dashboard styles (55KB+ premium design)
│   │
│   ├── PaperDetail.jsx           # Individual paper detail view
│   ├── PaperDetail.css
│   │
│   ├── TransitionAnimation.jsx   # Page transition effects
│   ├── TransitionAnimation.css
│   │
│   ├── api.py                    # FastAPI application + routes
│   ├── main.py                   # Uvicorn server entry
│   ├── orchestrator.py           # 7-stage discovery pipeline + analysis modes
│   ├── schemas.py                # Pydantic request/response models
│   ├── prompts.py                # LLM prompt templates (persona, depth, format)
│   ├── store.py                  # Data persistence utilities
│   │
│   ├── models/
│   │   ├── __init__.py
│   │   └── paper.py              # Paper dataclass with None-safe serialization
│   │
│   ├── core/
│   │   ├── __init__.py           # Module exports
│   │   ├── config.py             # Centralized configuration (100+ env-driven settings)
│   │   ├── llm_service.py        # Multi-endpoint LLM service with think-tag handling
│   │   ├── database_searcher.py  # Semantic Scholar + OpenAlex + ArXiv search
│   │   ├── specter_ranker.py     # SPECTER 2.0 embedding + multi-anchor ranking
│   │   ├── keyword_generator.py  # 3-stage hybrid keyword extraction pipeline
│   │   ├── query_profiler.py     # Stage 0: Query classification + threshold derivation
│   │   ├── citation_graph.py     # Stage 2B: Citation graph expansion via S2 API
│   │   ├── semantic_retriever.py # Stage 2C: S2 Recommendations API
│   │   ├── quality_filter.py     # Stage 3: Percentile-based quality filtering
│   │   ├── scoring.py            # Stage 4: Multi-signal paper scoring
│   │   ├── mmr_diversifier.py    # Stage 5: Maximal Marginal Relevance selection
│   │   ├── chunked_processor.py  # PDF chunking + rolling-context summarization
│   │   ├── pdf_parser.py         # PyMuPDF page-level text extraction
│   │   ├── pdf_downloader.py     # Multi-source PDF resolution + download
│   │   ├── pdf_enricher.py       # PDF metadata enrichment
│   │   ├── visual_grouper.py     # Figure/table/equation grouping + explanation
│   │   ├── paper_collector.py    # Paper collection utilities
│   │   ├── paper_service.py      # Paper metadata service
│   │   ├── paper_discovery.py    # Legacy discovery pipeline
│   │   ├── locator.py            # File locator utilities
│   │   └── dataset_agent.py      # Dataset identification agent
│   │
│   ├── pipelines/
│   │   ├── __init__.py
│   │   ├── discovery_pipeline.py # High-level discovery pipeline wrapper
│   │   ├── research.py           # Research pipeline orchestration
│   │   ├── summarize.py          # Summarization pipeline
│   │   ├── compare.py            # Comparison pipeline
│   │   └── implement.py          # Implementation pipeline
│   │
│   ├── data/                     # Processed data storage
│   └── downloaded_pdfs/          # Cached PDF downloads
│
├── data/                         # Root data directory
├── downloaded_pdfs/              # Root PDF cache
└── dist/                         # Production build output
```

---

## 🚀 Setup & Installation

### Prerequisites
- **Node.js** 18+ and **npm**
- **Python** 3.10+
- **spaCy English model**: `python -m spacy download en_core_web_sm`

### 1. Clone & Install Frontend

```bash
git clone https://github.com/YOUR_USERNAME/CogniView.AI.git
cd CogniView.AI

# Install Node.js dependencies
npm install
```

### 2. Install Backend Dependencies

```bash
pip install -r requirements.txt

# Download spaCy model
python -m spacy download en_core_web_sm
```

### 3. Configure Environment

Create `src/.env` (or copy from the template) with your API keys:

```env
# ═══════════════════════════════════════
# TEXT / SUMMARY LLM
# ═══════════════════════════════════════
TEXT_API_KEY=your_api_key
TEXT_BASE_URL=https://api.sambanova.ai/v1
TEXT_MODEL=gpt-oss-120b

# ═══════════════════════════════════════
# DISCOVERY LLM (seed papers, keywords)
# ═══════════════════════════════════════
DISCOVERY_API_KEY=your_api_key
DISCOVERY_BASE_URL=https://api.sambanova.ai/v1
DISCOVERY_MODEL=DeepSeek-V3.1

# ═══════════════════════════════════════
# JUDGE LLM (relevance scoring)
# ═══════════════════════════════════════
JUDGE_API_KEY=your_api_key
JUDGE_BASE_URL=https://api.sambanova.ai/v1
JUDGE_MODEL=DeepSeek-V3.2

# ═══════════════════════════════════════
# CODE IMPLEMENTATION LLM
# ═══════════════════════════════════════
CODE_API_KEY=your_api_key
CODE_BASE_URL=https://api.sambanova.ai/v1
CODE_MODEL=DeepSeek-V3.1

# ═══════════════════════════════════════
# IMAGE / GRAPH / EQUATION LLMs
# ═══════════════════════════════════════
IMAGE_API_KEY=your_api_key
IMAGE_BASE_URL=https://api.sambanova.ai/v1
IMAGE_MODEL=gemma-3-12b-it

GRAPH_API_KEY=your_api_key
GRAPH_BASE_URL=https://api.sambanova.ai/v1
GRAPH_MODEL=gemma-3-12b-it

EQUATION_API_KEY=your_api_key
EQUATION_BASE_URL=https://api.sambanova.ai/v1
EQUATION_MODEL=gemma-3-12b-it

# ═══════════════════════════════════════
# PAPER SEARCH APIs
# ═══════════════════════════════════════
SEMANTIC_SCHOLAR_API_KEY=your_s2_key
UNPAYWALL_EMAIL=your_email@example.com

# ═══════════════════════════════════════
# STORAGE
# ═══════════════════════════════════════
PDF_DOWNLOAD_DIR=./downloaded_pdfs
DATA_DIR=./data
```

### 4. Start the Application

```bash
# Terminal 1 — Backend API (port 8000)
cd src
python main.py
# or: uvicorn api:app --host 0.0.0.0 --port 8000 --reload

# Terminal 2 — Frontend dev server (port 5173)
npm run dev
```

Open **http://localhost:5173** in your browser.

---

## ⚙️ Configuration

All pipeline parameters are configurable via environment variables in `src/.env` or `src/core/config.py`:

### Pipeline Knobs

| Variable | Default | Description |
|---|---|---|
| `TOP_N_STUDENT` | 10 | Papers returned for Student/Learner persona |
| `TOP_N_EDUCATOR` | 15 | Papers returned for Educator persona |
| `TOP_N_RESEARCHER` | 20 | Papers returned for Researcher persona |
| `STAGE1_MIN_SEEDS` | 2 | Minimum seed papers |
| `STAGE1_MAX_SEEDS` | 6 | Maximum seed papers |
| `STAGE2A_PAPERS_PER_KEYWORD` | 25 | Papers fetched per search term |
| `STAGE2A_MAX_SEARCH_TERMS` | 20 | Max deduplicated search terms |
| `STAGE2A_CONCEPT_COUNT` | 5 | Adjacent concepts to generate |
| `STAGE2B_MAX_REFS_PER_SEED` | 30 | Max references per seed |
| `STAGE2B_MAX_CITES_PER_SEED` | 80 | Max citations per seed |
| `STAGE2C_TOP_K` | 200 | Max semantic retrieval results |
| `STAGE3_MIN_RESULTS` | 30 | Min papers after quality filter |
| `STAGE4_TOP_FOR_MMR` | 100 | Papers sent to MMR |
| `STAGE5_MMR_POOL_SIZE` | 30 | Papers kept after MMR |
| `API_DELAY` | 1.0 | Delay between API calls (seconds) |

---

## 📡 API Reference

### Base URL: `http://localhost:8000`

| Method | Endpoint | Description |
|---|---|---|
| `GET` | `/` | Service info + version |
| `GET` | `/health` | Health check |
| `POST` | `/discover` | Run 7-stage discovery pipeline |
| `POST` | `/summarize` | Summarize a single paper |
| `POST` | `/analyze` | Full pipeline (discover + analyze) |
| `POST` | `/compare` | Compare multiple papers |
| `POST` | `/implement` | Generate implementation from papers |
| `POST` | `/upload` | Upload a PDF for direct analysis |
| `GET` | `/pdf/{pdf_hash}` | Serve a cached PDF |

### Example — Discover Papers

```bash
curl -X POST http://localhost:8000/discover \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "vision transformers",
    "persona": "Researcher",
    "field_of_study": "computer science",
    "time_filter": "relevant"
  }'
```

### Example — Summarize a Paper

```bash
curl -X POST http://localhost:8000/summarize \
  -H "Content-Type: application/json" \
  -d '{
    "topic": "attention mechanism",
    "persona": "Learner",
    "paper": {
      "title": "Attention Is All You Need",
      "pdf_url": "https://arxiv.org/pdf/1706.03762.pdf"
    }
  }'
```

---

## 🎨 Frontend

### Landing Page (`App.jsx`)

A cinematic **scroll-driven 3D animation** built with React Three Fiber:

1. **Paper Stack** — Research papers stacked in a neat pile
2. **Flying Papers** — Papers scatter and fly upward with procedural bending
3. **Cloud Cover** — Volumetric clouds rush in and envelop the scene
4. **Neural Network** — Papers shrink and feed into a 4-layer neural network visualization
5. **Signal Flow** — Particles travel along curved connections between nodes
6. **Output Card** — A summary card materializes pixel-by-pixel at the output node
7. **Call to Action** — Blurred backdrop fades in with a "Begin Research" button

### Analysis Dashboard (`Dashboard-2.jsx`)

A premium, dark-themed analysis interface with:

- **Tabbed sections**: Summary, Insights, Methodology, Results, Limitations, Visuals, Comparison, Implementation
- **Inline markdown rendering**: Headings, bold, italic, code, bullet points, numbered lists
- **Split-pane PDF viewer**: Click any visual element to open the PDF at the exact page
- **Resizable panels**: Drag the divider to adjust the split ratio
- **Paper metadata card**: Title, authors, year, venue, DOI link, PDF access
- **Visual groups**: Figures, tables, and equations grouped and explained with click-to-view-in-PDF

### Prompt System (`prompts.py`)

A sophisticated prompt engineering system with 6 configurable dimensions:

| Dimension | Options |
|---|---|
| **Persona** | Learner, Educator, Researcher |
| **Depth** | Skim (300–500 words), Understand (800–1500), DeepDive (1800–4000) |
| **Time Budget** | Quick (0.7×), Focused (1.0×), DeepResearch (1.5×) |
| **Knowledge Level** | Beginner, Intermediate, Advanced |
| **Goal** | Learn, Teach, Publish, Build, Implement, Apply |
| **Output Format** | Bullet, Structured, Report |

---

## 🧩 Core Modules

### `core/llm_service.py`
Multi-endpoint LLM service supporting 7 specialized configurations (text, discovery, judge, code, image, graph, equation). Features:
- **DeepSeek-R1 think-tag stripping** — removes `<think>` reasoning blocks before JSON extraction
- **Robust JSON extraction** — bracket-matching parser handles malformed outputs
- **Automatic retry** with exponential backoff and rate-limit handling (5 retries, up to 30s backoff)
- **Placeholder detection** — filters out fake/fabricated paper titles from LLM suggestions

### `core/specter_ranker.py`
Lazy-loaded SPECTER 2.0 (allenai/specter2_base) with the proximity adapter for semantic paper ranking:
- **Multi-anchor embedding**: Weighted blend of query (25%), query+domain (20%), seeds (40%), alternative phrasings (10%), concepts (5%)
- **CPU-only** inference (~110M params, fast enough without GPU)
- **Graceful fallback** if torch/adapters/transformers not installed

### `core/keyword_generator.py`
Hybrid 3-stage keyword extraction:
1. **KeyBERT** with MMR diversity extracts 40 candidates per paper → spaCy POS filters to 10–15 → SentenceTransformer ranks top 10
2. **LLM** reviews all 30 candidates and picks the best 5 search terms
3. **Post-validation** applies banlist (90+ generic academic terms), off-topic domain blocking, deduplication, and substring filtering

### `core/database_searcher.py`
Unified search across three academic databases:
- **Semantic Scholar** — with year filtering, field-of-study, and full metadata
- **OpenAlex** — with curated concept ID mapping (70+ fields), citation count filtering, sorted by citations
- **ArXiv** — XML API fallback for papers not in other databases
- **PDF URL resolution** — ArXiv PDF construction, OpenAlex OA URL, Unpaywall fallback

### `core/chunked_processor.py`
Processes full-text PDFs in manageable chunks:
- **2–3 page chunks** with adaptive sizing (shorter pages → 3 per chunk)
- **Rolling context** — previous chunk summaries feed into the next for coherence
- **Per-chunk extraction** of figures, tables, equations with page number tracking
- **Final combination** — LLM synthesizes all chunk summaries into unified output sections

---

## 📄 License

This project is developed as an academic/semester project. See the repository for license details.

---

<p align="center">
  <strong>Built with ❤️ by the CogniView.AI team</strong>
</p>
