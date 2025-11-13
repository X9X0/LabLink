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

    // Load MFA status
    loadMFAStatus();

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

    // MFA buttons
    document.getElementById('enableMFAButton').addEventListener('click', startMFASetup);
    document.getElementById('disableMFAButton').addEventListener('click', disableMFA);
    document.getElementById('regenerateCodesButton').addEventListener('click', regenerateBackupCodes);
    document.getElementById('closeMFAModal').addEventListener('click', closeMFAModal);
    document.getElementById('continueToVerify').addEventListener('click', () => {
        document.getElementById('mfaSetupStep1').style.display = 'none';
        document.getElementById('mfaSetupStep2').style.display = 'block';
    });
    document.getElementById('verifyMFAButton').addEventListener('click', verifyMFA);
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

// Load MFA status
async function loadMFAStatus() {
    try {
        const status = await api.getMFAStatus();
        if (status.mfa_enabled) {
            document.getElementById('mfaStatus').style.display = 'block';
            document.getElementById('mfaDisabled').style.display = 'none';
            document.getElementById('backupCodesCount').textContent = status.backup_codes_remaining;
        } else {
            document.getElementById('mfaStatus').style.display = 'none';
            document.getElementById('mfaDisabled').style.display = 'block';
        }
    } catch (error) {
        console.error('Failed to load MFA status:', error);
    }
}

// Start MFA setup
async function startMFASetup() {
    try {
        const data = await api.setupMFA();

        // Show modal
        document.getElementById('mfaSetupModal').style.display = 'flex';
        document.getElementById('mfaSetupStep1').style.display = 'block';
        document.getElementById('mfaSetupStep2').style.display = 'none';

        // Display QR code and secret
        document.getElementById('mfaQRCode').src = data.qr_code;
        document.getElementById('mfaSecret').textContent = data.secret;

        // Display backup codes
        const codesText = data.backup_codes.map((code, i) => `${i + 1}. ${code}`).join('\n');
        document.getElementById('backupCodes').textContent = codesText;

    } catch (error) {
        console.error('Failed to setup MFA:', error);
        showAlert('Failed to setup MFA: ' + error.message, 'error', 'alert');
    }
}

// Verify MFA
async function verifyMFA() {
    const token = document.getElementById('mfaVerifyToken').value.trim();

    if (!token || token.length !== 6) {
        showAlert('Please enter a 6-digit code', 'error', 'alert');
        return;
    }

    try {
        await api.verifyMFA(token);
        showAlert('Two-factor authentication enabled successfully!', 'success', 'alert');
        closeMFAModal();
        await loadMFAStatus();
    } catch (error) {
        console.error('Failed to verify MFA:', error);
        showAlert('Invalid code. Please try again.', 'error', 'alert');
    }
}

// Disable MFA
async function disableMFA() {
    const password = prompt('Enter your password to disable 2FA:');
    if (!password) return;

    try {
        await api.disableMFA(password);
        showAlert('Two-factor authentication disabled', 'success', 'alert');
        await loadMFAStatus();
    } catch (error) {
        console.error('Failed to disable MFA:', error);
        showAlert('Failed to disable 2FA: ' + error.message, 'error', 'alert');
    }
}

// Regenerate backup codes
async function regenerateBackupCodes() {
    if (!confirm('This will invalidate your old backup codes. Continue?')) return;

    try {
        const data = await api.regenerateBackupCodes();
        const codesText = data.backup_codes.map((code, i) => `${i + 1}. ${code}`).join('\n');
        alert('New Backup Codes:\n\n' + codesText + '\n\nSave these codes in a safe place!');
        await loadMFAStatus();
    } catch (error) {
        console.error('Failed to regenerate backup codes:', error);
        showAlert('Failed to regenerate backup codes: ' + error.message, 'error', 'alert');
    }
}

// Close MFA modal
function closeMFAModal() {
    document.getElementById('mfaSetupModal').style.display = 'none';
    document.getElementById('mfaVerifyToken').value = '';
}
