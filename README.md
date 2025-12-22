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
│   └── topics.py           # Search topics
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

See [docs/CLI_TOOLS.md](docs/CLI_TOOLS.md) for detailed CLI documentation.

## API Endpoints

- `GET /` - Terminal interface
- `POST /api/news/{ticker}` - Get news for a single ticker (JSON body)
- `POST /api/news-multi` - Get news for multiple tickers (JSON body)
- `GET /api/health` - Health check
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
    {"topic_name": "Earnings", "topic_text": "What key takeaways emerged from {company}'s latest earnings report?"}
  ]
}
```

For multi-ticker requests, add `"tickers": ["AAPL", "TSLA", "NVDA"]` to the body.

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
- **Gemini Service** - Google AI integration (API key or Vertex AI)
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
3. Parallel topic-based searches (28+ queries)
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

# Optional: Gemini AI authentication (choose one method)
# Method 1: ADC - Application Default Credentials (recommended for Google Cloud)
USE_ADC=true

# Method 2: API Key (simple, for local development)
GEMINI_API_KEY=your_gemini_api_key_here

# Method 3: Vertex AI with service account
GOOGLE_APPLICATION_CREDENTIALS=/path/to/service-account.json
GOOGLE_CLOUD_PROJECT=your-project-id
```

### Gemini AI Setup (Optional)

The application includes an AI-powered query reformulation service using Google's Gemini. Three authentication methods are supported:

**Method 1: ADC - Application Default Credentials (Recommended for Google Cloud)**

Best for environments where credentials are automatically available (Google Cloud, authenticated gcloud CLI):
```bash
echo "USE_ADC=true" >> .env
```

This uses `HttpOptions` to automatically detect credentials from:
- `gcloud auth application-default login` (local development)
- GCP metadata service (Cloud Run, GKE, Compute Engine)
- `GOOGLE_APPLICATION_CREDENTIALS` environment variable

**Method 2: API Key (Simple)**
```bash
echo "GEMINI_API_KEY=your_api_key_here" >> .env
```

**Method 3: Vertex AI with Service Account**
1. Place your service account JSON file in the project directory
2. Set environment variables:
   ```bash
   export GOOGLE_APPLICATION_CREDENTIALS="/path/to/service-account.json"
   export GOOGLE_CLOUD_PROJECT="your-project-id"
   ```

For detailed Vertex AI setup instructions, see [docs/VERTEX_AI_SETUP.md](docs/VERTEX_AI_SETUP.md).

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

## Troubleshooting

### Common Issues

**"API key not configured"**
- Ensure both `BIGDATA_API_KEY` and `GEMINI_API_KEY` are set in `.env`
- For Vertex AI: Verify `GOOGLE_APPLICATION_CREDENTIALS` path is correct

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

- [CLI Report Generator](docs/CLI_REPORT_GENERATOR.md) - Complete CLI reference
- [CLI Tools](docs/CLI_TOOLS.md) - All command-line tools
- [Vertex AI Setup](docs/VERTEX_AI_SETUP.md) - Google Cloud AI configuration
- [API Developer Guide](docs/BIGDATA_API_DEVELOPER_GUIDE.md) - Bigdata.com API reference

## License

MIT License

## Contributing

This is a production-ready financial news platform. Contributions welcome for:
- Additional search topics and configurations
- Enhanced AI prompts for better commentary
- UI/UX improvements
- Performance optimizations
- Additional data sources
