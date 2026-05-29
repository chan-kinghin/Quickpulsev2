function mtoSearch() {
    return {
        // === Core State ===
        mtoNumber: '',
        parentItem: null,
        childItems: [],
        dataSource: null,      // 'cache' or 'live'
        cacheAgeSeconds: null, // age in seconds when from cache
        loading: false,
        searchPerformed: false,
        error: '',
        successMessage: '',
        isFullScreen: false,
        isCollapsed: false,

        // === Filters ===
        // 物料类型: 成品, 自制, 包材, 委外
        filters: {
            materialTypes: { '成品': false, '自制': false, '包材': false, '委外': false },
            status: 'all', // 保留但简化
            searchText: ''
        },
        showClosedRows: false,

        // === Column Configuration ===
        // 列名直接使用金蝶的"表单.字段名"格式，不做任何计算
        columns: [
            { key: 'index', label: '序号', width: 60, defaultWidth: 60, minWidth: 40, maxWidth: 120, resizable: false, visible: true, sortable: false, locked: true, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'material_code', label: '物料编码', width: 120, defaultWidth: 120, minWidth: 80, maxWidth: 300, resizable: true, visible: true, sortable: true, locked: true, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'material_name', label: '物料名称', width: 150, defaultWidth: 150, minWidth: 100, maxWidth: 500, resizable: true, visible: true, sortable: true, locked: true, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'specification', label: '规格型号', width: 120, defaultWidth: 120, minWidth: 80, maxWidth: 400, resizable: true, visible: true, sortable: true, locked: false, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'bom_short_name', label: 'BOM简称', width: 150, defaultWidth: 150, minWidth: 100, maxWidth: 400, resizable: true, visible: true, sortable: true, locked: false, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'aux_attributes', label: '辅助属性', width: 150, defaultWidth: 150, minWidth: 100, maxWidth: 500, resizable: true, visible: true, sortable: false, locked: false, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'close_status', label: '关闭状态', width: 90, defaultWidth: 90, minWidth: 70, maxWidth: 160, resizable: true, visible: true, sortable: true, locked: false, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'material_type', label: '物料类型', width: 90, defaultWidth: 90, minWidth: 70, maxWidth: 200, resizable: true, visible: true, sortable: true, locked: false, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'material_group_name', label: '物料分组', width: 130, defaultWidth: 130, minWidth: 80, maxWidth: 300, resizable: true, visible: true, sortable: true, locked: false, align: 'left', headerColorClass: 'text-slate-400', borderClasses: '' },
            // 数量列：根据物料类型显示不同来源
            { key: 'sales_order_qty', label: '销售订单.数量', width: 120, defaultWidth: 120, minWidth: 80, maxWidth: 300, resizable: true, visible: true, sortable: true, locked: false, group: 'green', align: 'right', headerColorClass: 'text-slate-400', borderClasses: 'border-l border-slate-700' },
            { key: 'prod_instock_must_qty', label: '生产入库单.应收数量', width: 140, defaultWidth: 140, minWidth: 100, maxWidth: 350, resizable: true, visible: true, sortable: true, locked: false, group: 'green', align: 'right', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'purchase_order_qty', label: '采购/委外订单.数量', width: 130, defaultWidth: 130, minWidth: 80, maxWidth: 300, resizable: true, visible: true, sortable: true, locked: false, group: 'green', align: 'right', headerColorClass: 'text-slate-400', borderClasses: 'border-r border-slate-700' },
            // 领料/入库列
            { key: 'pick_actual_qty', label: '生产领料单.实发数量', width: 140, defaultWidth: 140, minWidth: 100, maxWidth: 350, resizable: true, visible: true, sortable: true, locked: false, group: 'blue', align: 'right', headerColorClass: 'text-slate-400', borderClasses: 'border-l border-slate-700' },
            { key: 'prod_instock_real_qty', label: '生产入库单.实收数量', width: 140, defaultWidth: 140, minWidth: 100, maxWidth: 350, resizable: true, visible: true, sortable: true, locked: false, group: 'blue', align: 'right', headerColorClass: 'text-slate-400', borderClasses: '' },
            { key: 'purchase_stock_in_qty', label: '采购/委外.累计入库数量', width: 160, defaultWidth: 160, minWidth: 100, maxWidth: 400, resizable: true, visible: true, sortable: true, locked: false, group: 'blue', align: 'right', headerColorClass: 'text-slate-400', borderClasses: 'border-r border-slate-700' },
            // 语义层：完成率列（从 metrics 计算得出）
            { key: 'fulfillment_rate', label: '完成率', width: 100, defaultWidth: 100, minWidth: 70, maxWidth: 200, resizable: true, visible: true, sortable: true, locked: false, group: 'semantic', align: 'center', headerColorClass: 'text-slate-400', borderClasses: 'border-l border-slate-700' }
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
        _chatAbort: null,    // AbortController for active stream
        _errorTimer: null,
        _successTimer: null,

        // === Photo Inline Panel State === (shown below the BOM table)
        inlinePhotoOpen: false,
        inlinePhotoFileIds: [],
        inlinePhotoIndex: 0,
        inlinePhotoMaterialName: '',
        inlinePhotoMaterialCode: '',
        // === Photo Lightbox State === (full-screen modal, opened from inline panel)
        photoModalOpen: false,
        photoModalFileIds: [],
        photoModalIndex: 0,
        photoModalMaterialName: '',

        // === Preferences ===
        STORAGE_KEY: 'quickpulse_preferences',
        STORAGE_VERSION: 3,

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

            this._abortController = new AbortController();
            this.setupKeyboardListeners();
            this.setupResizeListeners();
            this.initChat();

            // Register Alpine cleanup
            this.$cleanup = () => this.destroy();
        },

        destroy() {
            if (this._abortController) {
                this._abortController.abort();
                this._abortController = null;
            }
        },

        setupKeyboardListeners() {
            const signal = this._abortController.signal;
            document.addEventListener('keydown', (event) => {
                // Photo modal owns arrow keys + Escape while open
                if (this.photoModalOpen) {
                    if (event.key === 'Escape') {
                        event.preventDefault();
                        this.closePhotoModal();
                        return;
                    }
                    if (event.key === 'ArrowLeft') {
                        event.preventDefault();
                        this.photoModalPrev();
                        return;
                    }
                    if (event.key === 'ArrowRight') {
                        event.preventDefault();
                        this.photoModalNext();
                        return;
                    }
                }
                if (event.key === 'F11' && this.childItems.length > 0) {
                    event.preventDefault();
                    this.toggleFullScreen();
                }
                if (event.key === '/' && !['INPUT', 'TEXTAREA'].includes(document.activeElement.tagName)) {
                    event.preventDefault();
                    document.getElementById('mto-search')?.focus();
                }
            }, { signal });
            // Listen for MTO link clicks from chat messages
            document.addEventListener('chat-mto-click', (event) => {
                const mtoNum = event.detail;
                if (mtoNum) {
                    this.mtoNumber = mtoNum;
                    this.search();
                }
            }, { signal });
        },

        setupResizeListeners() {
            const signal = this._abortController.signal;
            document.addEventListener('mousemove', (e) => this.doResize(e), { signal, passive: true });
            document.addEventListener('mouseup', () => this.stopResize(), { signal });
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

                // Apply close-status toggle
                if (prefs.showClosedRows !== undefined) {
                    this.showClosedRows = prefs.showClosedRows;
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
                    searchHistory: this.searchHistory,
                    showClosedRows: this.showClosedRows
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
                // Close-status filter: hide closed (B) rows by default unless toggle is on
                if (!this.showClosedRows && item.close_status === 'B') return false;

                // Material type filter — all-false means "no filter, show everything"
                const activeTypes = Object.entries(this.filters.materialTypes).filter(([k, v]) => v).map(([k]) => k);
                if (activeTypes.length > 0 && !activeTypes.includes(item.material_type)) return false;

                // Status filter — uses server-computed completion_status from semantic layer
                if (this.filters.status !== 'all' && !item.metrics?.completion_status?.status) return false;
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

        // Note: getSortedItems() is called on every render by Alpine.js.
        // For current data sizes (~100 items) re-sorting is negligible.
        // If datasets grow significantly, consider caching with a dirty flag.
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

        toggleShowClosedRows() {
            this.showClosedRows = !this.showClosedRows;
            this.savePreferences();
        },

        setStatusFilter(status) {
            this.filters.status = status;
            this.savePreferences();
        },

        hasActiveFilters() {
            const anyTypeActive = Object.values(this.filters.materialTypes).some(v => v);
            return anyTypeActive || this.filters.status !== 'all' || this.filters.searchText.length > 0;
        },

        resetFilters() {
            this.filters.materialTypes = { '成品': false, '自制': false, '包材': false, '委外': false };
            this.filters.status = 'all';
            this.filters.searchText = '';
            this.savePreferences();
        },

        getActiveFilterCount() {
            let count = 0;
            if (Object.values(this.filters.materialTypes).some(v => v)) count++;
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

            // Find next visible resizable neighbor for proportional resize
            let neighborIndex = null;
            let neighborStartWidth = 0;
            for (let i = colIndex + 1; i < this.columns.length; i++) {
                if (this.columns[i].visible && this.columns[i].resizable) {
                    neighborIndex = i;
                    neighborStartWidth = this.columns[i].width;
                    break;
                }
            }

            this.resizing = {
                active: true,
                columnIndex: colIndex,
                startX: event.clientX,
                startWidth: this.columns[colIndex].width,
                neighborIndex,
                neighborStartWidth
            };
            document.body.style.cursor = 'col-resize';
            document.body.style.userSelect = 'none';

            // Create visual guide line
            this._guideLine = document.createElement('div');
            this._guideLine.className = 'resize-guide-line';
            this._guideLine.style.left = event.clientX + 'px';
            document.body.appendChild(this._guideLine);
        },

        doResize(event) {
            if (!this.resizing.active) return;
            const diff = event.clientX - this.resizing.startX;
            const col = this.columns[this.resizing.columnIndex];
            const newWidth = this.resizing.startWidth + diff;
            const clampedWidth = Math.min(col.maxWidth, Math.max(col.minWidth, newWidth));

            // Shift+drag: proportional resize (shrink neighbor to keep total width constant)
            if (event.shiftKey && this.resizing.neighborIndex !== null) {
                const neighbor = this.columns[this.resizing.neighborIndex];
                const totalWidth = this.resizing.startWidth + this.resizing.neighborStartWidth;
                const neighborWidth = totalWidth - clampedWidth;
                if (neighborWidth >= neighbor.minWidth && neighborWidth <= neighbor.maxWidth) {
                    col.width = clampedWidth;
                    neighbor.width = neighborWidth;
                } else {
                    col.width = clampedWidth;
                }
            } else {
                col.width = clampedWidth;
            }

            // Update guide line position
            if (this._guideLine) {
                this._guideLine.style.left = event.clientX + 'px';
            }
        },

        stopResize() {
            if (!this.resizing.active) return;
            this.resizing.active = false;
            document.body.style.cursor = '';
            document.body.style.userSelect = '';

            // Remove guide line
            if (this._guideLine) {
                this._guideLine.remove();
                this._guideLine = null;
            }

            this.savePreferences();
        },

        getColumnStyle(columnKey) {
            const col = this.columns.find(c => c.key === columnKey);
            return col ? `width: ${col.width}px; min-width: ${col.minWidth}px; max-width: ${col.maxWidth}px; overflow: hidden; text-overflow: ellipsis;` : '';
        },

        // Double-click resize handle to auto-fit column width to content
        autoFitColumn(columnKey) {
            const col = this.columns.find(c => c.key === columnKey);
            if (!col || !col.resizable) return;

            // Find the table and measure content widths
            const table = document.querySelector('.bom-table table');
            if (!table) return;

            const colIndex = this.getVisibleColumns().findIndex(c => c.key === columnKey);
            if (colIndex === -1) return;

            // Measure header text width
            const headerCells = table.querySelectorAll('thead th:not(.col-hidden)');
            let maxWidth = 0;

            // Create off-screen measurement element
            const measurer = document.createElement('span');
            measurer.style.cssText = 'position:absolute;visibility:hidden;white-space:nowrap;font:inherit;';
            document.body.appendChild(measurer);

            // Measure header
            if (headerCells[colIndex]) {
                const headerText = headerCells[colIndex].textContent.trim();
                measurer.style.fontWeight = '500';
                measurer.style.fontSize = '0.875rem';
                measurer.textContent = headerText;
                maxWidth = measurer.offsetWidth;
            }

            // Measure body cells
            const rows = table.querySelectorAll('tbody tr');
            measurer.style.fontWeight = 'normal';
            rows.forEach(row => {
                const cells = row.querySelectorAll('td:not(.col-hidden)');
                if (cells[colIndex]) {
                    measurer.textContent = cells[colIndex].textContent.trim();
                    maxWidth = Math.max(maxWidth, measurer.offsetWidth);
                }
            });

            document.body.removeChild(measurer);

            // Add padding (px-4 = 32px both sides) + sort icon space
            const padding = 48;
            const fitWidth = Math.min(col.maxWidth, Math.max(col.minWidth, maxWidth + padding));
            col.width = fitWidth;
            this.savePreferences();
        },

        // Reset all column widths to defaults
        resetColumnWidths() {
            this.columns.forEach(col => {
                col.width = col.defaultWidth;
            });
            this.savePreferences();
        },

        // Keyboard-based column resize: ←/→ = 10px, Shift+←/→ = 50px
        resizeColumnByKeyboard(event, columnKey) {
            if (event.key !== 'ArrowLeft' && event.key !== 'ArrowRight') return;
            const col = this.columns.find(c => c.key === columnKey);
            if (!col || !col.resizable) return;

            event.preventDefault();
            const step = event.shiftKey ? 50 : 10;
            const delta = event.key === 'ArrowRight' ? step : -step;
            col.width = Math.min(col.maxWidth, Math.max(col.minWidth, col.width + delta));
            this.savePreferences();
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

            const input = this.mtoNumber.trim();

            // Detect natural language queries (not MTO numbers)
            // MTO pattern: 2+ uppercase letters followed by 5+ digits, optionally with suffix
            const isMtoNumber = /^[A-Za-z]{2}\d{5,}/.test(input);
            if (!isMtoNumber) {
                // Route to chat panel with the NL query
                if (!this.chatOpen) this.chatOpen = true;
                this.chatInput = input;
                this.mtoNumber = '';
                await this.$nextTick();
                this.sendChat();
                return;
            }

            // Add to history
            this.addToSearchHistory(input);

            this.clearMessages();
            this.parentItem = null;
            this.childItems = [];
            this.dataSource = null;
            this.cacheAgeSeconds = null;
            this.closePhotoPanel();
            this.loading = true;

            try {
                const data = await api.get(`/mto/${encodeURIComponent(this.mtoNumber.trim())}`);

                this.parentItem = data.parent_item || null;
                this.childItems = data.child_items || [];
                this.dataSource = data.data_source || 'live';
                this.cacheAgeSeconds = data.cache_age_seconds ?? null;

                this.successMessage = `成功查询到 ${this.childItems.length} 条BOM组件记录`;
                clearTimeout(this._successTimer);
                this._successTimer = setTimeout(() => {
                    this.successMessage = '';
                }, 3000);

                // Refresh icons after data loads
                if (typeof refreshIcons === 'function') {
                    setTimeout(refreshIcons, 50);
                }

                const newUrl = `${window.location.pathname}?mto=${encodeURIComponent(this.mtoNumber.trim())}`;
                if (window.location.search !== '?mto=' + encodeURIComponent(this.mtoNumber.trim())) {
                    window.history.pushState({}, '', newUrl);
                }

            } catch (err) {
                console.error('Search error:', err);
                const msg = typeof err.message === 'string' ? err.message : JSON.stringify(err.message);
                this.showError(msg || '查询失败，请稍后重试');
            } finally {
                this.loading = false;
                this.searchPerformed = true;
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
                    // 使用物料类型字段控制列显示
                    const exportData = items.map((item, index) => {
                        const isFinished = item.is_finished_goods;
                        const typeCode = item.material_type_code;
                        const isSelfMade = typeCode === 1 && !isFinished;
                        const isPurchasedOrSubcontract = typeCode === 2 || typeCode === 3;

                        const rate = this.getFulfillmentRate(item);
                        return {
                            '序号': index + 1,
                            '物料编码': item.material_code || '',
                            '物料名称': item.material_name,
                            '规格型号': item.specification || '-',
                            'BOM简称': isFinished ? (item.bom_short_name || '-') : '-',
                            '辅助属性': item.aux_attributes || '-',
                            '物料类型': item.material_type,
                            '销售订单.数量': isFinished ? parseFloat(item.sales_order_qty) || 0 : '-',
                            '生产入库单.应收数量': isSelfMade ? parseFloat(item.prod_instock_must_qty) || 0 : '-',
                            '采购/委外订单.数量': isPurchasedOrSubcontract ? parseFloat(item.purchase_order_qty) || 0 : '-',
                            '生产领料单.实发数量': !isFinished ? parseFloat(item.pick_actual_qty) || 0 : '-',
                            '生产入库单.实收数量': typeCode === 1 ? parseFloat(item.prod_instock_real_qty) || 0 : '-',
                            '采购/委外.累计入库数量': isPurchasedOrSubcontract ? parseFloat(item.purchase_stock_in_qty) || 0 : '-',
                            '完成率': rate !== null ? `${(rate * 100).toFixed(0)}%` : '-'
                        };
                    });

                    const ws = XLSX.utils.json_to_sheet(exportData);
                    const wb = XLSX.utils.book_new();
                    XLSX.utils.book_append_sheet(wb, ws, 'BOM组件');

                    // Set column widths
                    ws['!cols'] = [
                        { wch: 6 }, { wch: 15 }, { wch: 20 }, { wch: 15 }, { wch: 15 },
                        { wch: 20 }, { wch: 10 }, { wch: 15 }, { wch: 18 }, { wch: 15 },
                        { wch: 18 }, { wch: 18 }, { wch: 20 }, { wch: 10 }
                    ];

                    XLSX.writeFile(wb, `MTO_${this.mtoNumber}_${this.getTimestamp()}.xlsx`);
                    this.showSuccess('Excel 文件已生成');
                } else {
                    // Fallback to server-side CSV
                    const blob = await api.get(`/export/mto/${encodeURIComponent(this.mtoNumber.trim())}`);
                    if (!(blob instanceof Blob)) {
                        throw new Error(blob?.detail || 'Export failed');
                    }
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
                return '-';
            }
            if (value === 0) return '0';

            const num = parseFloat(value);
            if (isNaN(num)) {
                return '-';
            }

            return num % 1 === 0
                ? num.toLocaleString('zh-CN')
                : num.toLocaleString('zh-CN', { minimumFractionDigits: 2, maximumFractionDigits: 2 });
        },

        getMaterialTypeBadge(type) {
            const badges = {
                '成品': 'badge-finished',
                '自制': 'badge-self-made',
                '包材': 'badge-purchased',
                '委外': 'badge-subcontract'
            };

            return badges[type] || 'bg-slate-800 text-slate-400 border border-slate-700';
        },

        // Returns a tooltip string when any source for this row was resolved via an
        // aux-property fallback (the SQL/live 3-tier match logic). Empty string ⇒
        // no badge shown. Used by the ⚠ marker next to material_code.
        getAuxFallbackTooltip(item) {
            const breakdown = item && item.match_quality_breakdown;
            if (!breakdown) return '';
            const sourceLabels = {
                prod_receipt: '生产入库',
                pick: '生产领料',
                purchase_order: '采购订单',
                purchase_receipt: '采购入库',
                subcontract: '委外订单',
                delivery: '销售出库',
            };
            const tierLabels = {
                aux_zero_fallback: '辅助属性=0回落',
                all_aux_rollup: '汇总所有辅助属性变体',
            };
            const lines = [];
            for (const [source, tier] of Object.entries(breakdown)) {
                if (tier in tierLabels) {
                    lines.push(`${sourceLabels[source] || source}: ${tierLabels[tier]}`);
                }
            }
            if (lines.length === 0) return '';
            return '⚠ 数量按辅助属性回落估算：\n' + lines.join('\n');
        },

        showError(message) {
            this.error = message;
            this.successMessage = '';
            clearTimeout(this._errorTimer);
            this._errorTimer = setTimeout(() => {
                this.error = '';
            }, 5000);
        },

        showSuccess(message) {
            this.successMessage = message;
            this.error = '';
            clearTimeout(this._successTimer);
            this._successTimer = setTimeout(() => {
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

        // === Photo Inline Panel Methods === (shown below the BOM table)
        // /api/photo/{file_id} accepts the access_token cookie set on login,
        // so plain <img src="/api/photo/{id}"> works and benefits from the
        // browser's HTTP cache (backend returns immutable, max-age=1y).
        //
        // Photos live on PRD_MO.TreeEntity.F_QWJI_YSTP1/2/3 — production-order
        // level, not material level. In single-parent MTOs every BOM row carries
        // the same set, so showing a per-row badge is visual noise. Surface
        // photos once at the MTO/parent header instead. This getter deduplicates
        // across the union of children for the multi-parent edge case where
        // different PRD_MOs in one MTO contribute different photos.
        get parentPhotoFileIds() {
            if (!this.childItems || this.childItems.length === 0) return [];
            const seen = new Set();
            for (const c of this.childItems) {
                const ids = c.photo_file_ids;
                if (!Array.isArray(ids)) continue;
                for (const id of ids) {
                    if (id) seen.add(id);
                }
            }
            return [...seen];
        },

        // Triggered from the photo button in the parent info bar.
        openParentPhotoPanel() {
            const ids = this.parentPhotoFileIds;
            if (ids.length === 0) return;
            this.inlinePhotoFileIds = ids;
            this.inlinePhotoIndex = 0;
            this.inlinePhotoMaterialName = `MTO ${this.parentItem?.mto_number || ''}`;
            this.inlinePhotoMaterialCode = '';
            this.inlinePhotoOpen = true;
            this.$nextTick(() => {
                document.querySelector('[data-testid="photo-inline-panel"]')
                    ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            });
        },

        openPhotoPanel(child) {
            if (!child.photo_file_ids || child.photo_file_ids.length === 0) return;
            this.inlinePhotoFileIds = child.photo_file_ids;
            this.inlinePhotoIndex = 0;
            this.inlinePhotoMaterialName = child.material_name || '';
            this.inlinePhotoMaterialCode = child.material_code || '';
            this.inlinePhotoOpen = true;
            this.$nextTick(() => {
                document.querySelector('[data-testid="photo-inline-panel"]')
                    ?.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            });
        },

        closePhotoPanel() {
            this.inlinePhotoOpen = false;
            this.inlinePhotoFileIds = [];
            this.inlinePhotoIndex = 0;
            this.inlinePhotoMaterialName = '';
            this.inlinePhotoMaterialCode = '';
        },

        inlinePhotoNext() {
            if (this.inlinePhotoIndex < this.inlinePhotoFileIds.length - 1) {
                this.inlinePhotoIndex++;
            }
        },

        inlinePhotoPrev() {
            if (this.inlinePhotoIndex > 0) {
                this.inlinePhotoIndex--;
            }
        },

        // Open the full-screen lightbox from the inline panel, starting at the
        // currently-displayed photo.
        openPhotoLightboxFromInline() {
            if (this.inlinePhotoFileIds.length === 0) return;
            this.photoModalFileIds = this.inlinePhotoFileIds;
            this.photoModalIndex = this.inlinePhotoIndex;
            this.photoModalMaterialName = this.inlinePhotoMaterialName;
            this.photoModalOpen = true;
        },

        // === Photo Lightbox (full-screen modal) Methods ===
        closePhotoModal() {
            this.photoModalOpen = false;
            this.photoModalFileIds = [];
            this.photoModalIndex = 0;
            this.photoModalMaterialName = '';
        },

        photoModalNext() {
            if (this.photoModalIndex < this.photoModalFileIds.length - 1) {
                this.photoModalIndex++;
            }
        },

        photoModalPrev() {
            if (this.photoModalIndex > 0) {
                this.photoModalIndex--;
            }
        },

        photoUrl(fileId) {
            return fileId ? `/api/photo/${fileId}` : '';
        },

        // === Chat Methods ===
        async initChat() {
            // Delegated click listener for MTO links in chat messages
            const signal = this._abortController?.signal;
            document.addEventListener('click', (e) => {
                const el = e.target.closest('.chat-mto-link');
                if (el) document.dispatchEvent(new CustomEvent('chat-mto-click', {detail: el.dataset.mto}));
            }, signal ? { signal } : undefined);
            const token = localStorage.getItem('token');
            const authHeaders = token ? { 'Authorization': `Bearer ${token}` } : {};
            try {
                const agentResp = await fetch('/api/agent-chat/status', { headers: authHeaders });
                if (agentResp.ok) {
                    const agentData = await agentResp.json();
                    this.chatAvailable = !!agentData.available;
                    this.chatModel = agentData.model || '';
                }
            } catch (e) {
                this.chatAvailable = false;
            }
        },

        toggleChat() {
            this.chatOpen = !this.chatOpen;
            if (this.chatOpen) {
                this.showExportMenu = false;
                this.showColumnSettings = false;
                this._previousFocus = document.activeElement;
            } else if (this._previousFocus) {
                this._previousFocus.focus();
                this._previousFocus = null;
            }
        },

        trapFocusInChat(e) {
            if (e.key !== 'Tab') return;
            const sidebar = e.currentTarget;
            if (!sidebar) return;
            const focusable = sidebar.querySelectorAll('button, input, textarea, select, [tabindex]:not([tabindex="-1"])');
            if (focusable.length === 0) return;
            const first = focusable[0];
            const last = focusable[focusable.length - 1];
            if (e.shiftKey && document.activeElement === first) {
                e.preventDefault();
                last.focus();
            } else if (!e.shiftKey && document.activeElement === last) {
                e.preventDefault();
                first.focus();
            }
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
                const resp = await fetch('/api/agent-chat/stream', {
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
                let streamDone = false;

                while (!streamDone) {
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
                                streamDone = true;
                                break;
                            }
                        } catch (parseErr) {
                            // Ignore malformed SSE lines
                        }
                    }
                }
            } catch (err) {
                if (err.name === 'AbortError') return;
                // Show error in the assistant message with retry option
                if (this.chatMessages[assistantIdx]) {
                    this.chatMessages[assistantIdx].content = '⚠️ 请求失败: ' + err.message;
                    this.chatMessages[assistantIdx].hasError = true;
                }
            } finally {
                this.chatLoading = false;
                this._chatAbort = null;
                this._scrollChat();
            }
        },

        retryLastChat() {
            // Find last user message and re-send it
            const lastUserMsg = [...this.chatMessages].reverse().find(m => m.role === 'user');
            if (!lastUserMsg) return;

            // Remove the failed assistant message
            const lastIdx = this.chatMessages.length - 1;
            if (this.chatMessages[lastIdx]?.hasError) {
                this.chatMessages.pop();
            }

            // Re-send the last user message
            this.chatInput = lastUserMsg.content;
            // Remove the last user message so sendChat re-adds it
            const userIdx = this.chatMessages.lastIndexOf(lastUserMsg);
            if (userIdx >= 0) this.chatMessages.splice(userIdx, 1);
            this.sendChat();
        },

        _scrollChat() {
            this.$nextTick(() => {
                const el = this.$refs.chatMessages;
                if (el) el.scrollTop = el.scrollHeight;
            });
        },

        renderChatContent(text) {
            if (!text) return '';
            // Escape HTML (including quotes for attribute safety)
            let html = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;').replace(/'/g, '&#39;');
            // Convert MTO numbers to clickable links (delegated event, no inline handler)
            html = html.replace(/\b([A-Z]{2}\d{5,}[A-Za-z]?)\b/g,
                '<span class="chat-mto-link cursor-pointer text-emerald-400 hover:underline" data-mto="$1">$1</span>');
            // Basic markdown: **bold**, newlines
            html = html.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            html = html.replace(/\n/g, '<br>');
            return html;
        },

        // === Summary Calculations for Footer ===
        // 使用物料类型字段计算合计
        calculateTotals() {
            const items = this.getSortedItems();
            return {
                // 销售订单.数量 (成品)
                sales_order_qty: items.filter(i => i.is_finished_goods)
                    .reduce((sum, i) => sum + parseFloat(i.sales_order_qty || 0), 0),
                // 生产入库单.应收数量 (自制件, type=1 非成品)
                prod_instock_must_qty: items.filter(i => i.material_type_code === 1 && !i.is_finished_goods)
                    .reduce((sum, i) => sum + parseFloat(i.prod_instock_must_qty || 0), 0),
                // 采购/委外订单.数量 (外购 type=2 / 委外 type=3)
                purchase_order_qty: items.filter(i => i.material_type_code === 2 || i.material_type_code === 3)
                    .reduce((sum, i) => sum + parseFloat(i.purchase_order_qty || 0), 0),
                // 生产领料单.实发数量 (非成品)
                pick_actual_qty: items.filter(i => !i.is_finished_goods)
                    .reduce((sum, i) => sum + parseFloat(i.pick_actual_qty || 0), 0),
                // 生产入库单.实收数量 (type=1: 成品+自制件)
                prod_instock_real_qty: items.filter(i => i.material_type_code === 1)
                    .reduce((sum, i) => sum + parseFloat(i.prod_instock_real_qty || 0), 0),
                // 采购/委外.累计入库数量 (外购 type=2 / 委外 type=3)
                purchase_stock_in_qty: items.filter(i => i.material_type_code === 2 || i.material_type_code === 3)
                    .reduce((sum, i) => sum + parseFloat(i.purchase_stock_in_qty || 0), 0)
            };
        }
    };
}

window.mtoSearch = mtoSearch;
