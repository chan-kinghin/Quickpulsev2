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
        init() {
            if (!api.isAuthenticated()) {
                window.location.href = '/';
            }
        }
    };
}

window.loginForm = loginForm;
window.authGuard = authGuard;
