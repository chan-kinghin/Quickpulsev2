function loginForm() {
    return {
        username: '',
        password: '',
        error: null,
        loading: false,

        async submit() {
            this.loading = true;
            this.error = null;

            try {
                await api.login(this.username, this.password);
                window.location.href = '/dashboard.html';
            } catch (error) {
                this.error = error.message;
                this.$el.classList.add('animate-shake');
                setTimeout(() => this.$el.classList.remove('animate-shake'), 500);
            } finally {
                this.loading = false;
            }
        }
    };
}

function authGuard() {
    return {
        authenticated: false,

        async init() {
            // First check if token exists locally
            if (!api.isAuthenticated()) {
                window.location.href = '/';
                return;
            }

            // Then verify token is still valid with server
            try {
                await api.get('/auth/verify');
                this.authenticated = true;
            } catch (error) {
                // Token invalid/expired - redirect handled by api.request() on 401
                console.log('Token verification failed, redirecting to login');
            }
        }
    };
}

window.loginForm = loginForm;
window.authGuard = authGuard;
