# Financial News Terminal

Professional financial news platform with AI-powered commentary generation and modern terminal interface.

## Features

### Web Terminal
- 🖥️ Professional terminal interface with real-time news feeds
- 📱 Responsive design that works on desktop and mobile
- ⚡ Fast API responses with intelligent caching
- 🔄 Auto-refresh functionality
- 🎯 Topic-based news aggregation with relevance scoring

### AI-Powered Report Generation
- 📊 **Executive Briefs** - Concise bullet points (one per topic) for quick review
- 📝 **Wall Street Desk Notes** - Professional analyst-style commentary
- 🤖 **AI Query Reformulation** - 4x search coverage using Gemini AI
- 🔍 **Semantic Deduplication** - Intelligent article filtering
- 📁 **Multi-Format Output** - TXT and JSON formats for easy integration

### CLI Tools
- Production-ready command-line report generator
- Topic search with configurable parameters
- Entity/company lookup via Knowledge Graph API

## Project Structure

```
news_terminal/
├── main.py                 # FastAPI web application
├── services/               # Core business logic
│   ├── topic_search_service.py
│   ├── report_service.py
│   ├── gemini_service.py
│   ├── company_cache.py
│   ├── rate_limiter.py
│   └── price_service.py
├── scripts/                # CLI tools
│   ├── cli_report_generator.py
│   ├── cli_topic_search.py
│   └── cli_entity_search.py
├── config/                 # Configuration
│   ├── prompts.yaml        # AI prompt templates
│   └── topics.py           # Search topics & ``DEFAULT_TOPICS_REVISION``
├── tests/                  # Pytest (Gemini auth, topics, CLI helpers)
├── static/                 # Web UI assets
│   ├── index.html
│   ├── style.css
│   └── app.js
├── docs/                   # Documentation
├── output/                 # Generated reports
├── pyproject.toml          # Dependencies
└── Dockerfile              # Container config
```

## Quick Start

### Prerequisites
- Python 3.11+
- UV package manager
- Bigdata.com API key

### Local Development

1. **Clone and setup**:
   ```bash
   cd news_terminal
   echo "BIGDATA_API_KEY=your_api_key_here" > .env
   ```

2. **Create virtual environment and install dependencies**:
   ```bash
   uv venv
   source .venv/bin/activate  # On Windows: .venv\Scripts\activate
   uv sync
   ```

3. **Run the application**:
   ```bash
   uv run python main.py
   ```

4. **Open your browser**:
   ```
   http://localhost:8000
   ```
   
   **Enable auto-refresh for demo/debugging (refreshes every 60 seconds):**
   ```
   http://localhost:8000/?autoRefresh=true
   ```

### Docker Deployment

#### Quick Local Docker Deploy (Recommended for Development)

1. **One-command deploy** (rebuilds, clears port, and launches):
   ```bash
   ./scripts/deploy_local.sh
   ```

This script will:
- Check for `.env` file and API key
- Stop any existing containers
- Kill any processes using port 8000
- Rebuild the Docker image
- Start the container with auto-restart

#### Manual Docker Deploy

1. **Build the image**:
   ```bash
   docker build -t news-terminal .
   ```

2. **Run the container**:
   ```bash
   docker run -p 8000:8000 --env-file .env news-terminal
   ```

## CLI Tools

### 📊 Report Generator

Generate AI-powered commentary with executive briefs and Wall Street desk notes.

**Basic Usage:**
```bash
# Generate 7-day report (default)
python scripts/cli_report_generator.py TSLA

# 30-day comprehensive report
python scripts/cli_report_generator.py AAPL --days 30

# Custom output directory
python scripts/cli_report_generator.py NVDA --output-dir ~/reports/

# Preview without saving
python scripts/cli_report_generator.py GOOGL --no-save
```

**Output Files:**
Each run generates 3 files in `./output/`:
- `{TICKER}_{timestamp}_briefs.txt` - Executive bullet points (one per topic)
- `{TICKER}_{timestamp}_desk_note.txt` - Wall Street-style analyst note
- `{TICKER}_{timestamp}_full_report.json` - Complete structured data

**Options:**
- `--days` / `-d` : Date range (1, 7, 30, 90, 180, 365)
- `--output-dir` / `-o` : Custom output directory
- `--no-save` : Display only, don't save files
- `--show-articles` / `-a` : Show raw articles
- `--verbose` / `-v` : Detailed progress
- `--no-query-reformulation` / `--no-qr` : Faster search (less coverage)

See [docs/CLI_REPORT_GENERATOR.md](docs/CLI_REPORT_GENERATOR.md) for complete documentation.

### 🔍 Topic Search

Test search parameters and analyze raw results:

```bash
# Default: 7 days with query reformulation
python scripts/cli_topic_search.py TSLA

# 30-day search with article display
python scripts/cli_topic_search.py AAPL --days 30 --show-articles

# Fast configuration
python scripts/cli_topic_search.py MSFT --config fast
```

### 🏢 Entity Search

Look up companies via Knowledge Graph API:

```bash
# Search for company
python scripts/cli_entity_search.py "Tesla"

# Search by ticker
python scripts/cli_entity_search.py "AAPL" --type ticker
```

Run ``python scripts/cli_topic_search.py --help`` (and similar) for CLI options.

## API Endpoints

- `GET /` - Terminal interface
- `POST /api/news/{ticker}` - Get news for a single ticker (JSON body)
- `POST /api/news-multi` - Get news for multiple tickers (JSON body)
- `GET /api/health` - Health check
- `GET /api/config` - Default topics, ``default_topics_revision``, and commentary availability
- `GET /api/cache/stats` - Cache statistics
- `POST /api/cache/clear` - Clear cache

### News Search Request Body

```json
{
  "days": 7,
  "basic_search": false,
  "relevance": 0.1,
  "query_reformulation": false,
  "since_minutes": null,
  "topics": [
    {
      "topic_name": "Financial Metrics",
      "topic_text": "{company} reported earnings results beating or missing revenue and profit expectations"
    }
  ]
}
```

Omit ``topics`` to use the server default list from ``config/topics.py`` (currently ~29 topic rows). For multi-ticker requests, add `"tickers": ["AAPL", "TSLA", "NVDA"]` to the body.

## Usage

1. Enter any stock ticker symbol (e.g., AAPL, MSFT, GOOGL)
2. Click "GET NEWS" or press Enter
3. View real-time financial news in the terminal interface
4. News auto-refreshes every 1 minute (if enabled)

### Auto-Refresh

Auto-refresh is **disabled by default**. To enable it:

**Via URL parameter:**
- Enable: `http://localhost:8000/?autoRefresh=true`
- Disable: `http://localhost:8000/?autoRefresh=false`

**Via browser console:**
```javascript
searchSettings.autoRefresh = true;
saveSettingsToStorage();
```

When enabled, the terminal automatically fetches new articles every 60 seconds using incremental refresh (only fetches articles since the last refresh).

## Architecture

### Backend Services
- **FastAPI Application** (`main.py`) - RESTful API with async support
- **Topic Search Service** - Multi-query search with AI reformulation
- **Report Service** - AI-powered commentary generation
- **Gemini Service** - Google AI integration (Gemini API key, Vertex with service account, or Vertex with ADC)
- **Company Cache** - Knowledge Graph API integration with caching
- **Rate Limiter** - Intelligent API rate limiting
- **Price Service** - Stock price data integration

### Frontend
- **Professional UI** - Modern terminal interface
- **Responsive Design** - Desktop and mobile support
- **Real-Time Updates** - Auto-refresh functionality
- **Rich Visualizations** - Article relevance scoring and topic grouping

### Data Flow
1. User enters ticker symbol
2. Entity lookup via Knowledge Graph API
3. Parallel topic-based searches (one Bigdata ``/search`` call per topic template; default list length is defined in ``config/topics.py``)
4. AI query reformulation for expanded coverage
5. Semantic deduplication of results
6. Relevance scoring and ranking
7. Optional: AI commentary generation

### Deployment
- **Docker-Ready** - Single container with all dependencies
- **Stateless Design** - No persistent storage required
- **Health Monitoring** - Built-in health check endpoints

## Configuration

Environment variables in `.env`:

```env
BIGDATA_API_KEY=your_api_key_here

# Optional: Gemini — use EITHER Vertex (below) OR AI Studio API key, not both.
# Vertex (recommended for GCP): see env_example.txt for full matrix.

# Vertex + Application Default Credentials (local: gcloud auth application-default login)
GOOGLE_GENAI_USE_VERTEXAI=True
GOOGLE_CLOUD_PROJECT=your-project-id
GOOGLE_CLOUD_LOCATION=us-central1

# AI Studio (Gemini API key) — set GOOGLE_GENAI_USE_VERTEXAI=False or unset
# GEMINI_API_KEY=your_gemini_api_key_here

# Vertex + service account JSON instead of ADC
# GOOGLE_GENAI_USE_VERTEXAI=True
# GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
# GOOGLE_CLOUD_PROJECT=your-project-id
```

### Default topics and ``DEFAULT_TOPICS_REVISION``

The web UI loads default topic templates from ``GET /api/config`` and caches them in ``localStorage``. When you **add, remove, reorder, or edit** entries in ``DEFAULT_TOPICS`` inside ``config/topics.py``, you **must** increment ``DEFAULT_TOPICS_REVISION`` in the same file so existing browsers replace stale cached topics on the next visit.

The API always returns ``default_topics_revision`` as an integer **≥ 1** (``safe_default_topics_revision()`` in ``config/topics.py``). The browser also accepts a numeric string from older proxies. If ``newsTerminalSettings`` JSON is corrupt, it is archived under ``newsTerminalSettings__corrupt__<timestamp>``, the bad key is removed, and defaults are written once—other preferences are not read from the broken blob, but the app returns to a consistent first-run state instead of failing every load.

Category slugs returned by ``get_topic_category()`` were renamed (for example ``earnings`` → ``financial_metrics``). If you persist old slugs elsewhere, use ``normalize_topic_category_slug()`` from ``config.topics`` to map them to the current keys.

### Gemini AI Setup (Optional)

Commentary and optional query reformulation use ``services/gemini_service.py``. Resolution order is documented in that module; in short:

- **Vertex:** set ``GOOGLE_GENAI_USE_VERTEXAI=true`` and ``GOOGLE_CLOUD_PROJECT`` (and usually ``GOOGLE_CLOUD_LOCATION``). Use a service account JSON path **or** Application Default Credentials.
- **AI Studio:** set ``GEMINI_API_KEY`` and do **not** force Vertex (Vertex rejects API keys on ``aiplatform.googleapis.com``).

See ``env_example.txt`` for a copy-paste template.

## Performance

- **Search Coverage**: 4x more articles via AI query reformulation
- **Response Time**: ~2-5 seconds for comprehensive topic search
- **Caching**: Intelligent TTL-based caching reduces API calls
- **Deduplication**: Semantic similarity detection removes duplicates
- **Rate Limiting**: Automatic request throttling for API compliance
- **Scalability**: Async design supports concurrent requests

## Technology Stack

### Core Dependencies
- **FastAPI** - Modern async web framework
- **Google Gemini AI** - LLM for query reformulation & commentary
- **Bigdata.com API** - Financial news & Knowledge Graph data
- **SemHash** - Semantic similarity for deduplication
- **Rich** - Beautiful terminal UI
- **aiohttp** - Async HTTP client
- **Pydantic** - Data validation

### Development
- **Python 3.11+** - Required runtime
- **UV** - Fast Python package manager
- **Docker** - Containerization
- **Pytest** - ``uv sync --extra dev`` then ``uv run pytest``

## Troubleshooting

### Common Issues

**"API key not configured" / Gemini 401 on Vertex**
- ``BIGDATA_API_KEY`` is always required for news search.
- For **Vertex**, use OAuth (service account file or ``gcloud auth application-default login``); do not rely on ``GEMINI_API_KEY`` while ``GOOGLE_GENAI_USE_VERTEXAI=true``.
- For **AI Studio**, set ``GEMINI_API_KEY`` and disable Vertex for that environment.
- If ``GOOGLE_APPLICATION_CREDENTIALS`` points to a missing file, the app logs a warning and falls back to ADC; fix the path if you intended to use that service account.

**"No articles found"**
- Verify ticker symbol is valid (e.g., `AAPL` not `Apple`)
- Try increasing date range: `--days 30`
- Check if company is publicly traded

**"Rate limit exceeded"**
- Built-in rate limiter should prevent this
- If it occurs, wait 60 seconds and retry
- Consider reducing parallel query count in config

**Slow performance**
- First run may be slow due to cache warming
- Use `--no-qr` flag for faster (but less comprehensive) results
- Check internet connection stability

**AI commentary issues**
- Verify Gemini AI API key is valid
- Check API quota hasn't been exceeded
- Review logs for detailed error messages

### Logs

**Docker:**
```bash
docker logs <container_id>
```

**Local development:**
```bash
# Set log level
export LOG_LEVEL=DEBUG
uv run python main.py
```

**CLI tools:**
```bash
# Use verbose flag
python scripts/cli_report_generator.py TSLA --verbose
```

### Cache Management

Clear application cache:
```bash
curl -X POST http://localhost:8000/api/cache/clear
```

View cache statistics:
```bash
curl http://localhost:8000/api/cache/stats
```

## Documentation

- ``env_example.txt`` - Environment template (including Vertex vs API key)
- ``services/gemini_service.py`` - Gemini / Vertex authentication behavior
- In-repo references such as ``docs/CLI_TOOLS.md`` may be added separately; if missing, use script ``--help`` output.

## License

MIT License

## Contributing

This is a production-ready financial news platform. Contributions welcome for:
- Additional search topics and configurations (remember to bump ``DEFAULT_TOPICS_REVISION`` in ``config/topics.py`` when editing ``DEFAULT_TOPICS``)
- Enhanced AI prompts for better commentary
- UI/UX improvements
- Performance optimizations
- Additional data sources
