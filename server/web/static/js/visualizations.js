// LabLink Advanced Visualizations - Main Controller

// State
let currentEquipment = null;
let currentChannel = 1;
let waveformData = null;
let equipmentList = [];

// Initialize visualizations page
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

    // Load equipment list
    await loadEquipmentList();

    // Set up event listeners
    setupEventListeners();

    // Initialize all visualization modules
    if (window.Viz3DWaveform) {
        window.Viz3DWaveform.init();
    }
    if (window.VizWaterfall) {
        window.VizWaterfall.init();
    }
    if (window.VizSPC) {
        window.VizSPC.init();
    }
    if (window.VizCorrelation) {
        window.VizCorrelation.init();
    }
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

        // Update all visualizations for dark mode
        if (window.Viz3DWaveform) {
            window.Viz3DWaveform.updateTheme();
        }
        if (window.VizWaterfall) {
            window.VizWaterfall.updateTheme();
        }
        if (window.VizSPC) {
            window.VizSPC.updateTheme();
        }
        if (window.VizCorrelation) {
            window.VizCorrelation.updateTheme();
        }
    });

    // Logout
    document.getElementById('logoutButton').addEventListener('click', async () => {
        await logout();
        window.location.href = '/login.html';
    });

    // Equipment selection
    document.getElementById('vizEquipmentSelect').addEventListener('change', (e) => {
        currentEquipment = e.target.value;
    });

    // Channel selection
    document.getElementById('vizChannelSelect').addEventListener('change', (e) => {
        currentChannel = parseInt(e.target.value);
    });

    // Load data button
    const loadButton = document.getElementById('loadDataButton');
    loadButton.addEventListener('click', async () => {
        await loadWaveformData();
    });

    // Tab switching
    document.querySelectorAll('.viz-tab').forEach(tab => {
        tab.addEventListener('click', () => {
            switchTab(tab.dataset.tab);
        });
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

// Load equipment list
async function loadEquipmentList() {
    try {
        const equipment = await api.listEquipment();
        equipmentList = equipment.filter(e => e.status === 'connected');

        const select = document.getElementById('vizEquipmentSelect');
        const corrSelect = document.getElementById('corrEquipment2');

        select.innerHTML = '<option value="">Select equipment...</option>';
        corrSelect.innerHTML = '<option value="">Select second equipment...</option>';

        equipmentList.forEach(eq => {
            const option = document.createElement('option');
            option.value = eq.id;
            option.textContent = `${eq.name} (${eq.equipment_type})`;

            select.appendChild(option.cloneNode(true));
            corrSelect.appendChild(option.cloneNode(true));
        });

        if (equipmentList.length === 0) {
            showAlert('No connected equipment found. Please connect equipment first.', 'warning', 'alert');
        }
    } catch (error) {
        console.error('Failed to load equipment:', error);
        showAlert('Failed to load equipment: ' + error.message, 'error', 'alert');
    }
}

// Load waveform data
async function loadWaveformData() {
    if (!currentEquipment) {
        showAlert('Please select equipment first', 'warning', 'alert');
        return;
    }

    const loadButton = document.getElementById('loadDataButton');
    setButtonLoading(loadButton, true);

    try {
        // First, check if equipment is an oscilloscope
        const equipment = equipmentList.find(e => e.id === currentEquipment);
        if (!equipment || equipment.equipment_type !== 'oscilloscope') {
            showAlert('Please select an oscilloscope for waveform visualization', 'warning', 'alert');
            return;
        }

        // Capture waveform from oscilloscope
        const response = await api.captureWaveform(currentEquipment, currentChannel);

        if (response && response.voltage_data && response.time_data) {
            waveformData = {
                voltage: response.voltage_data,
                time: response.time_data,
                sampleRate: response.sample_rate || (1.0 / (response.time_data[1] - response.time_data[0])),
                channel: currentChannel,
                equipmentId: currentEquipment
            };

            showAlert('Waveform data loaded successfully', 'success', 'alert');

            // Update all visualizations with new data
            updateAllVisualizations();
        } else {
            showAlert('No waveform data received', 'error', 'alert');
        }
    } catch (error) {
        console.error('Failed to load waveform data:', error);
        showAlert('Failed to load waveform data: ' + error.message, 'error', 'alert');
    } finally {
        setButtonLoading(loadButton, false);
    }
}

// Update all visualizations with current data
function updateAllVisualizations() {
    if (!waveformData) {
        return;
    }

    const activeTab = document.querySelector('.viz-tab.active').dataset.tab;

    switch (activeTab) {
        case '3d-waveform':
            if (window.Viz3DWaveform) {
                window.Viz3DWaveform.updateData(waveformData);
            }
            break;
        case 'fft-waterfall':
            if (window.VizWaterfall) {
                window.VizWaterfall.updateData(waveformData);
            }
            break;
        case 'spc-charts':
            if (window.VizSPC) {
                window.VizSPC.updateData(waveformData);
            }
            break;
        case 'correlation':
            // Correlation needs two datasets - handle separately
            break;
    }
}

// Switch between tabs
function switchTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.viz-tab').forEach(tab => {
        if (tab.dataset.tab === tabName) {
            tab.classList.add('active');
        } else {
            tab.classList.remove('active');
        }
    });

    // Update tab content
    document.querySelectorAll('.viz-tab-content').forEach(content => {
        if (content.id === 'tab-' + tabName) {
            content.classList.add('active');
        } else {
            content.classList.remove('active');
        }
    });

    // Update visualization if we have data
    if (waveformData) {
        updateAllVisualizations();
    }
}

// Get current waveform data (for use by visualization modules)
function getCurrentWaveformData() {
    return waveformData;
}

// Get equipment list (for use by visualization modules)
function getEquipmentList() {
    return equipmentList;
}

// Export functions
window.getCurrentWaveformData = getCurrentWaveformData;
window.getEquipmentList = getEquipmentList;
