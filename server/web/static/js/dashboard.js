// LabLink Web Dashboard - Dashboard Page

// State
let equipmentData = [];
let discoveryInProgress = false;
let currentEquipmentId = null;
let refreshInterval = null;

// Initialize dashboard
document.addEventListener('DOMContentLoaded', async () => {
    // Require authentication
    if (!requireAuth()) {
        return;
    }

    // Initialize dark mode
    initDarkMode();
    updateDarkModeButton();

    // Load user info
    loadUserInfo();

    // Load initial data
    await loadEquipment();

    // Set up event listeners
    setupEventListeners();

    // Start auto-refresh (every 5 seconds)
    startAutoRefresh();
});

// Load user information
function loadUserInfo() {
    const user = getUser();
    if (user) {
        document.getElementById('userName').textContent = user.username;
    }
}

// Set up event listeners
function setupEventListeners() {
    // Dark mode toggle
    document.getElementById('darkModeToggle').addEventListener('click', () => {
        toggleDarkMode();
        updateDarkModeButton();
    });

    // Logout
    document.getElementById('logoutButton').addEventListener('click', async () => {
        await logout();
        window.location.href = '/login.html';
    });

    // Refresh button
    const refreshButton = document.getElementById('refreshButton');
    refreshButton.addEventListener('click', async () => {
        setButtonLoading(refreshButton, true);
        await loadEquipment();
        setButtonLoading(refreshButton, false);
    });

    // Discovery button
    const discoveryButton = document.getElementById('startDiscoveryButton');
    discoveryButton.addEventListener('click', async () => {
        setButtonLoading(discoveryButton, true);
        await startDiscovery();
        setButtonLoading(discoveryButton, false);
    });

    // Modal controls
    document.getElementById('closeModal').addEventListener('click', closeControlModal);
    document.getElementById('cancelCommand').addEventListener('click', closeControlModal);
    document.getElementById('sendCommand').addEventListener('click', sendEquipmentCommand);

    // Close modal on background click
    document.getElementById('controlModal').addEventListener('click', (e) => {
        if (e.target.id === 'controlModal') {
            closeControlModal();
        }
    });
}

// Update dark mode button icon
function updateDarkModeButton() {
    const theme = document.documentElement.getAttribute('data-theme');
    const sunIcon = document.querySelector('.icon-sun');
    const moonIcon = document.querySelector('.icon-moon');

    if (theme === 'dark') {
        sunIcon.style.display = 'none';
        moonIcon.style.display = 'inline';
    } else {
        sunIcon.style.display = 'inline';
        moonIcon.style.display = 'none';
    }
}

// Load equipment data
async function loadEquipment() {
    try {
        const equipment = await api.listEquipment();
        equipmentData = equipment;
        renderEquipment();
        updateStats();
    } catch (error) {
        console.error('Failed to load equipment:', error);
        showAlert('Failed to load equipment: ' + error.message, 'error', 'alert');
    }
}

// Render equipment cards
function renderEquipment() {
    const container = document.getElementById('equipmentList');
    const emptyState = document.getElementById('emptyState');

    if (equipmentData.length === 0) {
        container.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }

    emptyState.style.display = 'none';

    container.innerHTML = equipmentData.map(equipment => `
        <div class="equipment-card">
            <div class="equipment-header">
                <div>
                    <h3 class="equipment-name">${escapeHtml(equipment.name)}</h3>
                    <p class="equipment-type">${escapeHtml(equipment.equipment_type)}</p>
                </div>
                <span class="badge badge-${getStatusClass(equipment.status)}">${equipment.status}</span>
            </div>

            <div class="equipment-details">
                ${equipment.address ? `
                    <div class="equipment-detail">
                        <span class="equipment-detail-label">Address:</span>
                        <span class="equipment-detail-value">${escapeHtml(equipment.address)}</span>
                    </div>
                ` : ''}
                ${equipment.manufacturer ? `
                    <div class="equipment-detail">
                        <span class="equipment-detail-label">Manufacturer:</span>
                        <span class="equipment-detail-value">${escapeHtml(equipment.manufacturer)}</span>
                    </div>
                ` : ''}
                ${equipment.model ? `
                    <div class="equipment-detail">
                        <span class="equipment-detail-label">Model:</span>
                        <span class="equipment-detail-value">${escapeHtml(equipment.model)}</span>
                    </div>
                ` : ''}
            </div>

            <div class="equipment-actions">
                ${equipment.status === 'disconnected' ? `
                    <button class="btn btn-primary btn-sm" onclick="connectEquipment('${equipment.id}')">
                        Connect
                    </button>
                ` : equipment.status === 'connected' ? `
                    <button class="btn btn-secondary btn-sm" onclick="disconnectEquipment('${equipment.id}')">
                        Disconnect
                    </button>
                    <button class="btn btn-primary btn-sm" onclick="openControlModal('${equipment.id}', '${escapeHtml(equipment.name)}')">
                        Control
                    </button>
                ` : `
                    <button class="btn btn-secondary btn-sm" disabled>
                        ${equipment.status}
                    </button>
                `}
            </div>
        </div>
    `).join('');
}

// Update statistics
function updateStats() {
    const total = equipmentData.length;
    const connected = equipmentData.filter(e => e.status === 'connected').length;
    const disconnected = equipmentData.filter(e => e.status === 'disconnected').length;
    const error = equipmentData.filter(e => e.status === 'error').length;

    document.getElementById('totalEquipment').textContent = total;
    document.getElementById('connectedEquipment').textContent = connected;
    document.getElementById('disconnectedEquipment').textContent = disconnected;
    document.getElementById('errorEquipment').textContent = error;
}

// Get status class for badge
function getStatusClass(status) {
    const statusMap = {
        'connected': 'success',
        'disconnected': 'secondary',
        'error': 'error',
        'connecting': 'warning'
    };
    return statusMap[status] || 'secondary';
}

// Connect equipment
async function connectEquipment(equipmentId) {
    try {
        showAlert('Connecting equipment...', 'info', 'alert');
        await api.connectEquipment(equipmentId);
        showAlert('Equipment connected successfully', 'success', 'alert');
        await loadEquipment();
    } catch (error) {
        console.error('Failed to connect equipment:', error);
        showAlert('Failed to connect: ' + error.message, 'error', 'alert');
    }
}

// Disconnect equipment
async function disconnectEquipment(equipmentId) {
    try {
        showAlert('Disconnecting equipment...', 'info', 'alert');
        await api.disconnectEquipment(equipmentId);
        showAlert('Equipment disconnected successfully', 'success', 'alert');
        await loadEquipment();
    } catch (error) {
        console.error('Failed to disconnect equipment:', error);
        showAlert('Failed to disconnect: ' + error.message, 'error', 'alert');
    }
}

// Open control modal
function openControlModal(equipmentId, equipmentName) {
    currentEquipmentId = equipmentId;
    document.getElementById('modalTitle').textContent = `Control: ${equipmentName}`;
    document.getElementById('commandInput').value = '';
    document.getElementById('commandResponse').style.display = 'none';
    hideAlert('modalAlert');
    document.getElementById('controlModal').style.display = 'flex';
}

// Close control modal
function closeControlModal() {
    document.getElementById('controlModal').style.display = 'none';
    currentEquipmentId = null;
}

// Send equipment command
async function sendEquipmentCommand() {
    const commandInput = document.getElementById('commandInput');
    const command = commandInput.value.trim();

    if (!command) {
        showAlert('Please enter a command', 'error', 'modalAlert');
        return;
    }

    if (!currentEquipmentId) {
        showAlert('No equipment selected', 'error', 'modalAlert');
        return;
    }

    const sendButton = document.getElementById('sendCommand');
    setButtonLoading(sendButton, true);
    hideAlert('modalAlert');

    try {
        const response = await api.sendCommand(currentEquipmentId, command);

        // Show response
        document.getElementById('responseText').textContent = response.response || 'Command sent successfully';
        document.getElementById('commandResponse').style.display = 'block';

        showAlert('Command sent successfully', 'success', 'modalAlert');
    } catch (error) {
        console.error('Failed to send command:', error);
        showAlert('Failed to send command: ' + error.message, 'error', 'modalAlert');
    } finally {
        setButtonLoading(sendButton, false);
    }
}

// Start discovery
async function startDiscovery() {
    if (discoveryInProgress) {
        showAlert('Discovery already in progress', 'warning', 'alert');
        return;
    }

    discoveryInProgress = true;
    document.getElementById('discoveryStatus').style.display = 'block';
    document.getElementById('discoveredDevices').style.display = 'none';

    try {
        // Start discovery
        await api.startDiscovery();

        // Simulate progress (in real implementation, this would poll the discovery status)
        let progress = 0;
        const progressInterval = setInterval(() => {
            progress += 10;
            document.getElementById('discoveryProgress').style.width = `${progress}%`;

            if (progress >= 100) {
                clearInterval(progressInterval);
            }
        }, 500);

        // Wait a bit for discovery to complete
        setTimeout(async () => {
            try {
                const devices = await api.listDiscoveredDevices();
                displayDiscoveredDevices(devices);
                document.getElementById('discoveryStatus').style.display = 'none';
                showAlert(`Discovery complete: ${devices.length} device(s) found`, 'success', 'alert');
            } catch (error) {
                console.error('Failed to fetch discovered devices:', error);
                showAlert('Discovery completed, but failed to fetch results', 'warning', 'alert');
                document.getElementById('discoveryStatus').style.display = 'none';
            }
            discoveryInProgress = false;
        }, 5000);

    } catch (error) {
        console.error('Failed to start discovery:', error);
        showAlert('Failed to start discovery: ' + error.message, 'error', 'alert');
        document.getElementById('discoveryStatus').style.display = 'none';
        discoveryInProgress = false;
    }
}

// Display discovered devices
function displayDiscoveredDevices(devices) {
    const container = document.getElementById('discoveredDevices');

    if (devices.length === 0) {
        container.innerHTML = '<p class="text-muted">No devices discovered</p>';
        container.style.display = 'block';
        return;
    }

    container.innerHTML = devices.map(device => `
        <div class="discovered-device">
            <div class="discovered-device-info">
                <div class="discovered-device-name">${escapeHtml(device.name || 'Unknown Device')}</div>
                <div class="discovered-device-details">
                    ${device.address ? escapeHtml(device.address) : ''}
                    ${device.manufacturer ? '- ' + escapeHtml(device.manufacturer) : ''}
                </div>
            </div>
            <button class="btn btn-primary btn-sm" onclick="addDiscoveredDevice('${device.id}')">
                Add
            </button>
        </div>
    `).join('');

    container.style.display = 'block';
}

// Add discovered device to equipment
async function addDiscoveredDevice(deviceId) {
    try {
        await api.addDiscoveredDevice(deviceId);
        showAlert('Device added successfully', 'success', 'alert');
        await loadEquipment();
        document.getElementById('discoveredDevices').style.display = 'none';
    } catch (error) {
        console.error('Failed to add device:', error);
        showAlert('Failed to add device: ' + error.message, 'error', 'alert');
    }
}

// Auto-refresh equipment status
function startAutoRefresh() {
    // Refresh every 5 seconds
    refreshInterval = setInterval(async () => {
        try {
            await loadEquipment();
        } catch (error) {
            console.error('Auto-refresh failed:', error);
        }
    }, 5000);
}

// Stop auto-refresh
function stopAutoRefresh() {
    if (refreshInterval) {
        clearInterval(refreshInterval);
        refreshInterval = null;
    }
}

// Clean up on page unload
window.addEventListener('beforeunload', () => {
    stopAutoRefresh();
});

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Make functions globally accessible
window.connectEquipment = connectEquipment;
window.disconnectEquipment = disconnectEquipment;
window.openControlModal = openControlModal;
window.addDiscoveredDevice = addDiscoveredDevice;
