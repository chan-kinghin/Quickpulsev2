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
            { key: 'purchase_stock_in_qty', label: '采购订单.累计入库数量', width: 150, minWidth: 100, resizable: true, visible: true, sortable: true, locked: false, group: 'blue', materialPrefix: '03' }
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

                // Status filter - 简化版，不再使用计算字段
                // 由于不再计算未领/未入库数量，状态筛选功能暂时禁用
                // 保留代码结构以便未来需要时恢复

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
                    let valA = a[this.sort.column];
                    let valB = b[this.sort.column];

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
        startResize(event, columnIndex) {
            event.preventDefault();
            event.stopPropagation();
            this.resizing = {
                active: true,
                columnIndex,
                startX: event.clientX,
                startWidth: this.columns[columnIndex].width
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
                            '采购订单.累计入库数量': is03 ? parseFloat(item.purchase_stock_in_qty) || 0 : '-'
                        };
                    });

                    const ws = XLSX.utils.json_to_sheet(exportData);
                    const wb = XLSX.utils.book_new();
                    XLSX.utils.book_append_sheet(wb, ws, 'BOM组件');

                    // Set column widths
                    ws['!cols'] = [
                        { wch: 6 }, { wch: 15 }, { wch: 20 }, { wch: 15 }, { wch: 20 },
                        { wch: 10 }, { wch: 15 }, { wch: 18 }, { wch: 15 }, { wch: 18 },
                        { wch: 18 }, { wch: 20 }
                    ];

                    XLSX.writeFile(wb, `MTO_${this.mtoNumber}_${this.getTimestamp()}.xlsx`);
                    this.showSuccess('Excel导出成功');
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
                    this.showSuccess('CSV导出成功');
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
