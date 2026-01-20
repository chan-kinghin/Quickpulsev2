function syncPanel() {
    return {
        status: {
            is_running: false,
            progress: 0,
            current_task: null,
            last_sync: null,
            records_synced: null
        },
        daysBack: 30,  // Default fallback, will be overwritten by config
        forceSync: false,
        loading: false,
        error: null,
        pollInterval: null,

        async init() {
            console.log('Sync Panel initialized');
            await this.fetchConfig();
            await this.fetchStatus();
            this.startPolling();
        },

        async fetchConfig() {
            try {
                const config = await api.get('/sync/config');
                if (config.manual_sync_default_days) {
                    this.daysBack = config.manual_sync_default_days;
                }
            } catch (err) {
                console.error('Failed to fetch sync config:', err);
            }
        },

        async fetchStatus() {
            try {
                const data = await api.get('/sync/status');
                this.status = { ...this.status, ...data };
            } catch (err) {
                console.error('Failed to fetch sync status:', err);
            }
        },

        startPolling() {
            this.pollInterval = setInterval(() => this.fetchStatus(), 5000);
        },

        stopPolling() {
            if (this.pollInterval) {
                clearInterval(this.pollInterval);
            }
        },

        async triggerSync() {
            console.log('triggerSync called', { daysBack: this.daysBack, forceSync: this.forceSync });
            this.loading = true;
            this.error = null;

            try {
                console.log('Calling api.post /sync/trigger...');
                const result = await api.post('/sync/trigger', {
                    days_back: parseInt(this.daysBack, 10),
                    force: this.forceSync
                });
                console.log('Sync trigger result:', result);

                await this.fetchStatus();
            } catch (err) {
                console.error('Sync trigger error:', err);
                this.error = err.message;
            } finally {
                this.loading = false;
            }
        },

        destroy() {
            this.stopPolling();
        }
    };
}

window.syncPanel = syncPanel;
