// LabLink Web Dashboard - User Settings

// Initialize settings page
document.addEventListener('DOMContentLoaded', () => {
    // Require authentication
    if (!requireAuth()) {
        return;
    }

    // Initialize dark mode
    initDarkMode();
    updateDarkModeButton();

    // Load user info and settings
    loadUserSettings();

    // Set up event listeners
    setupEventListeners();
});

// Load user settings
function loadUserSettings() {
    const user = getUser();
    if (user) {
        // Populate form fields
        document.getElementById('userName').textContent = user.username;
        document.getElementById('username').value = user.username || '';
        document.getElementById('email').value = user.email || '';
        document.getElementById('fullName').value = user.full_name || '';

        // Set dark mode preference
        const theme = document.documentElement.getAttribute('data-theme');
        document.getElementById('darkModePreference').checked = theme === 'dark';
    }
}

// Set up event listeners
function setupEventListeners() {
    // Dark mode toggle (navbar)
    document.getElementById('darkModeToggle').addEventListener('click', () => {
        toggleDarkMode();
        updateDarkModeButton();

        // Update preference checkbox
        const theme = document.documentElement.getAttribute('data-theme');
        document.getElementById('darkModePreference').checked = theme === 'dark';
    });

    // Dark mode preference toggle
    document.getElementById('darkModePreference').addEventListener('change', (e) => {
        if (e.target.checked) {
            document.documentElement.setAttribute('data-theme', 'dark');
            localStorage.setItem('theme', 'dark');
        } else {
            document.documentElement.setAttribute('data-theme', 'light');
            localStorage.setItem('theme', 'light');
        }
        updateDarkModeButton();
    });

    // Logout
    document.getElementById('logoutButton').addEventListener('click', async () => {
        await logout();
        window.location.href = '/login.html';
    });

    // Profile form submission
    document.getElementById('profileForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        await saveProfile();
    });

    // Password form submission
    document.getElementById('passwordForm').addEventListener('submit', async (e) => {
        e.preventDefault();
        await changePassword();
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

// Save profile changes
async function saveProfile() {
    const email = document.getElementById('email').value.trim();
    const fullName = document.getElementById('fullName').value.trim();

    const saveButton = document.getElementById('saveProfileButton');
    setButtonLoading(saveButton, true);
    hideAlert('alert');

    try {
        const user = getUser();
        if (!user) {
            throw new Error('User not found');
        }

        // Update user profile via API
        await api.updateUser(user.user_id, {
            email: email,
            full_name: fullName
        });

        // Update stored user data
        const updatedUser = { ...user, email, full_name: fullName };
        localStorage.setItem('user', JSON.stringify(updatedUser));

        showAlert('Profile updated successfully', 'success', 'alert');
    } catch (error) {
        console.error('Failed to update profile:', error);
        showAlert('Failed to update profile: ' + error.message, 'error', 'alert');
    } finally {
        setButtonLoading(saveButton, false);
    }
}

// Change password
async function changePassword() {
    const currentPassword = document.getElementById('currentPassword').value;
    const newPassword = document.getElementById('newPassword').value;
    const confirmPassword = document.getElementById('confirmPassword').value;

    // Validate
    if (newPassword.length < 8) {
        showAlert('New password must be at least 8 characters', 'error', 'alert');
        return;
    }

    if (newPassword !== confirmPassword) {
        showAlert('New passwords do not match', 'error', 'alert');
        return;
    }

    const changeButton = document.getElementById('changePasswordButton');
    setButtonLoading(changeButton, true);
    hideAlert('alert');

    try {
        const user = getUser();
        if (!user) {
            throw new Error('User not found');
        }

        // Change password via API
        await api.changePassword(user.user_id, {
            current_password: currentPassword,
            new_password: newPassword
        });

        showAlert('Password changed successfully', 'success', 'alert');

        // Clear password fields
        document.getElementById('passwordForm').reset();
    } catch (error) {
        console.error('Failed to change password:', error);
        showAlert('Failed to change password: ' + error.message, 'error', 'alert');
    } finally {
        setButtonLoading(changeButton, false);
    }
}
