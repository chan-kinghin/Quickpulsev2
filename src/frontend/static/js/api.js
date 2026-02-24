const api = {
    baseUrl: '/api',

    getToken() {
        return localStorage.getItem('token');
    },

    setToken(token) {
        localStorage.setItem('token', token);
    },

    clearToken() {
        localStorage.removeItem('token');
    },

    isAuthenticated() {
        return !!this.getToken();
    },

    async request(endpoint, options = {}) {
        const token = this.getToken();
        const headers = {
            'Content-Type': 'application/json',
            ...(token && { Authorization: `Bearer ${token}` }),
            ...options.headers
        };

        const controller = new AbortController();
        const timeoutMs = options.timeout || 30000;
        const timeoutId = setTimeout(() => controller.abort(), timeoutMs);

        let response;
        try {
            response = await fetch(`${this.baseUrl}${endpoint}`, {
                ...options,
                headers,
                signal: controller.signal
            });
        } catch (err) {
            clearTimeout(timeoutId);
            if (err.name === 'AbortError') {
                throw new Error('请求超时，请稍后重试');
            }
            throw err;
        }
        clearTimeout(timeoutId);

        if (response.status === 401) {
            this.clearToken();
            window.location.href = '/';
            throw new Error('Unauthorized');
        }

        if (!response.ok) {
            const contentType = response.headers.get('content-type') || '';
            let errorMessage = `HTTP ${response.status}`;

            if (contentType.includes('application/json')) {
                const error = await response.json().catch(() => ({}));
                errorMessage = error.detail || errorMessage;
            } else {
                const text = await response.text().catch(() => '');
                if (text) {
                    errorMessage = text.length > 200 ? text.substring(0, 200) + '...' : text;
                }
            }
            throw new Error(errorMessage);
        }

        const contentType = response.headers.get('content-type') || '';

        // Binary/downloadable response types
        const blobTypes = ['text/csv', 'application/vnd', 'application/octet-stream',
                          'application/pdf', 'application/zip', 'image/'];
        if (blobTypes.some(type => contentType.includes(type))) {
            return response.blob();
        }

        // Plain text responses
        if (contentType.includes('text/plain')) {
            return response.text();
        }

        return response.json();
    },

    get: (endpoint) => api.request(endpoint),
    post: (endpoint, body) => api.request(endpoint, { method: 'POST', body: JSON.stringify(body) }),
    put: (endpoint, body) => api.request(endpoint, { method: 'PUT', body: JSON.stringify(body) }),

    async login(username, password) {
        const formData = new URLSearchParams();
        formData.append('username', username);
        formData.append('password', password);

        // Add timeout for network issues
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 15000); // 15s timeout

        let response;
        try {
            response = await fetch(`${this.baseUrl}/auth/token`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                body: formData,
                signal: controller.signal
            });
        } catch (fetchError) {
            clearTimeout(timeoutId);
            if (fetchError.name === 'AbortError') {
                throw new Error('连接超时，请检查网络后重试');
            }
            throw new Error('网络连接失败，请检查网络后重试');
        } finally {
            clearTimeout(timeoutId);
        }

        if (!response.ok) {
            const contentType = response.headers.get('content-type') || '';
            if (contentType.includes('application/json')) {
                const error = await response.json().catch(() => ({}));
                throw new Error(error.detail || '用户名或密码错误');
            }
            throw new Error('用户名或密码错误');
        }

        const contentType = response.headers.get('content-type') || '';
        if (!contentType.includes('application/json')) {
            throw new Error('服务器响应格式错误');
        }

        const data = await response.json();
        this.setToken(data.access_token);
        return data;
    },

    logout() {
        this.clearToken();
        window.location.href = '/';
    }
};

window.api = api;
