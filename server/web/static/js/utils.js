// LabLink Web Dashboard - Utility Functions

/**
 * Show an alert message
 * @param {string} message - Message to display
 * @param {string} type - Alert type (success, error, warning, info)
 * @param {string} elementId - ID of the alert element
 */
function showAlert(message, type = 'info', elementId = 'alert') {
    const alertEl = document.getElementById(elementId);
    if (!alertEl) return;

    alertEl.className = `alert alert-${type}`;
    alertEl.textContent = message;
    alertEl.style.display = 'block';

    // Auto-hide after 5 seconds for success/info messages
    if (type === 'success' || type === 'info') {
        setTimeout(() => {
            alertEl.style.display = 'none';
        }, 5000);
    }
}

/**
 * Hide an alert message
 * @param {string} elementId - ID of the alert element
 */
function hideAlert(elementId = 'alert') {
    const alertEl = document.getElementById(elementId);
    if (alertEl) {
        alertEl.style.display = 'none';
    }
}

/**
 * Format date/time
 * @param {string|Date} date - Date to format
 * @returns {string} Formatted date string
 */
function formatDateTime(date) {
    if (!date) return 'N/A';
    const d = typeof date === 'string' ? new Date(date) : date;
    return d.toLocaleString();
}

/**
 * Format relative time (e.g., "2 minutes ago")
 * @param {string|Date} date - Date to format
 * @returns {string} Relative time string
 */
function formatRelativeTime(date) {
    if (!date) return 'N/A';
    const d = typeof date === 'string' ? new Date(date) : date;
    const now = new Date();
    const seconds = Math.floor((now - d) / 1000);

    if (seconds < 60) return 'just now';
    if (seconds < 3600) return `${Math.floor(seconds / 60)} minutes ago`;
    if (seconds < 86400) return `${Math.floor(seconds / 3600)} hours ago`;
    return `${Math.floor(seconds / 86400)} days ago`;
}

/**
 * Debounce function
 * @param {Function} func - Function to debounce
 * @param {number} wait - Milliseconds to wait
 * @returns {Function} Debounced function
 */
function debounce(func, wait = 300) {
    let timeout;
    return function executedFunction(...args) {
        const later = () => {
            clearTimeout(timeout);
            func(...args);
        };
        clearTimeout(timeout);
        timeout = setTimeout(later, wait);
    };
}

/**
 * Copy text to clipboard
 * @param {string} text - Text to copy
 * @returns {Promise<boolean>} Success status
 */
async function copyToClipboard(text) {
    try {
        await navigator.clipboard.writeText(text);
        return true;
    } catch (err) {
        console.error('Failed to copy:', err);
        return false;
    }
}

/**
 * Get query parameter from URL
 * @param {string} param - Parameter name
 * @returns {string|null} Parameter value
 */
function getQueryParam(param) {
    const urlParams = new URLSearchParams(window.location.search);
    return urlParams.get(param);
}

/**
 * Set page title
 * @param {string} title - Page title
 */
function setPageTitle(title) {
    document.title = title ? `${title} - LabLink` : 'LabLink';
}

/**
 * Create status badge element
 * @param {string} status - Status (online, offline, error, warning)
 * @param {string} label - Label text
 * @returns {HTMLElement} Badge element
 */
function createStatusBadge(status, label) {
    const badge = document.createElement('span');
    badge.className = `status-badge ${status}`;
    badge.innerHTML = `
        <span class="status-dot"></span>
        <span>${label || status}</span>
    `;
    return badge;
}

/**
 * Toggle dark mode
 */
function toggleDarkMode() {
    const html = document.documentElement;
    const currentTheme = html.getAttribute('data-theme');
    const newTheme = currentTheme === 'dark' ? 'light' : 'dark';

    html.setAttribute('data-theme', newTheme);
    localStorage.setItem('theme', newTheme);

    return newTheme;
}

/**
 * Initialize dark mode from localStorage
 */
function initDarkMode() {
    const savedTheme = localStorage.getItem('theme');
    const prefersDark = window.matchMedia('(prefers-color-scheme: dark)').matches;
    const theme = savedTheme || (prefersDark ? 'dark' : 'light');

    document.documentElement.setAttribute('data-theme', theme);
}

// Initialize dark mode on load
document.addEventListener('DOMContentLoaded', initDarkMode);

/**
 * Show/hide loading spinner on button
 * @param {HTMLButtonElement} button - Button element
 * @param {boolean} loading - Loading state
 */
function setButtonLoading(button, loading) {
    if (!button) return;

    button.disabled = loading;
    const textEl = button.querySelector('.btn-text');
    const spinnerEl = button.querySelector('.btn-spinner');

    if (textEl && spinnerEl) {
        textEl.style.display = loading ? 'none' : 'inline';
        spinnerEl.style.display = loading ? 'inline-flex' : 'none';
    }
}

/**
 * Format bytes to human readable string
 * @param {number} bytes - Bytes
 * @returns {string} Formatted string
 */
function formatBytes(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB', 'TB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return `${(bytes / Math.pow(k, i)).toFixed(2)} ${sizes[i]}`;
}

/**
 * Escape HTML to prevent XSS
 * @param {string} text - Text to escape
 * @returns {string} Escaped text
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

/**
 * Check if user has permission for role-based UI
 * @param {string} requiredRole - Required role (admin, operator, viewer)
 * @returns {boolean} Has permission
 */
function hasRole(requiredRole) {
    const user = getCurrentUser();
    if (!user) return false;

    // Superuser has all permissions
    if (user.is_superuser) return true;

    // Check if user has the required role
    const roleMap = {
        'admin': ['admin'],
        'operator': ['admin', 'operator'],
        'viewer': ['admin', 'operator', 'viewer']
    };

    const allowedRoles = roleMap[requiredRole] || [];
    return user.roles?.some(roleId => allowedRoles.includes(roleId));
}

/**
 * Get current user from localStorage
 * @returns {Object|null} User object
 */
function getCurrentUser() {
    try {
        const userStr = localStorage.getItem('user');
        return userStr ? JSON.parse(userStr) : null;
    } catch (err) {
        console.error('Failed to get current user:', err);
        return null;
    }
}
