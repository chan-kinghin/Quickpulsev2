function loginForm() {
    return {
        username: '',
        password: '',
        error: null,
        loading: false,

        init() {
            if (api.isAuthenticated()) {
                window.location.href = '/dashboard.html';
            }
        },

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

            // Then verify token is still valid with server.
            try {
                await api.get('/auth/verify');
                this.authenticated = true;
            } catch (error) {
                // Fail-OPEN on transient failures. A real 401 is already handled
                // inside api.request() (clears token + redirects to login), so a
                // surfaced error here means the gateway flaked (503/timeout/network)
                // — the local token is still valid. Blanking the page on a transient
                // 503 was making every protected page look "broken" whenever the
                // shared nginx rate-limited /api/* under load. Show the page; real
                // API calls still enforce auth (401 -> redirect) on their own.
                if (error && error.message === 'Unauthorized') {
                    return; // 401: api.request() already redirected to login
                }
                console.warn(
                    'Token verify failed transiently, proceeding with local token:',
                    error && error.message,
                );
                this.authenticated = true;
            }
        }
    };
}

window.loginForm = loginForm;
window.authGuard = authGuard;
