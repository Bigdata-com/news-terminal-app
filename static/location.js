// Location News Terminal - Knowledge Graph place + event-taxonomy topics, one row per chunk
const LOCATION_STORAGE_KEY = 'locationTerminalSettings';
const LOCATION_FETCH_TIMEOUT_MS = 120000;
const LOOKUP_DEBOUNCE_MS = 300;

// Demo defaults: copper and lithium supply risk in Chile
const DEFAULT_PLACE = { id: '47A64D', name: 'Chile', type: 'Country', country: 'CL' };
const DEFAULT_TOPICS = [
    { id: 'business,labor-issues,workers-strike,,', name: 'Strike' },
    { id: 'society,civil-unrest,protest,,', name: 'Protest' },
    { id: 'business,industrial-accidents,mine-accident,,', name: 'Mine Accident' },
    { id: 'business,products-services,supply-chain-disruption,,', name: 'Supply Chain Disruption' },
    { id: 'business,industrial-accidents,force-majeure,,', name: 'Force Majeure' },
    { id: 'environment,natural-disasters,water-shortage,,', name: 'Water Shortage' }
];

// Persisted user settings
let locationSettings = {
    place: null,
    topics: [],
    days: 7,
    strict: true,
    maxChunks: null
};

// Feed state
let allChunks = [];
let currentTopicFilter = 'all';
let lastRequests = [];
let lastSearchStats = null;

// ============================================================================
// UTILITIES
// ============================================================================

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
    setTimeout(() => notification.remove(), 3000);
}

function titleCase(text) {
    return (text || '').replace(/[-_]/g, ' ').replace(/\b\w/g, c => c.toUpperCase());
}

function placeDescription(place) {
    return [place.type, place.region, place.country].filter(Boolean).join(' · ');
}

function debounce(fn, ms) {
    let timer = null;
    return (...args) => {
        clearTimeout(timer);
        timer = setTimeout(() => fn(...args), ms);
    };
}

/**
 * Escape chunk text and wrap the place and topic detection spans.
 * Spans are character offsets into the chunk; they can overlap, so each segment
 * between boundaries gets whichever classes cover it.
 */
function highlightChunk(text, placeSpans, topicSpans) {
    const bounds = new Set([0, text.length]);
    [...placeSpans, ...topicSpans].forEach(([s, e]) => {
        bounds.add(Math.max(0, Math.min(s, text.length)));
        bounds.add(Math.max(0, Math.min(e, text.length)));
    });
    const points = [...bounds].sort((a, b) => a - b);
    const covers = (spans, s, e) => spans.some(([a, b]) => a <= s && e <= b);

    let html = '';
    for (let i = 0; i < points.length - 1; i++) {
        const s = points[i];
        const e = points[i + 1];
        const segment = escapeHtml(text.slice(s, e));
        const classes = [];
        if (covers(placeSpans, s, e)) classes.push('hl-place');
        if (covers(topicSpans, s, e)) classes.push('hl-topic');
        html += classes.length ? `<span class="${classes.join(' ')}">${segment}</span>` : segment;
    }
    return html;
}

// ============================================================================
// INITIALIZATION
// ============================================================================

async function initializeLocationApp() {
    loadSettings();
    initializeFilters();
    initializeLookup({
        inputId: 'placeInput',
        resultsId: 'placeResults',
        url: q => `/api/places?q=${encodeURIComponent(q)}`,
        renderItem: p => `
            <span class="lookup-name">${escapeHtml(p.name)}</span>
            <span class="lookup-meta">${escapeHtml(placeDescription(p))}</span>
            <span class="lookup-id">${escapeHtml(p.id)}</span>`,
        onPick: selectPlace
    });
    initializeLookup({
        inputId: 'topicInput',
        resultsId: 'topicResults',
        url: q => `/api/topics?q=${encodeURIComponent(q)}`,
        renderItem: t => `
            <span class="lookup-name">${escapeHtml(t.name)}</span>
            <span class="lookup-meta">${escapeHtml(t.description || '')}</span>
            <span class="lookup-id">${escapeHtml(t.id)}</span>`,
        onPick: addTopic
    });
    renderPicked();

    document.addEventListener('keydown', function(e) {
        if (e.key === 'Escape') {
            closeAllLookups();
        }
    });
    document.addEventListener('click', function(e) {
        if (!e.target.closest('.lookup')) {
            closeAllLookups();
        }
    });
}

document.addEventListener('DOMContentLoaded', async function() {
    setOnAppReady(initializeLocationApp);
    const ready = await runLaunchGate();
    if (ready) {
        await initializeLocationApp();
    }
});

function loadSettings() {
    try {
        const stored = JSON.parse(localStorage.getItem(LOCATION_STORAGE_KEY) || 'null');
        if (stored && typeof stored === 'object') {
            locationSettings = { ...locationSettings, ...stored };
        }
    } catch (error) {
        console.warn('Could not read location settings:', error);
    }
    if (!locationSettings.place && (!locationSettings.topics || locationSettings.topics.length === 0)) {
        locationSettings.place = { ...DEFAULT_PLACE };
        locationSettings.topics = DEFAULT_TOPICS.map(t => ({ ...t }));
    }
    locationSettings.topics = locationSettings.topics || [];
}

function saveSettingsToStorage() {
    try {
        localStorage.setItem(LOCATION_STORAGE_KEY, JSON.stringify(locationSettings));
    } catch (error) {
        console.warn('Could not save location settings:', error);
    }
}

// ============================================================================
// FILTERS
// ============================================================================

function initializeFilters() {
    document.querySelectorAll('.date-btn').forEach(btn => {
        const days = parseInt(btn.getAttribute('data-days'));
        btn.classList.toggle('active', days === locationSettings.days);

        btn.addEventListener('click', function() {
            locationSettings.days = parseInt(this.getAttribute('data-days'));
            document.querySelectorAll('.date-btn').forEach(b => b.classList.remove('active'));
            this.classList.add('active');
            saveSettingsToStorage();
        });
    });

    const strictToggle = document.getElementById('strictToggle');
    strictToggle.checked = locationSettings.strict !== false;
    strictToggle.addEventListener('change', function() {
        locationSettings.strict = this.checked;
        saveSettingsToStorage();
    });

    const maxChunksInput = document.getElementById('maxChunksInput');
    maxChunksInput.value = locationSettings.maxChunks || '';
    maxChunksInput.addEventListener('change', function() {
        const n = parseInt(this.value);
        locationSettings.maxChunks = Number.isFinite(n) ? Math.max(1, Math.min(n, 500)) : null;
        this.value = locationSettings.maxChunks || '';
        saveSettingsToStorage();
    });
}

// ============================================================================
// KNOWLEDGE GRAPH LOOKUPS
// ============================================================================

function initializeLookup({ inputId, resultsId, url, renderItem, onPick }) {
    const input = document.getElementById(inputId);
    const results = document.getElementById(resultsId);
    let items = [];
    let active = -1;

    const highlight = () => {
        results.querySelectorAll('.lookup-item').forEach((el, i) => el.classList.toggle('active', i === active));
    };

    const pick = index => {
        if (!items[index]) return;
        onPick(items[index]);
        input.value = '';
        results.hidden = true;
        items = [];
    };

    const search = debounce(async () => {
        const q = input.value.trim();
        if (q.length < 2) {
            results.hidden = true;
            return;
        }
        results.hidden = false;
        results.innerHTML = '<div class="lookup-empty">Searching Knowledge Graph…</div>';
        try {
            const response = await fetchWithTimeout(url(q), { timeout: 20000 });
            const data = await response.json();
            if (!response.ok) throw new Error(data.detail || data.message || 'Lookup failed');
            if (input.value.trim() !== q) return; // a newer query is in flight
            items = data.results || [];
            active = items.length ? 0 : -1;
            results.innerHTML = items.length
                ? items.map((item, i) => `<div class="lookup-item" data-index="${i}">${renderItem(item)}</div>`).join('')
                : '<div class="lookup-empty">No matches</div>';
            results.querySelectorAll('.lookup-item').forEach(el => {
                el.addEventListener('mousedown', e => {
                    e.preventDefault();
                    pick(parseInt(el.dataset.index));
                });
            });
            highlight();
        } catch (error) {
            results.innerHTML = `<div class="lookup-empty">${escapeHtml(error.message)}</div>`;
        }
    }, LOOKUP_DEBOUNCE_MS);

    input.addEventListener('input', search);
    input.addEventListener('keydown', e => {
        if (results.hidden || !items.length) return;
        if (e.key === 'ArrowDown') {
            active = (active + 1) % items.length;
            highlight();
            e.preventDefault();
        } else if (e.key === 'ArrowUp') {
            active = (active - 1 + items.length) % items.length;
            highlight();
            e.preventDefault();
        } else if (e.key === 'Enter') {
            pick(active);
            e.preventDefault();
        }
    });
}

function closeAllLookups() {
    document.querySelectorAll('.lookup-results').forEach(el => { el.hidden = true; });
}

function selectPlace(place) {
    locationSettings.place = {
        id: place.id,
        name: place.name,
        type: place.type,
        region: place.region,
        country: place.country
    };
    saveSettingsToStorage();
    renderPicked();
}

function addTopic(topic) {
    if (locationSettings.topics.some(t => t.id === topic.id)) {
        showNotification(`${topic.name} is already added`);
        return;
    }
    locationSettings.topics.push({ id: topic.id, name: topic.name });
    saveSettingsToStorage();
    renderPicked();
}

function removeTopic(index) {
    locationSettings.topics.splice(index, 1);
    saveSettingsToStorage();
    renderPicked();
}

function clearPlace() {
    locationSettings.place = null;
    saveSettingsToStorage();
    renderPicked();
}

function renderPicked() {
    const place = locationSettings.place;
    document.getElementById('placePicked').innerHTML = place ? `
        <span class="picked-chip place-chip" title="${escapeHtml(placeDescription(place))}">
            ${escapeHtml(place.name)}
            <span class="picked-id">${escapeHtml(place.id)}</span>
            <button type="button" onclick="clearPlace()" aria-label="Remove location">&times;</button>
        </span>` : '';

    document.getElementById('topicPicked').innerHTML = locationSettings.topics.map((t, i) => `
        <span class="picked-chip" title="${escapeHtml(t.id)}">
            ${escapeHtml(t.name || t.id)}
            <button type="button" onclick="removeTopic(${i})" aria-label="Remove ${escapeHtml(t.name || t.id)}">&times;</button>
        </span>`).join('');

    const label = document.getElementById('activeLocationLabel');
    label.textContent = place
        ? `${place.name} × ${locationSettings.topics.length} topic${locationSettings.topics.length === 1 ? '' : 's'}`
        : 'No location selected';
}

// ============================================================================
// SEARCH
// ============================================================================

async function getLocationNews() {
    const place = locationSettings.place;
    if (!place) {
        showError('Look up and pick a location first');
        return;
    }
    if (locationSettings.topics.length === 0) {
        showError('Add at least one event topic');
        return;
    }

    setLoading(true);

    try {
        const requestBody = {
            place_id: place.id,
            topics: locationSettings.topics,
            days: locationSettings.days,
            strict: locationSettings.strict !== false
        };
        if (locationSettings.maxChunks) {
            requestBody.max_chunks = locationSettings.maxChunks;
        }

        const response = await fetchWithTimeout('/api/location-news', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(requestBody),
            timeout: LOCATION_FETCH_TIMEOUT_MS
        });
        const data = await response.json();
        if (!response.ok) {
            throw new Error(data.detail || data.message || 'Failed to fetch location news');
        }

        allChunks = data.chunk_results || [];
        lastRequests = data.requests || [];
        lastSearchStats = data.search_stats || null;
        currentTopicFilter = 'all';
        document.getElementById('payloadBtn').disabled = lastRequests.length === 0;
        renderPayload();
        displayNews();
    } catch (error) {
        console.error('Error fetching location news:', error);
        showError(`Error: ${error.message}`);
    } finally {
        setLoading(false);
    }
}

// ============================================================================
// RENDERING
// ============================================================================

function displayNews() {
    const newsFeed = document.getElementById('newsFeed');
    const articleCount = document.getElementById('articleCount');

    renderTopicTabs();

    let chunks = allChunks;
    if (currentTopicFilter !== 'all') {
        chunks = chunks.filter(c => c.topic_id === currentTopicFilter);
    }

    const docCount = new Set(chunks.map(c => c.document_id)).size;
    let countText = `${chunks.length} Chunks · ${docCount} Docs`;
    if (lastSearchStats && lastSearchStats.strict && lastSearchStats.chunks_dropped > 0) {
        countText += ` | ${lastSearchStats.chunks_dropped} chunks without both mentions hidden`;
    }
    countText += ` | ${new Date().toLocaleTimeString('en-US', { hour12: false })}`;
    articleCount.textContent = countText;

    if (chunks.length === 0) {
        newsFeed.innerHTML = `
            <div class="no-results">
                <div style="font-size: 16px; margin-bottom: 10px;">📍</div>
                <div>No chunks found</div>
                <div style="margin-top: 10px; font-size: 10px;">
                    Try a wider date range, more topics, or untick "Chunk must mention place + topic"
                </div>
            </div>
        `;
        return;
    }

    // Most recent first, then chunk order within a document
    const sorted = [...chunks].sort((a, b) =>
        (new Date(b.timestamp) - new Date(a.timestamp)) || ((a.cnum || 0) - (b.cnum || 0)));

    newsFeed.innerHTML = sorted.map(chunk => {
        const relevancePercent = Math.round((chunk.relevance || 0) * 100);
        const relevanceColor = getRelevanceColor(chunk.relevance || 0);
        const sentiment = typeof chunk.sentiment === 'number' ? chunk.sentiment : null;
        const sentimentClass = sentiment === null ? '' : (sentiment < -0.1 ? 'neg' : (sentiment > 0.1 ? 'pos' : 'neu'));
        const sentimentHtml = sentiment === null ? '' : `
            <span style="color: #30363d;">•</span>
            <span class="chunk-sentiment ${sentimentClass}" title="Chunk sentiment">${sentiment > 0 ? '+' : ''}${sentiment.toFixed(2)}</span>`;
        const fullText = chunk.full_text || '';

        const articleLink = chunk.document_url ? `
            <div class="article-link">
                <a href="${escapeHtml(chunk.document_url)}" target="_blank" rel="noopener noreferrer" onclick="event.stopPropagation()">
                    🔗 Read full article
                </a>
            </div>
        ` : '';

        return `
            <div class="news-item" onclick="toggleArticle(event)">
                <div class="news-row">
                    <div class="news-row-sector">
                        <span class="ticker-tag">${escapeHtml(titleCase(chunk.sector))}</span>
                    </div>
                    <div class="news-row-topic">
                        <span class="topic-tag" title="${escapeHtml(chunk.topic_id)}">${escapeHtml(chunk.topic_name || '-')}</span>
                    </div>
                    <div class="news-row-headline">
                        <div class="news-headline">${escapeHtml(chunk.headline)}</div>
                        <div class="news-meta">
                            <span class="news-type">CHUNK ${escapeHtml(String(chunk.cnum ?? '-'))}</span>
                            <span style="color: #30363d;">•</span>
                            <div class="relevance-bar">
                                <div class="relevance-fill" style="width: ${relevancePercent}%; background: ${relevanceColor}"></div>
                            </div>
                            <span class="news-relevance">${relevancePercent}%</span>
                            ${sentimentHtml}
                        </div>
                    </div>
                    <div class="news-row-source">${escapeHtml(chunk.source || 'Unknown')}</div>
                    <div class="news-row-time">${escapeHtml(chunk.time_ago || '')}</div>
                </div>
                <div class="news-summary">
                    ${highlightChunk(fullText, chunk.place_spans || [], chunk.topic_spans || [])}
                    ${articleLink}
                </div>
            </div>
        `;
    }).join('');

    newsFeed.scrollTop = 0;
}

function toggleArticle(event) {
    // Let readers select chunk text without collapsing the row
    if (window.getSelection && String(window.getSelection()).length > 0) return;
    event.currentTarget.classList.toggle('expanded');
}

function renderTopicTabs() {
    const tabsBar = document.getElementById('topicTabsBar');
    const tabsList = document.getElementById('topicTabsList');
    tabsList.innerHTML = '';

    if (allChunks.length === 0) {
        tabsBar.style.display = 'none';
        return;
    }
    tabsBar.style.display = 'flex';

    const counts = {};
    allChunks.forEach(c => { counts[c.topic_id] = (counts[c.topic_id] || 0) + 1; });

    const addTab = (id, label) => {
        const tab = document.createElement('div');
        tab.className = 'topic-tab' + (id === 'all' ? ' all-tab' : '') + (currentTopicFilter === id ? ' active' : '');
        tab.textContent = label;
        tab.onclick = () => filterByTopic(id);
        tabsList.appendChild(tab);
    };

    addTab('all', `ALL · ${allChunks.length}`);
    locationSettings.topics.forEach(t => {
        if (counts[t.id]) addTab(t.id, `${(t.name || t.id).toUpperCase()} · ${counts[t.id]}`);
    });
}

function filterByTopic(topicId) {
    currentTopicFilter = topicId;
    displayNews();
}

function setLoading(loading) {
    const getNewsBtn = document.getElementById('getNewsBtn');
    getNewsBtn.disabled = loading;
    getNewsBtn.textContent = loading ? 'LOADING...' : 'GET NEWS';

    if (loading) {
        const n = locationSettings.topics.length;
        document.getElementById('newsFeed').innerHTML = `
            <div class="loading">
                <div style="font-size: 16px; margin-bottom: 10px;">📡</div>
                <div>Searching ${escapeHtml(locationSettings.place.name)} × ${n} topic${n === 1 ? '' : 's'}</div>
            </div>
        `;
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
    allChunks = [];
    lastRequests = [];
    lastSearchStats = null;
    currentTopicFilter = 'all';

    document.getElementById('articleCount').textContent = '';
    document.getElementById('topicTabsBar').style.display = 'none';
    document.getElementById('payloadPanel').hidden = true;
    document.getElementById('payloadBtn').disabled = true;
    document.getElementById('newsFeed').innerHTML = `
        <div class="welcome-message">
            <div class="welcome-title">Location News Desk</div>
            <div class="welcome-text">Look up a place, add event topics, then GET NEWS</div>
        </div>
    `;
}

// ============================================================================
// PAYLOAD PANEL
// ============================================================================

function renderPayload() {
    document.getElementById('payloadJson').textContent = JSON.stringify(lastRequests, null, 2);
}

function togglePayloadPanel() {
    const panel = document.getElementById('payloadPanel');
    panel.hidden = !panel.hidden;
}

async function copyPayload() {
    try {
        await navigator.clipboard.writeText(JSON.stringify(lastRequests, null, 2));
        showNotification('Payload copied');
    } catch (error) {
        showNotification('Copy failed');
    }
}
