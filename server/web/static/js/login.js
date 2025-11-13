// LabLink Web Dashboard - Login Page

document.addEventListener('DOMContentLoaded', () => {
    // Redirect if already logged in
    if (isAuthenticated()) {
        handleReturnUrl();
        return;
    }

    const form = document.getElementById('loginForm');
    const usernameInput = document.getElementById('username');
    const passwordInput = document.getElementById('password');
    const rememberMeInput = document.getElementById('rememberMe');
    const loginButton = document.getElementById('loginButton');
    const errorAlert = document.getElementById('errorAlert');

    // Handle form submission
    form.addEventListener('submit', async (e) => {
        e.preventDefault();

        const username = usernameInput.value.trim();
        const password = passwordInput.value;
        const rememberMe = rememberMeInput.checked;

        if (!username || !password) {
            showAlert('Please enter username and password', 'error', 'errorAlert');
            return;
        }

        // Show loading state
        setButtonLoading(loginButton, true);
        hideAlert('errorAlert');

        try {
            await login(username, password, rememberMe);

            // Show success message briefly
            showAlert('Login successful! Redirecting...', 'success', 'errorAlert');

            // Redirect after short delay
            setTimeout(() => {
                handleReturnUrl();
            }, 500);
        } catch (error) {
            console.error('Login error:', error);
            showAlert(
                error.message || 'Login failed. Please check your credentials and try again.',
                'error',
                'errorAlert'
            );
        } finally {
            setButtonLoading(loginButton, false);
        }
    });

    // Focus username input
    usernameInput.focus();

    // Handle Enter key in password field
    passwordInput.addEventListener('keypress', (e) => {
        if (e.key === 'Enter') {
            form.dispatchEvent(new Event('submit'));
        }
    });
});
