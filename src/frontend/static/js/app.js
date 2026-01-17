/**
 * QuickPulse V2 - MTO Search Dashboard
 * Alpine.js component for product status detail sheet
 */

function mtoSearch() {
    return {
        // State
        mtoNumber: '',
        parentItem: null,
        childItems: [],
        loading: false,
        error: '',
        successMessage: '',
        isFullScreen: false,
        isCollapsed: false,

        // API Configuration
        apiBaseUrl: '/api',

        /**
         * Initialize component
         */
        init() {
            console.log('QuickPulse V2 Dashboard initialized');

            // Check for MTO number in URL parameters
            const urlParams = new URLSearchParams(window.location.search);
            const mtoParam = urlParams.get('mto');
            if (mtoParam) {
                this.mtoNumber = mtoParam;
                this.search();
            }

            // Add escape key listener for fullscreen
            this.setupKeyboardListeners();
        },

        /**
         * Setup keyboard event listeners
         */
        setupKeyboardListeners() {
            // ESC key is handled via Alpine's @keydown.escape.window
            // F11 alternative for fullscreen toggle
            document.addEventListener('keydown', (e) => {
                if (e.key === 'F11' && this.childItems.length > 0) {
                    e.preventDefault();
                    this.toggleFullScreen();
                }
            });
        },

        /**
         * Search for MTO data
         */
        async search() {
            // Validation
            if (!this.mtoNumber || !this.mtoNumber.trim()) {
                this.showError('请输入MTO单号');
                return;
            }

            // Clear previous results
            this.clearMessages();
            this.parentItem = null;
            this.childItems = [];
            this.loading = true;

            try {
                // Call API
                const response = await fetch(`${this.apiBaseUrl}/mto/${encodeURIComponent(this.mtoNumber.trim())}`);

                if (!response.ok) {
                    const errorData = await response.json().catch(() => ({ detail: '服务器错误' }));
                    throw new Error(errorData.detail || `HTTP ${response.status}: ${response.statusText}`);
                }

                const data = await response.json();

                // Validate response structure
                if (!data || typeof data !== 'object') {
                    throw new Error('无效的响应数据格式');
                }

                // Set results
                this.parentItem = data.parent_item || null;
                this.childItems = data.child_items || [];

                // Success feedback
                this.successMessage = `成功查询到 ${this.childItems.length} 条BOM组件记录`;
                setTimeout(() => this.successMessage = '', 3000);

                // Update URL with MTO number
                const newUrl = `${window.location.pathname}?mto=${encodeURIComponent(this.mtoNumber.trim())}`;
                window.history.pushState({}, '', newUrl);

                console.log('Search completed:', {
                    parentItem: this.parentItem,
                    childCount: this.childItems.length
                });

            } catch (err) {
                console.error('Search error:', err);
                this.showError(err.message || '查询失败，请稍后重试');
            } finally {
                this.loading = false;
            }
        },

        /**
         * Toggle full screen mode
         */
        toggleFullScreen() {
            this.isFullScreen = !this.isFullScreen;

            if (this.isFullScreen) {
                // Auto-collapse search area when entering fullscreen
                this.isCollapsed = true;
                // Prevent body scroll
                document.body.style.overflow = 'hidden';
            } else {
                // Restore search area visibility
                this.isCollapsed = false;
                // Restore body scroll
                document.body.style.overflow = '';
            }
        },

        /**
         * Exit full screen mode (ESC key handler)
         */
        exitFullScreen() {
            if (this.isFullScreen) {
                this.isFullScreen = false;
                this.isCollapsed = false;
                document.body.style.overflow = '';
            }
        },

        /**
         * Export table data to Excel
         */
        async exportToExcel() {
            if (this.childItems.length === 0) {
                this.showError('没有可导出的数据');
                return;
            }

            try {
                this.showSuccess('正在导出Excel...');

                const response = await fetch(`${this.apiBaseUrl}/export/mto/${encodeURIComponent(this.mtoNumber.trim())}`, {
                    method: 'GET'
                });

                if (!response.ok) {
                    throw new Error('导出失败');
                }

                // Download file
                const blob = await response.blob();
                const url = window.URL.createObjectURL(blob);
                const a = document.createElement('a');
                a.href = url;
                a.download = `MTO_${this.mtoNumber}_${this.getTimestamp()}.xlsx`;
                document.body.appendChild(a);
                a.click();
                window.URL.revokeObjectURL(url);
                document.body.removeChild(a);

                this.showSuccess('Excel导出成功');

            } catch (err) {
                console.error('Export error:', err);
                this.showError('导出失败: ' + err.message);
            }
        },

        /**
         * Check if quantity indicates over-picking (negative unpicked_qty)
         */
        isOverPicked(qty) {
            return parseFloat(qty) < 0;
        },

        /**
         * Format number for display
         */
        formatNumber(value) {
            if (value === null || value === undefined || value === '') {
                return '0';
            }

            const num = parseFloat(value);
            if (isNaN(num)) {
                return '0';
            }

            // Format with thousand separators and 2 decimal places if needed
            if (num % 1 === 0) {
                // Integer
                return num.toLocaleString('zh-CN');
            } else {
                // Decimal
                return num.toLocaleString('zh-CN', {
                    minimumFractionDigits: 2,
                    maximumFractionDigits: 2
                });
            }
        },

        /**
         * Get badge class for material type
         */
        getMaterialTypeBadge(type) {
            const badges = {
                '自制': 'bg-blue-100 text-blue-800',
                '外购': 'bg-green-100 text-green-800',
                '委外': 'bg-purple-100 text-purple-800',
                '虚拟': 'bg-gray-100 text-gray-800',
                '配置': 'bg-yellow-100 text-yellow-800'
            };

            return badges[type] || 'bg-gray-100 text-gray-600';
        },

        /**
         * Show error message
         */
        showError(message) {
            this.error = message;
            this.successMessage = '';
            setTimeout(() => this.error = '', 5000);
        },

        /**
         * Show success message
         */
        showSuccess(message) {
            this.successMessage = message;
            this.error = '';
            setTimeout(() => this.successMessage = '', 3000);
        },

        /**
         * Clear all messages
         */
        clearMessages() {
            this.error = '';
            this.successMessage = '';
        },

        /**
         * Get current timestamp for file naming
         */
        getTimestamp() {
            const now = new Date();
            const year = now.getFullYear();
            const month = String(now.getMonth() + 1).padStart(2, '0');
            const day = String(now.getDate()).padStart(2, '0');
            const hours = String(now.getHours()).padStart(2, '0');
            const minutes = String(now.getMinutes()).padStart(2, '0');
            const seconds = String(now.getSeconds()).padStart(2, '0');

            return `${year}${month}${day}_${hours}${minutes}${seconds}`;
        }
    };
}

// Global utility functions
window.mtoSearch = mtoSearch;

// Debug helper
if (window.location.hostname === 'localhost' || window.location.hostname === '127.0.0.1') {
    console.log('QuickPulse V2 - Development Mode');
    console.log('Keyboard shortcuts:');
    console.log('  - F11: Toggle fullscreen');
    console.log('  - ESC: Exit fullscreen');
}
