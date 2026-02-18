function mtoSearch() {
    return {
        // === Core State ===
        mtoNumber: '',
        parentItem: null,
        childItems: [],
        dataSource: null,      // 'cache' or 'live'
        cacheAgeSeconds: null, // age in seconds when from cache
        loading: false,
        error: '',
        successMessage: '',
        relatedOrders: null,
        relatedOrdersExpanded: true,
        relatedOrdersLoading: false,
        relatedOrdersError: '',
        isFullScreen: false,
        isCollapsed: false,

        // === Filters ===
        // 物料类型: 成品(07.xx), 自制(05.xx), 包材(03.xx)
        filters: {
            materialTypes: { '成品': true, '自制': true, '包材': true },
            status: 'all', // 保留但简化
            searchText: ''
        },

        // === Column Configuration ===
        // 列名直接使用金蝶的"表单.字段名"格式，不做任何计算
        columns: [
            { key: 'index', label: '序号', width: 60, minWidth: 40, resizable: false, visible: true, sortable: false, locked: true },
            { key: 'material_code', label: '物料编码', width: 120, minWidth: 80, resizable: true, visible: true, sortable: true, locked: true },
            { key: 'material_name', label: '物料名称', width: 150, minWidth: 100, resizable: true, visible: true, sortable: true, locked: true },
            { key: 'specification', label: '规格型号', width: 120, minWidth: 80, resizable: true, visible: true, sortable: true, locked: false },
            { key: 'bom_short_name', label: 'BOM简称', width: 150, minWidth: 100, resizable: true, visible: true, sortable: true, locked: false, materialPrefix: '07' },
            { key: 'aux_attributes', label: '辅助属性', width: 150, minWidth: 100, resizable: true, visible: true, sortable: false, locked: false },
            { key: 'material_type', label: '物料类型', width: 90, minWidth: 70, resizable: true, visible: true, sortable: true, locked: false },
            // 数量列：根据物料类型显示不同来源
            { key: 'sales_order_qty', label: '销售订单.数量', width: 120, minWidth: 80, resizable: true, visible: true, sortable: true, locked: false, group: 'green', materialPrefix: '07' },
            { key: 'prod_instock_must_qty', label: '生产入库单.应收数量', width: 140, minWidth: 100, resizable: true, visible: true, sortable: true, locked: false, group: 'green', materialPrefix: '05' },
            { key: 'purchase_order_qty', label: '采购订单.数量', width: 120, minWidth: 80, resizable: true, visible: true, sortable: true, locked: false, group: 'green', materialPrefix: '03' },
            // 领料/入库列
            { key: 'pick_actual_qty', label: '生产领料单.实发数量', width: 140, minWidth: 100, resizable: true, visible: true, sortable: true, locked: false, group: 'green', materialPrefix: '05,03' },
            { key: 'prod_instock_real_qty', label: '生产入库单.实收数量', width: 140, minWidth: 100, resizable: true, visible: true, sortable: true, locked: false, group: 'blue', materialPrefix: '07,05' },
            { key: 'purchase_stock_in_qty', label: '采购订单.累计入库数量', width: 150, minWidth: 100, resizable: true, visible: true, sortable: true, locked: false, group: 'blue', materialPrefix: '03' },
            // 语义层：完成率列（从 metrics 计算得出）
            { key: 'fulfillment_rate', label: '完成率', width: 100, minWidth: 70, resizable: true, visible: true, sortable: true, locked: false, group: 'semantic' }
        ],

        // === Sorting ===
        sort: {
            column: null,
            direction: null // 'asc' | 'desc' | null
        },

        // === Column Resize State ===
        resizing: {
            active: false,
            columnIndex: null,
            startX: 0,
            startWidth: 0
        },

        // === UI State ===
        showColumnSettings: false,
        showSearchHistory: false,
        showExportMenu: false,

        // === Search History ===
        searchHistory: [],
        MAX_HISTORY_ITEMS: 10,

        // === MTO Search-as-you-type State ===
        searchResults: [],
        searchTotal: 0,
        searchLoading: false,
        showSearchResults: false,
        _searchDebounce: null,

        // === Chat State ===
        chatAvailable: false,
        chatOpen: false,
        chatMessages: [],   // [{role, content, sql?, sqlResult?}]
        chatInput: '',
        chatLoading: false,
        chatModel: '',
        chatMode: 'simple',          // 'simple' or 'agent'
        agentChatAvailable: false,
        _chatAbort: null,    // AbortController for active stream

        // === Preferences ===
        STORAGE_KEY: 'quickpulse_preferences',
        STORAGE_VERSION: 1,

        // === Lifecycle ===
        init() {
            console.log('QuickPulse V2 Dashboard initialized');
            this.loadPreferences();

            const urlParams = new URLSearchParams(window.location.search);
            const mtoParam = urlParams.get('mto');
            if (mtoParam) {
                this.mtoNumber = mtoParam;
                this.search();
            }

            this.setupKeyboardListeners();
            this.setupResizeListeners();
            this.initChat();
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
            // Listen for MTO link clicks from chat messages
            document.addEventListener('chat-mto-click', (event) => {
                const mtoNum = event.detail;
                if (mtoNum) {
                    this.mtoNumber = mtoNum;
                    this.search();
                }
            });
        },

        setupResizeListeners() {
            document.addEventListener('mousemove', (e) => this.doResize(e));
            document.addEventListener('mouseup', () => this.stopResize());
        },

        // === Preferences Persistence ===
        loadPreferences() {
            try {
                const stored = localStorage.getItem(this.STORAGE_KEY);
                if (!stored) return;

                const prefs = JSON.parse(stored);
                if (prefs.version !== this.STORAGE_VERSION) return;

                // Apply column settings
                if (prefs.columns) {
                    this.columns.forEach(col => {
                        if (prefs.columns[col.key]) {
                            col.width = prefs.columns[col.key].width ?? col.width;
                            col.visible = prefs.columns[col.key].visible ?? col.visible;
                        }
                    });
                }

                // Apply filter settings (except searchText)
                if (prefs.filters) {
                    this.filters.materialTypes = prefs.filters.materialTypes ?? this.filters.materialTypes;
                    this.filters.status = prefs.filters.status ?? this.filters.status;
                }

                // Apply sort settings
                if (prefs.sort) {
                    this.sort = prefs.sort;
                }

                // Apply search history
                if (prefs.searchHistory) {
                    this.searchHistory = prefs.searchHistory;
                }

                console.log('Preferences loaded');
            } catch (e) {
                console.warn('Failed to load preferences:', e);
            }
        },

        savePreferences() {
            try {
                const prefs = {
                    version: this.STORAGE_VERSION,
                    columns: {},
                    filters: {
                        materialTypes: this.filters.materialTypes,
                        status: this.filters.status
                    },
                    sort: this.sort,
                    searchHistory: this.searchHistory
                };

                this.columns.forEach(col => {
                    prefs.columns[col.key] = {
                        width: col.width,
                        visible: col.visible
                    };
                });

                localStorage.setItem(this.STORAGE_KEY, JSON.stringify(prefs));
            } catch (e) {
                console.warn('Failed to save preferences:', e);
            }
        },

        // === Computed Properties (as methods for Alpine.js) ===
        getFilteredItems() {
            return this.childItems.filter(item => {
                // Material type filter
                if (!this.filters.materialTypes[item.material_type]) return false;

                // Status filter — uses server-computed completion_status from semantic layer
                if (this.filters.status !== 'all' && item.metrics?.completion_status?.status) {
                    const itemStatus = item.metrics.completion_status.status;
                    if (this.filters.status === 'completed' && itemStatus !== 'completed') return false;
                    if (this.filters.status === 'in_progress' && itemStatus !== 'in_progress') return false;
                    if (this.filters.status === 'not_started' && itemStatus !== 'not_started') return false;
                    if (this.filters.status === 'warning' && itemStatus !== 'warning') return false;
                }

                // Text search (material code + name + spec + aux)
                if (this.filters.searchText) {
                    const searchLower = this.filters.searchText.toLowerCase();
                    const searchFields = [
                        item.material_code,
                        item.material_name,
                        item.specification,
                        item.aux_attributes
                    ].filter(Boolean).join(' ').toLowerCase();
                    if (!searchFields.includes(searchLower)) return false;
                }

                return true;
            });
        },

        getSortedItems() {
            let items = [...this.getFilteredItems()];

            if (this.sort.column && this.sort.direction) {
                items.sort((a, b) => {
                    let valA, valB;

                    // Handle metric columns (nested in metrics dict)
                    if (this.sort.column === 'fulfillment_rate') {
                        valA = this.getFulfillmentRate(a);
                        valB = this.getFulfillmentRate(b);
                        // Nulls sort last
                        if (valA === null && valB === null) return 0;
                        if (valA === null) return 1;
                        if (valB === null) return -1;
                        return this.sort.direction === 'asc' ? valA - valB : valB - valA;
                    }

                    valA = a[this.sort.column];
                    valB = b[this.sort.column];

                    // Handle numeric values
                    const numA = parseFloat(valA);
                    const numB = parseFloat(valB);
                    if (!isNaN(numA) && !isNaN(numB)) {
                        return this.sort.direction === 'asc' ? numA - numB : numB - numA;
                    }

                    // Handle string values
                    valA = String(valA || '').toLowerCase();
                    valB = String(valB || '').toLowerCase();
                    if (valA < valB) return this.sort.direction === 'asc' ? -1 : 1;
                    if (valA > valB) return this.sort.direction === 'asc' ? 1 : -1;
                    return 0;
                });
            }

            return items;
        },

        getVisibleColumns() {
            return this.columns.filter(c => c.visible);
        },

        // === Filter Methods ===
        toggleMaterialType(type) {
            this.filters.materialTypes[type] = !this.filters.materialTypes[type];
            this.savePreferences();
        },

        setStatusFilter(status) {
            this.filters.status = status;
            this.savePreferences();
        },

        hasActiveFilters() {
            const allTypesOn = Object.values(this.filters.materialTypes).every(v => v);
            return !allTypesOn || this.filters.status !== 'all' || this.filters.searchText.length > 0;
        },

        resetFilters() {
            this.filters.materialTypes = { '成品': true, '自制': true, '包材': true };
            this.filters.status = 'all';
            this.filters.searchText = '';
            this.savePreferences();
        },

        getActiveFilterCount() {
            let count = 0;
            if (!Object.values(this.filters.materialTypes).every(v => v)) count++;
            if (this.filters.status !== 'all') count++;
            if (this.filters.searchText.length > 0) count++;
            return count;
        },

        // === Sort Methods ===
        toggleSort(columnKey) {
            const col = this.columns.find(c => c.key === columnKey);
            if (!col || !col.sortable) return;

            if (this.sort.column !== columnKey) {
                this.sort.column = columnKey;
                this.sort.direction = 'asc';
            } else if (this.sort.direction === 'asc') {
                this.sort.direction = 'desc';
            } else {
                this.sort.column = null;
                this.sort.direction = null;
            }
            this.savePreferences();

            // Refresh sort icons
            if (typeof refreshIcons === 'function') {
                setTimeout(refreshIcons, 50);
            }
        },

        getSortIcon(columnKey) {
            if (this.sort.column !== columnKey) return 'chevrons-up-down';
            return this.sort.direction === 'asc' ? 'chevron-up' : 'chevron-down';
        },

        // === Column Visibility Methods ===
        toggleColumnVisibility(columnKey) {
            const col = this.columns.find(c => c.key === columnKey);
            if (!col || col.locked) return;
            col.visible = !col.visible;
            this.savePreferences();
        },

        isColumnLocked(columnKey) {
            const col = this.columns.find(c => c.key === columnKey);
            return col ? col.locked : false;
        },

        // === Column Resize Methods ===
        startResize(event, columnKey) {
            event.preventDefault();
            event.stopPropagation();
            const colIndex = this.columns.findIndex(c => c.key === columnKey);
            if (colIndex === -1) return;
            this.resizing = {
                active: true,
                columnIndex: colIndex,
                startX: event.clientX,
                startWidth: this.columns[colIndex].width
            };
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';
        },

        doResize(event) {
            if (!this.resizing.active) return;
            const diff = event.clientX - this.resizing.startX;
            const col = this.columns[this.resizing.columnIndex];
            col.width = Math.max(col.minWidth, this.resizing.startWidth + diff);
        },

        stopResize() {
            if (!this.resizing.active) return;
            this.resizing.active = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';
            this.savePreferences();
        },

        getColumnStyle(columnKey) {
            const col = this.columns.find(c => c.key === columnKey);
            return col ? `width: ${col.width}px; min-width: ${col.minWidth}px;` : '';
        },

        colVisible(key) {
            const col = this.columns.find(c => c.key === key);
            return col ? col.visible : false;
        },

        // === Search History Methods ===
        addToSearchHistory(mtoNumber) {
            if (!mtoNumber?.trim()) return;

            // Remove duplicate if exists
            this.searchHistory = this.searchHistory.filter(
                item => item.toLowerCase() !== mtoNumber.toLowerCase()
            );

            // Add to front
            this.searchHistory.unshift(mtoNumber.trim());

            // Limit size
            if (this.searchHistory.length > this.MAX_HISTORY_ITEMS) {
                this.searchHistory = this.searchHistory.slice(0, this.MAX_HISTORY_ITEMS);
            }

            this.savePreferences();
        },

        selectFromHistory(mtoNumber) {
            this.mtoNumber = mtoNumber;
            this.showSearchHistory = false;
            this.search();
        },

        clearSearchHistory() {
            this.searchHistory = [];
            this.savePreferences();
        },

        // === MTO Fuzzy Search ===
        performSearch() {
            const query = this.mtoNumber.trim();
            if (this._searchDebounce) clearTimeout(this._searchDebounce);

            if (query.length < 2) {
                this.searchResults = [];
                this.searchTotal = 0;
                this.showSearchResults = false;
                return;
            }

            this._searchDebounce = setTimeout(async () => {
                this.searchLoading = true;
                try {
                    const token = localStorage.getItem('token');
                    const resp = await fetch(`/api/search?q=${encodeURIComponent(query)}&limit=10`, {
                        headers: { Authorization: `Bearer ${token}` }
                    });
                    if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
                    const total = parseInt(resp.headers.get('X-Total-Count') || '0');
                    const results = await resp.json();
                    this.searchResults = results;
                    this.searchTotal = total;
                    this.showSearchResults = true;
                    this.showSearchHistory = false;
                } catch (err) {
                    console.warn('Search-as-you-type failed:', err);
                    this.searchResults = [];
                    this.searchTotal = 0;
                    this.showSearchResults = false;
                } finally {
                    this.searchLoading = false;
                }
            }, 300);
        },

        selectSearchResult(mtoNumber) {
            this.mtoNumber = mtoNumber;
            this.showSearchResults = false;
            this.searchResults = [];
            this.search();
        },

        // === Core Search Method ===
        async search() {
            if (!this.mtoNumber?.trim()) {
                this.showError('请输入MTO单号');
                return;
            }

            // Add to history
            this.addToSearchHistory(this.mtoNumber.trim());

            this.clearMessages();
            this.parentItem = null;
            this.childItems = [];
            this.dataSource = null;
            this.cacheAgeSeconds = null;
            this.relatedOrders = null;
            this.relatedOrdersExpanded = true;
            this.relatedOrdersLoading = false;
            this.relatedOrdersError = '';
            this.loading = true;

            try {
                const data = await api.get(`/mto/${encodeURIComponent(this.mtoNumber.trim())}`);

                this.parentItem = data.parent_item || null;
                this.childItems = data.child_items || [];
                this.dataSource = data.data_source || 'live';
                this.cacheAgeSeconds = data.cache_age_seconds || null;

                this.successMessage = `成功查询到 ${this.childItems.length} 条BOM组件记录`;
                setTimeout(() => {
                    this.successMessage = '';
                }, 3000);

                // Refresh icons after data loads
                if (typeof refreshIcons === 'function') {
                    setTimeout(refreshIcons, 50);
                }

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

        // === Full Screen Methods ===
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

        // === Export Methods ===
        async exportToExcel(format = 'xlsx') {
            const items = this.getSortedItems();
            if (items.length === 0) {
                this.showError('没有可导出的数据');
                return;
            }

            try {
                this.showSuccess('正在导出...');

                if (format === 'xlsx' && typeof XLSX !== 'undefined') {
                    // Client-side Excel export using SheetJS
                    // 使用金蝶原始字段名，根据物料类型显示不同值
                    const exportData = items.map((item, index) => {
                        const code = item.material_code || '';
                        const is07 = code.startsWith('07');
                        const is05 = code.startsWith('05');
                        const is03 = code.startsWith('03');

                        const rate = this.getFulfillmentRate(item);
                        return {
                            '序号': index + 1,
                            '物料编码': code,
                            '物料名称': item.material_name,
                            '规格型号': item.specification || '-',
                            '辅助属性': item.aux_attributes || '-',
                            '物料类型': item.material_type,
                            '销售订单.数量': is07 ? parseFloat(item.sales_order_qty) || 0 : '-',
                            '生产入库单.应收数量': is05 ? parseFloat(item.prod_instock_must_qty) || 0 : '-',
                            '采购订单.数量': is03 ? parseFloat(item.purchase_order_qty) || 0 : '-',
                            '生产领料单.实发数量': (is05 || is03) ? parseFloat(item.pick_actual_qty) || 0 : '-',
                            '生产入库单.实收数量': (is07 || is05) ? parseFloat(item.prod_instock_real_qty) || 0 : '-',
                            '采购订单.累计入库数量': is03 ? parseFloat(item.purchase_stock_in_qty) || 0 : '-',
                            '完成率': rate !== null ? `${(rate * 100).toFixed(0)}%` : '-'
                        };
                    });

                    const ws = XLSX.utils.json_to_sheet(exportData);
                    const wb = XLSX.utils.book_new();
                    XLSX.utils.book_append_sheet(wb, ws, 'BOM组件');

                    // Set column widths
                    ws['!cols'] = [
                        { wch: 6 }, { wch: 15 }, { wch: 20 }, { wch: 15 }, { wch: 20 },
                        { wch: 10 }, { wch: 15 }, { wch: 18 }, { wch: 15 }, { wch: 18 },
                        { wch: 18 }, { wch: 20 }, { wch: 10 }
                    ];

                    XLSX.writeFile(wb, `MTO_${this.mtoNumber}_${this.getTimestamp()}.xlsx`);
                    this.showSuccess('Excel 文件已生成');
                } else {
                    // Fallback to server-side CSV
                    const blob = await api.get(`/export/mto/${encodeURIComponent(this.mtoNumber.trim())}`);
                    const url = window.URL.createObjectURL(blob);
                    const anchor = document.createElement('a');
                    anchor.href = url;
                    anchor.download = `MTO_${this.mtoNumber}_${this.getTimestamp()}.csv`;
                    document.body.appendChild(anchor);
                    anchor.click();
                    window.URL.revokeObjectURL(url);
                    document.body.removeChild(anchor);
                    this.showSuccess('CSV 文件已生成');
                }

                this.showExportMenu = false;
            } catch (err) {
                console.error('Export error:', err);
                this.showError('导出失败: ' + err.message);
            }
        },

        // === Related Orders ===
        async fetchRelatedOrders() {
            if (!this.mtoNumber?.trim()) return;

            this.relatedOrdersLoading = true;
            this.relatedOrdersError = '';

            try {
                const data = await api.get(`/mto/${encodeURIComponent(this.mtoNumber.trim())}/related-orders`);
                this.relatedOrders = data;

                // Refresh icons after related orders load
                if (typeof refreshIcons === 'function') {
                    setTimeout(refreshIcons, 50);
                }
            } catch (err) {
                console.error('Related orders error:', err);
                this.relatedOrdersError = err.message || '关联单据加载失败';
                this.relatedOrders = null;
            } finally {
                this.relatedOrdersLoading = false;
            }
        },

        // === Semantic Metric Helpers ===
        getFulfillmentRate(item) {
            const rate = item.metrics?.fulfillment_rate?.value;
            if (rate === null || rate === undefined) return null;
            return parseFloat(rate);
        },

        formatPercent(value) {
            if (value === null || value === undefined) return '-';
            const num = parseFloat(value);
            if (isNaN(num)) return '-';
            return (num * 100).toFixed(0) + '%';
        },

        getCompletionStatus(item) {
            return item.metrics?.completion_status?.status || null;
        },

        getStatusColor(status) {
            const colors = {
                'completed': 'text-emerald-400',
                'in_progress': 'text-amber-400',
                'warning': 'text-rose-400',
                'not_started': 'text-slate-500'
            };
            return colors[status] || 'text-slate-400';
        },

        getStatusBgColor(status) {
            const colors = {
                'completed': 'bg-emerald-500/15',
                'in_progress': 'bg-amber-500/15',
                'warning': 'bg-rose-500/15',
                'not_started': 'bg-slate-500/10'
            };
            return colors[status] || '';
        },

        // === Utility Methods ===
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
                '成品': 'badge-finished',          // 成品 07.xx
                '自制': 'badge-self-made',         // 自制件 05.xx
                '包材': 'badge-purchased'          // 包材 03.xx
            };

            return badges[type] || 'bg-slate-800 text-slate-400 border border-slate-700';
        },

        hasRelatedOrders() {
            if (!this.relatedOrders) return false;

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
        },

        formatCacheAge() {
            if (!this.cacheAgeSeconds) return '';
            const mins = Math.floor(this.cacheAgeSeconds / 60);
            if (mins < 1) return '刚刚';
            if (mins < 60) return `${mins}分钟前`;
            const hours = Math.floor(mins / 60);
            return `${hours}小时前`;
        },

        // === Chat Methods ===
        async initChat() {
            try {
                const resp = await fetch('/api/chat/status');
                if (resp.ok) {
                    const data = await resp.json();
                    this.chatAvailable = data.available;
                    this.chatModel = data.model || '';
                }
            } catch (e) {
                this.chatAvailable = false;
            }
            // Also check agent chat availability
            try {
                const agentResp = await fetch('/api/agent-chat/status');
                if (agentResp.ok) {
                    const agentData = await agentResp.json();
                    this.agentChatAvailable = agentData.available;
                }
            } catch (e) {
                this.agentChatAvailable = false;
            }
        },

        switchChatMode(mode) {
            if (this.chatMode === mode) return;
            this.chatMode = mode;
            this.clearChat();
        },

        toggleChat() {
            this.chatOpen = !this.chatOpen;
        },

        clearChat() {
            if (this._chatAbort) {
                this._chatAbort.abort();
                this._chatAbort = null;
            }
            this.chatMessages = [];
            this.chatLoading = false;
            this.chatInput = '';
        },

        async sendChat() {
            const text = this.chatInput.trim();
            if (!text || this.chatLoading) return;

            // Add user message
            this.chatMessages.push({ role: 'user', content: text });
            this.chatInput = '';
            this.chatLoading = true;

            // Reset textarea height
            this.$nextTick(() => {
                const ta = this.$el.querySelector('.chat-sidebar textarea');
                if (ta) ta.style.height = 'auto';
            });

            // Build messages payload (keep last N messages)
            const maxHistory = 20;
            const historyMessages = this.chatMessages
                .filter(m => m.role === 'user' || m.role === 'assistant')
                .slice(-maxHistory)
                .map(m => ({ role: m.role, content: m.content }));

            // Build MTO context when we have an active MTO search
            let mtoContext = null;
            if (this.parentItem) {
                mtoContext = {
                    parent_item: { mto_number: this.parentItem.mto_number }
                };
            }

            const body = {
                messages: historyMessages,
                mto_context: mtoContext
            };

            // Add a placeholder assistant message for streaming
            const assistantIdx = this.chatMessages.length;
            this.chatMessages.push({ role: 'assistant', content: '' });

            try {
                const token = localStorage.getItem('token');
                this._chatAbort = new AbortController();
                const chatEndpoint = this.chatMode === 'agent' ? '/api/agent-chat/stream' : '/api/chat/stream';
                const resp = await fetch(chatEndpoint, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                        'Authorization': `Bearer ${token}`
                    },
                    body: JSON.stringify(body),
                    signal: this._chatAbort.signal
                });

                if (!resp.ok) {
                    const errData = await resp.json().catch(() => ({}));
                    throw new Error(errData.detail || `HTTP ${resp.status}`);
                }

                const reader = resp.body.getReader();
                const decoder = new TextDecoder();
                let buffer = '';

                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;

                    buffer += decoder.decode(value, { stream: true });
                    const lines = buffer.split('\n');
                    buffer = lines.pop() || '';

                    for (const line of lines) {
                        if (!line.startsWith('data: ')) continue;
                        const jsonStr = line.slice(6).trim();
                        if (!jsonStr) continue;

                        try {
                            const evt = JSON.parse(jsonStr);
                            if (evt.type === 'token') {
                                this.chatMessages[assistantIdx].content += evt.content;
                                this._scrollChat();
                            } else if (evt.type === 'sql') {
                                this.chatMessages[assistantIdx].sql = evt.query;
                            } else if (evt.type === 'sql_result') {
                                this.chatMessages[assistantIdx].sqlResult = {
                                    columns: evt.columns,
                                    rows: evt.rows,
                                    total_rows: evt.total_rows
                                };
                                this._scrollChat();
                            } else if (evt.type === 'error') {
                                this.chatMessages[assistantIdx].content += '\n\n⚠️ ' + evt.message;
                            } else if (evt.type === 'done') {
                                break;
                            }
                        } catch (parseErr) {
                            // Ignore malformed SSE lines
                        }
                    }
                }
            } catch (err) {
                if (err.name === 'AbortError') return;
                // Show error in the assistant message
                if (this.chatMessages[assistantIdx]) {
                    this.chatMessages[assistantIdx].content = '⚠️ 请求失败: ' + err.message;
                }
            } finally {
                this.chatLoading = false;
                this._chatAbort = null;
                this._scrollChat();
            }
        },

        _scrollChat() {
            this.$nextTick(() => {
                const el = this.$refs.chatMessages;
                if (el) el.scrollTop = el.scrollHeight;
            });
        },

        renderChatContent(text) {
            if (!text) return '';
            // Escape HTML
            let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');
            // Convert MTO numbers to clickable links
            html = html.replace(/\b(AK\d{7,})\b/g,
                '<a class="mto-link" href="javascript:void(0)" onclick="document.dispatchEvent(new CustomEvent(\'chat-mto-click\', {detail: \'$1\'}))">' +
                '$1</a>');
            // Basic markdown: **bold**, newlines
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/\n/g, '<br>');
            return html;
        },

        // === Summary Calculations for Footer ===
        // 使用金蝶原始字段名计算合计
        calculateTotals() {
            const items = this.getSortedItems();
            return {
                // 销售订单.数量 (成品 07.xx)
                sales_order_qty: items.filter(i => i.material_code?.startsWith('07'))
                    .reduce((sum, i) => sum + parseFloat(i.sales_order_qty || 0), 0),
                // 生产入库单.应收数量 (自制件 05.xx)
                prod_instock_must_qty: items.filter(i => i.material_code?.startsWith('05'))
                    .reduce((sum, i) => sum + parseFloat(i.prod_instock_must_qty || 0), 0),
                // 采购订单.数量 (包材 03.xx)
                purchase_order_qty: items.filter(i => i.material_code?.startsWith('03'))
                    .reduce((sum, i) => sum + parseFloat(i.purchase_order_qty || 0), 0),
                // 生产领料单.实发数量 (自制件/包材)
                pick_actual_qty: items.filter(i => ['03', '05'].some(p => i.material_code?.startsWith(p)))
                    .reduce((sum, i) => sum + parseFloat(i.pick_actual_qty || 0), 0),
                // 生产入库单.实收数量 (成品/自制件)
                prod_instock_real_qty: items.filter(i => ['05', '07'].some(p => i.material_code?.startsWith(p)))
                    .reduce((sum, i) => sum + parseFloat(i.prod_instock_real_qty || 0), 0),
                // 采购订单.累计入库数量 (包材)
                purchase_stock_in_qty: items.filter(i => i.material_code?.startsWith('03'))
                    .reduce((sum, i) => sum + parseFloat(i.purchase_stock_in_qty || 0), 0)
            };
        }
    };
}

window.mtoSearch = mtoSearch;
