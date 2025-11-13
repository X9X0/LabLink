// LabLink Web Dashboard - Authentication Module

/**
 * Check if user is authenticated
 * @returns {boolean} Authentication status
 */
function isAuthenticated() {
    const token = localStorage.getItem('access_token');
    return !!token;
}

/**
 * Initialize authentication from localStorage
 */
function initAuth() {
    const accessToken = localStorage.getItem('access_token');
    const refreshToken = localStorage.getItem('refresh_token');

    if (accessToken && refreshToken) {
        api.setTokens(accessToken, refreshToken);
    }
}

/**
 * Login user
 * @param {string} username - Username
 * @param {string} password - Password
 * @param {boolean} rememberMe - Remember login
 * @returns {Promise<Object>} Login response
 */
async function login(username, password, rememberMe = false) {
    try {
        const response = await api.login(username, password);

        // Store tokens
        localStorage.setItem('access_token', response.access_token);
        localStorage.setItem('refresh_token', response.refresh_token);
        localStorage.setItem('user', JSON.stringify(response.user));

        if (rememberMe) {
            localStorage.setItem('remember_me', 'true');
        }

        return response;
    } catch (error) {
        console.error('Login failed:', error);
        throw error;
    }
}

/**
 * Logout user
 */
async function logout() {
    try {
        await api.logout();
    } catch (error) {
        console.error('Logout failed:', error);
    } finally {
        // Clear all auth data
        localStorage.removeItem('access_token');
        localStorage.removeItem('refresh_token');
        localStorage.removeItem('user');
        localStorage.removeItem('remember_me');
        api.clearTokens();

        // Redirect to login
        window.location.href = '/login.html';
    }
}

/**
 * Get current user
 * @returns {Object|null} User object
 */
function getUser() {
    try {
        const userStr = localStorage.getItem('user');
        return userStr ? JSON.parse(userStr) : null;
    } catch (error) {
        console.error('Failed to get user:', error);
        return null;
    }
}

/**
 * Refresh user data from API
 * @returns {Promise<Object>} User object
 */
async function refreshUserData() {
    try {
        const user = await api.getCurrentUser();
        localStorage.setItem('user', JSON.stringify(user));
        return user;
    } catch (error) {
        console.error('Failed to refresh user data:', error);
        throw error;
    }
}

/**
 * Check if user has specific role
 * @param {string} roleName - Role name (admin, operator, viewer)
 * @returns {boolean} Has role
 */
function hasRole(roleName) {
    const user = getUser();
    if (!user) return false;

    // Superuser has all roles
    if (user.is_superuser) return true;

    // Map role names to access levels
    const roleMap = {
        'admin': ['admin'],
        'operator': ['admin', 'operator'],
        'viewer': ['admin', 'operator', 'viewer']
    };

    const allowedRoles = roleMap[roleName] || [];
    return user.roles?.some(role => allowedRoles.includes(role));
}

/**
 * Require authentication - redirect to login if not authenticated
 */
function requireAuth() {
    if (!isAuthenticated()) {
        // Save current page for redirect after login
        const returnUrl = window.location.pathname + window.location.search;
        if (returnUrl !== '/login.html') {
            localStorage.setItem('return_url', returnUrl);
        }
        window.location.href = '/login.html';
    }
}

/**
 * Handle return URL after login
 */
function handleReturnUrl() {
    const returnUrl = localStorage.getItem('return_url');
    if (returnUrl) {
        localStorage.removeItem('return_url');
        window.location.href = returnUrl;
    } else {
        window.location.href = '/dashboard.html';
    }
}

/**
 * Setup logout button
 * @param {string} buttonId - ID of logout button
 */
function setupLogoutButton(buttonId = 'logoutButton') {
    const button = document.getElementById(buttonId);
    if (button) {
        button.addEventListener('click', async (e) => {
            e.preventDefault();
            if (confirm('Are you sure you want to logout?')) {
                await logout();
            }
        });
    }
}

/**
 * Display user info in UI
 * @param {string} elementId - ID of element to display user info
 */
function displayUserInfo(elementId = 'userInfo') {
    const element = document.getElementById(elementId);
    if (!element) return;

    const user = getUser();
    if (user) {
        element.innerHTML = `
            <div class="user-info">
                <span class="user-name">${escapeHtml(user.full_name || user.username)}</span>
                <span class="user-role text-sm text-muted">${user.is_superuser ? 'Admin' : 'User'}</span>
            </div>
        `;
    }
}

// Initialize auth on page load
document.addEventListener('DOMContentLoaded', () => {
    initAuth();
});
