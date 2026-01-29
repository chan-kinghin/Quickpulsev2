function mtoSearch() {
    return {
        mtoNumber: '',
        parentItem: null,
        childItems: [],
        loading: false,
        error: '',
        successMessage: '',
        relatedOrders: null,
        relatedOrdersExpanded: true,
        relatedOrdersLoading: false,
        relatedOrdersError: '',
        isFullScreen: false,
        isCollapsed: false,

        init() {
            console.log('QuickPulse V2 Dashboard initialized');

            const urlParams = new URLSearchParams(window.location.search);
            const mtoParam = urlParams.get('mto');
            if (mtoParam) {
                this.mtoNumber = mtoParam;
                this.search();
            }

            this.setupKeyboardListeners();
        },

        setupKeyboardListeners() {
            document.addEventListener('keydown', (event) => {
                if (event.key === 'F11' && this.childItems.length > 0) {
                    event.preventDefault();
                    this.toggleFullScreen();
                }
                if (event.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                    event.preventDefault();
                    document.getElementById('mto-search')?.focus();
                }
            });
        },

        async search() {
            if (!this.mtoNumber?.trim()) {
                this.showError('请输入MTO单号');
                return;
            }

            this.clearMessages();
            this.parentItem = null;
            this.childItems = [];
            this.relatedOrders = null;
            this.relatedOrdersExpanded = true;
            this.relatedOrdersLoading = false;
            this.relatedOrdersError = '';
            this.loading = true;

            try {
                const data = await api.get(`/mto/${encodeURIComponent(this.mtoNumber.trim())}`);

                this.parentItem = data.parent_item || null;
                this.childItems = data.child_items || [];

                this.successMessage = `成功查询到 ${this.childItems.length} 条BOM组件记录`;
                setTimeout(() => {
                    this.successMessage = '';
                }, 3000);

                const newUrl = `${window.location.pathname}?mto=${encodeURIComponent(this.mtoNumber.trim())}`;
                window.history.pushState({}, '', newUrl);

                this.fetchRelatedOrders();
            } catch (err) {
                console.error('Search error:', err);
                this.showError(err.message || '查询失败，请稍后重试');
            } finally {
                this.loading = false;
            }
        },

        toggleFullScreen() {
            this.isFullScreen = !this.isFullScreen;
            this.isCollapsed = this.isFullScreen;
            document.body.style.overflow = this.isFullScreen ? 'hidden' : '';
        },

        exitFullScreen() {
            if (this.isFullScreen) {
                this.isFullScreen = false;
                this.isCollapsed = false;
                document.body.style.overflow = '';
            }
        },

        async exportToExcel() {
            if (this.childItems.length === 0) {
                this.showError('没有可导出的数据');
                return;
            }

            try {
                this.showSuccess('正在导出Excel...');
                const blob = await api.get(`/export/mto/${encodeURIComponent(this.mtoNumber.trim())}`);

                const url = window.URL.createObjectURL(blob);
                const anchor = document.createElement('a');
                anchor.href = url;
                anchor.download = `MTO_${this.mtoNumber}_${this.getTimestamp()}.csv`;
                document.body.appendChild(anchor);
                anchor.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(anchor);

                this.showSuccess('Excel导出成功');
            } catch (err) {
                console.error('Export error:', err);
                this.showError('导出失败: ' + err.message);
            }
        },

        async fetchRelatedOrders() {
            if (!this.mtoNumber?.trim()) {
                return;
            }

            this.relatedOrdersLoading = true;
            this.relatedOrdersError = '';

            try {
                const data = await api.get(`/mto/${encodeURIComponent(this.mtoNumber.trim())}/related-orders`);
                this.relatedOrders = data;
            } catch (err) {
                console.error('Related orders error:', err);
                this.relatedOrdersError = err.message || '关联单据加载失败';
                this.relatedOrders = null;
            } finally {
                this.relatedOrdersLoading = false;
            }
        },

        isOverPicked: (qty) => parseFloat(qty) < 0,

        formatNumber(value) {
            if (value === null || value === undefined || value === '') {
                return '0';
            }

            const num = parseFloat(value);
            if (isNaN(num)) {
                return '0';
            }

            return num % 1 === 0
                ? num.toLocaleString('zh-CN')
                : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },

        getMaterialTypeBadge(type) {
            const badges = {
                自制: 'badge-self-made',
                外购: 'badge-purchased',
                委外: 'badge-subcontracted'
            };

            return badges[type] || 'bg-slate-800 text-slate-400 border border-slate-700';
        },

        hasRelatedOrders() {
            if (!this.relatedOrders) {
                return false;
            }

            const orders = Object.values(this.relatedOrders.orders || {});
            const documents = Object.values(this.relatedOrders.documents || {});
            const orderCount = orders.reduce((sum, items) => sum + (items?.length || 0), 0);
            const docCount = documents.reduce((sum, items) => sum + (items?.length || 0), 0);
            return orderCount + docCount > 0;
        },

        showError(message) {
            this.error = message;
            this.successMessage = '';
            setTimeout(() => {
                this.error = '';
            }, 5000);
        },

        showSuccess(message) {
            this.successMessage = message;
            this.error = '';
            setTimeout(() => {
                this.successMessage = '';
            }, 3000);
        },

        clearMessages() {
            this.error = '';
            this.successMessage = '';
        },

        getTimestamp() {
            const now = new Date();
            return `${now.getFullYear()}${String(now.getMonth() + 1).padStart(2, '0')}${String(now.getDate()).padStart(2, '0')}_${String(now.getHours()).padStart(2, '0')}${String(now.getMinutes()).padStart(2, '0')}`;
        }
    };
}

window.mtoSearch = mtoSearch;
