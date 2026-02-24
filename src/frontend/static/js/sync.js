function syncPanel() {
    return {
        status: {
            is_running: false,
            progress: 0,
            current_task: null,
            last_sync: null,
            records_synced: null
        },
        daysBack: 30,
        forceSync: false,
        loading: false,
        error: null,
        pollInterval: null,

        // Config editor state
        config: {
            auto_sync_enabled: false,
            auto_sync_schedule: [],
            auto_sync_days: 365,
            manual_sync_default_days: 30
        },
        configLoading: false,
        configMsg: null,
        configMsgType: 'success',

        // Sync history state
        history: [],
        historyLoading: false,

        // Cache admin state
        cacheStats: null,
        cacheLoading: false,
        cacheMsg: null,
        cacheMsgType: 'success',
        cacheStatsInterval: null,
        hotMtos: [],
        hotMtosLoading: false,
        invalidateMto: '',
        invalidateLoading: false,
        warmCount: 100,
        warmLoading: false,
        clearCacheConfirm: false,
        _originalConfig: null,

        async init() {
            // Wait for authGuard to verify token before making API calls
            if (!api.isAuthenticated()) return;
            try {
                await api.get('/auth/verify');
            } catch {
                return; // Token invalid — authGuard will redirect
            }

            await Promise.all([
                this.fetchConfig(),
                this.fetchStatus(),
                this.fetchHistory(),
                this.fetchCacheStats(),
                this.fetchHotMtos()
            ]);
            this.startPolling();
            this.cacheStatsInterval = setInterval(() => this.fetchCacheStats(), 30000);
        },

        // --- Config ---
        async fetchConfig() {
            try {
                const data = await api.get('/sync/config');
                this.config = { ...this.config, ...data };
                if (data.manual_sync_default_days) {
                    this.daysBack = data.manual_sync_default_days;
                }
                this._originalConfig = JSON.stringify({
                    auto_sync_enabled: this.config.auto_sync_enabled,
                    auto_sync_days: parseInt(this.config.auto_sync_days, 10),
                    manual_sync_default_days: parseInt(this.config.manual_sync_default_days, 10)
                });
            } catch (err) {
                console.error('Failed to fetch sync config:', err);
            }
        },

        async saveConfig() {
            this.configLoading = true;
            this.configMsg = null;
            try {
                await api.put('/sync/config', {
                    auto_sync_enabled: this.config.auto_sync_enabled,
                    auto_sync_days: parseInt(this.config.auto_sync_days, 10),
                    manual_sync_default_days: parseInt(this.config.manual_sync_default_days, 10)
                });
                this._originalConfig = JSON.stringify({
                    auto_sync_enabled: this.config.auto_sync_enabled,
                    auto_sync_days: parseInt(this.config.auto_sync_days, 10),
                    manual_sync_default_days: parseInt(this.config.manual_sync_default_days, 10)
                });
                this.configMsg = '配置已保存';
                this.configMsgType = 'success';
                setTimeout(() => { this.configMsg = null; }, 3000);
            } catch (err) {
                this.configMsg = '保存失败: ' + err.message;
                this.configMsgType = 'error';
            } finally {
                this.configLoading = false;
            }
        },

        isConfigDirty() {
            if (!this._originalConfig) return false;
            const current = JSON.stringify({
                auto_sync_enabled: this.config.auto_sync_enabled,
                auto_sync_days: parseInt(this.config.auto_sync_days, 10),
                manual_sync_default_days: parseInt(this.config.manual_sync_default_days, 10)
            });
            return current !== this._originalConfig;
        },

        // --- Status ---
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
            if (this.pollInterval) clearInterval(this.pollInterval);
        },

        // --- Trigger sync ---
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

        // --- History ---
        async fetchHistory() {
            this.historyLoading = true;
            try {
                this.history = await api.get('/sync/history?limit=10');
            } catch (err) {
                console.error('Failed to fetch sync history:', err);
                this.history = [];
            } finally {
                this.historyLoading = false;
            }
        },

        formatDate(iso) {
            if (!iso) return '-';
            try {
                const d = new Date(iso);
                const pad = (n) => String(n).padStart(2, '0');
                return `${d.getFullYear()}-${pad(d.getMonth() + 1)}-${pad(d.getDate())} ${pad(d.getHours())}:${pad(d.getMinutes())}:${pad(d.getSeconds())}`;
            } catch {
                return iso;
            }
        },

        statusBadgeClass(status) {
            switch (status) {
                case 'success':
                case 'completed': return 'bg-emerald-500/20 text-emerald-400';
                case 'failed': return 'bg-rose-500/20 text-rose-400';
                case 'running': return 'bg-amber-500/20 text-amber-400';
                default: return 'bg-slate-500/20 text-slate-400';
            }
        },

        // --- Cache stats ---
        async fetchCacheStats() {
            this.cacheLoading = true;
            try {
                this.cacheStats = await api.get('/cache/stats');
            } catch (err) {
                console.error('Failed to fetch cache stats:', err);
            } finally {
                this.cacheLoading = false;
            }
        },

        async clearCache() {
            if (!this.clearCacheConfirm) {
                this.clearCacheConfirm = true;
                setTimeout(() => { this.clearCacheConfirm = false; }, 3000);
                return;
            }
            this.clearCacheConfirm = false;
            this.cacheMsg = null;
            try {
                const result = await api.post('/cache/clear');
                this.cacheMsg = '缓存已清除，清除 ' + (result.entries_cleared || 0) + ' 条';
                this.cacheMsgType = 'success';
                await this.fetchCacheStats();
            } catch (err) {
                this.cacheMsg = '清除失败: ' + err.message;
                this.cacheMsgType = 'error';
            }
            setTimeout(() => { this.cacheMsg = null; }, 4000);
        },

        async resetCacheStats() {
            this.cacheMsg = null;
            try {
                await api.post('/cache/reset-stats');
                this.cacheMsg = '统计已重置';
                this.cacheMsgType = 'success';
                await this.fetchCacheStats();
            } catch (err) {
                this.cacheMsg = '重置失败: ' + err.message;
                this.cacheMsgType = 'error';
            }
            setTimeout(() => { this.cacheMsg = null; }, 4000);
        },

        async warmCache() {
            this.warmLoading = true;
            this.cacheMsg = null;
            try {
                const result = await api.post('/cache/warm?count=' + parseInt(this.warmCount, 10) + '&use_hot=false');
                this.cacheMsg = '预热完成: ' + (result.warmed || 0) + ' 成功, ' + (result.failed || 0) + ' 失败';
                this.cacheMsgType = 'success';
                await this.fetchCacheStats();
            } catch (err) {
                this.cacheMsg = '预热失败: ' + err.message;
                this.cacheMsgType = 'error';
            } finally {
                this.warmLoading = false;
            }
            setTimeout(() => { this.cacheMsg = null; }, 5000);
        },

        // --- Hot MTOs ---
        async fetchHotMtos() {
            this.hotMtosLoading = true;
            try {
                const result = await api.get('/cache/hot-mtos?top_n=20');
                this.hotMtos = result.hot_mtos || [];
            } catch (err) {
                console.error('Failed to fetch hot MTOs:', err);
                this.hotMtos = [];
            } finally {
                this.hotMtosLoading = false;
            }
        },

        // --- Invalidate MTO ---
        async doInvalidateMto() {
            if (!this.invalidateMto.trim()) return;
            this.invalidateLoading = true;
            this.cacheMsg = null;
            try {
                const result = await api.request('/cache/' + encodeURIComponent(this.invalidateMto.trim()), { method: 'DELETE' });
                if (result.status === 'invalidated') {
                    this.cacheMsg = 'MTO ' + this.invalidateMto.trim() + ' 缓存已失效';
                    this.cacheMsgType = 'success';
                } else {
                    this.cacheMsg = 'MTO ' + this.invalidateMto.trim() + ' 未找到';
                    this.cacheMsgType = 'error';
                }
                this.invalidateMto = '';
                await this.fetchCacheStats();
            } catch (err) {
                this.cacheMsg = '失效操作失败: ' + err.message;
                this.cacheMsgType = 'error';
            } finally {
                this.invalidateLoading = false;
            }
            setTimeout(() => { this.cacheMsg = null; }, 4000);
        },

        formatNumber(n) {
            if (n == null) return '-';
            return Number(n).toLocaleString();
        },

        formatPercent(n) {
            if (n == null) return '-';
            return (Number(n) * 100).toFixed(1) + '%';
        },

        destroy() {
            this.stopPolling();
            if (this.cacheStatsInterval) clearInterval(this.cacheStatsInterval);
        }
    };
}

window.syncPanel = syncPanel;
