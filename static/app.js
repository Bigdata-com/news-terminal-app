// Financial News Terminal JavaScript - v2.1
let currentTicker = '';
let refreshInterval = null;
let previousArticleIds = new Set(); // Track previously seen articles

// Default topics list - will be loaded from backend
let DEFAULT_TOPICS = [];
/** True after /api/config returns a non-empty default_topics list. */
let defaultTopicsConfigLoadedOk = false;
/**
 * Integer revision from /api/config (>=1), or null if missing/invalid/unloaded.
 * Do not run localStorage topic sync when null — avoids wiping topics on config errors.
 */
let defaultTopicsRevisionFromServer = null;

// Settings object (default: 7 days, Topics ON, Reformulation OFF)
let searchSettings = {
    allNews: false, // If true, use basic search (no topics) - default OFF means selective ON
    topics: [],
    days: 7, // Default 7 days (1 week)
    queryReformulation: false, // Default OFF - generates 3 variations per topic using Gemini AI
    autoRefresh: false // Default OFF - auto-refresh news every minute
};

// Topic filtering state
let currentTopicFilter = 'all'; // 'all' or topic name
let allNewsData = null; // Store all news data for filtering
let originalTopics = null; // Store original topics to detect changes
let lastRefreshTime = null; // Track last refresh timestamp for incremental updates

// Commentary state
let currentNewsData = null; // Store full news response for commentary generation
let currentCommentary = null; // Store generated commentary

// LocalStorage key for saved commentaries
const COMMENTARY_STORAGE_KEY = 'news_terminal_commentaries';
const MAX_SAVED_COMMENTARIES = 10; // Keep last 10 commentaries

// Utility function: fetch with timeout
function fetchWithTimeout(url, options = {}) {
    const { timeout = 30000, ...fetchOptions } = options; // Default 30s timeout
    
    return Promise.race([
        fetch(url, fetchOptions),
        new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Request timeout - operation is still running on the server')), timeout)
        )
    ]);
}

// Initialize when page loads
document.addEventListener('DOMContentLoaded', async function() {
    await loadDefaultTopics();
    loadSettings();
    parseUrlParameters(); // Parse URL parameters and override settings if needed
    populateCommentaryDropdown();
    setupEventListeners();
    initializeFilters(); // This will update topics count after settings are loaded
});

function setupEventListeners() {
    // Enter key support
    document.getElementById('tickerInput').addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            getNews();
        }
    });
    
    // ESC key to clear
    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            clearResults();
        } else if (e.key === 'F5') {
            e.preventDefault();
            if (currentTicker) {
                getNews();
            }
        } else if (e.ctrlKey && e.key === 'c') {
            document.getElementById('tickerInput').focus();
            document.getElementById('tickerInput').select();
        }
    });
    
    // Focus input on page load
    document.getElementById('tickerInput').focus();
}

async function getNews(isRefresh = false) {
    const ticker = document.getElementById('tickerInput').value.trim().toUpperCase();
    
    if (!ticker) {
        showError('Please enter a ticker symbol');
        return;
    }
    
    // If new ticker, clear previous article tracking and commentary
    if (ticker !== currentTicker) {
        previousArticleIds.clear();
        currentCommentary = null; // Clear cached commentary for new ticker
        currentNewsData = null;
    }
    
    currentTicker = ticker;
    
    // Check if multiple tickers (comma-separated)
    const isMultipleTickers = ticker.includes(',');
    
    // Validate ticker format
    if (isMultipleTickers) {
        const tickers = ticker.split(',').map(t => t.trim());
        if (tickers.some(t => !/^[A-Z]{1,10}$/.test(t))) {
            showError('Invalid ticker format. Use comma-separated tickers (e.g., AAPL,TSLA,MSFT)');
            return;
        }
    } else {
        if (!/^[A-Z]{1,10}$/.test(ticker)) {
            showError('Invalid ticker format. Use 1-10 letters only.');
            return;
        }
    }
    
    // Update UI state (less intrusive for refresh)
    if (!isRefresh) {
        setLoading(true);
    }
    
    try {
        let response, data;
        
        // Build request body
        const requestBody = {
            basic_search: searchSettings.allNews,
            relevance: 0.1, // Default minimum relevance threshold
            days: searchSettings.days,
            query_reformulation: searchSettings.queryReformulation
        };
        
        // On refresh, only fetch articles since last refresh (incremental update)
        if (isRefresh && lastRefreshTime) {
            const now = Date.now();
            const minutesSinceLastRefresh = Math.ceil((now - lastRefreshTime) / (60 * 1000));
            requestBody.since_minutes = minutesSinceLastRefresh;
            console.log(`Incremental refresh: fetching last ${minutesSinceLastRefresh} minutes of news`);
        }
        
        // Add custom topics if not using basic search
        if (!searchSettings.allNews && searchSettings.topics.length > 0) {
            requestBody.topics = searchSettings.topics;
        }
        
        if (isMultipleTickers) {
            // Multi-ticker: add tickers array to body
            requestBody.tickers = ticker.split(',').map(t => t.trim());
            response = await fetch('/api/news-multi', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
        } else {
            // Single ticker: ticker in URL path
            response = await fetch(`/api/news/${ticker}`, {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody)
            });
        }
        
        data = await response.json();
        
        if (response.ok) {
            displayNews(data, isMultipleTickers, isRefresh);
            
            // Store news data for commentary generation (single ticker only)
            if (!isMultipleTickers && data.topic_results) {
                // Only update currentNewsData if this is NOT a refresh, or if we don't have cached commentary
                // This preserves the original full dataset that commentary was generated from
                if (!isRefresh || !currentCommentary) {
                    currentNewsData = data;
                }
                showCommentaryButton();
                // Note: We keep currentCommentary cached unless user explicitly regenerates or clears
            } else {
                currentNewsData = null;
                currentCommentary = null; // Clear commentary for multi-ticker searches
                hideCommentaryButton();
            }
            
            // Get article count based on response format
            let articleCount;
            if (data.aggregate_stats) {
                // Multi-ticker format
                articleCount = data.aggregate_stats.total_results;
            } else if (data.total_results !== undefined) {
                // Single ticker format (new)
                articleCount = data.total_results;
            } else {
                // Fallback for old format
                articleCount = data.count || 0;
            }
            
            
            // Update last refresh timestamp for incremental updates
            lastRefreshTime = Date.now();
            
            // Start auto-refresh if enabled and not already running
            if (!isRefresh && searchSettings.autoRefresh) {
                startAutoRefresh();
            }
        } else {
            throw new Error(data.detail || 'Failed to fetch news');
        }
    } catch (error) {
        console.error('Error fetching news:', error);
        if (!isRefresh) {
            showError(`Error: ${error.message}`);
        }
    } finally {
        if (!isRefresh) {
            setLoading(false);
        }
    }
}

function displayNews(data, isMultipleTickers = false, isRefresh = false) {
    const newsFeed = document.getElementById('newsFeed');
    const articleCount = document.getElementById('articleCount');
    
    // Track new articles
    const currentArticleIds = new Set();
    let newArticleCount = 0;
    
    // Extract entity_id for highlighting (may be at top level or in results)
    let entityIdMap = {};  // Map ticker -> entity_id
    
    if (data.entity_id) {
        // Single ticker format
        entityIdMap[data.ticker] = data.entity_id;
    } else if (data.results) {
        // Multi-ticker format
        data.results.forEach(tickerResult => {
            if (tickerResult.entity_id) {
                entityIdMap[tickerResult.ticker] = tickerResult.entity_id;
            }
        });
    }
    
    // Handle new topic-based search format - extract NEW articles
    let newArticles = [];
    let totalCount = 0;
    
    if (data.results) {
        // Multi-ticker format from topic search
        data.results.forEach(tickerResult => {
            const ticker = tickerResult.ticker;
            
            // Combine baseline and topic results
            const allArticles = [
                ...(tickerResult.baseline_results || []),
                ...(tickerResult.topic_results || [])
            ];
            
            // Tag each article with ticker
            allArticles.forEach(article => {
                article.ticker = ticker;
                newArticles.push(article);
            });
        });
        
        totalCount = data.aggregate_stats?.total_results || newArticles.length;
    } else if (data.baseline_results || data.topic_results) {
        // Single ticker format from topic search
        newArticles = [
            ...(data.baseline_results || []),
            ...(data.topic_results || [])
        ];
        totalCount = data.total_results || newArticles.length;
    } else {
        // Old format (fallback)
        newArticles = data.news || [];
        totalCount = data.count || newArticles.length;
    }
    
    // Merge new articles with existing ones if this is a refresh
    let newsArray = [];
    if (isRefresh && allNewsData) {
        // Extract existing articles from stored data
        let existingArticles = [];
        if (allNewsData.results) {
            allNewsData.results.forEach(tickerResult => {
                const allArticles = [
                    ...(tickerResult.baseline_results || []),
                    ...(tickerResult.topic_results || [])
                ];
                existingArticles.push(...allArticles);
            });
        } else if (allNewsData.baseline_results || allNewsData.topic_results) {
            existingArticles = [
                ...(allNewsData.baseline_results || []),
                ...(allNewsData.topic_results || [])
            ];
        } else {
            existingArticles = allNewsData.news || [];
        }
        
        console.log(`📰 Refresh: ${existingArticles.length} existing articles in cache`);
        console.log(`📥 Refresh: ${newArticles.length} new articles from API`);
        
        // Merge: combine existing + new articles
        const combinedArticles = [...existingArticles, ...newArticles];
        
        // Deduplicate by article ID
        const articleMap = new Map();
        combinedArticles.forEach(article => {
            if (!articleMap.has(article.id)) {
                articleMap.set(article.id, article);
            }
        });
        
        newsArray = Array.from(articleMap.values());
        console.log(`✅ Merged result: ${newsArray.length} total unique articles (removed ${combinedArticles.length - newsArray.length} duplicates)`);
    } else {
        // Initial load - use new articles as-is
        newsArray = newArticles;
        console.log(`🆕 Initial load: ${newsArray.length} articles`);
    }
    
    // Store merged data for next refresh and topic filtering
    if (isRefresh && allNewsData) {
        // On refresh, update allNewsData with merged results to preserve history
        if (data.baseline_results || data.topic_results) {
            const baselineArticles = newsArray.filter(a => a.search_type === 'baseline');
            const topicArticles = newsArray.filter(a => a.search_type === 'topic');
            allNewsData.baseline_results = baselineArticles;
            allNewsData.topic_results = topicArticles;
            allNewsData.total_results = newsArray.length;
        } else if (data.news) {
            // Old format - update with merged array
            allNewsData.news = newsArray;
            allNewsData.count = newsArray.length;
        } else if (data.results) {
            // Multi-ticker format - update with merged results
            allNewsData.results = allNewsData.results || [];
            // Keep the aggregate structure but update articles
            const baselineArticles = newsArray.filter(a => a.search_type === 'baseline');
            const topicArticles = newsArray.filter(a => a.search_type === 'topic');
            allNewsData.results.forEach(tickerResult => {
                const tickerSymbol = tickerResult.ticker;
                tickerResult.baseline_results = baselineArticles.filter(a => a.ticker === tickerSymbol);
                tickerResult.topic_results = topicArticles.filter(a => a.ticker === tickerSymbol);
            });
        }
        allNewsData.multi_ticker = isMultipleTickers;
    } else {
        // Initial load - store new data as-is
        allNewsData = data;
        allNewsData.multi_ticker = isMultipleTickers;
    }
    
    // Apply topic filter if not showing "all"
    if (currentTopicFilter !== 'all') {
        newsArray = newsArray.filter(article => {
            // Keep baseline results if no topic specified
            if (!article.topic_name && !article.topic) {
                return false; // Exclude baseline when filtering by topic
            }
            // Match by topic_name (new format) or by topic index/text (old format)
            const articleTopicName = article.topic_name || `Topic ${article.topic_index}`;
            return articleTopicName === currentTopicFilter;
        });
    }
    
    // Update article count with new articles info and last update time
    const now = new Date();
    const timeString = now.toLocaleTimeString('en-US', { 
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });
    
    let countText = `${newsArray.length} Articles`;
    if (isRefresh && newArticles.length > 0) {
        countText += ` (${newArticles.length} new)`;
    }
    countText += ` | Last Update: ${timeString}`;
    if (currentTopicFilter !== 'all') {
        countText += ` (${currentTopicFilter.toUpperCase()})`;
    }
    
    articleCount.textContent = countText;
    
    if (newsArray.length === 0) {
        newsFeed.innerHTML = `
            <div class="no-results">
                <div style="font-size: 16px; margin-bottom: 10px;">📰</div>
                <div>No recent news found</div>
                <div style="margin-top: 10px; font-size: 10px;">
                    Try a different ticker or check back later
                </div>
            </div>
        `;
        return;
    }
    
    // Sort by timestamp (most recent first)
    newsArray.sort((a, b) => {
        return new Date(b.timestamp) - new Date(a.timestamp);
    });
    
    let html = '';
    newsArray.forEach((article, index) => {
        // Track article IDs
        currentArticleIds.add(article.id);
        
        // Check if this is a new article
        const isNewArticle = isRefresh && !previousArticleIds.has(article.id);
        if (isNewArticle) {
            newArticleCount++;
        }
        
        // Format relevance percentage
        const relevancePercent = Math.round(article.relevance * 100);
        const relevanceColor = getRelevanceColor(article.relevance);
        
        // Get ticker for display - article.ticker should now be set by the data parser
        const ticker = article.ticker || currentTicker.split(',')[0];
        
        // Get topic name (or "Baseline" for non-topic articles)
        const topicName = article.topic_name || (article.search_type === 'baseline' ? 'Baseline' : '-');
        
        // Add new article badge
        const newBadge = isNewArticle ? '<span class="new-badge">NEW</span>' : '';
        const animationClass = isNewArticle ? 'new-article' : '';
        
        // Prepare full text and link
        const fullText = article.full_text || article.summary;
        const hasUrl = article.document_url;
        const articleLink = hasUrl ? `
            <div class="article-link">
                <a href="${escapeHtml(article.document_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">
                    🔗 Read full article
                </a>
            </div>
        ` : '';
        
        // Get entity ID for this ticker to highlight entities
        const entityId = entityIdMap[ticker];
        const detections = article.detections || [];
        
        // Highlight entity text if we have detections and entity_id
        const highlightedText = highlightEntityText(fullText, detections, entityId);
        
        // Create table row HTML
        html += `
            <div class="news-item ${animationClass}" onclick="toggleArticle(event, ${index})">
                <div class="news-row">
                    <div class="news-row-ticker">
                        <span class="ticker-tag">${ticker}</span>
                    </div>
                    <div class="news-row-topic">
                        <span class="topic-tag">${escapeHtml(topicName)}</span>
                    </div>
                    <div class="news-row-headline">
                        <div class="news-headline">${escapeHtml(article.headline)}${newBadge}</div>
                        <div class="news-meta">
                            <span class="news-source">${escapeHtml(article.source)}</span>
                            <span style="color: #30363d;">•</span>
                            <span class="news-type">${article.document_type}</span>
                            <span style="color: #30363d;">•</span>
                            <div class="relevance-bar">
                                <div class="relevance-fill" style="width: ${relevancePercent}%; background: ${relevanceColor}"></div>
                            </div>
                            <span class="news-relevance">${relevancePercent}%</span>
                        </div>
                    </div>
                    <div class="news-row-price" data-ticker="${ticker}">--</div>
                    <div class="news-row-change" data-ticker="${ticker}">--</div>
                    <div class="news-row-time">${article.time_ago}</div>
                </div>
                <div class="news-summary">
                    ${highlightedText}
                    ${articleLink}
                </div>
            </div>
        `;
    });
    
    newsFeed.innerHTML = html;
    
    // Update previous article IDs for next refresh
    previousArticleIds = currentArticleIds;
    
    // Show new article notification if this is a refresh
    if (isRefresh && newArticleCount > 0) {
        showNotification(`${newArticleCount} new article${newArticleCount > 1 ? 's' : ''} found!`);
    }
    
    // Scroll to top only on initial load, not on refresh
    if (!isRefresh) {
        newsFeed.scrollTop = 0;
    }
    
    // Fetch prices for unique tickers
    fetchAndDisplayPrices(data, isMultipleTickers);
}

function toggleArticle(event, index) {
    event.currentTarget.classList.toggle('expanded');
}

async function fetchAndDisplayPrices(newsData, isMultipleTickers) {
    // Get unique tickers from the news
    const tickers = new Set();
    
    // Handle new topic-based search format
    if (newsData.results) {
        // Multi-ticker format - get tickers from results
        newsData.results.forEach(result => {
            if (result.ticker) {
                tickers.add(result.ticker);
            }
        });
    } else if (newsData.ticker) {
        // Single ticker format
        tickers.add(newsData.ticker);
    } else if (newsData.tickers) {
        // Old multi-ticker format
        newsData.tickers.forEach(t => tickers.add(t));
    }
    
    if (tickers.size === 0) {
        return;
    }
    
    const tickerList = Array.from(tickers).join(',');
    
    try {
        const response = await fetch(`/api/prices?tickers=${encodeURIComponent(tickerList)}`);
        const data = await response.json();
        
        if (response.ok) {
            updatePriceDisplay(data.prices);
        } else {
            console.error('Error fetching prices:', data);
        }
    } catch (error) {
        console.error('Error fetching prices:', error);
    }
}

function updatePriceDisplay(prices) {
    // Update all price elements
    Object.entries(prices).forEach(([ticker, priceData]) => {
        // Find all elements for this ticker
        const priceElements = document.querySelectorAll(`.news-row-price[data-ticker="${ticker}"]`);
        const changeElements = document.querySelectorAll(`.news-row-change[data-ticker="${ticker}"]`);
        
        priceElements.forEach(el => {
            if (priceData.price !== null) {
                // Format price with 2 decimal places
                el.textContent = `$${priceData.price.toFixed(2)}`;
            } else {
                el.textContent = '--';
            }
        });
        
        changeElements.forEach(el => {
            if (priceData.change !== null) {
                const change = priceData.change;
                const sign = change > 0 ? '+' : '';
                el.textContent = `${sign}${change.toFixed(2)}%`;
                
                // Add color class
                el.classList.remove('price-positive', 'price-negative', 'price-neutral');
                if (change > 0) {
                    el.classList.add('price-positive');
                } else if (change < 0) {
                    el.classList.add('price-negative');
                } else {
                    el.classList.add('price-neutral');
                }
            } else {
                el.textContent = '--';
                el.classList.add('price-neutral');
            }
        });
    });
}

function showNotification(message) {
    const notification = document.createElement('div');
    notification.className = 'refresh-notification';
    notification.textContent = message;
    document.body.appendChild(notification);
    
    // Remove after animation
    setTimeout(() => {
        notification.remove();
    }, 3000);
}

function createRelevanceBar(relevance) {
    const percentage = Math.round(relevance * 100);
    const barLength = 10;
    const filledBars = Math.round((percentage / 100) * barLength);
    
    let bar = '';
    for (let i = 0; i < barLength; i++) {
        if (i < filledBars) {
            bar += '█';
        } else {
            bar += '░';
        }
    }
    
    return `<span style="color: ${getRelevanceColor(relevance)}">${bar}</span>`;
}

function highlightEntityText(text, detections, entityId) {
    /**
     * Highlight entity mentions in text based on detections array.
     * @param {string} text - The full text to highlight
     * @param {Array} detections - Array of detection objects with {id, start, end, type}
     * @param {string} entityId - The entity ID to highlight (from search)
     * @returns {string} HTML string with <strong> tags around matching entities
     */
    
    if (!text || !detections || !entityId || detections.length === 0) {
        return escapeHtml(text || '');
    }
    
    // Filter detections to only those matching the search entity ID
    const matchingDetections = detections.filter(d => d.id === entityId);
    
    if (matchingDetections.length === 0) {
        return escapeHtml(text);
    }
    
    // Sort by start position (ascending) to process from beginning to end
    matchingDetections.sort((a, b) => a.start - b.start);
    
    // Remove overlapping detections (keep first occurrence)
    const nonOverlappingDetections = [];
    let lastEnd = -1;
    matchingDetections.forEach(detection => {
        if (detection.start >= lastEnd) {
            nonOverlappingDetections.push(detection);
            lastEnd = detection.end;
        }
    });
    
    // Build HTML by processing text segments
    let result = '';
    let currentPos = 0;
    
    nonOverlappingDetections.forEach(detection => {
        // Add text before the detection (escaped)
        if (currentPos < detection.start) {
            result += escapeHtml(text.substring(currentPos, detection.start));
        }
        
        // Add the highlighted entity text (escaped but wrapped in strong tags)
        const entityText = text.substring(detection.start, detection.end);
        result += '<strong>' + escapeHtml(entityText) + '</strong>';
        
        currentPos = detection.end;
    });
    
    // Add any remaining text after the last detection (escaped)
    if (currentPos < text.length) {
        result += escapeHtml(text.substring(currentPos));
    }
    
    return result;
}

function getRelevanceColor(relevance) {
    if (relevance >= 0.8) return '#58a6ff';  // High relevance - blue
    if (relevance >= 0.6) return '#79c0ff';  // Medium relevance - light blue
    if (relevance >= 0.4) return '#ffa657';  // Low-medium relevance - orange
    return '#6e7681';  // Low relevance - gray
}

function showArticleDetails(articleId) {
    // For now, just highlight the clicked article
    // In the future, this could open a detailed view
    console.log('Article clicked:', articleId);
    
    // Add click feedback
    event.currentTarget.style.backgroundColor = '#002200';
    setTimeout(() => {
        event.currentTarget.style.backgroundColor = '';
    }, 200);
}

function loadExample(ticker) {
    document.getElementById('tickerInput').value = ticker;
    getNews();
}

function clearResults() {
    currentTicker = '';
    lastRefreshTime = null; // Reset refresh timestamp
    stopAutoRefresh();
    
    document.getElementById('tickerInput').value = '';
    document.getElementById('newsFeed').innerHTML = `
        <div class="welcome-message">
            <div class="welcome-title">🚀 Welcome to News Terminal</div>
            <div class="welcome-text">
                Enter a ticker symbol above to get started with real-time financial news.
                <br><br>
                <strong>Try these examples:</strong>
                <div class="example-tickers">
                    <span class="example-ticker" onclick="loadExample('AAPL')">AAPL</span>
                    <span class="example-ticker" onclick="loadExample('MSFT')">MSFT</span>
                    <span class="example-ticker" onclick="loadExample('GOOGL')">GOOGL</span>
                    <span class="example-ticker" onclick="loadExample('TSLA')">TSLA</span>
                    <span class="example-ticker" onclick="loadExample('NVDA')">NVDA</span>
                </div>
            </div>
        </div>
    `;
    
    document.getElementById('articleCount').textContent = '';
    document.getElementById('tickerInput').focus();
    
    // Clear commentary
    currentNewsData = null;
    currentCommentary = null;
    hideCommentaryButton();
}

function showError(message) {
    const newsFeed = document.getElementById('newsFeed');
    newsFeed.innerHTML = `
        <div class="error">
            <div style="font-size: 16px; margin-bottom: 10px;">⚠️</div>
            <div>${escapeHtml(message)}</div>
            <div style="margin-top: 15px; font-size: 10px;">
                <button onclick="clearResults()" style="font-size: 10px;">Try Again</button>
            </div>
        </div>
    `;
}

function setLoading(loading) {
    const getNewsBtn = document.getElementById('getNewsBtn');
    const tickerInput = document.getElementById('tickerInput');
    
    if (loading) {
        getNewsBtn.disabled = true;
        getNewsBtn.textContent = 'LOADING...';
        tickerInput.disabled = true;
        
        document.getElementById('newsFeed').innerHTML = `
            <div class="loading">
                <div style="font-size: 16px; margin-bottom: 10px;">📡</div>
                <div>Fetching latest news</div>
            </div>
        `;
    } else {
        getNewsBtn.disabled = false;
        getNewsBtn.textContent = 'GET NEWS';
        tickerInput.disabled = false;
    }
}

// Status functions removed - status now shown in article count

function startAutoRefresh() {
    // Clear any existing interval
    stopAutoRefresh();
    
    // Set up auto-refresh every 1 minute
    refreshInterval = setInterval(() => {
        if (currentTicker) {
            console.log('Auto-refreshing news for:', currentTicker);
            getNews(true); // Pass true to indicate this is a refresh
        }
    }, 60 * 1000); // 1 minute
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// ============================================================
// COMMENTARY GENERATION FUNCTIONS
// ============================================================

function showCommentaryButton() {
    document.getElementById('viewCommentaryBtn').style.display = 'block';
}

function hideCommentaryButton() {
    document.getElementById('viewCommentaryBtn').style.display = 'none';
    document.getElementById('commentarySidebar').style.display = 'none';
}

function toggleCommentarySidebar() {
    const sidebar = document.getElementById('commentarySidebar');
    const isVisible = sidebar.style.display === 'block';
    
    if (isVisible) {
        sidebar.style.display = 'none';
    } else {
        sidebar.style.display = 'block';
        
        // Refresh the dropdown with latest saved commentaries
        populateCommentaryDropdown();
        
        // If we have cached commentary, show it. Otherwise, reset display state
        if (currentCommentary) {
            displayCommentary(currentCommentary);
        } else {
            document.getElementById('commentaryDisplay').style.display = 'none';
            document.getElementById('commentaryError').style.display = 'none';
        }
    }
}

async function generateCommentary() {
    if (!currentTicker) {
        showCommentaryError('No ticker selected. Please fetch news first.');
        return;
    }
    
    const btn = document.getElementById('runCommentaryBtn');
    const btnText = document.getElementById('runBtnText');
    const commentaryStatus = document.getElementById('commentaryStatus');
    const commentaryError = document.getElementById('commentaryError');
    const commentaryDisplay = document.getElementById('commentaryDisplay');
    
    // Clear previous commentary when regenerating
    currentCommentary = null;
    
    // Show loading state
    btn.disabled = true;
    btnText.innerHTML = '<span class="spinner"></span> GENERATING...';
    commentaryStatus.textContent = 'Fetching full news data...';
    commentaryError.style.display = 'none';
    commentaryDisplay.style.display = 'none';
    
    try {
        // STEP 1: Fetch FULL news data (not incremental) for commentary
        const requestBody = {
            basic_search: searchSettings.allNews,
            relevance: 0.1,
            days: searchSettings.days,
            query_reformulation: searchSettings.queryReformulation
        };
        
        // Add custom topics if not using basic search
        if (!searchSettings.allNews && searchSettings.topics.length > 0) {
            requestBody.topics = searchSettings.topics;
        }
        
        // Calculate expected API calls for progress indication
        const topicCount = searchSettings.topics.length;
        const expectedCalls = searchSettings.queryReformulation ? topicCount * 4 : topicCount;
        const estimatedMinutes = Math.ceil(expectedCalls / 20); // Rough estimate at ~20 calls/min with rate limiting
        
        console.log('Fetching full news data for commentary generation...');
        commentaryStatus.textContent = `Searching ${topicCount} topics (${expectedCalls} API calls, ~${estimatedMinutes} min)...`;
        
        // Use extended timeout for long-running topic searches (5 minutes)
        const newsResponse = await fetchWithTimeout(
            `/api/news/${currentTicker}`,
            {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify(requestBody),
                timeout: 300000 // 5 minutes
            }
        );
        
        if (!newsResponse.ok) {
            throw new Error('Failed to fetch news data');
        }
        
        const fullNewsData = await newsResponse.json();
        
        if (!fullNewsData.topic_results || fullNewsData.topic_results.length === 0) {
            throw new Error('You have to select topics to generate commentary on a ticker.');
        }
        
        console.log(`Fetched ${fullNewsData.total_results || 0} articles for commentary`);
        
        // STEP 2: Generate commentary from full dataset
        commentaryStatus.textContent = 'Generating AI commentary...';
        
        // Use extended timeout for AI commentary generation (5 minutes)
        const response = await fetchWithTimeout('/api/generate-commentary', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json',
            },
            body: JSON.stringify(fullNewsData),
            timeout: 300000 // 5 minutes
        });
        
        if (!response.ok) {
            const error = await response.json();
            throw new Error(error.detail || 'Failed to generate commentary');
        }
        
        const commentaryData = await response.json();
        currentCommentary = commentaryData;
        
        // Save to localStorage
        saveCommentaryToStorage(commentaryData);
        
        // Display the commentary
        displayCommentary(commentaryData);
        
        // Update button state
        btn.disabled = false;
        btnText.textContent = 'RUN';
        commentaryStatus.textContent = '✓ Generated';
        commentaryStatus.style.color = '#10b981';
        
    } catch (error) {
        console.error('Commentary generation error:', error);
        
        // Provide helpful error message for timeouts
        let errorMessage = error.message;
        if (error.message.includes('timeout')) {
            errorMessage = 'Request timed out. For large topic searches (many topics with reformulation), this can take 3-5 minutes. Try reducing the number of topics or disabling query reformulation, or wait a bit longer and try clicking RUN again.';
        }
        
        showCommentaryError(errorMessage);
        
        // Reset button state
        btn.disabled = false;
        btnText.textContent = 'RUN';
        commentaryStatus.textContent = '';
    }
}

function displayCommentary(data) {
    const commentaryDisplay = document.getElementById('commentaryDisplay');
    const deskNoteContent = document.getElementById('deskNoteContent');
    const briefsList = document.getElementById('briefsList');
    const commentaryTicker = document.getElementById('commentaryTicker');
    const briefsCount = document.getElementById('briefsCount');
    
    // Update metadata
    commentaryTicker.textContent = data.ticker;
    briefsCount.textContent = `${data.briefs.length}`;
    
    // Display desk note
    deskNoteContent.innerHTML = formatDeskNote(data.desk_note);
    
    // Display briefs
    briefsList.innerHTML = data.briefs.map((brief, index) => `
        <div class="brief-item">
            <div class="brief-topic">${brief.topic_name}</div>
            <div class="brief-content">${formatBulletPoint(brief.bullet_point)}</div>
        </div>
    `).join('');
    
    // Show the display
    commentaryDisplay.style.display = 'block';
}

function formatDeskNote(text) {
    // Convert markdown-style bold to HTML and add line breaks before bullets
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/•/g, '<br/><br/>•')
        .trim();
}

function formatBulletPoint(text) {
    // Convert markdown-style bold to HTML
    return text
        .replace(/\*\*(.*?)\*\*/g, '<strong>$1</strong>')
        .replace(/^\*\s*/, ''); // Remove leading bullet if present
}

function showCommentaryError(message) {
    const commentaryError = document.getElementById('commentaryError');
    commentaryError.textContent = message;
    commentaryError.style.display = 'block';
}

function copyDeskNote() {
    if (!currentCommentary || !currentCommentary.desk_note) {
        return;
    }
    
    navigator.clipboard.writeText(currentCommentary.desk_note).then(() => {
        // Show temporary feedback
        const btn = event.target.closest('button');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<svg class="action-icon" viewBox="0 0 24 24" fill="none" xmlns="http://www.w3.org/2000/svg"><path d="M9 16.2L4.8 12l-1.4 1.4L9 19 21 7l-1.4-1.4L9 16.2z" fill="currentColor"/></svg> Copied!';
        setTimeout(() => {
            btn.innerHTML = originalText;
        }, 2000);
    }).catch(err => {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard');
    });
}

function saveDeskNote() {
    if (!currentCommentary || !currentCommentary.desk_note) {
        return;
    }
    
    const timestamp = new Date().toISOString().replace(/[:.]/g, '-').slice(0, -5);
    const filename = `desk_note_${currentCommentary.ticker}_${timestamp}.txt`;
    
    const content = `Wall Street Desk Note - ${currentCommentary.ticker}\n` +
                   `Generated: ${currentCommentary.generated_at}\n` +
                   `${'='.repeat(80)}\n\n` +
                   currentCommentary.desk_note +
                   `\n\n${'='.repeat(80)}\n` +
                   `Executive Briefs (${currentCommentary.briefs.length} topics)\n` +
                   `${'='.repeat(80)}\n\n` +
                   currentCommentary.briefs.map((brief, i) => 
                       `${i + 1}. ${brief.topic_name}\n   ${brief.bullet_point}\n`
                   ).join('\n');
    
    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
}

// ============================================================
// COMMENTARY PERSISTENCE FUNCTIONS
// ============================================================

function saveCommentaryToStorage(commentary) {
    try {
        // Get existing commentaries
        let commentaries = JSON.parse(localStorage.getItem(COMMENTARY_STORAGE_KEY) || '[]');
        
        // Add new commentary with metadata
        const savedCommentary = {
            id: Date.now(),
            ticker: commentary.ticker,
            generated_at: commentary.generated_at,
            desk_note: commentary.desk_note,
            briefs: commentary.briefs,
            saved_at: new Date().toISOString()
        };
        
        // Add to beginning of array
        commentaries.unshift(savedCommentary);
        
        // Keep only last MAX_SAVED_COMMENTARIES
        if (commentaries.length > MAX_SAVED_COMMENTARIES) {
            commentaries = commentaries.slice(0, MAX_SAVED_COMMENTARIES);
        }
        
        // Save back to localStorage
        localStorage.setItem(COMMENTARY_STORAGE_KEY, JSON.stringify(commentaries));
        
        // Update dropdown
        populateCommentaryDropdown();
        
        console.log('Commentary saved to localStorage');
    } catch (error) {
        console.error('Error saving commentary to localStorage:', error);
    }
}

function getSavedCommentaries() {
    try {
        return JSON.parse(localStorage.getItem(COMMENTARY_STORAGE_KEY) || '[]');
    } catch (error) {
        console.error('Error loading commentaries from localStorage:', error);
        return [];
    }
}

function populateCommentaryDropdown() {
    const select = document.getElementById('previousCommentarySelect');
    if (!select) {
        console.warn('previousCommentarySelect element not found');
        return;
    }
    
    const commentaries = getSavedCommentaries();
    console.log('Populating dropdown with', commentaries.length, 'commentaries');
    
    // Clear existing options except first one
    select.innerHTML = '<option value="">-- Select --</option>';
    
    // Add saved commentaries
    commentaries.forEach(commentary => {
        const option = document.createElement('option');
        option.value = commentary.id;
        
        const date = new Date(commentary.generated_at);
        const dateStr = date.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
        const timeStr = date.toLocaleTimeString('en-US', { hour: '2-digit', minute: '2-digit' });
        
        option.textContent = `${commentary.ticker} - ${dateStr} ${timeStr}`;
        select.appendChild(option);
    });
}

function loadPreviousCommentary() {
    const select = document.getElementById('previousCommentarySelect');
    const selectedId = select.value;
    
    if (!selectedId) return;
    
    const commentaries = getSavedCommentaries();
    const commentary = commentaries.find(c => c.id == selectedId);
    
    if (commentary) {
        // Load the commentary
        currentCommentary = commentary;
        displayCommentary(commentary);
        
        // Update status
        const commentaryStatus = document.getElementById('commentaryStatus');
        commentaryStatus.textContent = '✓ Loaded from history';
        commentaryStatus.style.color = '#10b981';
        
        console.log('Loaded commentary from history:', commentary.ticker);
    }
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Health check on page load
async function checkHealth() {
    try {
        const response = await fetch('/api/health');
        const data = await response.json();
        
        if (response.ok && data.status === 'healthy') {
            console.log('API health check passed');
        } else {
            console.warn('API health check failed');
        }
    } catch (error) {
        console.error('API health check error:', error);
    }
}

// Run health check
checkHealth();

// ============================================================================
// SETTINGS FUNCTIONS
// ============================================================================

const LOCAL_STORAGE_SETTINGS_KEY = 'newsTerminalSettings';
/** Prior corrupt payloads are archived under this prefix (one newest backup at a time). */
const LOCAL_STORAGE_CORRUPT_PREFIX = 'newsTerminalSettings__corrupt__';

/**
 * Coerce /api/config default_topics_revision to a finite integer >= 1, or null.
 * Accepts JSON numbers or numeric strings (e.g. "2").
 */
function normalizeServerTopicsRevision(rev) {
    if (typeof rev === 'number' && Number.isFinite(rev) && rev >= 1) {
        return Math.floor(rev);
    }
    if (typeof rev === 'string' && rev.trim() !== '') {
        const n = Number(rev.trim());
        if (Number.isFinite(n) && n >= 1) {
            return Math.floor(n);
        }
    }
    return null;
}

/** First-run defaults; topic revision is set only when /api/config loaded successfully. */
function buildDefaultSearchSettings() {
    const s = {
        allNews: false,
        topics: [...DEFAULT_TOPICS],
        days: 7,
        queryReformulation: false,
        autoRefresh: false
    };
    if (defaultTopicsConfigLoadedOk && defaultTopicsRevisionFromServer != null) {
        s.defaultTopicsRevision = defaultTopicsRevisionFromServer;
    }
    return s;
}

/** Keep a single archived copy so a bad JSON blob does not fill storage. */
function archiveCorruptSettingsSnapshot(raw) {
    if (typeof raw !== 'string' || raw.length === 0 || raw.length > 100000) {
        return;
    }
    try {
        for (let i = localStorage.length - 1; i >= 0; i--) {
            const k = localStorage.key(i);
            if (k && k.startsWith(LOCAL_STORAGE_CORRUPT_PREFIX)) {
                localStorage.removeItem(k);
            }
        }
        localStorage.setItem(LOCAL_STORAGE_CORRUPT_PREFIX + Date.now(), raw);
    } catch (err) {
        console.warn('Could not archive corrupt settings:', err);
    }
}

async function loadDefaultTopics() {
    // Load default topics from backend
    defaultTopicsConfigLoadedOk = false;
    defaultTopicsRevisionFromServer = null;
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        
        if (
            response.ok &&
            data.default_topics &&
            Array.isArray(data.default_topics) &&
            data.default_topics.length > 0
        ) {
            DEFAULT_TOPICS = data.default_topics;
            defaultTopicsRevisionFromServer = normalizeServerTopicsRevision(data.default_topics_revision);
            defaultTopicsConfigLoadedOk = true;
            console.log(
                `Loaded ${DEFAULT_TOPICS.length} default topics from backend (revision ${
                    defaultTopicsRevisionFromServer ?? 'none'
                })`
            );
        } else {
            console.error('Failed to load default topics from backend');
            // Fallback to minimal topics if backend fails
            DEFAULT_TOPICS = [{
                topic_name: "Earnings",
                topic_text: "What key takeaways emerged from {company}'s latest earnings report?"
            }];
        }
    } catch (error) {
        console.error('Error loading default topics:', error);
        // Fallback to minimal topics if backend fails
        DEFAULT_TOPICS = [{
            topic_name: "Earnings",
            topic_text: "What key takeaways emerged from {company}'s latest earnings report?"
        }];
    }
}

function syncStoredTopicsToServerRevision() {
    if (!defaultTopicsConfigLoadedOk || defaultTopicsRevisionFromServer == null) {
        return;
    }
    const serverRev = defaultTopicsRevisionFromServer;
    if (searchSettings.defaultTopicsRevision === serverRev) {
        return;
    }
    searchSettings.topics = [...DEFAULT_TOPICS];
    searchSettings.defaultTopicsRevision = serverRev;
    saveSettingsToStorage();
    console.log(
        'Replaced cached topics with server defaults (revision ' +
            serverRev +
            '). Clear localStorage or use Reset if you need to force-refresh again.'
    );
}

function loadSettings() {
    // Load settings from localStorage
    const saved = localStorage.getItem(LOCAL_STORAGE_SETTINGS_KEY);
    if (saved) {
        try {
            searchSettings = JSON.parse(saved);
            // Ensure topics array exists and is populated
            if (!searchSettings.topics || searchSettings.topics.length === 0) {
                searchSettings.topics = [...DEFAULT_TOPICS];
                if (defaultTopicsConfigLoadedOk && defaultTopicsRevisionFromServer != null) {
                    searchSettings.defaultTopicsRevision = defaultTopicsRevisionFromServer;
                }
                saveSettingsToStorage();
            } else {
                // Check if topics are in old string format and convert to new dict format
                const hasOldFormat = searchSettings.topics.some(t => typeof t === 'string');
                if (hasOldFormat) {
                    console.log('Converting old string topics to new dictionary format...');
                    // Clear old topics and use new defaults
                    searchSettings.topics = [...DEFAULT_TOPICS];
                    if (defaultTopicsConfigLoadedOk && defaultTopicsRevisionFromServer != null) {
                        searchSettings.defaultTopicsRevision = defaultTopicsRevisionFromServer;
                    }
                    saveSettingsToStorage(); // Save the updated format
                }
            }
            // Replace localStorage topics when server default set changed (topics.py revision bump)
            syncStoredTopicsToServerRevision();
            // Ensure days field exists (default 7)
            if (!searchSettings.days) {
                searchSettings.days = 7;
            }
            // Ensure queryReformulation field exists (default false)
            if (searchSettings.queryReformulation === undefined) {
                searchSettings.queryReformulation = false;
            }
            // Ensure autoRefresh field exists (default false)
            if (searchSettings.autoRefresh === undefined) {
                searchSettings.autoRefresh = false;
            }
        } catch (e) {
            console.error('Error loading settings:', e);
            archiveCorruptSettingsSnapshot(saved);
            try {
                localStorage.removeItem(LOCAL_STORAGE_SETTINGS_KEY);
            } catch (removeErr) {
                console.warn('Could not remove corrupt settings key:', removeErr);
            }
            searchSettings = buildDefaultSearchSettings();
            saveSettingsToStorage();
            console.warn(
                'newsTerminalSettings contained invalid JSON; reset to defaults. ' +
                    'A copy was saved under ' +
                    LOCAL_STORAGE_CORRUPT_PREFIX +
                    '<timestamp> in localStorage when possible.'
            );
        }
    } else {
        // No saved settings - use defaults (7 days, Topics ON, Reformulation OFF, Auto-refresh OFF)
        searchSettings = buildDefaultSearchSettings();
    }
}

function saveSettingsToStorage() {
    localStorage.setItem(LOCAL_STORAGE_SETTINGS_KEY, JSON.stringify(searchSettings));
}

function parseUrlParameters() {
    /**
     * Parse URL parameters and override settings accordingly.
     * Supports: ?autoRefresh=true or ?autoRefresh=false
     */
    const urlParams = new URLSearchParams(window.location.search);
    const autoRefreshParam = urlParams.get('autoRefresh');
    
    if (autoRefreshParam !== null) {
        // Convert string to boolean
        const autoRefreshValue = autoRefreshParam.toLowerCase() === 'true';
        searchSettings.autoRefresh = autoRefreshValue;
        
        // Save to localStorage so it persists
        saveSettingsToStorage();
        
        console.log(`Auto-refresh set to ${autoRefreshValue} via URL parameter`);
    }
}

// ============================================================================
// FILTERS FUNCTIONS
// ============================================================================

function initializeFilters() {
    const advancedGroup = document.querySelector('.filter-group.advanced-options');
    const advancedDivider = document.querySelector('.filter-divider.advanced-options');
    
    // Set search mode buttons and show/hide advanced options
    if (searchSettings.allNews) {
        document.getElementById('allModeBtn').classList.add('active');
        document.getElementById('topicModeBtn').classList.remove('active');
        if (advancedGroup) advancedGroup.style.display = 'none';
        if (advancedDivider) advancedDivider.style.display = 'none';
    } else {
        document.getElementById('topicModeBtn').classList.add('active');
        document.getElementById('allModeBtn').classList.remove('active');
        if (advancedGroup) advancedGroup.style.display = 'flex';
        if (advancedDivider) advancedDivider.style.display = 'block';
    }
    
    // Set date filter buttons
    document.querySelectorAll('.date-btn').forEach(btn => {
        const days = parseInt(btn.getAttribute('data-days'));
        if (days === searchSettings.days) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }
    });
    
    // Set AI expansion checkbox
    document.getElementById('reformulateToggle').checked = searchSettings.queryReformulation;
    
    // Initialize date button click handlers
    document.querySelectorAll('.date-btn').forEach(btn => {
        btn.addEventListener('click', function() {
            const days = parseInt(this.getAttribute('data-days'));
            searchSettings.days = days;
            
            // Update active state
            document.querySelectorAll('.date-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            
            // Save to localStorage
            saveSettingsToStorage();
            console.log('Date filter updated:', days, 'days');
        });
    });
    
    // Initialize topics edit panel
    renderTopicsInputList();
    updateTopicsCount();
    
    // Initialize topic tabs
    renderTopicTabs();
}

function updateFilters() {
    // Get values from filter UI
    searchSettings.days = parseInt(document.getElementById('dateFilter').value);
    
    // Save to localStorage
    saveSettingsToStorage();
    
    console.log('Filters updated:', searchSettings);
}

function setSearchMode(mode) {
    const topicBtn = document.getElementById('topicModeBtn');
    const allBtn = document.getElementById('allModeBtn');
    const advancedGroup = document.querySelector('.filter-group.advanced-options');
    const advancedDivider = document.querySelector('.filter-divider.advanced-options');
    
    if (mode === 'topic') {
        topicBtn.classList.add('active');
        allBtn.classList.remove('active');
        searchSettings.allNews = false;
        if (advancedGroup) advancedGroup.style.display = 'flex';
        if (advancedDivider) advancedDivider.style.display = 'block';
        console.log('Search mode: Topic-Based');
    } else {
        topicBtn.classList.remove('active');
        allBtn.classList.add('active');
        searchSettings.allNews = true;
        if (advancedGroup) advancedGroup.style.display = 'none';
        if (advancedDivider) advancedDivider.style.display = 'none';
        console.log('Search mode: All News');
    }
}

function toggleSelective() {
    const selectiveToggle = document.getElementById('selectiveToggle');
    searchSettings.allNews = !selectiveToggle.checked;
    
    // Update visibility of topics dropdown
    updateTopicsDropdownVisibility();
    
    // Render topic tabs
    renderTopicTabs();
    
    // Save to localStorage
    saveSettingsToStorage();
    
    console.log('Selective toggle:', selectiveToggle.checked ? 'ON' : 'OFF', '(allNews:', searchSettings.allNews + ')');
}

function toggleReformulate() {
    const reformulateToggle = document.getElementById('reformulateToggle');
    searchSettings.queryReformulation = reformulateToggle.checked;
    
    // Save to localStorage
    saveSettingsToStorage();
    
    console.log('Query Reformulation toggle:', reformulateToggle.checked ? 'ON' : 'OFF');
    
    // Show notification about the change
    const status = reformulateToggle.checked ? 'enabled' : 'disabled';
    showNotification(`Query reformulation ${status}${reformulateToggle.checked ? ' (generates 3 variations per topic)' : ''}`);
}

function updateTopicsDropdownVisibility() {
    const topicsWrapper = document.getElementById('topicsDropdownWrapper');
    const selectiveOn = !searchSettings.allNews;
    
    if (selectiveOn) {
        topicsWrapper.style.display = 'flex';
    } else {
        topicsWrapper.style.display = 'none';
        // Also close panel if it's open
        closeTopicsPanel();
    }
}

function toggleTopicsPanel() {
    const panel = document.getElementById('topicsPanel');
    const button = document.getElementById('topicsDropdown');
    const arrow = document.getElementById('topicsArrow');
    
    if (panel.classList.contains('active')) {
        closeTopicsPanel();
    } else {
        openTopicsPanel();
    }
}

function openTopicsPanel() {
    const panel = document.getElementById('topicsPanel');
    const button = document.getElementById('topicsDropdown');
    const arrow = document.getElementById('topicsArrow');
    
    if (panel) panel.classList.add('active');
    if (button) button.classList.add('active');
    if (arrow) arrow.textContent = '▲';
    
    // Store original topics to detect changes later
    originalTopics = JSON.parse(JSON.stringify(searchSettings.topics));
    
    // Render topics list
    renderTopicsInputList();
}

function closeTopicsPanel() {
    const panel = document.getElementById('topicsPanel');
    const button = document.getElementById('topicsDropdown');
    const arrow = document.getElementById('topicsArrow');
    
    if (panel) panel.classList.remove('active');
    if (button) button.classList.remove('active');
    if (arrow) arrow.textContent = '▼';
}

function renderTopicsInputList() {
    const listContainer = document.getElementById('topicsInputList');
    listContainer.innerHTML = '';
    
    searchSettings.topics.forEach((topic, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'topics-input-item';
        
        const label = document.createElement('span');
        label.className = 'topics-input-label';
        label.textContent = `${index + 1}.`;
        
        // Handle both string (old format) and dict (new format)
        const topicName = typeof topic === 'string' ? `Topic ${index + 1}` : topic.topic_name || `Topic ${index + 1}`;
        const topicText = typeof topic === 'string' ? topic : topic.topic_text || '';
        
        // Topic Name input
        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'topics-input-field';
        nameInput.value = topicName;
        nameInput.placeholder = 'Topic name...';
        nameInput.dataset.index = index;
        nameInput.dataset.field = 'name';
        nameInput.style.width = '25%';
        nameInput.style.marginRight = '4px';
        
        // Update on input
        nameInput.addEventListener('input', (e) => {
            if (typeof searchSettings.topics[index] === 'string') {
                // Convert to dict format
                searchSettings.topics[index] = {
                    topic_name: e.target.value,
                    topic_text: searchSettings.topics[index]
                };
            } else {
                searchSettings.topics[index].topic_name = e.target.value;
            }
        });
        
        // Topic Text input
        const textInput = document.createElement('input');
        textInput.type = 'text';
        textInput.className = 'topics-input-field';
        textInput.value = topicText;
        textInput.placeholder = '{company} topic...';
        textInput.dataset.index = index;
        textInput.dataset.field = 'text';
        textInput.style.flex = '1';
        
        // Validate on render
        if (!topicText.includes('{company}')) {
            textInput.classList.add('error');
        }
        
        // Update on input
        textInput.addEventListener('input', (e) => {
            if (typeof searchSettings.topics[index] === 'string') {
                // Convert to dict format
                searchSettings.topics[index] = {
                    topic_name: topicName,
                    topic_text: e.target.value
                };
            } else {
                searchSettings.topics[index].topic_text = e.target.value;
            }
            validateTopicInput(textInput);
        });
        
        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'topics-delete-button';
        deleteBtn.textContent = '×';
        deleteBtn.onclick = () => deleteTopicInput(index);
        
        itemDiv.appendChild(label);
        itemDiv.appendChild(nameInput);
        itemDiv.appendChild(textInput);
        itemDiv.appendChild(deleteBtn);
        listContainer.appendChild(itemDiv);
    });
}

function validateTopicInput(input) {
    const value = input.value.trim();
    const isTextField = input.dataset.field === 'text';
    
    // Only validate {company} placeholder in the topic_text field, not the topic_name
    if (isTextField && !value.includes('{company}')) {
        input.classList.add('error');
        return false;
    } else {
        input.classList.remove('error');
        return true;
    }
}

function validateAllTopicInputs() {
    const inputs = document.querySelectorAll('.topics-input-field');
    let allValid = true;
    
    inputs.forEach(input => {
        if (!validateTopicInput(input)) {
            allValid = false;
        }
    });
    
    return allValid;
}

function addTopicInput() {
    searchSettings.topics.push({
        topic_name: `Topic ${searchSettings.topics.length + 1}`,
        topic_text: '{company} '
    });
    renderTopicsInputList();
    updateTopicsCount();
    
    // Focus the new input
    const inputs = document.querySelectorAll('.topics-input-field');
    const lastInput = inputs[inputs.length - 1];
    if (lastInput) {
        lastInput.focus();
        // Move cursor to end
        lastInput.setSelectionRange(lastInput.value.length, lastInput.value.length);
    }
}

function deleteTopicInput(index) {
    searchSettings.topics.splice(index, 1);
    renderTopicsInputList();
    updateTopicsCount();
}

function updateTopicsCount() {
    // Count unique topic names
    const uniqueNames = new Set();
    searchSettings.topics.forEach(topic => {
        const topicName = typeof topic === 'string' ? 'Unknown' : topic.topic_name;
        uniqueNames.add(topicName);
    });
    const count = uniqueNames.size;
    
    // Update both displays
    const topicsCountEl = document.getElementById('topicsCount');
    const topicsCountInlineEl = document.getElementById('topicsCountInline');
    
    if (topicsCountEl) topicsCountEl.textContent = count;
    if (topicsCountInlineEl) topicsCountInlineEl.textContent = count;
}

function resetTopicsToDefault() {
    if (confirm('Reset topics to defaults?')) {
        searchSettings.topics = [...DEFAULT_TOPICS];
        if (defaultTopicsRevisionFromServer != null) {
            searchSettings.defaultTopicsRevision = defaultTopicsRevisionFromServer;
        } else {
            delete searchSettings.defaultTopicsRevision;
        }
        saveSettingsToStorage();
        renderTopicsInputList();
        updateTopicsCount();
        showNotification('Topics reset to defaults');
    }
}

function saveAndCloseTopics() {
    // First, sync all input field values back to searchSettings.topics
    // This ensures we capture any values that might not have triggered input events
    const nameInputs = document.querySelectorAll('.topics-input-field[data-field="name"]');
    const textInputs = document.querySelectorAll('.topics-input-field[data-field="text"]');
    
    // Sync topic names by index
    nameInputs.forEach((nameInput) => {
        const index = parseInt(nameInput.dataset.index);
        const topicName = nameInput.value.trim();
        if (searchSettings.topics[index]) {
            if (typeof searchSettings.topics[index] === 'string') {
                searchSettings.topics[index] = {
                    topic_name: topicName,
                    topic_text: searchSettings.topics[index]
                };
            } else {
                searchSettings.topics[index].topic_name = topicName;
            }
        }
    });
    
    // Sync topic texts by index
    textInputs.forEach((textInput) => {
        const index = parseInt(textInput.dataset.index);
        const topicText = textInput.value.trim();
        if (searchSettings.topics[index]) {
            if (typeof searchSettings.topics[index] === 'string') {
                // Get the topic name from the corresponding name input
                const nameInput = document.querySelector(`.topics-input-field[data-field="name"][data-index="${index}"]`);
                const topicName = nameInput ? nameInput.value.trim() || `Topic ${index + 1}` : `Topic ${index + 1}`;
                searchSettings.topics[index] = {
                    topic_name: topicName,
                    topic_text: topicText
                };
            } else {
                searchSettings.topics[index].topic_text = topicText;
            }
        }
    });
    
    // Validate all topics
    if (!validateAllTopicInputs()) {
        alert('Error: All topics must include the {company} placeholder');
        return;
    }
    
    // Remove empty topics
    searchSettings.topics = searchSettings.topics.filter(t => {
        if (typeof t === 'string') {
            return t.trim() !== '';
        } else {
            return t.topic_text && t.topic_text.trim() !== '';
        }
    });
    
    // Check if topics have actually changed
    const topicsChanged = JSON.stringify(originalTopics) !== JSON.stringify(searchSettings.topics);
    
    // Update count
    updateTopicsCount();
    
    // Save to localStorage
    saveSettingsToStorage();
    
    // Close panel
    closeTopicsPanel();
    
    // Show confirmation
    showNotification('Topics saved successfully!');
    
    // Render topic tabs with new topics
    renderTopicTabs();
    
    // Only prompt to refresh if topics changed AND there's a current ticker
    if (topicsChanged && currentTicker) {
        const refresh = confirm('Topics saved! Reload news with new topics?');
        if (refresh) {
            getNews();
        }
    }
}

// ============================================================================
// TOPIC TABS FUNCTIONS
// ============================================================================

function renderTopicTabs() {
    const tabsBar = document.getElementById('topicTabsBar');
    const tabsList = document.getElementById('topicTabsList');
    
    if (!tabsBar || !tabsList) {
        return;
    }
    
    // Clear existing tabs
    tabsList.innerHTML = '';
    
    // Show/hide tabs bar based on SELECTIVE setting
    if (searchSettings.allNews) {
        // Selective OFF - only show "All" tab
        tabsBar.style.display = 'flex';
        
        const allTab = document.createElement('div');
        allTab.className = 'topic-tab all-tab active';
        allTab.textContent = 'ALL';
        allTab.onclick = () => filterByTopic('all');
        tabsList.appendChild(allTab);
    } else {
        // Selective ON - show "All" + individual topic tabs
        tabsBar.style.display = 'flex';
        
        // "All" tab
        const allTab = document.createElement('div');
        allTab.className = 'topic-tab all-tab' + (currentTopicFilter === 'all' ? ' active' : '');
        allTab.textContent = 'ALL';
        allTab.onclick = () => filterByTopic('all');
        tabsList.appendChild(allTab);
        
        // Get unique topic names (deduplicate)
        const uniqueTopicNames = [];
        const seenNames = new Set();
        
        searchSettings.topics.forEach((topic, index) => {
            let topicName;
            if (typeof topic === 'string') {
                topicName = `Topic ${index + 1}`;
            } else {
                // Handle undefined, null, or empty topic names
                topicName = topic.topic_name && topic.topic_name.trim() 
                    ? topic.topic_name.trim() 
                    : `Topic ${index + 1}`;
            }
            
            // Skip empty topic names and ensure uniqueness
            if (topicName && topicName.trim() && !seenNames.has(topicName)) {
                seenNames.add(topicName);
                uniqueTopicNames.push(topicName);
            }
        });
        
        // Individual topic tabs (one per unique name)
        uniqueTopicNames.forEach(topicName => {
            if (topicName && topicName.trim()) {
                const tab = document.createElement('div');
                tab.className = 'topic-tab' + (currentTopicFilter === topicName ? ' active' : '');
                tab.textContent = topicName.toUpperCase();
                tab.onclick = () => filterByTopic(topicName);
                tabsList.appendChild(tab);
            }
        });
    }
}

function filterByTopic(topicName) {
    currentTopicFilter = topicName;
    
    // Update active tab styling
    const tabs = document.querySelectorAll('.topic-tab');
    tabs.forEach(tab => {
        if (topicName === 'all' && tab.classList.contains('all-tab')) {
            tab.classList.add('active');
        } else if (tab.textContent.toLowerCase() === topicName.toLowerCase()) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });
    
    // Re-display news with filter applied
    if (allNewsData) {
        displayNews(allNewsData, allNewsData.multi_ticker || false, false);
    }
}

