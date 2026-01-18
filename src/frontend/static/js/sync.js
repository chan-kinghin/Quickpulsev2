function syncPanel() {
    return {
        status: {
            is_running: false,
            progress: 0,
            current_task: null,
            last_sync: null,
            records_synced: null
        },
        daysBack: 7,
        forceSync: false,
        loading: false,
        error: null,
        pollInterval: null,

        async init() {
            console.log('Sync Panel initialized');
            await this.fetchStatus();
            this.startPolling();
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
            this.loading = true;
            this.error = null;

            try {
                await api.post('/sync/trigger', {
                    days_back: parseInt(this.daysBack, 10),
                    force: this.forceSync
                });

                await this.fetchStatus();
            } catch (err) {
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
