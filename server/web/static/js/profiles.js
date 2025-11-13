// LabLink Web Dashboard - Equipment Profiles Management

// State
let profiles = [];
let equipmentList = [];
let editingProfile = null;
let deletingProfile = null;
let applyingProfile = null;

// Initialize profiles page
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

    // Load profiles and equipment
    await Promise.all([
        loadProfiles(),
        loadEquipment()
    ]);

    // Set up event listeners
    setupEventListeners();
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

    // Create profile button
    document.getElementById('createProfileButton').addEventListener('click', () => {
        openProfileModal();
    });

    // Profile modal controls
    document.getElementById('closeModal').addEventListener('click', closeProfileModal);
    document.getElementById('cancelButton').addEventListener('click', closeProfileModal);
    document.getElementById('saveProfileButton').addEventListener('click', saveProfile);

    // Delete modal controls
    document.getElementById('closeDeleteModal').addEventListener('click', closeDeleteModal);
    document.getElementById('cancelDeleteButton').addEventListener('click', closeDeleteModal);
    document.getElementById('confirmDeleteButton').addEventListener('click', confirmDelete);

    // Apply modal controls
    document.getElementById('closeApplyModal').addEventListener('click', closeApplyModal);
    document.getElementById('cancelApplyButton').addEventListener('click', closeApplyModal);
    document.getElementById('confirmApplyButton').addEventListener('click', confirmApply);

    // Close modals on background click
    document.getElementById('profileModal').addEventListener('click', (e) => {
        if (e.target.id === 'profileModal') {
            closeProfileModal();
        }
    });

    document.getElementById('deleteModal').addEventListener('click', (e) => {
        if (e.target.id === 'deleteModal') {
            closeDeleteModal();
        }
    });

    document.getElementById('applyModal').addEventListener('click', (e) => {
        if (e.target.id === 'applyModal') {
            closeApplyModal();
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

// Load profiles
async function loadProfiles() {
    try {
        const response = await api.listProfiles();
        profiles = response.profiles || [];
        renderProfiles();
    } catch (error) {
        console.error('Failed to load profiles:', error);
        showAlert('Failed to load profiles: ' + error.message, 'error', 'alert');
    }
}

// Load equipment list for apply modal
async function loadEquipment() {
    try {
        equipmentList = await api.listEquipment();
    } catch (error) {
        console.error('Failed to load equipment:', error);
    }
}

// Render profiles
function renderProfiles() {
    const container = document.getElementById('profilesList');
    const emptyState = document.getElementById('emptyState');

    if (profiles.length === 0) {
        container.innerHTML = '';
        emptyState.style.display = 'block';
        return;
    }

    emptyState.style.display = 'none';

    container.innerHTML = profiles.map(profile => `
        <div class="profile-card">
            <div class="profile-header">
                <div>
                    <h3 class="profile-name">${escapeHtml(profile.name)}</h3>
                    <p class="profile-type">${escapeHtml(profile.equipment_type)}</p>
                </div>
                ${profile.is_default ? '<span class="badge badge-success">Default</span>' : ''}
            </div>

            ${profile.description ? `
                <p class="profile-description">${escapeHtml(profile.description)}</p>
            ` : ''}

            <div class="profile-config">
                <strong>Configuration:</strong>
                <pre class="config-preview">${formatJSON(profile.config)}</pre>
            </div>

            <div class="profile-actions">
                <button class="btn btn-primary btn-sm" onclick="openApplyModal('${escapeHtml(profile.name)}')">
                    Apply
                </button>
                <button class="btn btn-secondary btn-sm" onclick="editProfile('${escapeHtml(profile.name)}')">
                    Edit
                </button>
                <button class="btn btn-error btn-sm" onclick="openDeleteModal('${escapeHtml(profile.name)}')">
                    Delete
                </button>
            </div>
        </div>
    `).join('');
}

// Format JSON for display
function formatJSON(obj) {
    try {
        return JSON.stringify(obj, null, 2);
    } catch (e) {
        return String(obj);
    }
}

// Open profile modal for create/edit
function openProfileModal(profile = null) {
    editingProfile = profile;

    const modal = document.getElementById('profileModal');
    const title = document.getElementById('modalTitle');

    if (profile) {
        // Edit mode
        title.textContent = 'Edit Profile';
        document.getElementById('profileName').value = profile.name;
        document.getElementById('profileName').disabled = true; // Can't change name
        document.getElementById('profileDescription').value = profile.description || '';
        document.getElementById('equipmentType').value = profile.equipment_type;
        document.getElementById('profileConfig').value = formatJSON(profile.config);
        document.getElementById('isDefault').checked = profile.is_default || false;
    } else {
        // Create mode
        title.textContent = 'Create Profile';
        document.getElementById('profileForm').reset();
        document.getElementById('profileName').disabled = false;
    }

    hideAlert('modalAlert');
    modal.style.display = 'flex';
}

// Close profile modal
function closeProfileModal() {
    document.getElementById('profileModal').style.display = 'none';
    editingProfile = null;
}

// Save profile (create or update)
async function saveProfile() {
    const name = document.getElementById('profileName').value.trim();
    const description = document.getElementById('profileDescription').value.trim();
    const equipmentType = document.getElementById('equipmentType').value.trim();
    const configText = document.getElementById('profileConfig').value.trim();
    const isDefault = document.getElementById('isDefault').checked;

    // Validate
    if (!name || !equipmentType || !configText) {
        showAlert('Please fill in all required fields', 'error', 'modalAlert');
        return;
    }

    // Parse config JSON
    let config;
    try {
        config = JSON.parse(configText);
    } catch (e) {
        showAlert('Invalid JSON in configuration: ' + e.message, 'error', 'modalAlert');
        return;
    }

    const saveButton = document.getElementById('saveProfileButton');
    setButtonLoading(saveButton, true);
    hideAlert('modalAlert');

    try {
        if (editingProfile) {
            // Update existing profile
            await api.updateProfile(name, {
                description,
                equipment_type: equipmentType,
                config,
                is_default: isDefault
            });

            showAlert('Profile updated successfully', 'success', 'alert');
        } else {
            // Create new profile
            await api.createProfile({
                name,
                description,
                equipment_type: equipmentType,
                config,
                is_default: isDefault
            });

            showAlert('Profile created successfully', 'success', 'alert');
        }

        // Reload profiles
        await loadProfiles();

        // Close modal
        closeProfileModal();

    } catch (error) {
        console.error('Failed to save profile:', error);
        showAlert('Failed to save profile: ' + error.message, 'error', 'modalAlert');
    } finally {
        setButtonLoading(saveButton, false);
    }
}

// Edit profile
function editProfile(profileName) {
    const profile = profiles.find(p => p.name === profileName);
    if (profile) {
        openProfileModal(profile);
    }
}

// Open delete confirmation modal
function openDeleteModal(profileName) {
    deletingProfile = profileName;
    document.getElementById('deleteProfileName').textContent = profileName;
    document.getElementById('deleteModal').style.display = 'flex';
}

// Close delete modal
function closeDeleteModal() {
    document.getElementById('deleteModal').style.display = 'none';
    deletingProfile = null;
}

// Confirm delete
async function confirmDelete() {
    if (!deletingProfile) return;

    const deleteButton = document.getElementById('confirmDeleteButton');
    setButtonLoading(deleteButton, true);

    try {
        await api.deleteProfile(deletingProfile);

        showAlert(`Profile "${deletingProfile}" deleted successfully`, 'success', 'alert');

        // Reload profiles
        await loadProfiles();

        // Close modal
        closeDeleteModal();

    } catch (error) {
        console.error('Failed to delete profile:', error);
        showAlert('Failed to delete profile: ' + error.message, 'error', 'alert');
    } finally {
        setButtonLoading(deleteButton, false);
    }
}

// Open apply modal
function openApplyModal(profileName) {
    applyingProfile = profileName;
    document.getElementById('applyProfileName').textContent = profileName;

    // Populate equipment dropdown
    const select = document.getElementById('applyEquipmentSelect');
    select.innerHTML = '<option value="">Select equipment...</option>';

    // Get profile to filter equipment by type
    const profile = profiles.find(p => p.name === profileName);

    equipmentList.forEach(eq => {
        // Only show equipment that matches profile type or show all if no type filter
        if (!profile || !profile.equipment_type || eq.equipment_type === profile.equipment_type) {
            const option = document.createElement('option');
            option.value = eq.id;
            option.textContent = `${eq.name} (${eq.equipment_type})`;
            select.appendChild(option);
        }
    });

    hideAlert('applyModalAlert');
    document.getElementById('applyModal').style.display = 'flex';
}

// Close apply modal
function closeApplyModal() {
    document.getElementById('applyModal').style.display = 'none';
    applyingProfile = null;
}

// Confirm apply
async function confirmApply() {
    const equipmentId = document.getElementById('applyEquipmentSelect').value;

    if (!equipmentId) {
        showAlert('Please select equipment', 'error', 'applyModalAlert');
        return;
    }

    if (!applyingProfile) return;

    const applyButton = document.getElementById('confirmApplyButton');
    setButtonLoading(applyButton, true);
    hideAlert('applyModalAlert');

    try {
        await api.applyProfile(applyingProfile, equipmentId);

        showAlert(`Profile applied successfully to equipment`, 'success', 'alert');

        // Close modal
        closeApplyModal();

    } catch (error) {
        console.error('Failed to apply profile:', error);
        showAlert('Failed to apply profile: ' + error.message, 'error', 'applyModalAlert');
    } finally {
        setButtonLoading(applyButton, false);
    }
}

// Helper function to escape HTML
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Make functions globally accessible
window.editProfile = editProfile;
window.openDeleteModal = openDeleteModal;
window.openApplyModal = openApplyModal;
