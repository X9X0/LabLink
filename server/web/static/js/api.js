// LabLink Web Dashboard - API Client

const API_BASE_URL = window.location.origin;

class LabLinkAPI {
    constructor(baseURL = API_BASE_URL) {
        this.baseURL = baseURL;
        this.accessToken = null;
        this.refreshToken = null;
        this.refreshPromise = null;
    }

    /**
     * Set authentication tokens
     * @param {string} accessToken - JWT access token
     * @param {string} refreshToken - JWT refresh token
     */
    setTokens(accessToken, refreshToken) {
        this.accessToken = accessToken;
        this.refreshToken = refreshToken;
    }

    /**
     * Clear authentication tokens
     */
    clearTokens() {
        this.accessToken = null;
        this.refreshToken = null;
    }

    /**
     * Get authorization headers
     * @returns {Object} Headers object
     */
    getHeaders() {
        const headers = {
            'Content-Type': 'application/json',
        };

        if (this.accessToken) {
            headers['Authorization'] = `Bearer ${this.accessToken}`;
        }

        return headers;
    }

    /**
     * Make API request with automatic token refresh
     * @param {string} endpoint - API endpoint
     * @param {Object} options - Fetch options
     * @returns {Promise<any>} Response data
     */
    async request(endpoint, options = {}) {
        const url = `${this.baseURL}${endpoint}`;
        const config = {
            ...options,
            headers: {
                ...this.getHeaders(),
                ...options.headers,
            },
        };

        try {
            let response = await fetch(url, config);

            // If 401 and we have a refresh token, try to refresh
            if (response.status === 401 && this.refreshToken && !endpoint.includes('/refresh')) {
                await this.refreshAccessToken();
                // Retry with new token
                config.headers = {
                    ...this.getHeaders(),
                    ...options.headers,
                };
                response = await fetch(url, config);
            }

            if (!response.ok) {
                const error = await response.json().catch(() => ({ detail: 'Request failed' }));
                throw new Error(error.detail || `HTTP ${response.status}`);
            }

            return await response.json();
        } catch (error) {
            console.error(`API Error [${endpoint}]:`, error);
            throw error;
        }
    }

    /**
     * Refresh access token
     * @returns {Promise<void>}
     */
    async refreshAccessToken() {
        // Prevent multiple simultaneous refresh attempts
        if (this.refreshPromise) {
            return this.refreshPromise;
        }

        this.refreshPromise = (async () => {
            try {
                const response = await fetch(`${this.baseURL}/api/security/refresh`, {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: this.refreshToken }),
                });

                if (!response.ok) {
                    throw new Error('Token refresh failed');
                }

                const data = await response.json();
                this.setTokens(data.access_token, data.refresh_token);

                // Update localStorage
                localStorage.setItem('access_token', data.access_token);
                localStorage.setItem('refresh_token', data.refresh_token);
            } catch (error) {
                // Refresh failed, clear tokens and redirect to login
                this.clearTokens();
                localStorage.removeItem('access_token');
                localStorage.removeItem('refresh_token');
                localStorage.removeItem('user');
                window.location.href = '/login.html';
                throw error;
            } finally {
                this.refreshPromise = null;
            }
        })();

        return this.refreshPromise;
    }

    // ==================== Authentication Endpoints ====================

    async login(username, password, mfaToken = null) {
        const body = { username, password };
        if (mfaToken) {
            body.mfa_token = mfaToken;
        }

        const data = await this.request('/api/security/login', {
            method: 'POST',
            body: JSON.stringify(body),
        });

        this.setTokens(data.access_token, data.refresh_token);
        return data;
    }

    async logout() {
        try {
            await this.request('/api/security/logout', { method: 'POST' });
        } finally {
            this.clearTokens();
        }
    }

    async getCurrentUser() {
        return await this.request('/api/security/me');
    }

    // ==================== Equipment Endpoints ====================

    async listEquipment() {
        return await this.request('/api/equipment/list');
    }

    async getEquipment(equipmentId) {
        return await this.request(`/api/equipment/${equipmentId}`);
    }

    async connectEquipment(equipmentId) {
        return await this.request(`/api/equipment/${equipmentId}/connect`, {
            method: 'POST',
        });
    }

    async disconnectEquipment(equipmentId) {
        return await this.request(`/api/equipment/${equipmentId}/disconnect`, {
            method: 'POST',
        });
    }

    async getEquipmentInfo(equipmentId) {
        return await this.request(`/api/equipment/${equipmentId}/info`);
    }

    async sendCommand(equipmentId, command) {
        return await this.request(`/api/equipment/${equipmentId}/command`, {
            method: 'POST',
            body: JSON.stringify({ command }),
        });
    }

    async queryCommand(equipmentId, command) {
        return await this.request(`/api/equipment/${equipmentId}/query`, {
            method: 'POST',
            body: JSON.stringify({ command }),
        });
    }

    // ==================== Waveform Endpoints ====================

    async captureWaveform(equipmentId, channel, config = {}) {
        const defaultConfig = {
            channel: channel,
            num_averages: 1,
            high_resolution: false,
            interpolation: false,
            single_shot: false,
            apply_smoothing: false,
            ...config
        };

        return await this.request('/api/waveform/capture', {
            method: 'POST',
            body: JSON.stringify({
                equipment_id: equipmentId,
                config: defaultConfig
            }),
        });
    }

    async getCachedWaveform(equipmentId, channel) {
        return await this.request(`/api/waveform/cached/${equipmentId}/${channel}`);
    }

    async getWaveformMeasurements(equipmentId, channel, useCached = true) {
        return await this.request(`/api/waveform/measurements/${equipmentId}/${channel}`);
    }

    // ==================== Profile Endpoints ====================

    async listProfiles() {
        return await this.request('/api/profiles');
    }

    async getProfile(profileName) {
        return await this.request(`/api/profiles/${profileName}`);
    }

    async saveProfile(equipmentId, profileName, description = '') {
        return await this.request(`/api/equipment/${equipmentId}/profiles/save`, {
            method: 'POST',
            body: JSON.stringify({ profile_name: profileName, description }),
        });
    }

    async loadProfile(equipmentId, profileName) {
        return await this.request(`/api/equipment/${equipmentId}/profiles/load`, {
            method: 'POST',
            body: JSON.stringify({ profile_name: profileName }),
        });
    }

    // ==================== Diagnostics Endpoints ====================

    async getSystemHealth() {
        return await this.request('/api/diagnostics/system');
    }

    async getEquipmentHealth(equipmentId) {
        return await this.request(`/api/diagnostics/equipment/${equipmentId}`);
    }

    // ==================== Alarm Endpoints ====================

    async listAlarms() {
        return await this.request('/api/alarms');
    }

    async acknowledgeAlarm(alarmId) {
        return await this.request(`/api/alarms/${alarmId}/acknowledge`, {
            method: 'POST',
        });
    }

    // ==================== Discovery Endpoints ====================

    async scanDevices() {
        return await this.request('/api/discovery/scan', { method: 'POST' });
    }

    async getDiscoveredDevices() {
        return await this.request('/api/discovery/devices');
    }

    async getRecommendations() {
        return await this.request('/api/discovery/recommendations');
    }

    // ==================== Profile Endpoints ====================

    async listProfiles() {
        return await this.request('/api/profiles/list');
    }

    async getProfile(profileName) {
        return await this.request(`/api/profiles/${encodeURIComponent(profileName)}`);
    }

    async createProfile(profileData) {
        return await this.request('/api/profiles/create', {
            method: 'POST',
            body: JSON.stringify(profileData),
        });
    }

    async updateProfile(profileName, profileData) {
        return await this.request(`/api/profiles/${encodeURIComponent(profileName)}`, {
            method: 'PUT',
            body: JSON.stringify(profileData),
        });
    }

    async deleteProfile(profileName) {
        return await this.request(`/api/profiles/${encodeURIComponent(profileName)}`, {
            method: 'DELETE',
        });
    }

    async applyProfile(profileName, equipmentId) {
        return await this.request(`/api/profiles/${encodeURIComponent(profileName)}/apply/${equipmentId}`, {
            method: 'POST',
        });
    }

    // ==================== User Settings Endpoints ====================

    async updateUser(userId, userData) {
        return await this.request(`/api/security/users/${userId}`, {
            method: 'PUT',
            body: JSON.stringify(userData),
        });
    }

    async changePassword(userId, passwordData) {
        return await this.request(`/api/security/users/${userId}/password`, {
            method: 'POST',
            body: JSON.stringify(passwordData),
        });
    }

    // ==================== MFA Endpoints ====================

    async setupMFA() {
        return await this.request('/api/security/mfa/setup', {
            method: 'POST',
        });
    }

    async verifyMFA(token) {
        return await this.request('/api/security/mfa/verify', {
            method: 'POST',
            body: JSON.stringify({ token }),
        });
    }

    async disableMFA(password, mfaToken = null) {
        return await this.request('/api/security/mfa/disable', {
            method: 'POST',
            body: JSON.stringify({ password, mfa_token: mfaToken }),
        });
    }

    async getMFAStatus() {
        return await this.request('/api/security/mfa/status');
    }

    async regenerateBackupCodes() {
        return await this.request('/api/security/mfa/backup-codes/regenerate', {
            method: 'POST',
        });
    }
}

// Create global API instance
const api = new LabLinkAPI();
