// IOC Management Dashboard Application

// ==================== State ====================
let currentComponents = [];
let currentPlugins = [];
let discoveredPlugins = [];
let currentLogs = [];
let configTargets = [];
let originalConfigValues = {};  // Track original values to detect changes
let secretFields = new Set();   // Track which fields are secrets
let ws = null;
let reconnectAttempts = 0;
let selectedComponent = null;
let currentPanelItem = null;
let currentConfigPrefix = null;  // Track current config prefix for multiple configs
let currentConfigs = [];         // Array of config objects for current item
let treeNodeIdCounter = 0;

// ==================== Tab Switching ====================
function switchTab(tabName) {
    document.querySelectorAll('.tab-btn').forEach(btn => btn.classList.remove('active'));
    document.querySelectorAll('.tab-content').forEach(content => content.classList.remove('active'));

    document.querySelector(`[onclick="switchTab('${tabName}')"]`).classList.add('active');
    document.getElementById(`tab-${tabName}`).classList.add('active');
}

// ==================== WebSocket Connection ====================
function connectWebSocket() {
    const wsUrl = `ws://${location.hostname}:8091`;
    updateConnectionStatus('connecting');

    try {
        ws = new WebSocket(wsUrl);

        ws.onopen = () => {
            updateConnectionStatus('connected');
            reconnectAttempts = 0;
            requestRefresh();
            requestLogs();
        };

        ws.onclose = () => {
            updateConnectionStatus('disconnected');
            setTimeout(() => {
                reconnectAttempts++;
                connectWebSocket();
            }, Math.min(1000 * Math.pow(2, reconnectAttempts), 30000));
        };

        ws.onerror = () => updateConnectionStatus('disconnected');

        ws.onmessage = (event) => {
            try {
                const data = JSON.parse(event.data);
                handleMessage(data);
            } catch (e) {
                console.error('Failed to parse message:', e);
            }
        };
    } catch (e) {
        updateConnectionStatus('disconnected');
    }
}

function updateConnectionStatus(status) {
    const el = document.getElementById('connectionStatus');
    el.className = 'connection-status ' + status;
    const dot = el.querySelector('.status-dot');
    dot.className = 'status-dot ' + status;

    const labels = { connected: 'Connected', disconnected: 'Disconnected', connecting: 'Connecting...' };
    el.querySelector('span:last-child').textContent = labels[status] || status;
}

function handleMessage(data) {
    switch (data.type) {
        case 'full_state':
            currentComponents = data.components || [];
            currentPlugins = data.plugins || [];
            discoveredPlugins = data.discovered_plugins || [];
            configTargets = (data.state && data.state.config_targets) || [];
            updateTopPanel();
            updateConfigTargetDropdown();
            renderAllSections();
            renderDiscoveredPlugins();
            // Refresh pot components list if pot browser is open
            refreshSelectedPotComponents();
            // Auto-select app if nothing selected
            if (!selectedComponent) {
                const apps = currentComponents.filter(c => c.type === 'app');
                if (apps.length > 0) {
                    selectComponent(apps[0].name);
                }
            } else {
                // Refresh current selection
                selectComponent(selectedComponent);
            }
            break;
        case 'component_update':
            if (data.component) {
                const idx = currentComponents.findIndex(c => c.name === data.component.name);
                if (idx >= 0) currentComponents[idx] = data.component;
                else currentComponents.push(data.component);
                renderAllSections(data.component.name);
                if (selectedComponent === data.component.name) {
                    selectComponent(selectedComponent);
                }
            }
            break;
        case 'logs_history':
            currentLogs = data.logs || [];
            renderLogs();
            break;
        case 'log':
            addLogEntry(data.entry);
            break;
        case 'logs_cleared':
            currentLogs = [];
            renderLogs();
            break;
        case 'success':
            // Handle pot browser responses
            if (data.pots !== undefined) {
                handlePotsResponse(data);
                break;
            }
            if (data.pot_name !== undefined && data.components !== undefined) {
                handlePotComponentsResponse(data);
                break;
            }
            showToast(data.message, 'success');
            // After successful save, update original values with the saved values
            // so subsequent saves only track new changes
            if (data.message && data.message.includes('Saved') && data.message.includes('field')) {
                updateOriginalConfigAfterSave();
            }
            break;
        case 'error':
        case 'info':
            showToast(data.message || data.error, data.type);
            break;
    }
}

function updateTopPanel() {
    const app = currentComponents.find(c => c.type === 'app');
    if (app) {
        document.getElementById('appName').textContent = app.name;
        document.getElementById('appVersion').textContent = 'v' + (app.version || '?');
    }

    document.getElementById('statComponents').textContent = currentComponents.length;
    document.getElementById('statPlugins').textContent = currentPlugins.length;
}

function requestRefresh() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'refresh' }));
    }
}

function requestLogs() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'get_logs' }));
    }
}

// ==================== Helper Functions ====================
function escapeHtml(text) {
    if (text === undefined || text === null) return '';
    const div = document.createElement('div');
    div.textContent = String(text);
    return div.innerHTML;
}

function escapeJs(text) {
    if (text === undefined || text === null) return '';
    return String(text).replace(/\\/g, '\\\\').replace(/'/g, "\\'").replace(/"/g, '\\"');
}

function getStatusClass(item) {
    if (!item.state) return 'inactive';
    if (item.state.is_shutting_down) return 'shutting_down';
    if (item.state.is_initializing) return 'initializing';
    return item.state.is_initialized ? 'active' : 'inactive';
}

function getStatusLabel(item) {
    if (!item.state) return 'Inactive';
    if (item.state.is_shutting_down) return 'Stopping';
    if (item.state.is_initializing) return 'Starting';
    return item.state.is_initialized ? 'Active' : 'Inactive';
}

// ==================== Component List Rendering ====================
function getAllItemsCombined() {
    const combinedMap = new Map();
    (currentComponents || []).forEach(c => combinedMap.set(c.name, Object.assign({ _kind: 'component' }, c)));
    (currentPlugins || []).forEach(p => combinedMap.set(p.name, Object.assign({ _kind: 'plugin' }, p)));
    return Array.from(combinedMap.values()).sort((a, b) => a.name.localeCompare(b.name));
}

function applyFilters(items) {
    const nameSearch = (document.getElementById('itemSearch')?.value || '').toLowerCase().trim();
    const statusFilter = (document.getElementById('itemStatus')?.value || '').toLowerCase();

    return items.filter(item => {
        if (nameSearch && !item.name.toLowerCase().includes(nameSearch)) return false;
        if (statusFilter) {
            const isActive = !!(item.state && item.state.is_initialized);
            if (statusFilter === 'enabled' && !isActive) return false;
            if (statusFilter === 'disabled' && isActive) return false;
        }
        return true;
    });
}

function getItemsByCategory() {
    const all = getAllItemsCombined();
    const filtered = applyFilters(all);

    const apps = filtered.filter(item => String(item.type || '').toLowerCase() === 'app');
    const libraries = filtered.filter(item => String(item.type || '').toLowerCase() === 'library');
    const plugins = filtered.filter(item => item._kind === 'plugin');

    return { apps, libraries, plugins };
}

function renderComponentCard(item, highlightName) {
    const statusClass = getStatusClass(item);
    const statusLabel = getStatusLabel(item);
    const isSelected = selectedComponent === item.name;
    const isActive = item.state && item.state.is_initialized;
    const highlight = item.name === highlightName ? 'state-change' : '';

    return `
        <div class="component-card ${isSelected ? 'selected' : ''} ${isActive ? '' : 'disabled'} ${highlight}"
             data-name="${escapeHtml(item.name)}" onclick="selectComponent('${escapeJs(item.name)}')">
            <div class="component-card-header">
                <div>
                    <div class="component-card-name">${escapeHtml(item.name)}</div>
                    <div class="component-card-version">v${escapeHtml(item.version || '')}</div>
                </div>
                <span class="component-card-status ${statusClass}">${statusLabel}</span>
            </div>
        </div>
    `;
}

function renderSection(containerId, items, highlightName) {
    const container = document.getElementById(containerId);
    if (!container) return;

    if (items.length === 0) {
        container.innerHTML = '<div style="color:#666;font-size:0.85em;padding:8px;">No items</div>';
        return;
    }

    container.innerHTML = items.map(item => renderComponentCard(item, highlightName)).join('');

    if (highlightName) {
        setTimeout(() => {
            const el = container.querySelector(`[data-name="${highlightName}"]`);
            if (el) el.classList.remove('state-change');
        }, 600);
    }
}

function renderAllSections(highlightName = null) {
    const { apps, libraries, plugins } = getItemsByCategory();

    renderSection('appSection', apps, highlightName);
    renderSection('librariesSection', libraries, highlightName);
    renderSection('pluginsSection', plugins, highlightName);

    // Update counts
    document.getElementById('appCount').textContent = apps.length;
    document.getElementById('libCount').textContent = libraries.length;
    document.getElementById('pluginCount').textContent = plugins.length;
}

function renderDiscoveredPlugins() {
    const container = document.getElementById('discoveredSection');
    const header = document.getElementById('discoveredHeader');
    const countEl = document.getElementById('discoveredCount');

    if (!container || !header) return;

    if (discoveredPlugins.length === 0) {
        header.style.display = 'none';
        container.innerHTML = '';
        return;
    }

    header.style.display = 'flex';
    countEl.textContent = discoveredPlugins.length;

    container.innerHTML = discoveredPlugins.map(plugin => {
        const classes = plugin.component_classes || [];
        const hasModuleMeta = plugin.has_module_metadata || false;
        const hasClasses = classes.length > 0;

        // Build registration options
        let registrationOptionsHtml = '';

        if (hasClasses || hasModuleMeta) {
            // Show dropdown for multiple registration options
            registrationOptionsHtml = `
                <div style="margin-top:8px;">
                    <div style="color:#888;font-size:0.7em;margin-bottom:4px;text-transform:uppercase;">Register as:</div>
                    <div style="display:flex;flex-direction:column;gap:4px;">
                        ${hasModuleMeta ? `
                            <div style="display:flex;align-items:center;gap:6px;">
                                <button class="btn btn-enable" style="font-size:0.72em;padding:4px 8px;flex:1;"
                                        onclick="registerDiscoveredPlugin('${escapeJs(plugin.path)}', null)">
                                    Module (legacy)
                                </button>
                            </div>
                        ` : ''}
                        ${classes.map(cls => `
                            <div style="display:flex;align-items:center;gap:6px;">
                                <button class="btn btn-enable" style="font-size:0.72em;padding:4px 8px;flex:1;"
                                        onclick="registerDiscoveredPlugin('${escapeJs(plugin.path)}', '${escapeJs(cls.class_name)}')">
                                    ${escapeHtml(cls.class_name)}${cls.metadata_name ? ` (${escapeHtml(cls.metadata_name)})` : ''}
                                </button>
                            </div>
                        `).join('')}
                    </div>
                </div>
            `;
        } else {
            // No classes or module metadata found - show warning
            registrationOptionsHtml = `
                <div style="margin-top:8px;">
                    <div style="color:#ff9800;font-size:0.7em;margin-bottom:6px;padding:6px;background:rgba(255,152,0,0.1);border-radius:4px;">
                        No component classes detected. The module may have import errors or use a non-standard pattern.
                    </div>
                    <div style="display:flex;gap:6px;">
                        <button class="btn btn-secondary" style="font-size:0.75em;padding:4px 10px;"
                                onclick="registerDiscoveredPlugin('${escapeJs(plugin.path)}', null)">Try Register Module</button>
                    </div>
                </div>
            `;
        }

        // Build component classes info display
        let classesInfoHtml = '';
        if (hasClasses) {
            classesInfoHtml = `
                <div style="margin-top:4px;color:#00d9ff;font-size:0.7em;">
                    ${classes.length} component class${classes.length > 1 ? 'es' : ''} found
                </div>
            `;
        }

        return `
            <div class="component-card discovered" style="border-left: 3px solid #ff9800;">
                <div class="component-card-header">
                    <div>
                        <div class="component-card-name">${escapeHtml(plugin.name)}</div>
                        <div class="component-card-version" style="color:#ff9800;">
                            ${plugin.is_directory ? 'Directory' : 'File'}
                        </div>
                        ${classesInfoHtml}
                    </div>
                    <span class="component-card-status" style="background:#ff9800;color:#000;">Not Registered</span>
                </div>
                ${registrationOptionsHtml}
                <div style="margin-top:6px;padding-top:6px;border-top:1px solid rgba(255,255,255,0.06);">
                    <button class="btn btn-danger" style="font-size:0.7em;padding:3px 8px;"
                            onclick="removeDiscoveredPlugin('${escapeJs(plugin.path)}', '${escapeJs(plugin.name)}')">Remove from disk</button>
                </div>
            </div>
        `;
    }).join('');
}

function registerDiscoveredPlugin(path, classReference) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        showToast('Not connected', 'error');
        return;
    }
    const message = { action: 'register_plugin', path: path };
    if (classReference) {
        message.class_reference = classReference;
    }
    ws.send(JSON.stringify(message));
    showToast(classReference ? `Registering ${classReference}...` : 'Registering plugin...', 'info');
}

function removeDiscoveredPlugin(path, name) {
    if (!ws || ws.readyState !== WebSocket.OPEN) {
        showToast('Not connected', 'error');
        return;
    }
    if (confirm(`Are you sure you want to remove "${name}" from disk? This cannot be undone.`)) {
        ws.send(JSON.stringify({ action: 'remove_plugin', path: path }));
        showToast('Removing plugin...', 'info');
    }
}

function clearItemFilters() {
    document.getElementById('itemSearch').value = '';
    document.getElementById('itemStatus').value = '';
    renderAllSections();
}

// ==================== Component Selection and Details ====================
function findItemByName(name) {
    if (!name) return null;
    const all = getAllItemsCombined();
    return all.find(i => i.name === name) || null;
}

function selectComponent(name) {
    selectedComponent = name;
    const item = findItemByName(name);
    if (item) {
        populateDetailsPanel(item);
    }
    renderAllSections();
}

function populateDetailsPanel(item) {
    currentPanelItem = item;

    document.getElementById('panelTitle').textContent = item.name;
    document.getElementById('panelVersion').textContent = 'v' + (item.version || '');
    document.getElementById('panelDesc').textContent = item.description || 'No description available.';
    document.getElementById('panelKind').textContent = item._kind ? item._kind.charAt(0).toUpperCase() + item._kind.slice(1) : '-';
    document.getElementById('panelType').textContent = item.type ? item.type.charAt(0).toUpperCase() + item.type.slice(1) : '-';

    const statusEl = document.getElementById('panelStatus');
    statusEl.innerHTML = `<span class="status ${getStatusClass(item)}">${getStatusLabel(item)}</span>`;

    // Internals
    const internals = item.internals || {};
    document.getElementById('panelWire').textContent = internals.wire ? 'Yes' : 'No';

    // Dependencies
    const depsContainer = document.getElementById('panelDependencies');
    let depsHtml = '';

    const clickableBadge = (name, badgeClass) =>
        `<span class="type-badge ${badgeClass}" style="cursor:pointer;margin:2px;" onclick="selectComponent('${escapeJs(name)}')">${escapeHtml(name)}</span>`;

    const requires = internals.requires || [];
    if (requires.length > 0) {
        depsHtml += `<div style="margin-bottom:10px;"><span style="color:#666;font-size:0.75em;text-transform:uppercase;">Depends on</span><div style="margin-top:4px;">${requires.map(n => clickableBadge(n, 'type-library')).join('')}</div></div>`;
    }

    const requiredBy = item.required_by || [];
    if (requiredBy.length > 0) {
        depsHtml += `<div style="margin-bottom:10px;"><span style="color:#666;font-size:0.75em;text-transform:uppercase;">Required by</span><div style="margin-top:4px;">${requiredBy.map(n => clickableBadge(n, 'type-plugin')).join('')}</div></div>`;
    }

    const initializedBy = internals.initialized_by || [];
    if (initializedBy.length > 0) {
        depsHtml += `<div style="margin-bottom:10px;"><span style="color:#666;font-size:0.75em;text-transform:uppercase;">Initialized by</span><div style="margin-top:4px;">${initializedBy.map(n => clickableBadge(n, 'type-app')).join('')}</div></div>`;
    }

    if (!depsHtml) {
        depsHtml = '<span style="color:#666;font-size:0.9em;">No dependencies</span>';
    }
    depsContainer.innerHTML = depsHtml;

    // Registration info
    const registration = item.registration;
    const registrationSection = document.getElementById('panelRegistrationSection');
    if (registration) {
        registrationSection.style.display = 'block';
        document.getElementById('panelRegisteredBy').textContent = registration.registered_by || '-';

        // Format the timestamp nicely
        if (registration.registered_at) {
            const date = new Date(registration.registered_at);
            document.getElementById('panelRegisteredAt').textContent = date.toLocaleString();
        } else {
            document.getElementById('panelRegisteredAt').textContent = '-';
        }

        // Show source file if available
        const fileItem = document.getElementById('panelRegistrationFileItem');
        if (registration.file) {
            fileItem.style.display = 'block';
            const fileName = registration.file.split(/[/\\]/).pop();
            const lineInfo = registration.line ? `:${registration.line}` : '';
            document.getElementById('panelRegistrationFile').textContent = fileName + lineInfo;
            document.getElementById('panelRegistrationFile').title = registration.file + lineInfo;
        } else {
            fileItem.style.display = 'none';
        }
    } else {
        registrationSection.style.display = 'none';
    }

    // Config
    renderConfigForm(item);

    // Actions
    const actions = document.getElementById('panelActions');
    actions.innerHTML = '';

    const lowerType = String(item.type || '').toLowerCase();
    const isApp = lowerType === 'app';
    const isLibrary = lowerType === 'library';
    const isActive = item.state && item.state.is_initialized;
    const isTransitioning = item.state && (item.state.is_initializing || item.state.is_shutting_down);

    if (!isApp && !isLibrary) {
        if (isTransitioning) {
            const btn = document.createElement('button');
            btn.className = 'btn';
            btn.disabled = true;
            btn.textContent = 'Please wait...';
            actions.appendChild(btn);
        } else if (isActive) {
            const btn = document.createElement('button');
            btn.className = 'btn btn-disable';
            btn.textContent = 'Disable';
            btn.onclick = () => disableItem(item.name, item._kind);
            actions.appendChild(btn);
        } else {
            const btn = document.createElement('button');
            btn.className = 'btn btn-enable';
            btn.textContent = 'Enable';
            btn.onclick = () => enableItem(item.name, item._kind);
            actions.appendChild(btn);
        }

        // Add unregister button for plugins (only when inactive)
        if (item._kind === 'plugin' && !isActive && !isTransitioning) {
            const unregBtn = document.createElement('button');
            unregBtn.className = 'btn btn-danger';
            unregBtn.textContent = 'Unregister';
            unregBtn.onclick = () => unregisterPlugin(item.name);
            actions.appendChild(unregBtn);
        }
    }
}

// ==================== Config Form Rendering ====================
function renderConfigForm(item) {
    const configSection = document.getElementById('panelConfigSection');
    const configForm = document.getElementById('panelConfigForm');
    const configTabs = document.getElementById('configTabs');

    // Handle both array of configs and legacy single config object
    let configs = item.config;
    if (!configs) {
        configSection.style.display = 'none';
        currentConfigs = [];
        currentConfigPrefix = null;
        return;
    }

    // Normalize to array
    if (!Array.isArray(configs)) {
        configs = [configs];
    }

    // Filter out configs without schema
    configs = configs.filter(c => c && c.schema);
    if (configs.length === 0) {
        configSection.style.display = 'none';
        currentConfigs = [];
        currentConfigPrefix = null;
        return;
    }

    currentConfigs = configs;
    configSection.style.display = 'block';

    // Render tabs if multiple configs
    if (configs.length > 1) {
        configTabs.style.display = 'flex';
        configTabs.innerHTML = '';
        configs.forEach((cfg, index) => {
            const tab = document.createElement('button');
            tab.type = 'button'; // Prevent form submission
            tab.className = 'config-tab' + (index === 0 ? ' active' : '');
            tab.textContent = cfg.prefix || `Config ${index + 1}`;
            tab.dataset.configIndex = index;
            tab.addEventListener('click', (e) => {
                e.preventDefault();
                e.stopPropagation();
                switchConfigTab(parseInt(e.currentTarget.dataset.configIndex, 10));
            });
            configTabs.appendChild(tab);
        });
    } else {
        configTabs.style.display = 'none';
    }

    // Render first config
    renderSingleConfig(configs[0]);
}

function switchConfigTab(index) {
    if (index < 0 || index >= currentConfigs.length) return;

    // Update tab active state
    const tabs = document.querySelectorAll('#configTabs .config-tab');
    tabs.forEach((tab, i) => {
        tab.classList.toggle('active', i === index);
    });

    // Render selected config
    renderSingleConfig(currentConfigs[index]);
}

function renderSingleConfig(config) {
    const configForm = document.getElementById('panelConfigForm');
    configForm.innerHTML = '';
    treeNodeIdCounter = 0;

    // Reset tracking for original values and secrets
    originalConfigValues = {};
    secretFields = new Set();
    currentConfigPrefix = config.prefix || null;

    const schema = config.schema;
    const values = config.values || {};
    const properties = schema.properties || {};

    // Store original values for change detection
    originalConfigValues = JSON.parse(JSON.stringify(values));

    for (const [fieldName, fieldSchema] of Object.entries(properties)) {
        const fieldType = fieldSchema.type || 'string';
        const fieldTitle = fieldSchema.title || fieldName;
        const fieldDescription = fieldSchema.description || '';
        const currentValue = values[fieldName];
        const defaultValue = fieldSchema.default;
        const effectiveValue = currentValue !== undefined ? currentValue : defaultValue;

        // Detect secret fields (pydantic SecretStr, SecretBytes)
        const isSecret = fieldSchema.format === 'password' || fieldSchema.writeOnly === true;
        if (isSecret) {
            secretFields.add(fieldName);
        }

        let effectiveType = fieldType;
        if (typeof effectiveValue === 'object' && effectiveValue !== null) {
            effectiveType = Array.isArray(effectiveValue) ? 'array' : 'object';
        }

        if (effectiveType === 'array' || effectiveType === 'object') {
            const treeNode = renderTreeNode(fieldName, fieldTitle, effectiveType, fieldSchema, effectiveValue, fieldDescription, false);
            configForm.appendChild(treeNode);
        } else {
            const fieldDiv = document.createElement('div');
            fieldDiv.className = 'config-field';
            if (isSecret) {
                fieldDiv.classList.add('secret-field');
            }

            if (fieldType === 'boolean') {
                const checkboxLabel = document.createElement('label');
                checkboxLabel.className = 'checkbox-label';

                const input = document.createElement('input');
                input.type = 'checkbox';
                input.id = `config_${fieldName}`;
                input.name = fieldName;
                input.dataset.configPath = fieldName;
                input.dataset.configType = 'boolean';
                input.checked = effectiveValue || false;

                checkboxLabel.appendChild(input);
                checkboxLabel.appendChild(document.createTextNode(fieldTitle));
                fieldDiv.appendChild(checkboxLabel);
            } else {
                const label = document.createElement('label');
                label.htmlFor = `config_${fieldName}`;
                label.textContent = fieldTitle + (isSecret ? ' [secret]' : '');
                fieldDiv.appendChild(label);

                if (fieldSchema.enum && Array.isArray(fieldSchema.enum)) {
                    const select = document.createElement('select');
                    select.id = `config_${fieldName}`;
                    select.name = fieldName;
                    select.dataset.configPath = fieldName;
                    select.dataset.configType = fieldType;

                    fieldSchema.enum.forEach(enumValue => {
                        const option = document.createElement('option');
                        option.value = enumValue;
                        option.textContent = enumValue;
                        if (effectiveValue === enumValue) option.selected = true;
                        select.appendChild(option);
                    });

                    fieldDiv.appendChild(select);
                } else {
                    const input = document.createElement('input');
                    input.id = `config_${fieldName}`;
                    input.name = fieldName;
                    input.dataset.configPath = fieldName;
                    input.dataset.configType = fieldType;
                    if (isSecret) {
                        input.dataset.isSecret = 'true';
                    }

                    if (fieldType === 'integer' || fieldType === 'number') {
                        input.type = 'number';
                        if (fieldType === 'number') input.step = 'any';
                    } else if (isSecret) {
                        input.type = 'password';
                        input.placeholder = 'Enter new value to change';
                    } else {
                        input.type = 'text';
                    }

                    input.value = effectiveValue !== undefined ? effectiveValue : '';
                    fieldDiv.appendChild(input);
                }
            }

            if (fieldDescription) {
                const desc = document.createElement('div');
                desc.className = 'field-description';
                desc.textContent = fieldDescription;
                fieldDiv.appendChild(desc);
            }

            configForm.appendChild(fieldDiv);
        }
    }
}

function renderTreeNode(path, label, type, schema, value, description, isNested) {
    const nodeId = `tree_${treeNodeIdCounter++}`;
    const node = document.createElement('div');
    node.className = 'config-tree-node' + (isNested ? ' nested' : '');
    node.dataset.treePath = path;
    node.dataset.treeType = type;

    const header = document.createElement('div');
    header.className = 'config-tree-header';

    const toggle = document.createElement('button');
    toggle.className = 'config-tree-toggle';
    toggle.textContent = '\u25BC';
    toggle.type = 'button';
    toggle.onclick = (e) => {
        e.stopPropagation();
        const children = node.querySelector(':scope > .config-tree-children');
        if (children) {
            const isCollapsed = children.classList.toggle('collapsed');
            toggle.textContent = isCollapsed ? '\u25B6' : '\u25BC';
            const addRow = node.querySelector(':scope > .config-tree-add-row');
            if (addRow) addRow.style.display = isCollapsed ? 'none' : 'flex';
        }
    };
    header.appendChild(toggle);

    const labelSpan = document.createElement('span');
    labelSpan.className = 'config-tree-label';
    labelSpan.textContent = label;
    header.appendChild(labelSpan);

    const typeBadge = document.createElement('span');
    typeBadge.className = 'config-tree-type-badge';
    typeBadge.textContent = type;
    header.appendChild(typeBadge);

    node.appendChild(header);

    const children = document.createElement('div');
    children.className = 'config-tree-children';

    if (type === 'array' && Array.isArray(value)) {
        const itemSchema = schema.items || {};
        const itemType = itemSchema.type || 'string';
        value.forEach((v, idx) => {
            addArrayItemElement(children, path, idx, itemSchema, itemType, v);
        });
    } else if (type === 'object' && value && typeof value === 'object') {
        const props = schema.properties || {};
        for (const [key, val] of Object.entries(value)) {
            const propSchema = props[key] || {};
            const propType = propSchema.type || (typeof val === 'object' ? (Array.isArray(val) ? 'array' : 'object') : typeof val);
            addObjectPropertyElement(children, path, key, propSchema, propType, val, !!props[key]);
        }
    }

    node.appendChild(children);

    // Add "Add" row for objects and arrays
    if (type === 'object') {
        const addRow = createAddPropertyRow(node, children, path);
        node.appendChild(addRow);
    } else if (type === 'array') {
        const addRow = createAddArrayItemRow(node, children, path, schema.items || {});
        node.appendChild(addRow);
    }

    return node;
}

function createAddArrayItemRow(node, childrenContainer, basePath, itemSchema) {
    const addRow = document.createElement('div');
    addRow.className = 'config-tree-add-row';

    const itemType = itemSchema.type || 'string';

    const typeSelect = document.createElement('select');
    typeSelect.className = 'config-tree-type-select';
    typeSelect.innerHTML = `
        <option value="string" ${itemType === 'string' ? 'selected' : ''}>string</option>
        <option value="integer" ${itemType === 'integer' ? 'selected' : ''}>integer</option>
        <option value="number" ${itemType === 'number' ? 'selected' : ''}>number</option>
        <option value="boolean" ${itemType === 'boolean' ? 'selected' : ''}>boolean</option>
    `;

    const valueInput = document.createElement('input');
    valueInput.type = 'text';
    valueInput.placeholder = 'New item value';
    valueInput.style.cssText = 'flex:1;min-width:150px;background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);border-radius:4px;padding:4px 8px;color:#eee;font-size:0.85em;';

    const addBtn = document.createElement('button');
    addBtn.className = 'config-tree-btn add';
    addBtn.textContent = '+';
    addBtn.title = 'Add item';
    addBtn.onclick = () => {
        const selectedType = typeSelect.value;
        let value = valueInput.value;

        // Convert value based on type
        if (selectedType === 'integer') {
            value = parseInt(value, 10) || 0;
        } else if (selectedType === 'number') {
            value = parseFloat(value) || 0;
        } else if (selectedType === 'boolean') {
            value = value.toLowerCase() === 'true' || value === '1';
        }

        // Find the next index
        const existingItems = childrenContainer.querySelectorAll('[data-array-index]');
        const nextIndex = existingItems.length;

        // Add the array item element
        addArrayItemElement(childrenContainer, basePath, nextIndex, itemSchema, selectedType, value);

        // Clear input
        valueInput.value = '';
    };

    addRow.appendChild(typeSelect);
    addRow.appendChild(valueInput);
    addRow.appendChild(addBtn);

    return addRow;
}

function createAddPropertyRow(node, childrenContainer, basePath) {
    const addRow = document.createElement('div');
    addRow.className = 'config-tree-add-row';

    const keyInput = document.createElement('input');
    keyInput.type = 'text';
    keyInput.placeholder = 'Key';
    keyInput.style.cssText = 'flex:1;min-width:80px;background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);border-radius:4px;padding:4px 8px;color:#eee;font-size:0.85em;';

    const typeSelect = document.createElement('select');
    typeSelect.className = 'config-tree-type-select';
    typeSelect.innerHTML = `
        <option value="string">string</option>
        <option value="integer">integer</option>
        <option value="number">number</option>
        <option value="boolean">boolean</option>
    `;

    const valueInput = document.createElement('input');
    valueInput.type = 'text';
    valueInput.placeholder = 'Value';
    valueInput.style.cssText = 'flex:2;min-width:100px;background:rgba(0,0,0,0.3);border:1px solid rgba(255,255,255,0.1);border-radius:4px;padding:4px 8px;color:#eee;font-size:0.85em;';

    const addBtn = document.createElement('button');
    addBtn.className = 'config-tree-btn add';
    addBtn.textContent = '+';
    addBtn.title = 'Add property';
    addBtn.onclick = () => {
        const key = keyInput.value.trim();
        if (!key) {
            showToast('Property key is required', 'error');
            return;
        }

        // Check if key already exists
        const existingItem = childrenContainer.querySelector(`[data-property-key="${key}"]`);
        if (existingItem) {
            showToast('Property already exists', 'error');
            return;
        }

        const propType = typeSelect.value;
        let value = valueInput.value;

        // Convert value based on type
        if (propType === 'integer') {
            value = parseInt(value, 10) || 0;
        } else if (propType === 'number') {
            value = parseFloat(value) || 0;
        } else if (propType === 'boolean') {
            value = value.toLowerCase() === 'true' || value === '1';
        }

        // Add the property element
        addObjectPropertyElement(childrenContainer, basePath, key, {}, propType, value, false);

        // Clear inputs
        keyInput.value = '';
        valueInput.value = '';
    };

    addRow.appendChild(keyInput);
    addRow.appendChild(typeSelect);
    addRow.appendChild(valueInput);
    addRow.appendChild(addBtn);

    return addRow;
}

function addArrayItemElement(container, basePath, index, itemSchema, itemType, value) {
    const itemPath = `${basePath}[${index}]`;

    let effectiveType = itemType;
    if (typeof value === 'object' && value !== null) {
        effectiveType = Array.isArray(value) ? 'array' : 'object';
    }

    if (effectiveType === 'object' || effectiveType === 'array') {
        const nestedNode = renderTreeNode(itemPath, `[${index}]`, effectiveType, itemSchema, value, '', true);
        nestedNode.dataset.arrayIndex = index;

        // Add delete button to nested node header
        const header = nestedNode.querySelector('.config-tree-header');
        if (header) {
            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'config-tree-btn remove';
            deleteBtn.textContent = '\u00D7';
            deleteBtn.title = 'Remove item';
            deleteBtn.style.marginLeft = 'auto';
            deleteBtn.onclick = (e) => {
                e.stopPropagation();
                nestedNode.remove();
                reindexArrayItems(container, basePath);
            };
            header.appendChild(deleteBtn);
        }

        container.appendChild(nestedNode);
    } else {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'config-tree-item';
        itemDiv.dataset.arrayIndex = index;

        const keySpan = document.createElement('div');
        keySpan.className = 'config-tree-item-key';
        keySpan.textContent = `[${index}]`;
        itemDiv.appendChild(keySpan);

        const valueDiv = document.createElement('div');
        valueDiv.className = 'config-tree-item-value';

        const input = createValueInput(itemPath, itemType, value, itemSchema);
        valueDiv.appendChild(input);
        itemDiv.appendChild(valueDiv);

        // Add delete button
        const actionsDiv = document.createElement('div');
        actionsDiv.className = 'config-tree-actions';

        const deleteBtn = document.createElement('button');
        deleteBtn.className = 'config-tree-btn remove';
        deleteBtn.textContent = '\u00D7';
        deleteBtn.title = 'Remove item';
        deleteBtn.onclick = () => {
            itemDiv.remove();
            reindexArrayItems(container, basePath);
        };
        actionsDiv.appendChild(deleteBtn);
        itemDiv.appendChild(actionsDiv);

        container.appendChild(itemDiv);
    }
}

function reindexArrayItems(container, basePath) {
    // Re-index all array items after deletion
    const items = container.querySelectorAll(':scope > [data-array-index]');
    items.forEach((item, newIndex) => {
        item.dataset.arrayIndex = newIndex;

        // Update the key label
        const keySpan = item.querySelector('.config-tree-item-key, .config-tree-label');
        if (keySpan) {
            keySpan.textContent = `[${newIndex}]`;
        }

        // Update the input path
        const input = item.querySelector('[data-config-path]');
        if (input) {
            input.dataset.configPath = `${basePath}[${newIndex}]`;
        }

        // Update nested node path
        if (item.dataset.treePath) {
            item.dataset.treePath = `${basePath}[${newIndex}]`;
        }
    });
}

function addObjectPropertyElement(container, basePath, key, keySchema, valueType, value, isFixed) {
    const itemPath = key ? `${basePath}.${key}` : basePath;

    let effectiveType = valueType;
    if (typeof value === 'object' && value !== null) {
        effectiveType = Array.isArray(value) ? 'array' : 'object';
    }

    if (effectiveType === 'object' || effectiveType === 'array') {
        const nestedNode = renderTreeNode(itemPath, key || '(new)', effectiveType, keySchema, value, '', true);
        nestedNode.dataset.propertyKey = key;
        container.appendChild(nestedNode);
    } else {
        const itemDiv = document.createElement('div');
        itemDiv.className = 'config-tree-item';
        itemDiv.dataset.propertyKey = key;

        const keyDiv = document.createElement('div');
        keyDiv.className = 'config-tree-item-key';
        keyDiv.textContent = key;
        itemDiv.appendChild(keyDiv);

        const valueDiv = document.createElement('div');
        valueDiv.className = 'config-tree-item-value';

        const input = createValueInput(itemPath, valueType, value, keySchema);
        valueDiv.appendChild(input);
        itemDiv.appendChild(valueDiv);

        // Add delete button for dynamically added properties (not fixed schema properties)
        if (!isFixed) {
            const actionsDiv = document.createElement('div');
            actionsDiv.className = 'config-tree-actions';

            const deleteBtn = document.createElement('button');
            deleteBtn.className = 'config-tree-btn remove';
            deleteBtn.textContent = '\u00D7';
            deleteBtn.title = 'Remove property';
            deleteBtn.onclick = () => {
                itemDiv.remove();
            };
            actionsDiv.appendChild(deleteBtn);
            itemDiv.appendChild(actionsDiv);
        }

        container.appendChild(itemDiv);
    }
}

function createValueInput(path, type, value, schema = null) {
    if (schema && schema.enum && Array.isArray(schema.enum)) {
        const select = document.createElement('select');
        select.dataset.configPath = path;
        select.dataset.configType = type;

        schema.enum.forEach(enumValue => {
            const option = document.createElement('option');
            option.value = enumValue;
            option.textContent = enumValue;
            if (value === enumValue) option.selected = true;
            select.appendChild(option);
        });

        return select;
    }

    const input = document.createElement('input');
    input.dataset.configPath = path;
    input.dataset.configType = type;

    if (type === 'boolean') {
        input.type = 'checkbox';
        input.checked = !!value;
    } else if (type === 'integer') {
        input.type = 'number';
        input.step = '1';
        input.value = value !== undefined ? value : 0;
    } else if (type === 'number') {
        input.type = 'number';
        input.step = 'any';
        input.value = value !== undefined ? value : 0;
    } else {
        input.type = 'text';
        input.value = value !== undefined ? String(value) : '';
    }

    return input;
}

function collectConfigValues(onlyModified = true) {
    const form = document.getElementById('panelConfigForm');
    const values = {};
    const SECRET_MASK = '**********';

    // Collect values from inputs
    form.querySelectorAll('[data-config-path]').forEach(input => {
        const path = input.dataset.configPath;
        const type = input.dataset.configType;
        const isSecret = input.dataset.isSecret === 'true';
        let value;

        if (input.type === 'checkbox') {
            value = input.checked;
        } else if (type === 'integer') {
            value = parseInt(input.value, 10) || 0;
        } else if (type === 'number') {
            value = parseFloat(input.value) || 0;
        } else if (type === 'boolean') {
            value = input.value === 'true' || input.value === '1';
        } else {
            value = input.value;
        }

        // Skip secret fields that still have the masked value
        if (isSecret && value === SECRET_MASK) {
            return; // Don't include unchanged secrets
        }

        // Only include modified fields if onlyModified is true
        if (onlyModified) {
            const originalValue = getNestedValue(originalConfigValues, path);
            // For secrets, if original was masked and new value is different, include it
            if (isSecret) {
                if (value !== SECRET_MASK && value !== '') {
                    setNestedValue(values, path, value);
                }
            } else if (!deepEqual(value, originalValue)) {
                setNestedValue(values, path, value);
            }
        } else {
            // Skip masked secrets even when not in onlyModified mode
            if (!(isSecret && value === SECRET_MASK)) {
                setNestedValue(values, path, value);
            }
        }
    });

    // Handle arrays and objects that might be empty or have modified structure
    form.querySelectorAll('.config-tree-node[data-tree-type]').forEach(node => {
        const path = node.dataset.treePath;
        const type = node.dataset.treeType;

        // Only process top-level nodes (not nested)
        if (node.classList.contains('nested')) return;

        if (type === 'array') {
            // Collect all array items
            const children = node.querySelector('.config-tree-children');
            const items = children ? children.querySelectorAll(':scope > [data-array-index]') : [];
            const arrayValues = [];

            items.forEach((item, idx) => {
                // Check if this item has a direct input
                const input = item.querySelector('[data-config-path]');
                if (input) {
                    const itemType = input.dataset.configType;
                    let itemValue;
                    if (input.type === 'checkbox') {
                        itemValue = input.checked;
                    } else if (itemType === 'integer') {
                        itemValue = parseInt(input.value, 10) || 0;
                    } else if (itemType === 'number') {
                        itemValue = parseFloat(input.value) || 0;
                    } else {
                        itemValue = input.value;
                    }
                    arrayValues.push(itemValue);
                } else if (item.dataset.treeType) {
                    // Nested object/array - collect recursively
                    const nestedValue = collectNestedTreeValue(item);
                    arrayValues.push(nestedValue);
                }
            });

            // Check if array was modified
            const originalArray = getNestedValue(originalConfigValues, path);
            if (!onlyModified || !deepEqual(arrayValues, originalArray)) {
                values[path] = arrayValues;
            }
        } else if (type === 'object') {
            // Collect all object properties
            const children = node.querySelector('.config-tree-children');
            const items = children ? children.querySelectorAll(':scope > [data-property-key]') : [];
            const objectValues = {};

            items.forEach(item => {
                const key = item.dataset.propertyKey;
                const input = item.querySelector('[data-config-path]');
                if (input) {
                    const itemType = input.dataset.configType;
                    let itemValue;
                    if (input.type === 'checkbox') {
                        itemValue = input.checked;
                    } else if (itemType === 'integer') {
                        itemValue = parseInt(input.value, 10) || 0;
                    } else if (itemType === 'number') {
                        itemValue = parseFloat(input.value) || 0;
                    } else {
                        itemValue = input.value;
                    }
                    objectValues[key] = itemValue;
                } else if (item.dataset.treeType) {
                    // Nested object/array
                    objectValues[key] = collectNestedTreeValue(item);
                }
            });

            // Check if object was modified
            const originalObject = getNestedValue(originalConfigValues, path);
            if (!onlyModified || !deepEqual(objectValues, originalObject)) {
                values[path] = objectValues;
            }
        }
    });

    return values;
}

function collectNestedTreeValue(node) {
    const type = node.dataset.treeType;
    const children = node.querySelector('.config-tree-children');

    if (type === 'array') {
        const items = children ? children.querySelectorAll(':scope > [data-array-index]') : [];
        const arrayValues = [];

        items.forEach(item => {
            const input = item.querySelector('[data-config-path]');
            if (input) {
                const itemType = input.dataset.configType;
                let itemValue;
                if (input.type === 'checkbox') {
                    itemValue = input.checked;
                } else if (itemType === 'integer') {
                    itemValue = parseInt(input.value, 10) || 0;
                } else if (itemType === 'number') {
                    itemValue = parseFloat(input.value) || 0;
                } else {
                    itemValue = input.value;
                }
                arrayValues.push(itemValue);
            } else if (item.dataset.treeType) {
                arrayValues.push(collectNestedTreeValue(item));
            }
        });

        return arrayValues;
    } else if (type === 'object') {
        const items = children ? children.querySelectorAll(':scope > [data-property-key]') : [];
        const objectValues = {};

        items.forEach(item => {
            const key = item.dataset.propertyKey;
            const input = item.querySelector('[data-config-path]');
            if (input) {
                const itemType = input.dataset.configType;
                let itemValue;
                if (input.type === 'checkbox') {
                    itemValue = input.checked;
                } else if (itemType === 'integer') {
                    itemValue = parseInt(input.value, 10) || 0;
                } else if (itemType === 'number') {
                    itemValue = parseFloat(input.value) || 0;
                } else {
                    itemValue = input.value;
                }
                objectValues[key] = itemValue;
            } else if (item.dataset.treeType) {
                objectValues[key] = collectNestedTreeValue(item);
            }
        });

        return objectValues;
    }

    return null;
}

function getNestedValue(obj, path) {
    if (!obj) return undefined;
    const parts = path.replace(/\[(\d+)\]/g, '.$1').split('.');
    let current = obj;
    for (const part of parts) {
        if (current === undefined || current === null) return undefined;
        current = current[part];
    }
    return current;
}

function deepEqual(a, b) {
    if (a === b) return true;
    if (a === null || b === null) return false;
    if (typeof a !== typeof b) return false;
    if (typeof a !== 'object') return a === b;
    if (Array.isArray(a) !== Array.isArray(b)) return false;
    const keysA = Object.keys(a);
    const keysB = Object.keys(b);
    if (keysA.length !== keysB.length) return false;
    return keysA.every(key => deepEqual(a[key], b[key]));
}

function setNestedValue(obj, path, value) {
    const parts = path.replace(/\[(\d+)\]/g, '.$1').split('.');
    let current = obj;

    for (let i = 0; i < parts.length - 1; i++) {
        const part = parts[i];
        const nextPart = parts[i + 1];
        const isNextArray = /^\d+$/.test(nextPart);

        if (!(part in current)) {
            current[part] = isNextArray ? [] : {};
        }
        current = current[part];
    }

    const lastPart = parts[parts.length - 1];
    current[lastPart] = value;
}

function updateOriginalConfigAfterSave() {
    // Update original values with current form values after a successful save
    // This ensures subsequent saves only track new changes
    const currentValues = collectConfigValues(false); // Get all values, not just modified
    for (const [key, value] of Object.entries(currentValues)) {
        setNestedValue(originalConfigValues, key, value);
    }
}

function updateConfigTargetDropdown() {
    const select = document.getElementById('configTargetFile');
    if (!select) return;

    // Remember current selection
    const currentValue = select.value;

    // Clear and rebuild options
    select.innerHTML = '';

    if (configTargets.length === 0) {
        // Fallback if no targets available
        select.innerHTML = '<option value="yaml">YAML Config</option><option value="env">.env</option>';
    } else {
        configTargets.forEach(target => {
            const option = document.createElement('option');
            option.value = target.id;
            option.textContent = target.label + (target.exists ? '' : ' (new)');
            option.title = target.path;
            select.appendChild(option);
        });
    }

    // Restore selection if still valid
    if (currentValue && Array.from(select.options).some(o => o.value === currentValue)) {
        select.value = currentValue;
    }
}

function saveConfig() {
    if (!currentPanelItem) return;

    const values = collectConfigValues();
    const targetFile = document.getElementById('configTargetFile')?.value || 'yaml';

    // Check if any fields were modified
    if (Object.keys(values).length === 0) {
        showToast('No changes to save', 'info');
        return;
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
        const message = {
            action: 'save_config',
            name: currentPanelItem.name,
            config: values,
            target_file: targetFile
        };
        // Include prefix for components with multiple configs
        if (currentConfigPrefix) {
            message.prefix = currentConfigPrefix;
        }
        ws.send(JSON.stringify(message));
    }
}

// ==================== Enable/Disable with Optimistic UI ====================
function enableItem(name, kind) {
    // Optimistic UI: immediately show "initializing" state
    setOptimisticState(name, { is_initialized: false, is_initializing: true, is_shutting_down: false });

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'enable_plugin', name }));
    }
}

function disableItem(name, kind) {
    // Optimistic UI: immediately show "shutting_down" state
    setOptimisticState(name, { is_initialized: true, is_initializing: false, is_shutting_down: true });

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'disable_plugin', name }));
    }
}

function setOptimisticState(name, state) {
    // Update component state optimistically for immediate UI feedback
    const idx = currentComponents.findIndex(c => c.name === name);
    if (idx >= 0) {
        currentComponents[idx] = { ...currentComponents[idx], state };
    }
    const pidx = currentPlugins.findIndex(p => p.name === name);
    if (pidx >= 0) {
        currentPlugins[pidx] = { ...currentPlugins[pidx], state };
    }
    renderAllSections(name);
    if (selectedComponent === name) {
        selectComponent(selectedComponent);
    }
}

// ==================== Plugin Upload ====================
function uploadPluginFile() {
    const input = document.getElementById('pluginFile');
    const status = document.getElementById('uploadStatus');
    if (!input.files.length) return;

    const file = input.files[0];
    const reader = new FileReader();
    status.textContent = 'Uploading...';
    status.className = 'upload-status uploading';

    reader.onload = () => {
        if (ws && ws.readyState === WebSocket.OPEN) {
            ws.send(JSON.stringify({
                action: 'upload_plugin',
                type: 'file',
                filename: file.name,
                content: reader.result.split(',')[1]
            }));
        }
        input.value = '';
    };
    reader.readAsDataURL(file);
}

function uploadPluginDirectory() {
    const input = document.getElementById('pluginDir');
    const status = document.getElementById('uploadStatus');
    if (!input.files.length) return;

    const files = [];
    let loaded = 0;
    const total = input.files.length;
    status.textContent = `Reading ${total} files...`;
    status.className = 'upload-status uploading';

    const dirname = input.files[0].webkitRelativePath.split('/')[0];

    Array.from(input.files).forEach(file => {
        const reader = new FileReader();
        reader.onload = () => {
            files.push({
                path: file.webkitRelativePath,
                content: reader.result.split(',')[1]
            });
            loaded++;
            if (loaded === total) {
                if (ws && ws.readyState === WebSocket.OPEN) {
                    ws.send(JSON.stringify({
                        action: 'upload_plugin',
                        type: 'directory',
                        dirname,
                        files
                    }));
                }
                input.value = '';
            }
        };
        reader.readAsDataURL(file);
    });
}

// ==================== Logs ====================
function formatTime(timestamp) {
    if (timestamp === undefined || timestamp === null) {
        return '--:--:--';
    }
    const date = new Date(timestamp * 1000);
    if (isNaN(date.getTime())) {
        return '--:--:--';
    }
    return date.toLocaleTimeString('en-US', { hour12: false });
}

function renderLogs() {
    const container = document.getElementById('logsContainer');
    const searchText = (document.getElementById('logSearch')?.value || '').toLowerCase();
    const levelFilter = document.getElementById('logLevel')?.value || '';

    const filtered = currentLogs.filter(log => {
        if (levelFilter && log.level !== levelFilter) return false;
        if (searchText) {
            const searchable = `${log.component} ${log.message}`.toLowerCase();
            if (!searchable.includes(searchText)) return false;
        }
        return true;
    });

    document.getElementById('logCount').textContent = `${filtered.length} logs`;

    if (filtered.length === 0) {
        container.innerHTML = '<div class="no-logs">No logs match filters</div>';
        return;
    }

    container.innerHTML = filtered.map(log => `
        <div class="log-entry">
            <span class="log-time">${formatTime(log.timestamp)}</span>
            <span class="log-level ${log.level}">${log.level}</span>
            <span class="log-component">${escapeHtml(log.component)}</span>
            <span class="log-message">${escapeHtml(log.message)}</span>
        </div>
    `).join('');

    if (document.getElementById('autoScroll')?.checked) {
        container.scrollTop = container.scrollHeight;
    }
}

function addLogEntry(log) {
    if (!log) return;
    currentLogs.push(log);
    if (currentLogs.length > 1000) currentLogs.shift();
    renderLogs();
}

function filterLogs() {
    renderLogs();
}

function clearLogs() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'clear_logs' }));
    }
}

// ==================== Toast Notifications ====================
function showToast(message, type = 'info') {
    const container = document.getElementById('toastContainer');
    const toast = document.createElement('div');
    toast.className = `toast ${type}`;
    toast.innerHTML = `<span>${escapeHtml(message)}</span>`;
    container.appendChild(toast);

    requestAnimationFrame(() => toast.classList.add('show'));

    setTimeout(() => {
        toast.classList.remove('show');
        setTimeout(() => toast.remove(), 300);
    }, 4000);
}

// ==================== Drag and Drop Handlers ====================
function handleDragOver(event) {
    event.preventDefault();
    event.stopPropagation();
    const dropzone = document.getElementById('uploadDropzone');
    dropzone.classList.add('dragover');
}

function handleDragLeave(event) {
    event.preventDefault();
    event.stopPropagation();
    const dropzone = document.getElementById('uploadDropzone');
    dropzone.classList.remove('dragover');
}

function handleDrop(event) {
    event.preventDefault();
    event.stopPropagation();
    const dropzone = document.getElementById('uploadDropzone');
    dropzone.classList.remove('dragover');

    const items = event.dataTransfer.items;
    const files = event.dataTransfer.files;

    if (items && items.length > 0) {
        // Check if it's a directory (using webkitGetAsEntry)
        const firstItem = items[0];
        if (firstItem.webkitGetAsEntry) {
            const entry = firstItem.webkitGetAsEntry();
            if (entry && entry.isDirectory) {
                // Handle directory drop
                handleDirectoryDrop(entry);
                return;
            }
        }
    }

    // Handle file(s) drop
    if (files && files.length > 0) {
        handleFilesDrop(files);
    }
}

function handleFilesDrop(files) {
    const status = document.getElementById('uploadStatus');
    const pyFiles = Array.from(files).filter(f => f.name.endsWith('.py'));

    if (pyFiles.length === 0) {
        status.textContent = 'No .py files found';
        status.className = 'upload-status error';
        return;
    }

    status.textContent = `Uploading ${pyFiles.length} file(s)...`;
    status.className = 'upload-status';

    let uploaded = 0;
    pyFiles.forEach(file => {
        const reader = new FileReader();
        reader.onload = () => {
            if (ws && ws.readyState === WebSocket.OPEN) {
                ws.send(JSON.stringify({
                    action: 'upload_plugin',
                    type: 'file',
                    filename: file.name,
                    content: reader.result.split(',')[1]
                }));
            }
            uploaded++;
            if (uploaded === pyFiles.length) {
                status.textContent = `Uploaded ${uploaded} file(s)`;
                status.className = 'upload-status success';
            }
        };
        reader.readAsDataURL(file);
    });
}

function handleDirectoryDrop(directoryEntry) {
    const status = document.getElementById('uploadStatus');
    status.textContent = 'Reading directory...';
    status.className = 'upload-status';

    const files = [];
    const dirName = directoryEntry.name;

    function readEntries(reader, path) {
        return new Promise((resolve) => {
            reader.readEntries(async (entries) => {
                if (entries.length === 0) {
                    resolve();
                    return;
                }
                for (const entry of entries) {
                    if (entry.isFile) {
                        const file = await getFile(entry);
                        files.push({
                            path: path + '/' + entry.name,
                            file: file
                        });
                    } else if (entry.isDirectory) {
                        const newReader = entry.createReader();
                        await readEntries(newReader, path + '/' + entry.name);
                    }
                }
                // Keep reading until no more entries
                await readEntries(reader, path);
                resolve();
            });
        });
    }

    function getFile(entry) {
        return new Promise((resolve) => {
            entry.file(resolve);
        });
    }

    const reader = directoryEntry.createReader();
    readEntries(reader, dirName).then(() => {
        if (files.length === 0) {
            status.textContent = 'No files found in directory';
            status.className = 'upload-status error';
            return;
        }

        status.textContent = `Reading ${files.length} files...`;
        let loaded = 0;
        const fileData = [];

        files.forEach(({ path, file }) => {
            const reader = new FileReader();
            reader.onload = () => {
                fileData.push({
                    path: path,
                    content: reader.result.split(',')[1]
                });
                loaded++;
                if (loaded === files.length) {
                    if (ws && ws.readyState === WebSocket.OPEN) {
                        ws.send(JSON.stringify({
                            action: 'upload_plugin',
                            type: 'directory',
                            dirname: dirName,
                            files: fileData
                        }));
                    }
                    status.textContent = `Uploaded directory: ${dirName}`;
                    status.className = 'upload-status success';
                }
            };
            reader.readAsDataURL(file);
        });
    });
}

// ==================== Unregister Plugin ====================
function unregisterPlugin(name) {
    if (!confirm(`Are you sure you want to unregister plugin "${name}"?\n\nThis will remove it from the current session.`)) {
        return;
    }

    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: 'unregister_plugin',
            name: name
        }));
    }

    // Clear selection if we just unregistered the selected item
    if (selectedComponent === name) {
        selectedComponent = null;
        document.getElementById('panelTitle').textContent = 'Select a component';
        document.getElementById('panelVersion').textContent = '';
        document.getElementById('panelDesc').textContent = 'Select a component from the left panel to view its details.';
        document.getElementById('panelActions').innerHTML = '';
    }
}

// ==================== Save/Sync Plugins ====================
function savePlugins() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: 'save_plugins'
        }));
    }
}

function syncPlugins() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: 'sync_plugins'
        }));
    }
}

// ==================== Pot Browser ====================
let potBrowserVisible = false;
let currentPots = [];
let selectedPotName = null;

function togglePotBrowser() {
    potBrowserVisible = !potBrowserVisible;
    const section = document.getElementById('potBrowserSection');
    section.style.display = potBrowserVisible ? 'block' : 'none';
    if (potBrowserVisible) {
        refreshPots();
    }
}

function refreshPots() {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'list_pots' }));
        showToast('Refreshing pots...', 'info');
    }
}

function handlePotsResponse(data) {
    if (data.type === 'error') {
        showToast(data.error, 'error');
        return;
    }
    currentPots = data.pots || [];
    document.getElementById('potCount').textContent = currentPots.length;
    renderPotsList();
}

function renderPotsList() {
    const container = document.getElementById('potsList');
    if (currentPots.length === 0) {
        container.innerHTML = '<div style="color:#666; padding:10px; text-align:center;">No pots found.<br><small>Use <code>awioc pot init</code> to create one.</small></div>';
        return;
    }

    container.innerHTML = currentPots.map(pot => `
        <div class="component-card ${selectedPotName === pot.name ? 'selected' : ''}"
             onclick="selectPot('${escapeJs(pot.name)}')"
             style="cursor:pointer; border-left: 3px solid #9c27b0;">
            <div class="component-card-header">
                <div class="component-card-name" style="color:#9c27b0;">
                    ${escapeHtml(pot.name)}
                </div>
                <div class="component-card-version">v${escapeHtml(pot.version)}</div>
            </div>
            <div class="component-card-meta">
                ${pot.component_count} component(s)
            </div>
            ${pot.description ? `<div class="component-card-desc">${escapeHtml(pot.description)}</div>` : ''}
        </div>
    `).join('');
}

function selectPot(potName) {
    selectedPotName = potName;
    renderPotsList();
    // Fetch components for this pot
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'list_pot_components', pot_name: potName }));
    }
}

function handlePotComponentsResponse(data) {
    if (data.type === 'error') {
        showToast(data.error, 'error');
        return;
    }

    const container = document.getElementById('potComponentsList');
    container.style.display = 'block';

    const components = data.components || [];
    if (components.length === 0) {
        container.innerHTML = `
            <div style="color:#666; text-align:center;">
                <strong>${escapeHtml(data.pot_name)}</strong> has no components.<br>
                <small>Use <code>awioc pot push</code> to add components.</small>
            </div>`;
        return;
    }

    container.innerHTML = `
        <div style="margin-bottom:10px; padding-bottom:8px; border-bottom:1px solid #333;">
            <strong style="color:#9c27b0;">${escapeHtml(data.pot_name)}</strong>
            <span style="color:#666; font-size:0.85em;"> v${escapeHtml(data.pot_version)}</span>
            <div style="color:#888; font-size:0.8em; margin-top:4px;">${components.length} component(s)</div>
        </div>
        ${components.map(comp => `
            <div class="component-card" style="margin-bottom:8px; ${comp.is_registered ? 'opacity:0.6;' : ''}">
                <div class="component-card-header">
                    <div class="component-card-name">${escapeHtml(comp.name)}</div>
                    <div class="component-card-version">v${escapeHtml(comp.version)}</div>
                </div>
                ${comp.description ? `<div class="component-card-desc">${escapeHtml(comp.description)}</div>` : ''}
                <div style="display:flex; gap:8px; margin-top:8px; align-items:center;">
                    <code style="font-size:0.75em; color:#9c27b0; background:#2a2a3e; padding:2px 6px; border-radius:4px;">
                        ${escapeHtml(comp.pot_ref)}
                    </code>
                    ${comp.is_registered
                        ? '<span style="color:#4caf50; font-size:0.8em;">Already registered</span>'
                        : `<button class="btn btn-enable" onclick="registerPotComponent('${escapeJs(data.pot_name)}', '${escapeJs(comp.id)}')" style="font-size:0.8em; padding:4px 8px;">
                            Register
                           </button>`
                    }
                </div>
            </div>
        `).join('')}
    `;
}

function registerPotComponent(potName, componentId) {
    if (ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({
            action: 'register_pot_component',
            pot_name: potName,
            component_name: componentId
        }));
        showToast(`Registering @${potName}/${componentId}...`, 'info');
    }
}

// Refresh pot components after state changes (to update "Already registered" status)
function refreshSelectedPotComponents() {
    if (selectedPotName && potBrowserVisible && ws && ws.readyState === WebSocket.OPEN) {
        ws.send(JSON.stringify({ action: 'list_pot_components', pot_name: selectedPotName }));
    }
}

// ==================== Initialize ====================
connectWebSocket();
