// Sector News Terminal - theme-based feed, no ticker or entity involved
const SECTOR_STORAGE_KEY = 'sectorTerminalSettings';
const SECTOR_FETCH_TIMEOUT_MS = 300000; // Theme searches fan out one query per phrase
const AUTO_REFRESH_MS = 5 * 60 * 1000;
const SECTOR_TILE_GAP_PX = 10; // Must match the .sector-tiles gap in style.css

// Sector registry and server defaults from /api/sectors
let sectors = [];
let defaultTopicsBySector = {};
let sectorTopicsRevisionFromServer = null;
let queryExpansionAvailable = false;

// Persisted user settings
let sectorSettings = {
    sector: null,
    days: 7,
    topics: [],
    queryReformulation: false, // Generates 3 variations per phrase using the sector's expansion prompt
    autoRefresh: false // Auto-refresh the feed every AUTO_REFRESH_MS
};

// Feed state
let allArticles = [];
let currentTopicFilter = 'all';
let originalTopics = null;

let lastSearchStats = null;

// Auto-refresh state
let refreshInterval = null;
let lastRefreshTime = null;
let previousArticleIds = new Set();

// ============================================================================
// UTILITIES
// ============================================================================

function fetchWithTimeout(url, options = {}) {
    const { timeout = 30000, ...fetchOptions } = options;

    return Promise.race([
        fetch(url, fetchOptions),
        new Promise((_, reject) =>
            setTimeout(() => reject(new Error('Request timeout - operation is still running on the server')), timeout)
        )
    ]);
}

function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function getRelevanceColor(relevance) {
    if (relevance >= 0.8) return '#58a6ff';
    if (relevance >= 0.6) return '#79c0ff';
    if (relevance >= 0.4) return '#ffa657';
    return '#6e7681';
}

function showNotification(message) {
    const notification = document.createElement('div');
    notification.className = 'refresh-notification';
    notification.textContent = message;
    document.body.appendChild(notification);

    setTimeout(() => {
        notification.remove();
    }, 3000);
}

/** Coerce /api/sectors sector_topics_revision to a finite integer >= 1, or null. */
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

/** Human-readable cadence for AUTO_REFRESH_MS, e.g. "60s" or "5m", for UI copy. */
function formatRefreshInterval(ms) {
    const totalSeconds = Math.round(ms / 1000);
    if (totalSeconds % 60 === 0) {
        return `${totalSeconds / 60}m`;
    }
    return `${totalSeconds}s`;
}

function getSectorById(sectorId) {
    return sectors.find(s => s.id === sectorId) || null;
}

function getDefaultTopicsFor(sectorId) {
    const topics = defaultTopicsBySector[sectorId] || [];
    return topics.map(t => ({ topic_name: t.topic_name, topic_text: t.topic_text }));
}

// ============================================================================
// INITIALIZATION
// ============================================================================

document.addEventListener('DOMContentLoaded', async function() {
    await loadSectors();
    loadSettings();
    parseUrlParameters();
    renderSectorTiles();
    initializeSectorCarousel();
    initializeFilters();
    renderTopicsInputList();
    updateTopicsCount();
    updateActiveSectorLabel();
    updateLiveIndicator();

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            clearResults();
        }
    });
});

/**
 * Parse URL parameters and override settings accordingly.
 * Supports: ?autoRefresh=true|false and ?expand=true|false
 */
function parseUrlParameters() {
    const urlParams = new URLSearchParams(window.location.search);
    let changed = false;

    const autoRefreshParam = urlParams.get('autoRefresh');
    if (autoRefreshParam !== null) {
        sectorSettings.autoRefresh = autoRefreshParam.toLowerCase() === 'true';
        changed = true;
        console.log(`Auto-refresh set to ${sectorSettings.autoRefresh} via URL parameter`);
    }

    const expandParam = urlParams.get('expand');
    if (expandParam !== null) {
        sectorSettings.queryReformulation = expandParam.toLowerCase() === 'true';
        changed = true;
        console.log(`AI query expansion set to ${sectorSettings.queryReformulation} via URL parameter`);
    }

    if (changed) {
        saveSettingsToStorage();
    }
}

async function loadSectors() {
    try {
        const response = await fetch('/api/sectors');
        const data = await response.json();

        if (response.ok && Array.isArray(data.sectors) && data.sectors.length > 0) {
            sectors = data.sectors;
            defaultTopicsBySector = data.default_topics || {};
            sectorTopicsRevisionFromServer = normalizeServerTopicsRevision(data.sector_topics_revision);
            queryExpansionAvailable = data.query_expansion_available === true;
            console.log(
                `Loaded ${sectors.length} sectors (topics revision ${sectorTopicsRevisionFromServer ?? 'none'}, `
                + `expansion ${queryExpansionAvailable ? 'available' : 'unavailable'})`
            );
        } else {
            console.error('Failed to load sectors from backend');
        }
    } catch (error) {
        console.error('Error loading sectors:', error);
    }
}

function firstEnabledSectorId() {
    const enabled = sectors.find(s => s.enabled);
    return enabled ? enabled.id : null;
}

function buildDefaultSettings() {
    const sectorId = firstEnabledSectorId();
    const settings = {
        sector: sectorId,
        days: 7,
        topics: sectorId ? getDefaultTopicsFor(sectorId) : [],
        queryReformulation: false,
        autoRefresh: false
    };
    if (sectorTopicsRevisionFromServer != null) {
        settings.sectorTopicsRevision = sectorTopicsRevisionFromServer;
    }
    return settings;
}

function loadSettings() {
    const saved = localStorage.getItem(SECTOR_STORAGE_KEY);

    if (!saved) {
        sectorSettings = buildDefaultSettings();
        return;
    }

    try {
        sectorSettings = JSON.parse(saved);
    } catch (e) {
        console.error('Error loading sector settings, resetting to defaults:', e);
        try {
            localStorage.removeItem(SECTOR_STORAGE_KEY);
        } catch (removeErr) {
            console.warn('Could not remove corrupt sector settings key:', removeErr);
        }
        sectorSettings = buildDefaultSettings();
        saveSettingsToStorage();
        return;
    }

    // Fall back to a valid sector if the stored one disappeared or was disabled
    const stored = getSectorById(sectorSettings.sector);
    if (!stored || !stored.enabled) {
        sectorSettings.sector = firstEnabledSectorId();
        sectorSettings.topics = [];
    }

    if (!sectorSettings.days) {
        sectorSettings.days = 7;
    }

    // Backfill fields added after a user's settings were first written
    if (sectorSettings.queryReformulation === undefined) {
        sectorSettings.queryReformulation = false;
    }
    if (sectorSettings.autoRefresh === undefined) {
        sectorSettings.autoRefresh = false;
    }

    if (!Array.isArray(sectorSettings.topics) || sectorSettings.topics.length === 0) {
        sectorSettings.topics = getDefaultTopicsFor(sectorSettings.sector);
        if (sectorTopicsRevisionFromServer != null) {
            sectorSettings.sectorTopicsRevision = sectorTopicsRevisionFromServer;
        }
    }

    syncStoredTopicsToServerRevision();
    saveSettingsToStorage();
}

/** Replace cached phrases when SECTOR_TOPICS_REVISION was bumped server-side. */
function syncStoredTopicsToServerRevision() {
    if (sectorTopicsRevisionFromServer == null) {
        return;
    }
    if (sectorSettings.sectorTopicsRevision === sectorTopicsRevisionFromServer) {
        return;
    }
    sectorSettings.topics = getDefaultTopicsFor(sectorSettings.sector);
    sectorSettings.sectorTopicsRevision = sectorTopicsRevisionFromServer;
    console.log(
        `Replaced cached sector topics with server defaults (revision ${sectorTopicsRevisionFromServer}).`
    );
}

function saveSettingsToStorage() {
    try {
        localStorage.setItem(SECTOR_STORAGE_KEY, JSON.stringify(sectorSettings));
    } catch (e) {
        console.warn('Could not persist sector settings:', e);
    }
}

// ============================================================================
// SECTOR TILES
// ============================================================================

function renderSectorTiles() {
    const container = document.getElementById('sectorTiles');
    container.innerHTML = '';

    if (sectors.length === 0) {
        container.innerHTML = '<div class="sector-tiles-loading">No sectors available</div>';
        updateCarouselArrows();
        return;
    }

    let activeTile = null;

    sectors.forEach(sector => {
        const tile = document.createElement('div');
        const isActive = sector.enabled && sector.id === sectorSettings.sector;
        tile.className = 'sector-tile'
            + (sector.enabled ? '' : ' disabled')
            + (isActive ? ' active' : '');

        const label = document.createElement('div');
        label.className = 'sector-tile-label';
        label.textContent = sector.label;

        const meta = document.createElement('div');
        meta.className = 'sector-tile-meta';
        meta.textContent = sector.enabled
            ? `${sector.topic_count} topics`
            : 'Coming soon';

        const description = document.createElement('div');
        description.className = 'sector-tile-desc';
        description.textContent = sector.description;

        tile.appendChild(label);
        tile.appendChild(description);
        tile.appendChild(meta);

        if (sector.enabled) {
            tile.onclick = () => selectSector(sector.id);
        }

        if (isActive) {
            activeTile = tile;
        }

        container.appendChild(tile);
    });

    // The selected desk can sit past the right edge of the carousel on a narrow window
    if (activeTile) {
        activeTile.scrollIntoView({ block: 'nearest', inline: 'nearest' });
    }
    updateCarouselArrows();
}

/**
 * Wire the carousel arrows and keep their enabled state in sync with the scroll position.
 * Called once on load; the tile list itself is re-rendered on every sector switch.
 */
function initializeSectorCarousel() {
    const viewport = document.getElementById('sectorTilesViewport');
    const prev = document.getElementById('sectorScrollPrev');
    const next = document.getElementById('sectorScrollNext');
    if (!viewport || !prev || !next) {
        return;
    }

    prev.addEventListener('click', () => scrollSectorTiles(-1));
    next.addEventListener('click', () => scrollSectorTiles(1));
    viewport.addEventListener('scroll', updateCarouselArrows);
    window.addEventListener('resize', updateCarouselArrows);

    updateCarouselArrows();
}

/** Scroll roughly one screenful of tiles, snapping to a whole number of tiles. */
function scrollSectorTiles(direction) {
    const viewport = document.getElementById('sectorTilesViewport');
    if (!viewport) {
        return;
    }

    const tile = viewport.querySelector('.sector-tile');
    const step = tile ? tile.offsetWidth + SECTOR_TILE_GAP_PX : viewport.clientWidth;
    const tilesPerPage = Math.max(1, Math.floor(viewport.clientWidth / step));

    viewport.scrollBy({ left: direction * step * tilesPerPage, behavior: 'smooth' });
}

function updateCarouselArrows() {
    const viewport = document.getElementById('sectorTilesViewport');
    const prev = document.getElementById('sectorScrollPrev');
    const next = document.getElementById('sectorScrollNext');
    if (!viewport || !prev || !next) {
        return;
    }

    // Fractional scroll widths mean the end is never reached exactly
    const maxScroll = viewport.scrollWidth - viewport.clientWidth;
    const overflows = maxScroll > 1;

    // On a wide window every desk fits, so the arrows would be dead controls
    viewport.closest('.sector-carousel').classList.toggle('no-overflow', !overflows);

    prev.disabled = !overflows || viewport.scrollLeft <= 1;
    next.disabled = !overflows || viewport.scrollLeft >= maxScroll - 1;
}

function selectSector(sectorId) {
    const sector = getSectorById(sectorId);
    if (!sector || !sector.enabled) {
        return;
    }

    const isSwitch = sectorSettings.sector !== sectorId;
    sectorSettings.sector = sectorId;

    // Each sector has its own phrase set, so reset to that sector's defaults on switch
    if (isSwitch) {
        sectorSettings.topics = getDefaultTopicsFor(sectorId);
        currentTopicFilter = 'all';
        // Articles from the previous desk must not count as "new" for this one
        previousArticleIds = new Set();
        lastRefreshTime = null;
    }

    saveSettingsToStorage();
    renderSectorTiles();
    updateActiveSectorLabel();
    renderTopicsInputList();
    updateTopicsCount();
    getSectorNews();
}

function updateActiveSectorLabel() {
    const labelEl = document.getElementById('activeSectorLabel');
    const sector = getSectorById(sectorSettings.sector);
    labelEl.textContent = sector ? sector.label : 'No sector selected';
}

// ============================================================================
// FILTERS
// ============================================================================

function initializeFilters() {
    const reformulateToggle = document.getElementById('reformulateToggle');
    if (reformulateToggle) {
        reformulateToggle.checked = sectorSettings.queryReformulation;

        // Without Gemini configured the backend silently falls back to the original phrases
        if (!queryExpansionAvailable) {
            reformulateToggle.disabled = true;
            reformulateToggle.closest('.filter-checkbox-label').title =
                'AI query expansion needs Gemini credentials configured on the server';
        }
    }

    document.querySelectorAll('.date-btn').forEach(btn => {
        const days = parseInt(btn.getAttribute('data-days'));

        if (days === sectorSettings.days) {
            btn.classList.add('active');
        } else {
            btn.classList.remove('active');
        }

        btn.addEventListener('click', function() {
            sectorSettings.days = parseInt(this.getAttribute('data-days'));
            document.querySelectorAll('.date-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            saveSettingsToStorage();
            console.log('Date filter updated:', sectorSettings.days, 'days');
        });
    });
}

function toggleReformulate() {
    const reformulateToggle = document.getElementById('reformulateToggle');
    sectorSettings.queryReformulation = reformulateToggle.checked;
    saveSettingsToStorage();

    showNotification(
        sectorSettings.queryReformulation
            ? 'AI query expansion ON - 4x queries per search'
            : 'AI query expansion OFF'
    );
}

// ============================================================================
// SEARCH
// ============================================================================

async function getSectorNews(isRefresh = false) {
    const sector = getSectorById(sectorSettings.sector);

    if (!sector) {
        showError('Select a sector to load news');
        return;
    }

    if (!sectorSettings.topics || sectorSettings.topics.length === 0) {
        showError('No search phrases configured. Use Edit Topics to add at least one.');
        return;
    }

    // A refresh updates in place, so avoid replacing the feed with a spinner
    if (!isRefresh) {
        setLoading(true);
    }

    try {
        const requestBody = {
            sector: sector.id,
            days: sectorSettings.days,
            relevance: 0.1,
            topics: sectorSettings.topics,
            query_reformulation: sectorSettings.queryReformulation
        };

        // On refresh, only ask for what has been published since the last fetch
        if (isRefresh && lastRefreshTime) {
            const minutesSinceLastRefresh = Math.ceil((Date.now() - lastRefreshTime) / (60 * 1000));
            requestBody.since_minutes = minutesSinceLastRefresh;
            // Expansion costs an extra Gemini round trip per phrase; not worth it on an automated refresh
            requestBody.query_reformulation = false;
            console.log(`Incremental refresh: fetching last ${minutesSinceLastRefresh} minutes`);
        }

        const response = await fetchWithTimeout('/api/sector-news', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
            timeout: SECTOR_FETCH_TIMEOUT_MS
        });

        const data = await response.json();

        if (!response.ok) {
            throw new Error(data.detail || 'Failed to fetch sector news');
        }

        const fetched = data.theme_results || [];

        if (isRefresh) {
            allArticles = mergeArticles(allArticles, fetched);
            console.log(`Refresh: ${fetched.length} fetched, ${allArticles.length} total after merge`);
        } else {
            allArticles = fetched;
            previousArticleIds = new Set(fetched.map(a => a.id));
            lastSearchStats = data.search_stats || null;
        }

        displayNews(isRefresh);

        lastRefreshTime = Date.now();

        if (!isRefresh && sectorSettings.autoRefresh) {
            startAutoRefresh();
        }
    } catch (error) {
        console.error('Error fetching sector news:', error);
        // A failed background refresh should not wipe the feed the user is reading
        if (!isRefresh) {
            showError(`Error: ${error.message}`);
        }
    } finally {
        if (!isRefresh) {
            setLoading(false);
        }
    }
}

/** Merge incremental results into the existing feed, keeping the highest-relevance copy. */
function mergeArticles(existing, incoming) {
    const byId = new Map();

    existing.forEach(article => byId.set(article.id, article));

    incoming.forEach(article => {
        const current = byId.get(article.id);
        if (!current || (article.relevance || 0) > (current.relevance || 0)) {
            byId.set(article.id, article);
        }
    });

    return [...byId.values()];
}

// ============================================================================
// AUTO-REFRESH
// ============================================================================

function startAutoRefresh() {
    stopAutoRefresh();

    refreshInterval = setInterval(() => {
        if (sectorSettings.sector) {
            console.log('Auto-refreshing sector feed:', sectorSettings.sector);
            getSectorNews(true);
        }
    }, AUTO_REFRESH_MS);

    updateLiveIndicator();
    console.log(`Auto-refresh started (every ${formatRefreshInterval(AUTO_REFRESH_MS)})`);
}

function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
    updateLiveIndicator();
}

function setAutoRefresh(enabled) {
    sectorSettings.autoRefresh = enabled === true;
    saveSettingsToStorage();

    if (!sectorSettings.autoRefresh) {
        stopAutoRefresh();
    } else if (allArticles.length > 0) {
        startAutoRefresh();
    } else {
        updateLiveIndicator();
    }

    return sectorSettings.autoRefresh;
}

/** Show a LIVE pill while auto-refresh is armed so the feed's state is never ambiguous. */
function updateLiveIndicator() {
    const indicator = document.getElementById('liveIndicator');
    if (!indicator) {
        return;
    }

    if (!sectorSettings.autoRefresh) {
        indicator.style.display = 'none';
        return;
    }

    indicator.style.display = 'inline-flex';
    indicator.classList.toggle('armed', refreshInterval !== null);
    indicator.title = refreshInterval !== null
        ? `Auto-refresh on: fetching new articles every ${formatRefreshInterval(AUTO_REFRESH_MS)}`
        : 'Auto-refresh on: starts after the first search';
}

// ============================================================================
// RENDERING
// ============================================================================

function displayNews(isRefresh = false) {
    const newsFeed = document.getElementById('newsFeed');
    const articleCount = document.getElementById('articleCount');
    const sector = getSectorById(sectorSettings.sector);
    const sectorLabel = sector ? sector.label : '';

    renderTopicTabs();

    let articles = allArticles;
    if (currentTopicFilter !== 'all') {
        articles = articles.filter(a => (a.topic_name || '') === currentTopicFilter);
    }

    const timeString = new Date().toLocaleTimeString('en-US', {
        hour12: false,
        hour: '2-digit',
        minute: '2-digit',
        second: '2-digit'
    });

    const newIds = isRefresh
        ? allArticles.filter(a => !previousArticleIds.has(a.id)).map(a => a.id)
        : [];
    const newIdSet = new Set(newIds);

    // Rebuilding innerHTML resets scrollTop, so remember where the reader was
    const previousScrollTop = newsFeed.scrollTop;

    let countText = `${articles.length} Articles`;
    if (isRefresh && newIds.length > 0) {
        countText += ` (${newIds.length} new)`;
    }
    // Make it visible that expansion actually widened the search
    if (lastSearchStats && lastSearchStats.query_reformulation) {
        countText += ` | AI expanded: ${lastSearchStats.queries_executed} queries`;
    }
    countText += ` | Last Update: ${timeString}`;
    if (currentTopicFilter !== 'all') {
        countText += ` (${currentTopicFilter.toUpperCase()})`;
    }
    articleCount.textContent = countText;

    if (articles.length === 0) {
        newsFeed.innerHTML = `
            <div class="no-results">
                <div style="font-size: 16px; margin-bottom: 10px;">📰</div>
                <div>No recent news found</div>
                <div style="margin-top: 10px; font-size: 10px;">
                    Try a wider date range or edit the search phrases
                </div>
            </div>
        `;
        return;
    }

    // Most recent first
    const sorted = [...articles].sort((a, b) => new Date(b.timestamp) - new Date(a.timestamp));

    newsFeed.innerHTML = sorted.map(article => {
        const relevancePercent = Math.round((article.relevance || 0) * 100);
        const relevanceColor = getRelevanceColor(article.relevance || 0);
        const topicName = article.topic_name || '-';
        const fullText = article.full_text || article.summary || '';

        const isNew = newIdSet.has(article.id);
        const newBadge = isNew ? '<span class="new-badge">NEW</span>' : '';
        const animationClass = isNew ? ' new-article' : '';

        const articleLink = article.document_url ? `
            <div class="article-link">
                <a href="${escapeHtml(article.document_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">
                    🔗 Read full article
                </a>
            </div>
        ` : '';

        return `
            <div class="news-item${animationClass}" onclick="toggleArticle(event)">
                <div class="news-row">
                    <div class="news-row-sector">
                        <span class="ticker-tag">${escapeHtml(sectorLabel)}</span>
                    </div>
                    <div class="news-row-topic">
                        <span class="topic-tag">${escapeHtml(topicName)}</span>
                    </div>
                    <div class="news-row-headline">
                        <div class="news-headline">${newBadge}${escapeHtml(article.headline)}</div>
                        <div class="news-meta">
                            <span class="news-type">${escapeHtml(article.document_type || 'NEWS')}</span>
                            <span style="color: #30363d;">•</span>
                            <div class="relevance-bar">
                                <div class="relevance-fill" style="width: ${relevancePercent}%; background: ${relevanceColor}"></div>
                            </div>
                            <span class="news-relevance">${relevancePercent}%</span>
                        </div>
                    </div>
                    <div class="news-row-source">${escapeHtml(article.source || 'Unknown')}</div>
                    <div class="news-row-time">${escapeHtml(article.time_ago || '')}</div>
                </div>
                <div class="news-summary">
                    ${escapeHtml(fullText)}
                    ${articleLink}
                </div>
            </div>
        `;
    }).join('');

    previousArticleIds = new Set(allArticles.map(a => a.id));

    if (isRefresh) {
        newsFeed.scrollTop = previousScrollTop;
        if (newIds.length > 0) {
            showNotification(`${newIds.length} new article${newIds.length > 1 ? 's' : ''} found!`);
        }
    } else {
        newsFeed.scrollTop = 0;
    }
}

function toggleArticle(event) {
    event.currentTarget.classList.toggle('expanded');
}

function setLoading(loading) {
    const getNewsBtn = document.getElementById('getNewsBtn');

    if (loading) {
        getNewsBtn.disabled = true;
        getNewsBtn.textContent = 'LOADING...';

        const topicCount = sectorSettings.topics.length;
        const expanding = sectorSettings.queryReformulation && queryExpansionAvailable;
        const queryCount = expanding ? topicCount * 4 : topicCount;
        const detail = expanding
            ? `<div style="margin-top: 6px; font-size: 10px;">AI query expansion on: ${queryCount} queries</div>`
            : '';

        document.getElementById('newsFeed').innerHTML = `
            <div class="loading">
                <div style="font-size: 16px; margin-bottom: 10px;">📡</div>
                <div>Searching ${topicCount} topic${topicCount === 1 ? '' : 's'}</div>
                ${detail}
            </div>
        `;
    } else {
        getNewsBtn.disabled = false;
        getNewsBtn.textContent = 'GET NEWS';
    }
}

function showError(message) {
    document.getElementById('newsFeed').innerHTML = `
        <div class="error">
            <div style="font-size: 16px; margin-bottom: 10px;">⚠️</div>
            <div>${escapeHtml(message)}</div>
        </div>
    `;
}

function clearResults() {
    stopAutoRefresh();
    allArticles = [];
    currentTopicFilter = 'all';
    previousArticleIds = new Set();
    lastRefreshTime = null;
    lastSearchStats = null;

    document.getElementById('articleCount').textContent = '';
    document.getElementById('topicTabsBar').style.display = 'none';
    document.getElementById('newsFeed').innerHTML = `
        <div class="welcome-message">
            <div class="welcome-title">Sector News Desk</div>
            <div class="welcome-text">
                Select a sector above to load a single real-time feed for that desk
            </div>
        </div>
    `;
}

// ============================================================================
// TOPIC TABS
// ============================================================================

function renderTopicTabs() {
    const tabsBar = document.getElementById('topicTabsBar');
    const tabsList = document.getElementById('topicTabsList');

    if (!tabsBar || !tabsList) {
        return;
    }

    tabsList.innerHTML = '';

    if (allArticles.length === 0) {
        tabsBar.style.display = 'none';
        return;
    }

    tabsBar.style.display = 'flex';

    const allTab = document.createElement('div');
    allTab.className = 'topic-tab all-tab' + (currentTopicFilter === 'all' ? ' active' : '');
    allTab.textContent = 'ALL';
    allTab.onclick = () => filterByTopic('all');
    tabsList.appendChild(allTab);

    // Only offer tabs for topics that actually returned articles
    const namesWithResults = new Set(allArticles.map(a => a.topic_name).filter(Boolean));

    const seen = new Set();
    sectorSettings.topics.forEach(topic => {
        const name = (topic.topic_name || '').trim();
        if (!name || seen.has(name) || !namesWithResults.has(name)) {
            return;
        }
        seen.add(name);

        const tab = document.createElement('div');
        tab.className = 'topic-tab' + (currentTopicFilter === name ? ' active' : '');
        tab.textContent = name.toUpperCase();
        tab.onclick = () => filterByTopic(name);
        tabsList.appendChild(tab);
    });
}

function filterByTopic(topicName) {
    currentTopicFilter = topicName;
    displayNews();
}

// ============================================================================
// TOPICS EDITOR
// ============================================================================

function toggleTopicsPanel() {
    const panel = document.getElementById('topicsPanel');

    if (panel.classList.contains('active')) {
        closeTopicsPanel();
    } else {
        openTopicsPanel();
    }
}

function openTopicsPanel() {
    const panel = document.getElementById('topicsPanel');
    const button = document.getElementById('topicsDropdown');

    if (panel) panel.classList.add('active');
    if (button) button.classList.add('active');

    originalTopics = JSON.parse(JSON.stringify(sectorSettings.topics));
    renderTopicsInputList();
}

function closeTopicsPanel() {
    const panel = document.getElementById('topicsPanel');
    const button = document.getElementById('topicsDropdown');

    if (panel) panel.classList.remove('active');
    if (button) button.classList.remove('active');
}

function renderTopicsInputList() {
    const listContainer = document.getElementById('topicsInputList');
    listContainer.innerHTML = '';

    sectorSettings.topics.forEach((topic, index) => {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'topics-input-item';

        const label = document.createElement('span');
        label.className = 'topics-input-label';
        label.textContent = `${index + 1}.`;

        const nameInput = document.createElement('input');
        nameInput.type = 'text';
        nameInput.className = 'topics-input-field';
        nameInput.value = topic.topic_name || `Topic ${index + 1}`;
        nameInput.placeholder = 'Topic name...';
        nameInput.dataset.index = index;
        nameInput.dataset.field = 'name';
        nameInput.style.width = '25%';
        nameInput.style.marginRight = '4px';

        nameInput.addEventListener('input', (e) => {
            sectorSettings.topics[index].topic_name = e.target.value;
        });

        const textInput = document.createElement('input');
        textInput.type = 'text';
        textInput.className = 'topics-input-field';
        textInput.value = topic.topic_text || '';
        textInput.placeholder = 'Search phrase, e.g. crude oil supply disruption...';
        textInput.dataset.index = index;
        textInput.dataset.field = 'text';
        textInput.style.flex = '1';

        validateTopicInput(textInput);

        textInput.addEventListener('input', (e) => {
            sectorSettings.topics[index].topic_text = e.target.value;
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

/**
 * Sector phrases are sent verbatim, so the only hard requirement is non-empty text.
 * A leftover {company} placeholder would be searched literally, so flag it too.
 */
function validateTopicInput(input) {
    if (input.dataset.field !== 'text') {
        return true;
    }

    const value = input.value.trim();
    const isValid = value !== '' && !value.includes('{company}');

    if (isValid) {
        input.classList.remove('error');
        input.title = '';
    } else {
        input.classList.add('error');
        input.title = value === ''
            ? 'Search phrase cannot be empty'
            : 'Sector phrases have no company placeholder - remove {company}';
    }

    return isValid;
}

function addTopicInput() {
    sectorSettings.topics.push({
        topic_name: `Topic ${sectorSettings.topics.length + 1}`,
        topic_text: ''
    });
    renderTopicsInputList();
    updateTopicsCount();

    const inputs = document.querySelectorAll('.topics-input-field[data-field="text"]');
    const lastInput = inputs[inputs.length - 1];
    if (lastInput) {
        lastInput.focus();
    }
}

function deleteTopicInput(index) {
    sectorSettings.topics.splice(index, 1);
    renderTopicsInputList();
    updateTopicsCount();
}

function updateTopicsCount() {
    const uniqueNames = new Set(
        sectorSettings.topics.map(t => (t.topic_name || '').trim()).filter(Boolean)
    );

    const inlineEl = document.getElementById('topicsCountInline');
    if (inlineEl) {
        inlineEl.textContent = `${uniqueNames.size} / ${sectorSettings.topics.length} phrases`;
    }
}

function resetTopicsToDefault() {
    if (!confirm('Reset search phrases to defaults?')) {
        return;
    }

    sectorSettings.topics = getDefaultTopicsFor(sectorSettings.sector);
    if (sectorTopicsRevisionFromServer != null) {
        sectorSettings.sectorTopicsRevision = sectorTopicsRevisionFromServer;
    } else {
        delete sectorSettings.sectorTopicsRevision;
    }

    saveSettingsToStorage();
    renderTopicsInputList();
    updateTopicsCount();
    showNotification('Search phrases reset to defaults');
}

function saveAndCloseTopics() {
    // Sync every field back in case an input event was missed
    document.querySelectorAll('.topics-input-field').forEach(input => {
        const index = parseInt(input.dataset.index);
        const topic = sectorSettings.topics[index];
        if (!topic) {
            return;
        }
        if (input.dataset.field === 'name') {
            topic.topic_name = input.value.trim();
        } else {
            topic.topic_text = input.value.trim();
        }
    });

    // Rows left blank were abandoned rather than misconfigured, so drop them quietly
    const kept = sectorSettings.topics.filter(t => (t.topic_text || '').trim() !== '');
    const droppedCount = sectorSettings.topics.length - kept.length;

    // A leftover placeholder would be searched literally, so this one has to be corrected
    if (kept.some(t => t.topic_text.includes('{company}'))) {
        alert('Error: sector phrases have no company placeholder - remove {company}');
        return;
    }

    if (kept.length === 0) {
        alert('Error: add at least one search phrase');
        return;
    }

    // Backfill missing names so every phrase still maps to a topic tab
    sectorSettings.topics = kept.map((t, i) => ({
        topic_name: (t.topic_name || '').trim() || `Topic ${i + 1}`,
        topic_text: t.topic_text.trim()
    }));

    const topicsChanged = JSON.stringify(originalTopics) !== JSON.stringify(sectorSettings.topics);

    updateTopicsCount();
    saveSettingsToStorage();
    renderTopicsInputList();
    closeTopicsPanel();

    showNotification(
        droppedCount > 0
            ? `Search phrases saved (${droppedCount} empty row${droppedCount === 1 ? '' : 's'} removed)`
            : 'Search phrases saved'
    );

    if (topicsChanged && allArticles.length > 0) {
        if (confirm('Phrases saved. Reload the feed with the new phrases?')) {
            getSectorNews();
        }
    }
}
