/**
 * Client-only Bigdata API key: localStorage + X-API-KEY + launch gate.
 * No server default — the user must provide a key.
 */
const API_KEY_STORAGE_KEY = 'bigdata_api_key';
const API_KEY_CHANGED_EVENT = 'bigdata-api-key-changed';

let apiKeyGateActive = false;
let onAppReadyCallback = null;

function getUserApiKey() {
    try {
        return (localStorage.getItem(API_KEY_STORAGE_KEY) || '').trim();
    } catch (error) {
        console.error('Unable to read API key from localStorage:', error);
        return '';
    }
}

function setUserApiKey(key) {
    const trimmed = (key || '').trim();
    try {
        if (trimmed) {
            localStorage.setItem(API_KEY_STORAGE_KEY, trimmed);
        } else {
            localStorage.removeItem(API_KEY_STORAGE_KEY);
        }
    } catch (error) {
        console.error('Unable to persist API key:', error);
    }
    window.dispatchEvent(new CustomEvent(API_KEY_CHANGED_EVENT, { detail: { hasKey: Boolean(trimmed) } }));
}

function hasUserApiKey() {
    return Boolean(getUserApiKey());
}

function setOnAppReady(callback) {
    onAppReadyCallback = callback;
}

async function isApiKeyAvailable() {
    if (hasUserApiKey()) {
        return true;
    }
    try {
        const response = await fetch('/api/config');
        const data = await response.json();
        return data.bigdata_api_key_configured === true;
    } catch (error) {
        console.error('Failed to check /api/config for API key gate:', error);
        return false;
    }
}

function showAppContent() {
    const appContent = document.getElementById('appContent');
    if (appContent) {
        appContent.style.display = '';
        appContent.removeAttribute('hidden');
    }
}

function hideAppContent() {
    const appContent = document.getElementById('appContent');
    if (appContent) {
        appContent.style.display = 'none';
    }
}

async function runLaunchGate() {
    const available = await isApiKeyAvailable();
    if (!available) {
        hideAppContent();
        openSettings(true);
        return false;
    }
    showAppContent();
    return true;
}

async function apiRequest(url, options) {
    const fetchOptions = options ? { ...options } : {};
    const headers = { ...(fetchOptions.headers || {}) };
    const apiKey = getUserApiKey();
    if (apiKey) {
        headers['X-API-KEY'] = apiKey;
    }
    fetchOptions.headers = headers;

    const response = await fetch(url, fetchOptions);
    if (response.status === 401) {
        openSettings(false);
        const statusEl = document.getElementById('apiKeyStatus');
        if (statusEl) {
            try {
                const body = await response.clone().json();
                statusEl.textContent = body.message || body.error || 'API key required';
            } catch (_error) {
                statusEl.textContent = 'API key required';
            }
        }
    }
    return response;
}

function fetchWithTimeout(url, options) {
    const opts = options ? { ...options } : {};
    const timeout = opts.timeout !== undefined ? opts.timeout : 30000;
    delete opts.timeout;
    const skipApiKey = Boolean(opts.skipApiKey);
    delete opts.skipApiKey;

    const request = skipApiKey ? fetch(url, opts) : apiRequest(url, opts);
    return Promise.race([
        request,
        new Promise((_, reject) =>
            setTimeout(
                () => reject(new Error('Request timeout - operation is still running on the server')),
                timeout
            )
        )
    ]);
}

function updateApiKeyStatus() {
    const statusEl = document.getElementById('apiKeyStatus');
    if (!statusEl) {
        return;
    }
    statusEl.textContent = hasUserApiKey() ? '✓ Custom API key' : 'Enter your key below…';
}

function openSettings(isGate) {
    apiKeyGateActive = Boolean(isGate);
    const overlay = document.getElementById('settingsOverlay');
    const input = document.getElementById('settingsApiKey');
    const description = document.getElementById('settingsApiKeyDescription');
    const cancelBtn = document.querySelector('.btn-close-settings');

    if (input) {
        input.value = getUserApiKey();
        input.type = 'password';
    }
    if (description) {
        description.textContent = isGate
            ? 'Enter your Bigdata API key to continue. The news terminal will be available after you save.'
            : 'Enter your Bigdata API key to authenticate requests.';
    }
    if (cancelBtn) {
        cancelBtn.style.display = isGate ? 'none' : '';
    }
    updateApiKeyStatus();
    if (overlay) {
        overlay.classList.add('visible');
    }
}

function closeSettings() {
    if (apiKeyGateActive) {
        return;
    }
    const overlay = document.getElementById('settingsOverlay');
    const cancelBtn = document.querySelector('.btn-close-settings');
    if (overlay) {
        overlay.classList.remove('visible');
    }
    if (cancelBtn) {
        cancelBtn.style.display = '';
    }
}

async function saveApiKey() {
    const input = document.getElementById('settingsApiKey');
    const key = input ? input.value.trim() : '';
    if (!key) {
        updateApiKeyStatus();
        const statusEl = document.getElementById('apiKeyStatus');
        if (statusEl) {
            statusEl.textContent = 'Enter your key below…';
        }
        return;
    }

    const wasGate = apiKeyGateActive;
    setUserApiKey(key);
    apiKeyGateActive = false;
    updateApiKeyStatus();

    const overlay = document.getElementById('settingsOverlay');
    if (overlay) {
        overlay.classList.remove('visible');
    }

    if (wasGate) {
        showAppContent();
        if (typeof onAppReadyCallback === 'function') {
            await onAppReadyCallback();
        }
    }
}

function clearApiKey() {
    const input = document.getElementById('settingsApiKey');
    if (input) {
        input.value = '';
    }
    setUserApiKey('');
    updateApiKeyStatus();
}

function toggleApiKeyVisibility() {
    const input = document.getElementById('settingsApiKey');
    const eyeBtn = document.querySelector('.eye-btn');
    if (!input) {
        return;
    }
    const showing = input.type === 'text';
    input.type = showing ? 'password' : 'text';
    if (eyeBtn) {
        eyeBtn.setAttribute('aria-label', showing ? 'Show API key' : 'Hide API key');
        eyeBtn.classList.toggle('is-visible', !showing);
    }
}

document.addEventListener('click', function (event) {
    const overlay = document.getElementById('settingsOverlay');
    if (overlay && event.target === overlay && !apiKeyGateActive) {
        closeSettings();
    }
});
