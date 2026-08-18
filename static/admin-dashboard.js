        const state = {
            dashboard: null,
            selectedChatId: null,
            selectedMessages: [],
            selectedEvents: [],
            // integrationDraftDirty: false, // Credentials tab temporarily disabled
            chatPage: 1,
            chatPerPage: 20,
            activityEvents: [],
            activityPagination: { total: 0, has_more: false },
            activityLoading: false,
            chartSignature: '',
            pageVisible: !document.hidden
        };

        const ACTIVITY_DEFAULT_BATCH = 5;
        const managedIntervals = [];

        const flashBanner = document.getElementById('flash-banner');
        let flashTimer = null;
        let refreshInterval = null;
        let resizeTimer = null;
        const currentPage = document.body.dataset.adminPage || 'overview';
        const dashboardEnabled = document.body.dataset.dashboardEnabled === 'true';
        const isChatPage = currentPage === 'chats' || currentPage === 'chats-active';
        const isTicketPage = currentPage === 'tickets-current' || currentPage === 'tickets-old';

        function schedulePoll(callback, ms) {
            const id = window.setInterval(() => {
                if (document.hidden) return;
                callback();
            }, ms);
            managedIntervals.push(id);
            return id;
        }

        function openMobileSidebar() {
            document.body.classList.add('sidebar-open');
            const backdrop = document.getElementById('sidebar-backdrop');
            if (backdrop) backdrop.hidden = false;
            const toggle = document.getElementById('menu-toggle');
            if (toggle) toggle.setAttribute('aria-expanded', 'true');
        }

        function closeMobileSidebar() {
            document.body.classList.remove('sidebar-open');
            const backdrop = document.getElementById('sidebar-backdrop');
            if (backdrop) backdrop.hidden = true;
            const toggle = document.getElementById('menu-toggle');
            if (toggle) toggle.setAttribute('aria-expanded', 'false');
        }

        function setupMobileNav() {
            const toggle = document.getElementById('menu-toggle');
            const closeBtn = document.getElementById('sidebar-close');
            const backdrop = document.getElementById('sidebar-backdrop');
            if (toggle) {
                toggle.addEventListener('click', () => {
                    if (document.body.classList.contains('sidebar-open')) {
                        closeMobileSidebar();
                    } else {
                        openMobileSidebar();
                    }
                });
            }
            if (closeBtn) closeBtn.addEventListener('click', closeMobileSidebar);
            if (backdrop) backdrop.addEventListener('click', closeMobileSidebar);
            document.addEventListener('keydown', (event) => {
                if (event.key === 'Escape') closeMobileSidebar();
            });
            document.querySelectorAll('.sidebar a').forEach((link) => {
                link.addEventListener('click', () => {
                    if (window.matchMedia('(max-width: 1200px)').matches) {
                        closeMobileSidebar();
                    }
                });
            });
            window.addEventListener('resize', () => {
                if (!window.matchMedia('(max-width: 1200px)').matches) {
                    closeMobileSidebar();
                }
            });
        }

        function buildChartSignature(dashboard) {
            if (!dashboard || !dashboard.reports) return '';
            const status = dashboard.reports.status_breakdown || {};
            const board = dashboard.reports.resolution_leaderboard || [];
            return JSON.stringify({
                status,
                board: board.map((row) => [
                    row.id,
                    row.resolved_today,
                    row.resolved_yesterday,
                    row.open_chats,
                    row.is_online ? 1 : 0
                ])
            });
        }

        function buildDashboardApiUrl() {
            if (!dashboardEnabled) return null;
            const params = new URLSearchParams({ page: currentPage });
            if (isChatPage) {
                params.set('chat_page', String(state.chatPage));
                params.set('per_page', String(state.chatPerPage));
            }
            return `/api/dashboard-data?${params.toString()}`;
        }

        function escapeHtml(value) {
            return String(value || '')
                .replaceAll('&', '&amp;')
                .replaceAll('<', '&lt;')
                .replaceAll('>', '&gt;')
                .replaceAll('"', '&quot;')
                .replaceAll("'", '&#39;');
        }

        function parseServerDate(value) {
            if (!value) return null;
            if (value instanceof Date) {
                return Number.isNaN(value.getTime()) ? null : value;
            }
            let raw = String(value).trim();
            if (!raw) return null;

            // Treat naive timestamps from the API as UTC (append Z).
            const hasTimezone = /[zZ]$|[+-]\d{2}:?\d{2}$/.test(raw);
            if (!hasTimezone && /^\d{4}-\d{2}-\d{2}/.test(raw)) {
                raw = raw.replace(' ', 'T');
                if (/^\d{4}-\d{2}-\d{2}$/.test(raw)) {
                    raw = `${raw}T00:00:00Z`;
                } else if (!raw.endsWith('Z')) {
                    raw = `${raw}Z`;
                }
            }

            const date = new Date(raw);
            return Number.isNaN(date.getTime()) ? null : date;
        }

        function formatDateTime(value) {
            const date = parseServerDate(value);
            if (!date) return value || 'Not available';
            return date.toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                year: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                timeZoneName: 'short'
            });
        }

        function formatRelative(value) {
            const date = parseServerDate(value);
            if (!date) return value || 'Not available';
            const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
            if (seconds < 0) return 'Just now';
            if (seconds < 60) return 'Just now';
            if (seconds < 3600) {
                const mins = Math.floor(seconds / 60);
                return `${mins} min${mins === 1 ? '' : 's'} ago`;
            }
            if (seconds < 86400) {
                const hours = Math.floor(seconds / 3600);
                return `${hours} hr${hours === 1 ? '' : 's'} ago`;
            }
            const days = Math.floor(seconds / 86400);
            return `${days} day${days === 1 ? '' : 's'} ago`;
        }

        function formatLastSeen(value) {
            const date = parseServerDate(value);
            if (!date) return 'No heartbeat yet';
            return `Last seen ${formatRelative(value)} · ${formatDateTime(value)}`;
        }

        function formatPresence(csr) {
            if (csr.is_online) return 'Online now';
            const reference = csr.last_seen_at || csr.last_assigned_at;
            return reference ? formatLastSeen(reference) : 'No heartbeat yet';
        }

        function showBanner(message, tone = 'success') {
            if (!flashBanner) return;
            flashBanner.textContent = message;
            flashBanner.className = `flash-banner show ${tone}`;
            flashBanner.scrollIntoView({ behavior: 'smooth', block: 'nearest' });
            window.clearTimeout(flashTimer);
            flashTimer = window.setTimeout(() => {
                flashBanner.className = 'flash-banner';
            }, 5000);
        }

        async function requestJson(url, options = {}) {
            const response = await fetch(url, {
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Admin-Page': currentPage,
                    'X-Portal': 'admin',
                    ...(options.headers || {})
                },
                ...options
            });

            const payload = await response.json().catch(() => ({}));
            if (!response.ok) {
                throw new Error(payload.error || payload.message || 'Request failed');
            }
            return payload;
        }

        function getSelectedChat() {
            if (!state.dashboard || !state.selectedChatId) return null;
            return state.dashboard.chats.find((chat) => chat.id === state.selectedChatId) || null;
        }

        /* Credentials tab temporarily disabled
        function normalizeBaseUrl(value) {
            return String(value || '').trim().replace(/\/+$/, '');
        }

        function normalizeScriptSrc(value, baseUrl) {
            const raw = String(value || '').trim();
            const normalizedBaseUrl = normalizeBaseUrl(baseUrl);
            if (!raw) return normalizedBaseUrl ? `${normalizedBaseUrl}/widget-assets/csr-dashboard-widget.js` : '/widget-assets/csr-dashboard-widget.js';
            if (raw.startsWith('http://') || raw.startsWith('https://')) return raw;
            const normalizedPath = raw.startsWith('/') ? raw : `/${raw}`;
            return normalizedBaseUrl ? `${normalizedBaseUrl}${normalizedPath}` : normalizedPath;
        }

        function normalizePositiveInt(value, fallback) {
            const parsed = Number.parseInt(value, 10);
            return Number.isFinite(parsed) && parsed > 0 ? parsed : fallback;
        }

        function buildIntegrationPreview(settings) {
            const normalized = {
                page_title: String(settings.page_title || '').trim() || 'Frontline Customer Care CSR Widget',
                base_url: normalizeBaseUrl(settings.base_url),
                container_id: String(settings.container_id || '').trim() || 'csr-console',
                csr_key: String(settings.csr_key || '').trim(),
                widget_title: String(settings.widget_title || '').trim() || 'FLT CSR',
                primary_color: String(settings.primary_color || '').trim() || '#2563EB',
                auto_activate: Boolean(settings.auto_activate),
                chat_list_poll: normalizePositiveInt(settings.chat_list_poll, 5000),
                message_poll: normalizePositiveInt(settings.message_poll, 3000),
                relay_api_url: normalizeBaseUrl(settings.relay_api_url),
                relay_api_key: String(settings.relay_api_key || '').trim()
            };

            normalized.script_src = normalizeScriptSrc(settings.script_src, normalized.base_url);

            const configObject = {
                autoActivate: normalized.auto_activate,
                baseUrl: normalized.base_url,
                chatListPoll: normalized.chat_list_poll,
                containerId: normalized.container_id,
                csrKey: normalized.csr_key,
                messagePoll: normalized.message_poll,
                primaryColor: normalized.primary_color,
                widgetTitle: normalized.widget_title
            };
            const closingScript = '</' + 'script>';
            const pageHtml = `<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="UTF-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>${normalized.page_title}</title>
</head>
<body>
  <div id="${normalized.container_id}"></div>
  <script>
  window.CSRDashboardWidgetConfig = ${JSON.stringify(configObject, null, 2)};
  ${closingScript}
  <script src="${normalized.script_src}">${closingScript}
</body>
</html>`;

            return {
                ...normalized,
                relay_enabled: Boolean(normalized.relay_api_url && (normalized.relay_api_key || normalized.csr_key)),
                config_object: configObject,
                page_html: pageHtml
            };
        }

        function readIntegrationForm() {
            const form = document.getElementById('integration-settings-form');
            return {
                page_title: form.elements.page_title.value,
                base_url: form.elements.base_url.value,
                container_id: form.elements.container_id.value,
                csr_key: form.elements.csr_key.value,
                widget_title: form.elements.widget_title.value,
                primary_color: form.elements.primary_color.value,
                auto_activate: form.elements.auto_activate.checked,
                chat_list_poll: form.elements.chat_list_poll.value,
                message_poll: form.elements.message_poll.value,
                script_src: form.elements.script_src.value,
                relay_api_url: form.elements.relay_api_url.value,
                relay_api_key: form.elements.relay_api_key.value
            };
        }

        function fillIntegrationForm(settings) {
            const form = document.getElementById('integration-settings-form');
            form.elements.page_title.value = settings.page_title || '';
            form.elements.base_url.value = settings.base_url || '';
            form.elements.container_id.value = settings.container_id || '';
            form.elements.csr_key.value = settings.csr_key || '';
            form.elements.widget_title.value = settings.widget_title || '';
            form.elements.primary_color.value = settings.primary_color || '';
            form.elements.auto_activate.checked = Boolean(settings.auto_activate);
            form.elements.chat_list_poll.value = settings.chat_list_poll || 5000;
            form.elements.message_poll.value = settings.message_poll || 3000;
            form.elements.script_src.value = settings.script_src || '';
            form.elements.relay_api_url.value = settings.relay_api_url || '';
            form.elements.relay_api_key.value = settings.relay_api_key || '';
        }

        function renderIntegrationPreview(settings) {
            const preview = buildIntegrationPreview(settings);
            document.getElementById('integration-relay-status').textContent = preview.relay_enabled
                ? `Ready using ${preview.relay_api_key ? 'relay API key override' : 'CSR key'}`
                : 'Relay is inactive until relay URL and a key are configured';
            document.getElementById('integration-script-src').textContent = preview.script_src || 'Not configured';
            document.getElementById('integration-base-url').textContent = preview.base_url || 'Not configured';
            document.getElementById('integration-script-preview').value = preview.page_html;

            const previewLink = document.getElementById('integration-preview-link');
            previewLink.href = state.dashboard?.integration?.preview_url || '/static/csr-dashboard-app.html';
        }

        function renderIntegrationSettings(forceSync = false) {
            const savedSettings = state.dashboard.integration.settings || {};
            if (!state.integrationDraftDirty || forceSync) {
                fillIntegrationForm(savedSettings);
                state.integrationDraftDirty = false;
                renderIntegrationPreview(savedSettings);
                return;
            }

            renderIntegrationPreview(readIntegrationForm());
        }
        */

        function renderSummary() {
            const summary = state.dashboard.summary;
            document.getElementById('stat-registered').textContent = summary.registered_csrs;
            document.getElementById('stat-online').textContent = summary.online_csrs;
            document.getElementById('stat-active-csrs').textContent = summary.active_csrs;
            document.getElementById('stat-active').textContent = summary.active_chats;
            document.getElementById('stat-resolved-today').textContent = summary.resolved_today;
            document.getElementById('stat-resolved-yesterday').textContent = summary.resolved_yesterday;
        }

        function renderAvailableCsrList() {
            const container = document.getElementById('available-csr-list');
            const rows = state.dashboard.available_csr_users || [];
            document.getElementById('available-csr-count').textContent = `${rows.length} assignable`;

            if (!rows.length) {
                container.innerHTML = '<div class="tiny-note">No CSR is online and available for new assignments right now.</div>';
                return;
            }

            container.innerHTML = rows.map((csr) => `
                <article class="leaderboard-item">
                    <div class="item-head">
                        <div>
                            <div style="font-size:14px;font-weight:800;">${escapeHtml(csr.display_name)}</div>
                            <div class="tiny-note">${escapeHtml(csr.email)}</div>
                        </div>
                        <span class="badge online">Available</span>
                    </div>
                    <div class="row" style="margin-top:10px;">
                        <div class="tiny-note">Open chats ${csr.active_chat_count}</div>
                        <div class="tiny-note">${escapeHtml(formatPresence(csr))}</div>
                    </div>
                    <div class="load-bar"><span style="width:${Math.max(8, Math.min(40, Number(csr.active_chat_count || 0) * 4))}%"></span></div>
                </article>
            `).join('');
        }

        const CHART_THEME = {
            bg: '#eef2f7',
            emptyBg: '#e2e8f0',
            title: '#0f172a',
            detail: '#475569',
            legend: '#334155',
            axis: '#475569',
            grid: 'rgba(15, 23, 42, 0.08)',
            gridStrong: 'rgba(15, 23, 42, 0.16)',
            lane: 'rgba(15, 23, 42, 0.04)',
            value: '#0f172a',
            label: '#334155',
            donutTotal: '#0f172a',
            donutSub: '#475569',
            legendRowBg: '#ffffff',
            legendRowBorder: 'rgba(15, 23, 42, 0.08)',
            legendMeta: '#64748b',
        };

        function prepareCanvas(canvas) {
            const ratio = window.devicePixelRatio || 1;
            const rect = canvas.getBoundingClientRect();
            const width = Math.max(1, Math.round(rect.width || canvas.clientWidth || 300));
            const fallbackHeight = Number(canvas.getAttribute('height')) || 220;
            const height = Math.max(1, Math.round(rect.height || canvas.clientHeight || fallbackHeight));
            const ctx = canvas.getContext('2d');

            canvas.width = width * ratio;
            canvas.height = height * ratio;
            ctx.setTransform(1, 0, 0, 1, 0, 0);
            ctx.clearRect(0, 0, canvas.width, canvas.height);
            ctx.setTransform(ratio, 0, 0, ratio, 0, 0);
            ctx.lineJoin = 'round';
            ctx.lineCap = 'round';
            ctx.textBaseline = 'middle';
            ctx.fillStyle = CHART_THEME.bg;
            ctx.fillRect(0, 0, width, height);

            return { ctx, w: width, h: height };
        }

        function fillRoundedRect(ctx, x, y, width, height, radius, color) {
            if (width <= 0 || height <= 0) {
                return;
            }

            const safeRadius = Math.min(radius, width / 2, height / 2);
            ctx.beginPath();
            ctx.moveTo(x + safeRadius, y);
            ctx.lineTo(x + width - safeRadius, y);
            ctx.quadraticCurveTo(x + width, y, x + width, y + safeRadius);
            ctx.lineTo(x + width, y + height - safeRadius);
            ctx.quadraticCurveTo(x + width, y + height, x + width - safeRadius, y + height);
            ctx.lineTo(x + safeRadius, y + height);
            ctx.quadraticCurveTo(x, y + height, x, y + height - safeRadius);
            ctx.lineTo(x, y + safeRadius);
            ctx.quadraticCurveTo(x, y, x + safeRadius, y);
            ctx.closePath();
            ctx.fillStyle = color;
            ctx.fill();
        }

        function truncateLabel(ctx, text, maxWidth) {
            if (ctx.measureText(text).width <= maxWidth) {
                return text;
            }

            let trimmed = text;
            while (trimmed.length > 1 && ctx.measureText(`${trimmed}…`).width > maxWidth) {
                trimmed = trimmed.slice(0, -1);
            }
            return `${trimmed}…`;
        }

        function drawChartEmptyState(ctx, w, h, title, detail) {
            fillRoundedRect(ctx, 18, 18, w - 36, h - 36, 16, CHART_THEME.emptyBg);
            ctx.textAlign = 'center';
            ctx.fillStyle = CHART_THEME.title;
            ctx.font = '700 15px Inter';
            ctx.fillText(title, w / 2, h / 2 - 10);
            ctx.fillStyle = CHART_THEME.detail;
            ctx.font = '12px Inter';
            ctx.fillText(detail, w / 2, h / 2 + 14);
            ctx.textAlign = 'left';
        }

        function getScaleMax(maxValue) {
            if (maxValue <= 4) {
                return maxValue;
            }

            const magnitude = 10 ** Math.floor(Math.log10(maxValue));
            const normalized = maxValue / magnitude;
            if (normalized <= 1) return magnitude;
            if (normalized <= 2) return 2 * magnitude;
            if (normalized <= 5) return 5 * magnitude;
            return 10 * magnitude;
        }

        function drawBarChart(canvas, rows) {
            const { ctx, w, h } = prepareCanvas(canvas);
            const metrics = [
                { key: 'resolved_today', label: 'Today', color: '#14b8a6' },
                { key: 'resolved_yesterday', label: 'Yesterday', color: '#10b981' },
                { key: 'open_chats', label: 'Open Chats', color: '#f59e0b' }
            ];
            const chartRows = rows.filter((row) => metrics.some((metric) => Number(row[metric.key] || 0) > 0));
            if (!chartRows.length) {
                drawChartEmptyState(ctx, w, h, 'No resolution data yet', 'CSR activity will appear here once chats are handled.');
                return;
            }

            const maxValue = Math.max(...chartRows.flatMap((row) => metrics.map((metric) => Number(row[metric.key] || 0))));

            const compact = w < 760;
            const legendRowHeight = compact ? 22 : 0;
            const padding = { top: compact ? 60 : 42, right: 18, bottom: 38, left: 44 };
            const chartWidth = w - padding.left - padding.right;
            const slotPx = 108;
            const plotWidth = Math.min(chartWidth, Math.max(200, chartRows.length * slotPx));
            const plotLeft = padding.left + (chartWidth - plotWidth) / 2;
            const chartHeight = h - padding.top - padding.bottom;
            const scaleMax = getScaleMax(maxValue);
            const gridLines = Math.min(4, scaleMax) || 1;

            ctx.font = '600 12px Inter';
            ctx.textAlign = 'left';
            metrics.forEach((metric, index) => {
                const legendX = compact
                    ? padding.left + (index % 2) * 126
                    : padding.left + index * 116;
                const legendY = compact
                    ? 18 + Math.floor(index / 2) * legendRowHeight
                    : 18;
                fillRoundedRect(ctx, legendX, legendY - 6, 12, 12, 4, metric.color);
                ctx.fillStyle = CHART_THEME.legend;
                ctx.fillText(metric.label, legendX + 18, legendY);
            });

            for (let index = 0; index <= gridLines; index += 1) {
                const y = padding.top + (chartHeight / gridLines) * index;
                const value = scaleMax - (scaleMax / gridLines) * index;
                ctx.beginPath();
                ctx.strokeStyle = index === gridLines ? CHART_THEME.gridStrong : CHART_THEME.grid;
                ctx.lineWidth = 1;
                ctx.moveTo(plotLeft, y);
                ctx.lineTo(plotLeft + plotWidth, y);
                ctx.stroke();

                ctx.fillStyle = CHART_THEME.axis;
                ctx.font = '11px Inter';
                ctx.textAlign = 'right';
                ctx.fillText(Number.isInteger(value) ? String(value) : value.toFixed(1), padding.left - 8, y);
            }

            const groupWidth = plotWidth / chartRows.length;
            const groupGap = Math.max(12, groupWidth * 0.12);
            const availableBarWidth = Math.max(30, groupWidth - groupGap);
            const barGap = Math.max(6, Math.min(10, availableBarWidth * 0.08));
            const barWidth = Math.max(10, Math.min(24, (availableBarWidth - barGap * (metrics.length - 1)) / metrics.length));

            ctx.beginPath();
            ctx.strokeStyle = CHART_THEME.gridStrong;
            ctx.lineWidth = 1.2;
            ctx.moveTo(plotLeft, padding.top + chartHeight);
            ctx.lineTo(plotLeft + plotWidth, padding.top + chartHeight);
            ctx.stroke();

            chartRows.forEach((row, index) => {
                const totalBarsWidth = metrics.length * barWidth + (metrics.length - 1) * barGap;
                const groupStartX = plotLeft + index * groupWidth + (groupWidth - totalBarsWidth) / 2;

                metrics.forEach((metric, metricIndex) => {
                    const rawValue = Number(row[metric.key] || 0);
                    const barHeight = rawValue ? (rawValue / scaleMax) * chartHeight : 0;
                    const x = groupStartX + metricIndex * (barWidth + barGap);
                    const y = padding.top + chartHeight - barHeight;

                    if (barHeight > 0) {
                        fillRoundedRect(ctx, x, y, barWidth, barHeight, 8, metric.color);
                        ctx.fillStyle = CHART_THEME.value;
                        ctx.font = '600 11px Inter';
                        ctx.textAlign = 'center';
                        ctx.fillText(String(rawValue), x + barWidth / 2, Math.max(padding.top - 10, y - 8));
                    }
                });

                ctx.fillStyle = CHART_THEME.label;
                ctx.font = '600 12px Inter';
                ctx.textAlign = 'center';
                const label = truncateLabel(ctx, row.display_name || 'CSR', groupWidth - 10);
                ctx.fillText(label, plotLeft + index * groupWidth + groupWidth / 2, h - 18);
            });

            ctx.textAlign = 'left';
        }

        function drawDonutChart(canvas, statusBreakdown) {
            const compactHeight = canvas.getBoundingClientRect().width < 430;
            canvas.style.height = `${compactHeight ? 286 : 220}px`;
            const { ctx, w, h } = prepareCanvas(canvas);
            const entries = [
                { label: 'Queued', value: statusBreakdown.queued || 0, color: '#f59e0b' },
                { label: 'Assigned', value: statusBreakdown.assigned || 0, color: '#14b8a6' },
                { label: 'In Progress', value: statusBreakdown.in_progress || 0, color: '#06b6d4' },
                { label: 'Resolved', value: statusBreakdown.resolved || 0, color: '#10b981' }
            ];
            const total = entries.reduce((sum, entry) => sum + entry.value, 0);

            if (!total) {
                drawChartEmptyState(ctx, w, h, 'No status data yet', 'Queued, active, and resolved chat totals will show here.');
                return;
            }

            const compact = w < 430;
            const centerX = compact ? w / 2 : Math.min(132, w * 0.31);
            const centerY = compact ? 64 : h / 2;
            const radius = compact ? 44 : Math.min(68, h * 0.29);
            const ringWidth = Math.max(12, radius * 0.24);
            const segmentRadius = radius - ringWidth / 2;
            const legendX = compact ? 18 : Math.max(228, w * 0.58);
            const legendStartY = compact ? 132 : 40;
            let startAngle = -Math.PI / 2;

            ctx.beginPath();
            ctx.strokeStyle = CHART_THEME.grid;
            ctx.lineWidth = ringWidth;
            ctx.arc(centerX, centerY, segmentRadius, 0, Math.PI * 2);
            ctx.stroke();

            entries.filter((entry) => entry.value > 0).forEach((entry) => {
                const sliceAngle = (entry.value / total) * Math.PI * 2;
                const gap = Math.min(0.04, sliceAngle / 5);
                ctx.beginPath();
                ctx.strokeStyle = entry.color;
                ctx.lineWidth = ringWidth;
                ctx.arc(centerX, centerY, segmentRadius, startAngle + gap / 2, startAngle + sliceAngle - gap / 2);
                ctx.stroke();
                startAngle += sliceAngle;
            });

            ctx.textAlign = 'center';
            ctx.fillStyle = CHART_THEME.donutTotal;
            ctx.font = '700 22px Inter';
            ctx.fillText(String(total), centerX, centerY - 8);
            ctx.fillStyle = CHART_THEME.donutSub;
            ctx.font = '600 10px Inter';
            ctx.fillText('Tracked', centerX, centerY + 10);
            ctx.fillText('chats', centerX, centerY + 22);

            entries.forEach((entry, index) => {
                const legendY = legendStartY + index * 34;
                const percent = total ? Math.round((entry.value / total) * 100) : 0;

                fillRoundedRect(ctx, legendX, legendY - 10, compact ? w - 36 : Math.max(120, w - legendX - 18), 28, 10, CHART_THEME.legendRowBg);
                fillRoundedRect(ctx, legendX + 10, legendY - 3, 10, 10, 4, entry.color);
                ctx.textAlign = 'left';
                ctx.fillStyle = CHART_THEME.legend;
                ctx.font = '600 12px Inter';
                ctx.fillText(entry.label, legendX + 28, legendY + 1);
                ctx.fillStyle = CHART_THEME.legendMeta;
                ctx.font = '11px Inter';
                ctx.fillText(`${entry.value} chats`, legendX + 28, legendY + 13);
                ctx.textAlign = 'right';
                ctx.fillStyle = CHART_THEME.axis;
                ctx.font = '700 11px Inter';
                ctx.fillText(`${percent}%`, compact ? w - 30 : w - 24, legendY + 1);
            });

            ctx.textAlign = 'left';
        }

        function renderCharts(force = false) {
            renderCsrOverview();
            const signature = buildChartSignature(state.dashboard);
            if (!force && signature && signature === state.chartSignature) {
                return;
            }
            state.chartSignature = signature;
            drawDonutChart(document.getElementById('status-chart'), state.dashboard.reports.status_breakdown || {});
            drawBarChart(document.getElementById('resolution-chart'), state.dashboard.reports.resolution_leaderboard || []);
        }

        function renderCsrOverview() {
            const container = document.getElementById('csr-overview-list');
            if (!container) return;

            const rows = [...(state.dashboard.csr_users || [])].sort((left, right) => {
                if (Boolean(left.is_online) !== Boolean(right.is_online)) return left.is_online ? -1 : 1;
                const workloadDifference = Number(right.active_chat_count || 0) - Number(left.active_chat_count || 0);
                if (workloadDifference) return workloadDifference;
                return String(left.display_name || left.email).localeCompare(String(right.display_name || right.email));
            });
            const leaderboard = new Map((state.dashboard.reports.resolution_leaderboard || []).map((row) => [row.id, row]));

            if (!rows.length) {
                container.innerHTML = '<div class="tiny-note">No CSR accounts are available yet.</div>';
                return;
            }

            container.innerHTML = rows.map((csr) => {
                const report = leaderboard.get(csr.id) || {};
                const activeChats = Number(report.open_chats ?? csr.active_chat_count ?? 0);
                return `
                    <article class="csr-overview-card">
                        <div class="csr-overview-head">
                            <div class="csr-overview-identity">
                                <div class="csr-overview-name">${escapeHtml(csr.display_name || csr.email)}</div>
                                <div class="csr-overview-email" title="${escapeHtml(csr.email)}">${escapeHtml(csr.email)}</div>
                            </div>
                            <span class="badge ${csr.is_online ? 'online' : 'offline'}">${csr.is_online ? 'Online' : 'Offline'}</span>
                        </div>
                        <div class="csr-overview-state">
                            <span class="availability-badge ${csr.is_available ? 'available' : 'paused'}">
                                <i class="fa-solid ${csr.is_available ? 'fa-circle-check' : 'fa-circle-pause'}"></i>
                                ${csr.is_available ? 'Available' : 'Paused'}
                            </span>
                        </div>
                        <div class="csr-overview-metrics">
                            <div class="csr-metric today"><strong>${Number(report.resolved_today || 0)}</strong><span>Resolved today</span></div>
                            <div class="csr-metric yesterday"><strong>${Number(report.resolved_yesterday || 0)}</strong><span>Yesterday</span></div>
                            <div class="csr-metric open"><strong>${activeChats}</strong><span>Open chats</span></div>
                        </div>
                    </article>
                `;
            }).join('');
        }

        function renderCsrTable() {
            const list = document.getElementById('csr-roster-list');
            if (!list) return;
            const rows = state.dashboard.csr_users || [];
            const availableNow = state.dashboard.available_csr_users || [];
            const leaderboard = new Map((state.dashboard.reports.resolution_leaderboard || []).map((row) => [row.id, row]));
            const rosterCount = document.getElementById('roster-count');
            if (rosterCount) {
                rosterCount.textContent = `${rows.length} registered · ${availableNow.length} available now`;
            }

            if (!rows.length) {
                list.innerHTML = '<div class="tiny-note p-6">No CSR accounts have been registered yet.</div>';
                return;
            }

            list.innerHTML = rows.map((csr) => {
                const report = leaderboard.get(csr.id) || { resolved_today: 0, resolved_yesterday: 0 };
                return `
                    <article class="csr-roster-card">
                        <div class="csr-roster-head">
                            <div class="csr-roster-identity">
                                <div class="csr-roster-name">${escapeHtml(csr.display_name || csr.email)}</div>
                                <div class="csr-roster-email" title="${escapeHtml(csr.email)}">${escapeHtml(csr.email)}</div>
                            </div>
                            <span class="badge ${csr.is_online ? 'online' : 'offline'}">${csr.is_online ? 'Online' : 'Offline'}</span>
                        </div>
                        <div class="csr-roster-presence">${escapeHtml(formatPresence(csr))}</div>
                        <div class="csr-roster-metrics">
                            <div class="csr-roster-metric load">
                                <span>Open chats</span>
                                <strong>${csr.active_chat_count}</strong>
                                <small>Current workload</small>
                            </div>
                            <div class="csr-roster-metric today">
                                <span>Resolved today</span>
                                <strong>${report.resolved_today}</strong>
                                <small>Since midnight</small>
                            </div>
                            <div class="csr-roster-metric yesterday">
                                <span>Resolved yesterday</span>
                                <strong>${report.resolved_yesterday}</strong>
                                <small>Previous day</small>
                            </div>
                        </div>
                        <form class="settings-form csr-roster-actions" data-csr-id="${csr.id}">
                            <label class="availability-control">
                                <input type="checkbox" name="is_available" ${csr.is_available ? 'checked' : ''}>
                                <span>Available for assignments</span>
                            </label>
                            <div class="csr-save-group">
                                <span class="csr-save-status" role="status" aria-live="polite"></span>
                                <button class="mini-btn csr-password-reset-toggle" type="button" aria-expanded="false"><i class="fa-solid fa-key"></i> <span>Reset password</span></button>
                                <button class="mini-btn primary csr-save-btn" type="submit"><i class="fa-solid fa-check"></i> <span>Save</span></button>
                            </div>
                        </form>
                        <div class="csr-password-reset" hidden>
                            <label for="csr-password-${csr.id}">New password</label>
                            <div class="csr-password-reset-fields">
                                <input class="input" id="csr-password-${csr.id}" type="password" minlength="6" autocomplete="new-password" placeholder="At least 6 characters">
                                <button class="mini-btn primary csr-password-update" type="button" data-csr-id="${csr.id}"><i class="fa-solid fa-key"></i> Update password</button>
                            </div>
                            <span class="csr-password-reset-status" role="status" aria-live="polite"></span>
                        </div>
                    </article>
                `;
            }).join('');

            list.querySelectorAll('.settings-form').forEach((form) => {
                const checkbox = form.querySelector('input[name="is_available"]');
                const saveButton = form.querySelector('.csr-save-btn');
                const saveButtonIcon = saveButton.querySelector('i');
                const saveButtonLabel = saveButton.querySelector('span');
                const saveStatus = form.querySelector('.csr-save-status');

                checkbox.addEventListener('change', () => {
                    form.classList.add('is-dirty');
                    saveButton.classList.remove('is-saved');
                    saveButtonIcon.className = 'fa-solid fa-check';
                    saveStatus.className = 'csr-save-status pending';
                    saveStatus.textContent = 'Unsaved';
                    saveButtonLabel.textContent = 'Save changes';
                });

                form.addEventListener('submit', async (event) => {
                    event.preventDefault();
                    const csrId = form.dataset.csrId;
                    const isAvailable = checkbox.checked;
                    saveButton.disabled = true;
                    saveButton.classList.add('is-saving');
                    saveButtonIcon.className = 'fa-solid fa-spinner';
                    saveButtonLabel.textContent = 'Saving...';
                    saveStatus.className = 'csr-save-status saving';
                    saveStatus.textContent = 'Saving';
                    try {
                        const response = await requestJson(`/api/csrs/${csrId}/settings`, {
                            method: 'POST',
                            body: JSON.stringify({
                                is_available: isAvailable
                            })
                        });
                        state.dashboard = response.dashboard;
                        renderCurrentPage();
                        const updatedForm = list.querySelector(`.csr-roster-actions[data-csr-id="${csrId}"]`);
                        if (updatedForm) {
                            const updatedStatus = updatedForm.querySelector('.csr-save-status');
                            const updatedButton = updatedForm.querySelector('.csr-save-btn');
                            const updatedButtonIcon = updatedButton.querySelector('i');
                            const updatedButtonLabel = updatedButton.querySelector('span');
                            updatedButton.classList.add('is-saved');
                            updatedButton.disabled = false;
                            updatedButtonIcon.className = 'fa-solid fa-circle-check';
                            updatedStatus.className = 'csr-save-status saved';
                            updatedStatus.textContent = 'Saved';
                            updatedButtonLabel.textContent = 'Saved';
                        }
                        showBanner(response.message || 'CSR settings updated.', 'success');
                    } catch (error) {
                        saveButton.disabled = false;
                        saveButton.classList.remove('is-saving');
                        saveButtonIcon.className = 'fa-solid fa-triangle-exclamation';
                        saveButtonLabel.textContent = 'Try again';
                        saveStatus.className = 'csr-save-status error';
                        saveStatus.textContent = error.message;
                        showBanner(error.message, 'error');
                    }
                });
            });

            list.querySelectorAll('.csr-password-reset-toggle').forEach((button) => {
                button.addEventListener('click', () => {
                    const card = button.closest('.csr-roster-card');
                    const resetPanel = card.querySelector('.csr-password-reset');
                    const willOpen = resetPanel.hidden;
                    resetPanel.hidden = !willOpen;
                    button.setAttribute('aria-expanded', String(willOpen));
                    button.querySelector('span').textContent = willOpen ? 'Cancel reset' : 'Reset password';
                    if (willOpen) card.querySelector('.csr-password-reset input').focus();
                });
            });

            list.querySelectorAll('.csr-password-update').forEach((button) => {
                button.addEventListener('click', async () => {
                    const card = button.closest('.csr-roster-card');
                    const input = card.querySelector('.csr-password-reset input');
                    const status = card.querySelector('.csr-password-reset-status');
                    const password = input.value;
                    if (password.length < 6) {
                        status.className = 'csr-password-reset-status error';
                        status.textContent = 'Use at least 6 characters.';
                        input.focus();
                        return;
                    }

                    button.disabled = true;
                    button.classList.add('is-saving');
                    const original = button.innerHTML;
                    button.innerHTML = '<i class="fa-solid fa-spinner"></i> Updating...';
                    status.className = 'csr-password-reset-status';
                    status.textContent = '';
                    try {
                        const response = await requestJson(`/api/csrs/${button.dataset.csrId}/password`, {
                            method: 'POST',
                            body: JSON.stringify({ password })
                        });
                        input.value = '';
                        status.className = 'csr-password-reset-status success';
                        status.textContent = 'Password updated.';
                        showBanner(response.message || 'CSR password updated.', 'success');
                        window.setTimeout(() => {
                            const resetPanel = card.querySelector('.csr-password-reset');
                            const toggle = card.querySelector('.csr-password-reset-toggle');
                            if (!resetPanel || !toggle) return;
                            resetPanel.hidden = true;
                            toggle.setAttribute('aria-expanded', 'false');
                            toggle.querySelector('span').textContent = 'Reset password';
                        }, 1800);
                    } catch (error) {
                        status.className = 'csr-password-reset-status error';
                        status.textContent = error.message;
                        showBanner(error.message, 'error');
                    } finally {
                        button.disabled = false;
                        button.classList.remove('is-saving');
                        button.innerHTML = original;
                    }
                });
            });
        }

        function chatStatusBadgeClass(status) {
            const normalized = String(status || '').toLowerCase();
            if (normalized === 'queued') return 'queued';
            if (normalized === 'assigned') return 'assigned';
            if (normalized === 'in_progress') return 'in-progress';
            if (normalized === 'resolved') return 'resolved';
            if (normalized === 'closed') return 'closed';
            return 'neutral';
        }

        function chatStatusLabel(status) {
            const labels = {
                queued: 'Queued',
                assigned: 'Assigned',
                in_progress: 'In Progress',
                resolved: 'Resolved',
                closed: 'Closed',
            };
            return labels[String(status || '').toLowerCase()] || String(status || 'Unknown').replaceAll('_', ' ');
        }

        function renderChatTable() {
            const tbody = document.getElementById('chat-table-body');
            const chats = state.dashboard.chats || [];
            const pagination = state.dashboard.chats_pagination || null;
            const total = pagination ? pagination.total : chats.length;
            document.getElementById('chat-count').textContent = `${total} chat${total === 1 ? '' : 's'}`;

            if (!chats.length) {
                const emptyMsg = currentPage === 'chats-active'
                    ? 'No active chats right now.'
                    : 'No chats have been stored yet.';
                tbody.innerHTML = `<tr><td colspan="7" class="tiny-note" style="padding:24px;">${emptyMsg}</td></tr>`;
                renderChatPagination(pagination);
                return;
            }

            tbody.innerHTML = chats.map((chat) => `
                <tr class="${state.selectedChatId === chat.id ? 'is-selected' : ''}">
                    <td data-label="Customer">
                        <strong>${escapeHtml(chat.customer_name || chat.visitor_id)}</strong><br>
                        <span class="cell-subtle chat-id" title="${escapeHtml(chat.visitor_id)}">${escapeHtml(chat.visitor_id)}</span>
                    </td>
                    <td data-label="Status"><span class="chat-badge status-badge ${chatStatusBadgeClass(chat.status)}" title="${escapeHtml(chatStatusLabel(chat.status))}">${escapeHtml(chatStatusLabel(chat.status))}</span></td>
                    <td data-label="Assigned"><span class="chat-badge ${chat.assigned_label ? 'assigned' : 'waiting'}" title="${escapeHtml(chat.assigned_label || 'Waiting queue')}">${escapeHtml(chat.assigned_label || 'Waiting queue')}</span></td>
                    <td data-label="Messages"><span class="chat-badge count">${chat.message_count}</span></td>
                    <td data-label="Last Activity">
                        ${escapeHtml(formatRelative(chat.last_activity_at))}<br>
                        <span class="cell-subtle">${escapeHtml(formatDateTime(chat.last_activity_at))}</span>
                    </td>
                    <td data-label="Preview" title="${escapeHtml(chat.last_customer_message || chat.preview || 'No customer message yet.')}">${escapeHtml(chat.last_customer_message || chat.preview || 'No customer message yet.')}</td>
                    <td data-label="Actions">
                        <div class="action-row">
                            <button class="mini-btn" type="button" data-view-chat="${chat.id}">View</button>
                            <button class="mini-btn danger" type="button" data-delete-chat="${chat.id}">Delete</button>
                        </div>
                    </td>
                </tr>
            `).join('');

            tbody.querySelectorAll('[data-view-chat]').forEach((button) => {
                button.addEventListener('click', () => {
                    selectChat(Number(button.dataset.viewChat)).catch((error) => showBanner(error.message, 'error'));
                });
            });

            tbody.querySelectorAll('[data-delete-chat]').forEach((button) => {
                button.addEventListener('click', async () => {
                    const chatId = Number(button.dataset.deleteChat);
                    const chat = state.dashboard.chats.find((item) => item.id === chatId);
                    if (!chat) return;
                    const confirmed = window.confirm(`Delete chat ${chat.visitor_id} and all related messages from the database?`);
                    if (!confirmed) return;
                    try {
                        const response = await requestJson(`/api/chats/${chatId}/delete`, {
                            method: 'POST',
                            body: JSON.stringify({})
                        });
                        if (state.selectedChatId === chatId) {
                            state.selectedChatId = null;
                            state.selectedMessages = [];
                            state.selectedEvents = [];
                        }
                        state.dashboard = response.dashboard;
                        renderCurrentPage();
                        showBanner(response.message || 'Chat deleted.', 'success');
                    } catch (error) {
                        showBanner(error.message, 'error');
                    }
                });
            });

            renderChatPagination(pagination);
        }

        function renderChatPagination(pagination) {
            const bar = document.getElementById('chat-pagination');
            if (!bar) return;
            if (!pagination || pagination.total === 0) {
                bar.style.display = 'none';
                return;
            }
            bar.style.display = 'flex';

            // Keep client state in sync with the server’s clamped page number
            // so “Next”/“Prev” stay accurate if the dataset changed.
            state.chatPage = pagination.page;
            state.chatPerPage = pagination.per_page;
            const perPageSel = document.getElementById('chat-per-page');
            if (perPageSel && Number(perPageSel.value) !== pagination.per_page) {
                perPageSel.value = String(pagination.per_page);
            }

            const start = (pagination.page - 1) * pagination.per_page + 1;
            const end = Math.min(pagination.total, pagination.page * pagination.per_page);
            document.getElementById('chat-page-info').textContent =
                `Showing ${start}–${end} of ${pagination.total} chats (page ${pagination.page} of ${pagination.total_pages})`;

            const btns = document.getElementById('chat-page-buttons');
            const pages = buildPageList(pagination.page, pagination.total_pages);
            const html = [];
            html.push(`<button class="page-btn" data-page="prev" ${pagination.has_prev ? '' : 'disabled'}>‹ Prev</button>`);
            pages.forEach((entry) => {
                if (entry === '...') {
                    html.push('<span class="page-btn" style="cursor:default;border:none;">…</span>');
                } else {
                    html.push(`<button class="page-btn ${entry === pagination.page ? 'active' : ''}" data-page="${entry}">${entry}</button>`);
                }
            });
            html.push(`<button class="page-btn" data-page="next" ${pagination.has_next ? '' : 'disabled'}>Next ›</button>`);
            btns.innerHTML = html.join('');

            btns.querySelectorAll('button[data-page]').forEach((btn) => {
                btn.addEventListener('click', () => {
                    const val = btn.dataset.page;
                    let target = pagination.page;
                    if (val === 'prev') target = pagination.page - 1;
                    else if (val === 'next') target = pagination.page + 1;
                    else target = Number(val);
                    if (target < 1 || target > pagination.total_pages || target === pagination.page) return;
                    state.chatPage = target;
                    refreshDashboard(false).catch((error) => showBanner(error.message, 'error'));
                });
            });
        }

        // Condensed numeric pager: show first, last and a window around the current page.
        function buildPageList(current, total) {
            const out = [];
            if (total <= 7) {
                for (let i = 1; i <= total; i += 1) out.push(i);
                return out;
            }
            out.push(1);
            if (current > 3) out.push('...');
            const start = Math.max(2, current - 1);
            const end = Math.min(total - 1, current + 1);
            for (let i = start; i <= end; i += 1) out.push(i);
            if (current < total - 2) out.push('...');
            out.push(total);
            return out;
        }

        function renderMessages(messages) {
            if (!messages.length) {
                return `
                    <div class="empty-state">
                        <i class="fa-solid fa-comments"></i>
                        <div>No transcript stored for this chat yet.</div>
                    </div>
                `;
            }

            return messages.map((message) => {
                const senderLabel = message.sender_type === 'user'
                    ? 'Customer'
                    : message.sender_type === 'csr'
                        ? 'CSR'
                        : String(message.sender_type || 'System').replaceAll('_', ' ');
                return `
                <div class="message ${escapeHtml(message.sender_type)}">
                    <div class="message-label">${escapeHtml(senderLabel)}</div>
                    <div class="message-bubble">${escapeHtml(message.content)}</div>
                    <div class="message-time">${escapeHtml(formatDateTime(message.created_at))}</div>
                </div>
            `;
            }).join('');
        }

        function renderEvents(events) {
            if (!events.length) {
                return `
                    <div class="empty-state">
                        <i class="fa-solid fa-timeline"></i>
                        <div>No tracking events recorded for this chat yet.</div>
                    </div>
                `;
            }

            return events.map((event) => `
                <article class="timeline-item">
                    <div style="font-size:13px;font-weight:800; margin-bottom:4px;">${escapeHtml(event.event_type.replace('_', ' '))}</div>
                    <div class="tiny-note">${escapeHtml(formatDateTime(event.created_at))}</div>
                    <div style="font-size:13px; line-height:1.6; margin-top:8px;">${escapeHtml(event.notes || 'Workflow event recorded.')}</div>
                    <div class="tiny-note" style="margin-top:8px;">
                        ${escapeHtml(event.from_csr_name || 'Queue')} -> ${escapeHtml(event.to_csr_name || 'Queue')}
                        ${event.acted_by_name ? ` | acted by ${escapeHtml(event.acted_by_name)}` : ''}
                    </div>
                </article>
            `).join('');
        }

        function renderChatDetail() {
            const chat = getSelectedChat();
            const detailTitle = document.getElementById('detail-title');
            const detailSubtitle = document.getElementById('detail-subtitle');
            const detailGrid = document.getElementById('detail-grid');
            const detailActions = document.getElementById('detail-actions');
            const messagesPanel = document.getElementById('messages-panel');
            const eventPanel = document.getElementById('event-panel');

            if (!chat) {
                detailTitle.textContent = 'Select a chat';
                detailSubtitle.textContent = 'Open a chat from the ledger to see the transcript and tracking events.';
                detailActions.innerHTML = '';
                detailGrid.innerHTML = `
                    <div class="chat-meta-card"><div class="meta-label">Status</div><div class="meta-value">No chat selected</div></div>
                    <div class="chat-meta-card"><div class="meta-label">Assigned CSR</div><div class="meta-value">Not available</div></div>
                    <div class="chat-meta-card"><div class="meta-label">Customer Email</div><div class="meta-value">Not available</div></div>
                    <div class="chat-meta-card"><div class="meta-label">Last Activity</div><div class="meta-value">Not available</div></div>
                `;
                messagesPanel.innerHTML = `
                    <div class="empty-state">
                        <i class="fa-solid fa-comments"></i>
                        <div>No chat selected yet.</div>
                    </div>
                `;
                eventPanel.innerHTML = `
                    <div class="empty-state">
                        <i class="fa-solid fa-timeline"></i>
                        <div>Tracking events will appear here.</div>
                    </div>
                `;
                return;
            }

            detailTitle.textContent = chat.customer_name || chat.visitor_id;
            detailSubtitle.textContent = `${chat.visitor_id} · ${chat.message_count} messages · ${chatStatusLabel(chat.status)}`;
            detailActions.innerHTML = `
                <button class="mini-btn danger" id="detail-delete-btn" type="button">Delete Chat</button>
            `;
            detailGrid.innerHTML = `
                <div class="chat-meta-card">
                    <div class="meta-label">Status</div>
                    <div class="meta-value meta-value--single-line" title="${escapeHtml(chatStatusLabel(chat.status))}">${escapeHtml(chatStatusLabel(chat.status))}</div>
                </div>
                <div class="chat-meta-card">
                    <div class="meta-label">Assigned CSR</div>
                    <div class="meta-value meta-value--single-line" title="${escapeHtml(chat.assigned_label || 'Waiting queue')}">${escapeHtml(chat.assigned_label || 'Waiting queue')}</div>
                </div>
                <div class="chat-meta-card">
                    <div class="meta-label">Customer Email</div>
                    <div class="meta-value" title="${escapeHtml(chat.customer_email || 'Not available')}">${escapeHtml(chat.customer_email || 'Not available')}</div>
                </div>
                <div class="chat-meta-card">
                    <div class="meta-label">Last Activity</div>
                    <div class="meta-value" title="${escapeHtml(formatDateTime(chat.last_activity_at))}">${escapeHtml(formatDateTime(chat.last_activity_at))}</div>
                </div>
            `;
            messagesPanel.innerHTML = renderMessages(state.selectedMessages);
            eventPanel.innerHTML = renderEvents(state.selectedEvents);

            const deleteBtn = document.getElementById('detail-delete-btn');
            deleteBtn.addEventListener('click', async () => {
                const confirmed = window.confirm(`Delete chat ${chat.visitor_id} and all related messages from the database?`);
                if (!confirmed) return;
                try {
                    const response = await requestJson(`/api/chats/${chat.id}/delete`, {
                        method: 'POST',
                        body: JSON.stringify({})
                    });
                    state.selectedChatId = null;
                    state.selectedMessages = [];
                    state.selectedEvents = [];
                    state.dashboard = response.dashboard;
                    renderCurrentPage();
                    showBanner(response.message || 'Chat deleted.', 'success');
                } catch (error) {
                    showBanner(error.message, 'error');
                }
            });
        }

        function getActivityCustomBatchSize() {
            const input = document.getElementById('activity-custom-batch');
            const parsed = Number.parseInt(input?.value, 10);
            if (!Number.isFinite(parsed) || parsed < 1) {
                return ACTIVITY_DEFAULT_BATCH;
            }
            return Math.min(50, parsed);
        }

        function updateActivityControls() {
            const pagination = state.activityPagination || {};
            const countEl = document.getElementById('activity-count');
            const statusEl = document.getElementById('activity-load-status');
            const loadMoreBtn = document.getElementById('activity-load-more-btn');
            const customBtn = document.getElementById('activity-load-custom-btn');
            const resetBtn = document.getElementById('activity-reset-btn');
            const isLoading = Boolean(state.activityLoading);

            if (countEl) {
                countEl.textContent = pagination.total
                    ? `${state.activityEvents.length} of ${pagination.total} events`
                    : `${state.activityEvents.length} events`;
            }
            if (statusEl) {
                if (isLoading) {
                    statusEl.textContent = 'Loading activity events...';
                } else if (!pagination.total) {
                    statusEl.textContent = 'No workflow activity recorded yet.';
                } else if (pagination.has_more) {
                    statusEl.textContent = 'More events are available. Load only what you need.';
                } else {
                    statusEl.textContent = 'All available events are loaded.';
                }
            }
            if (loadMoreBtn) {
                loadMoreBtn.disabled = isLoading || !pagination.has_more;
            }
            if (customBtn) {
                customBtn.disabled = isLoading || !pagination.has_more;
            }
            if (resetBtn) {
                resetBtn.disabled = isLoading;
            }
        }

        async function loadActivityEvents({ append = false, limit = ACTIVITY_DEFAULT_BATCH } = {}) {
            const container = document.getElementById('activity-list');
            const offset = append ? state.activityEvents.length : 0;

            state.activityLoading = true;
            updateActivityControls();
            if (container && !append) {
                container.innerHTML = '<div class="tiny-note">Loading activity feed...</div>';
            }

            try {
                const payload = await requestJson(
                    `/api/admin/activity-events?limit=${encodeURIComponent(limit)}&offset=${encodeURIComponent(offset)}`,
                    { method: 'GET' }
                );
                const events = payload.events || [];
                state.activityEvents = append ? state.activityEvents.concat(events) : events;
                state.activityPagination = payload.pagination || { total: events.length, has_more: false };
                renderActivity();
            } catch (error) {
                if (container && !append) {
                    container.innerHTML = `<div class="tiny-note">${escapeHtml(error.message || 'Failed to load activity feed.')}</div>`;
                }
                updateActivityControls();
                showBanner(error.message || 'Failed to load activity feed.', 'error');
            } finally {
                state.activityLoading = false;
                updateActivityControls();
            }
        }

        function renderActivity() {
            const container = document.getElementById('activity-list');
            const events = state.activityEvents || [];

            if (!events.length) {
                container.innerHTML = '<div class="tiny-note">No workflow activity recorded yet.</div>';
                updateActivityControls();
                return;
            }

            container.innerHTML = events.map((event) => `
                <article class="activity-item">
                    <div class="item-head">
                        <div style="font-size:14px;font-weight:800;">${escapeHtml(event.event_type.replace('_', ' '))}</div>
                        <div class="tiny-note">${escapeHtml(formatRelative(event.created_at))}</div>
                    </div>
                    <div style="font-size:13px; line-height:1.6; margin-top:8px;">${escapeHtml(event.notes || 'Workflow event recorded.')}</div>
                    <div class="tiny-note" style="margin-top:8px;">
                        ${escapeHtml(event.from_csr_name || 'Queue')} -> ${escapeHtml(event.to_csr_name || 'Queue')}
                        ${event.acted_by_name ? ` | acted by ${escapeHtml(event.acted_by_name)}` : ''}
                        | ${escapeHtml(formatDateTime(event.created_at))}
                    </div>
                </article>
            `).join('');
            updateActivityControls();
        }

        function renderCurrentPage(forceIntegrationSync = false, forceCharts = false) {
            if (!state.dashboard) {
                return;
            }
            if (currentPage === 'overview') {
                renderSummary();
                renderCharts(forceCharts);
                return;
            }
            /* Credentials tab temporarily disabled
            if (currentPage === 'credentials') {
                renderIntegrationSettings(forceIntegrationSync);
                return;
            }
            */
            if (currentPage === 'team') {
                renderAvailableCsrList();
                renderCsrTable();
                return;
            }
            if (isChatPage) {
                renderChatTable();
                renderChatDetail();
                return;
            }
            if (currentPage === 'activity') {
                return;
            }
        }

        async function selectChat(chatId) {
            state.selectedChatId = chatId;
            const payload = await requestJson(`/api/chats/${chatId}/messages`, { method: 'GET' });
            state.selectedMessages = payload.messages || [];
            state.selectedEvents = payload.events || [];
            renderChatTable();
            renderChatDetail();
            document.getElementById('chat-section').scrollIntoView({ behavior: 'smooth', block: 'start' });
        }

        async function refreshDashboard(reloadSelectedChat = true) {
            if (!dashboardEnabled) {
                return;
            }
            const payload = await requestJson(buildDashboardApiUrl(), { method: 'GET' });
            state.dashboard = payload;
            const chats = state.dashboard.chats || [];
            if (isChatPage && reloadSelectedChat && state.selectedChatId && chats.some((chat) => chat.id === state.selectedChatId)) {
                try {
                    const detailPayload = await requestJson(`/api/chats/${state.selectedChatId}/messages`, { method: 'GET' });
                    state.selectedMessages = detailPayload.messages || [];
                    state.selectedEvents = detailPayload.events || [];
                } catch (_error) {
                    state.selectedChatId = null;
                    state.selectedMessages = [];
                    state.selectedEvents = [];
                }
            } else if (isChatPage && (!state.selectedChatId || !chats.some((chat) => chat.id === state.selectedChatId))) {
                state.selectedChatId = null;
                state.selectedMessages = [];
                state.selectedEvents = [];
            }
            renderCurrentPage();
        }

        const createCsrForm = document.getElementById('create-csr-form');
        if (createCsrForm) {
            createCsrForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const formData = new FormData(form);
                try {
                    const response = await requestJson('/api/admin/csrs/create', {
                        method: 'POST',
                        body: JSON.stringify({
                            display_name: formData.get('display_name'),
                            email: formData.get('email'),
                            password: formData.get('password'),
                            is_available: formData.get('is_available') === 'on'
                        })
                    });
                    form.reset();
                    form.querySelector('input[name="is_available"]').checked = true;
                    state.dashboard = response.dashboard;
                    renderCurrentPage();
                    showBanner(response.message || 'User added successfully.', 'success');
                } catch (error) {
                    showBanner(error.message, 'error');
                }
            });
        }

        const chatPerPageSel = document.getElementById('chat-per-page');
        if (chatPerPageSel) {
            chatPerPageSel.addEventListener('change', () => {
                state.chatPerPage = Number(chatPerPageSel.value) || 20;
                state.chatPage = 1;
                refreshDashboard(false).catch((error) => showBanner(error.message, 'error'));
            });
        }

        /* Credentials tab temporarily disabled
        const integrationSettingsForm = document.getElementById('integration-settings-form');
        if (integrationSettingsForm) {
            integrationSettingsForm.addEventListener('input', () => {
                state.integrationDraftDirty = true;
                renderIntegrationPreview(readIntegrationForm());
            });

            integrationSettingsForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                const settings = readIntegrationForm();
                try {
                    const response = await requestJson('/api/admin/integration-settings', {
                        method: 'POST',
                        body: JSON.stringify(settings)
                    });
                    state.dashboard = response.dashboard;
                    state.integrationDraftDirty = false;
                    renderCurrentPage(true);
                    showBanner(response.message || 'Integration settings saved.', 'success');
                } catch (error) {
                    showBanner(error.message, 'error');
                }
            });
        }

        const integrationResetBtn = document.getElementById('integration-reset-btn');
        if (integrationResetBtn) {
            integrationResetBtn.addEventListener('click', () => {
                state.integrationDraftDirty = false;
                renderIntegrationSettings(true);
                showBanner('Reloaded saved integration settings.', 'success');
            });
        }
        */

        async function handleDashboardRefresh() {
            try {
                if (currentPage === 'activity') {
                    await loadActivityEvents({ append: false, limit: ACTIVITY_DEFAULT_BATCH });
                    showBanner('Activity timeline refreshed.', 'success');
                    return;
                }
                if (isTicketPage) {
                    await loadTicketLedger();
                    showBanner('Tickets refreshed.', 'success');
                    return;
                }
                if (currentPage === 'tech') {
                    await loadTechData();
                    showBanner('Technical team refreshed.', 'success');
                    return;
                }
                if (!dashboardEnabled) {
                    window.location.reload();
                    return;
                }
                state.chartSignature = '';
                await refreshDashboard(true);
                showBanner('Dashboard refreshed.', 'success');
            } catch (error) {
                showBanner(error.message, 'error');
            }
        }

        const refreshBtn = document.getElementById('refresh-btn');
        if (refreshBtn) {
            refreshBtn.addEventListener('click', handleDashboardRefresh);
        }
        const topbarRefreshBtn = document.getElementById('topbar-refresh-btn');
        if (topbarRefreshBtn) {
            topbarRefreshBtn.addEventListener('click', handleDashboardRefresh);
        }

        /* Rebalance queue temporarily removed from admin sidebar
        document.getElementById('rebalance-btn').addEventListener('click', async () => {
            try {
                const response = await requestJson('/api/chats/rebalance', {
                    method: 'POST',
                    body: JSON.stringify({})
                });
                if (response.dashboard && dashboardEnabled) {
                    state.dashboard = response.dashboard;
                    renderCurrentPage();
                }
                showBanner(`Rebalanced ${response.assigned_count || 0} queued chats.`, 'success');
            } catch (error) {
                showBanner(error.message, 'error');
            }
        });
        */

        window.addEventListener('resize', () => {
            window.clearTimeout(resizeTimer);
            resizeTimer = window.setTimeout(() => {
                if (state.dashboard && currentPage === 'overview') {
                    renderCharts(true);
                }
            }, 180);
        });

        setupMobileNav();

        const activityLoadMoreBtn = document.getElementById('activity-load-more-btn');
        if (activityLoadMoreBtn) {
            activityLoadMoreBtn.addEventListener('click', () => {
                loadActivityEvents({ append: true, limit: ACTIVITY_DEFAULT_BATCH }).catch((error) => {
                    showBanner(error.message, 'error');
                });
            });
        }

        const activityLoadCustomBtn = document.getElementById('activity-load-custom-btn');
        if (activityLoadCustomBtn) {
            activityLoadCustomBtn.addEventListener('click', () => {
                loadActivityEvents({ append: true, limit: getActivityCustomBatchSize() }).catch((error) => {
                    showBanner(error.message, 'error');
                });
            });
        }

        const activityResetBtn = document.getElementById('activity-reset-btn');
        if (activityResetBtn) {
            activityResetBtn.addEventListener('click', () => {
                loadActivityEvents({ append: false, limit: ACTIVITY_DEFAULT_BATCH }).catch((error) => {
                    showBanner(error.message, 'error');
                });
            });
        }

        if (currentPage === 'activity') {
            loadActivityEvents({ append: false, limit: ACTIVITY_DEFAULT_BATCH }).catch((error) => {
                showBanner(error.message, 'error');
            });
        }

        document.querySelectorAll('.nav-dropdown-toggle').forEach((toggle) => {
            toggle.addEventListener('click', () => {
                const dropdown = toggle.closest('.nav-dropdown');
                if (!dropdown) return;
                const willOpen = !dropdown.classList.contains('open');
                dropdown.classList.toggle('open', willOpen);
                toggle.setAttribute('aria-expanded', willOpen ? 'true' : 'false');
            });
        });

        if (dashboardEnabled) {
            refreshDashboard(true).catch((error) => {
                showBanner(error.message, 'error');
            });

            // Active Chats + overview/team poll; Chat History loads once (Refresh button).
            // Pause while tab is hidden to cut wasted network/CPU.
            const shouldAutoPoll = currentPage === 'chats-active' || currentPage === 'overview' || currentPage === 'team';
            if (shouldAutoPoll) {
                const pollMs = currentPage === 'chats-active' ? 12000 : 20000;
                refreshInterval = schedulePoll(() => {
                    if (currentPage === 'team' && document.querySelector('.csr-roster-actions.is-dirty')) return;
                    refreshDashboard(currentPage === 'chats-active' && Boolean(state.selectedChatId)).catch(() => {});
                }, pollMs);
            }
        }

        // ── Technical Team Section ──
        function showTechSection() {
            document.querySelectorAll('.section').forEach(s => s.style.display = 'none');
            const techSection = document.getElementById('tech-section');
            if (techSection) techSection.style.display = 'block';
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(btn => {
                if (btn.textContent.includes('Technical Team')) btn.classList.add('active');
            });
            loadTechData();
        }

        let adminTicketStatuses = [];
        let adminTechMembers = [];
        let adminTechWorkload = [];

        function techPresenceLabel(tech) {
            if (!tech.is_active) return 'Account disabled';
            if (tech.is_online) return 'Online now';
            if (!tech.last_seen_at) return 'No heartbeat yet';
            return formatLastSeen(tech.last_seen_at);
        }

        function techPresenceChip(tech) {
            if (!tech.is_active) {
                return '<span class="chip chip-disabled">Disabled</span>';
            }
            return tech.is_online
                ? '<span class="chip chip-online">Online</span>'
                : '<span class="chip chip-offline">Offline</span>';
        }

        function techAccountChip(tech) {
            return tech.is_active
                ? '<span class="chip chip-active">Enabled</span>'
                : '<span class="chip chip-disabled">Disabled</span>';
        }

        function renderTechTeamTable(techs, workload) {
            adminTechMembers = techs || [];
            if (Array.isArray(workload)) {
                adminTechWorkload = workload;
            }
            const body = document.getElementById('tech-team-body');
            if (!body) return;

            const workloadById = new Map(
                (adminTechWorkload || []).map((row) => [Number(row.tech_id || row.id), row])
            );

            const techCount = document.getElementById('tech-count');
            if (!adminTechMembers.length) {
                body.innerHTML = '<tr><td colspan="9" class="tiny-note" style="padding:24px;">No technical team members yet. Use the form above to add one.</td></tr>';
                if (techCount) techCount.textContent = '0 members';
                return;
            }

            const onlineCount = adminTechMembers.filter((t) => t.is_active && t.is_online).length;
            if (techCount) {
                techCount.textContent = `${adminTechMembers.length} member${adminTechMembers.length !== 1 ? 's' : ''} · ${onlineCount} online`;
            }

            body.innerHTML = adminTechMembers.map((tech) => {
                const load = workloadById.get(Number(tech.id)) || {};
                const active = load.active ?? 0;
                const inProgress = load.in_progress ?? 0;
                const open = load.open ?? 0;
                const total = load.total_assigned ?? 0;
                return `
                    <tr>
                        <td data-label="Technician">
                            <strong>${escapeHtml(tech.display_name || 'Unnamed')}</strong>
                            <div class="admin-soft-muted">${escapeHtml(tech.email)}</div>
                            <div class="admin-soft-muted">${escapeHtml(techPresenceLabel(tech))}</div>
                        </td>
                        <td data-label="Specialty">${escapeHtml(tech.specialty || 'General')}</td>
                        <td data-label="Online">${techPresenceChip(tech)}</td>
                        <td data-label="Account">${techAccountChip(tech)}</td>
                        <td data-label="Active"><strong style="color:#0d9488;">${active}</strong></td>
                        <td data-label="In Progress">${inProgress}</td>
                        <td data-label="Open">${open}</td>
                        <td data-label="Total">${total}</td>
                        <td data-label="Actions">
                            <div class="action-row">
                                <button class="mini-btn" onclick="editTechMember(${tech.id})" title="Enable / disable account"><i class="fa-solid fa-power-off"></i></button>
                                <button class="mini-btn danger" onclick="deleteTechMember(${tech.id})" title="Delete member"><i class="fa-solid fa-trash"></i></button>
                            </div>
                        </td>
                    </tr>
                `;
            }).join('');
        }

        // Back-compat alias used by presence refresh.
        function renderTechMembersTable(techs) {
            renderTechTeamTable(techs, adminTechWorkload);
        }

        function setTechDataLoadError(message) {
            const err = escapeHtml(message || 'Failed to load data');
            const wl = document.getElementById('tech-team-body');
            const tb = document.getElementById('admin-ticket-table-body');
            if (wl) wl.innerHTML = `<tr><td colspan="9" class="tiny-note" style="padding:24px;color:var(--red);">${err}</td></tr>`;
            if (tb) tb.innerHTML = `<tr><td colspan="10" class="tiny-note" style="padding:24px;color:var(--red);">${err}</td></tr>`;
        }

        function getTicketLifecycle() {
            const section = document.getElementById('tickets-section');
            return section?.dataset?.ticketLifecycle || (currentPage === 'tickets-old' ? 'old' : 'current');
        }

        function renderAdminTicketRows(tickets, statuses) {
            const ticketBody = document.getElementById('admin-ticket-table-body');
            const countEl = document.getElementById('admin-ticket-count');
            if (countEl) countEl.textContent = `${tickets.length} ticket${tickets.length !== 1 ? 's' : ''}`;
            if (!ticketBody) return;

            if (!tickets.length) {
                ticketBody.innerHTML = '<tr><td colspan="10" class="tiny-note" style="padding:24px;">No tickets match this filter.</td></tr>';
                return;
            }

            ticketBody.innerHTML = tickets.map(t => {
                const status = statuses.find(s => s.name === t.status) || {};
                const creatorLabel = t.created_by_label
                    || (t.created_by_admin ? (t.created_by_admin.display_name || t.created_by_admin.email) : null)
                    || (t.created_by_csr ? (t.created_by_csr.display_name || t.created_by_csr.email) : null)
                    || '—';
                const creatorRole = t.created_by_role === 'admin' ? 'Admin' : (t.created_by_role === 'csr' ? 'CSR' : '');
                const statusColor = status.color || '#64748b';
                const lastNote = t.last_status_update?.notes
                    ? `<div class="admin-soft-muted" style="margin-top:4px;" title="${escapeHtml(t.last_status_update.notes)}">${escapeHtml(t.last_status_update.notes).slice(0, 50)}${t.last_status_update.notes.length > 50 ? '…' : ''}</div>`
                    : '';
                const lastAssignment = t.last_assignment_update;
                const assignmentTrail = lastAssignment
                    ? `<div class="admin-soft-muted" style="margin-top:4px;" title="${escapeHtml(lastAssignment.notes || '')}">
                        <i class="fa-solid fa-share-nodes"></i>
                        ${escapeHtml(lastAssignment.old_assigned_tech ? (lastAssignment.old_assigned_tech.display_name || lastAssignment.old_assigned_tech.email) : 'Unassigned')}
                        →
                        ${escapeHtml(lastAssignment.new_assigned_tech ? (lastAssignment.new_assigned_tech.display_name || lastAssignment.new_assigned_tech.email) : 'Unassigned')}
                        ${lastAssignment.changed_by_name ? `<div>By ${escapeHtml(lastAssignment.changed_by_name)}</div>` : ''}
                    </div>`
                    : '';
                return `
                    <tr>
                        <td class="ticket-num-cell" data-label="Ticket">${escapeHtml(t.ticket_number || ('#' + t.id))}</td>
                        <td data-label="Title"><strong>${escapeHtml(t.title)}</strong>${t.description ? `<div class="admin-soft-muted" style="margin-top:4px;">${escapeHtml(t.description).slice(0, 60)}${t.description.length > 60 ? '…' : ''}</div>` : ''}${lastNote}</td>
                        <td data-label="Status"><span class="admin-soft-chip" style="background:${statusColor}22;color:${statusColor}">${escapeHtml(status.label || t.status)}</span></td>
                        <td data-label="Priority" style="text-transform:capitalize;">${escapeHtml(t.priority || 'normal')}</td>
                        <td data-label="Created By"><strong>${escapeHtml(creatorLabel)}</strong>${creatorRole ? `<div class="admin-soft-muted">${creatorRole}</div>` : ''}</td>
                        <td data-label="Assigned">${t.assigned_tech ? `<strong>${escapeHtml(t.assigned_tech.display_name || 'Tech')}</strong><div class="admin-soft-muted">${escapeHtml(t.assigned_tech.specialty || '')}</div>${assignmentTrail}` : '<span class="admin-soft-chip">Unassigned</span>'}</td>
                        <td data-label="Msgs">${t.message_count ?? 0}</td>
                        <td class="admin-soft-muted" data-label="Created">${formatDate(t.created_at)}</td>
                        <td class="admin-soft-muted" data-label="Updated">${formatDate(t.updated_at)}</td>
                        <td class="admin-soft-muted" data-label="Resolved">${t.resolved_at ? formatDate(t.resolved_at) : '—'}</td>
                    </tr>
                `;
            }).join('');
        }

        async function loadTicketLedger() {
            const ticketBody = document.getElementById('admin-ticket-table-body');
            if (ticketBody) ticketBody.innerHTML = '<tr><td colspan="10" class="tiny-note" style="padding:24px;">Loading tickets...</td></tr>';
            try {
                const statusFilter = document.getElementById('admin-ticket-status-filter')?.value || 'all';
                const lifecycle = getTicketLifecycle();
                // The Current page normally scopes "All statuses" to active
                // work. If an administrator explicitly chooses a resolved
                // status there, request the completed scope as well so the
                // selected closed record is never filtered out by the page
                // lifecycle.
                const selectedStatus = adminTicketStatuses.find((status) => status.name === statusFilter);
                const requestLifecycle = lifecycle === 'current'
                    && statusFilter !== 'all'
                    && (statusFilter === 'closed' || statusFilter === 'resolved' || selectedStatus?.is_resolved)
                    ? 'old'
                    : lifecycle;
                const params = new URLSearchParams({
                    lifecycle: requestLifecycle,
                    include_stats: '0',
                    include_workload: '0',
                });
                if (statusFilter !== 'all') params.set('status', statusFilter);
                const ticketsResp = await requestJson(`/api/admin/tickets?${params.toString()}`);
                const tickets = ticketsResp.tickets || [];
                const statuses = ticketsResp.statuses || [];
                adminTicketStatuses = statuses;
                populateAdminTicketStatusFilter(statuses);
                renderAdminTicketRows(tickets, statuses);
            } catch (err) {
                console.error('Failed to load tickets:', err);
                setTechDataLoadError(err.message);
                showBanner(err.message || 'Failed to load tickets', 'error');
            }
        }

        async function loadTechData() {
            const teamBody = document.getElementById('tech-team-body');
            if (teamBody) {
                teamBody.innerHTML = '<tr><td colspan="9" class="tiny-note" style="padding:24px;">Loading technical team...</td></tr>';
            }

            try {
                const [techResp, ticketsResp] = await Promise.all([
                    requestJson('/api/admin/tech-accounts'),
                    requestJson('/api/admin/tickets?lifecycle=all&include_stats=1&include_workload=1'),
                ]);

                const techs = techResp.techs || [];
                const statuses = ticketsResp.statuses || [];
                const stats = ticketsResp.stats || {};
                const workload = ticketsResp.tech_workload || [];
                adminTicketStatuses = statuses;

                const setStat = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
                setStat('stat-tech-count', techs.filter(t => t.is_active && t.is_online).length);
                setStat('stat-open-tickets', stats.open ?? 0);
                setStat('stat-progress-tickets', stats.in_progress ?? 0);
                setStat('stat-closed-tickets', stats.closed ?? 0);
                setStat('stat-total-tickets', stats.total ?? 0);
                setStat('stat-unassigned-tickets', stats.unassigned ?? 0);

                renderTechTeamTable(techs, workload);
            } catch (err) {
                console.error('Failed to load tech data:', err);
                setTechDataLoadError(err.message);
                showBanner(err.message || 'Failed to load ticket data', 'error');
            }
        }

        function populateAdminTicketStatusFilter(statuses) {
            const select = document.getElementById('admin-ticket-status-filter');
            if (!select) return;
            const current = select.value || 'all';
            const options = ['<option value="all">All statuses</option>']
                .concat((statuses || []).map(s => `<option value="${escapeHtml(s.name)}">${escapeHtml(s.label)}</option>`));
            select.innerHTML = options.join('');
            if ([...select.options].some(o => o.value === current)) {
                select.value = current;
            }
        }

        const adminTicketStatusFilter = document.getElementById('admin-ticket-status-filter');
        if (adminTicketStatusFilter) {
            adminTicketStatusFilter.addEventListener('change', () => {
                if (isTicketPage) loadTicketLedger();
                else loadTechData();
            });
        }
        const adminTicketRefreshBtn = document.getElementById('admin-ticket-refresh-btn');
        if (adminTicketRefreshBtn) {
            adminTicketRefreshBtn.addEventListener('click', () => {
                if (isTicketPage) loadTicketLedger();
                else loadTechData();
            });
        }

        const adminCreateTicketForm = document.getElementById('admin-create-ticket-form');
        if (adminCreateTicketForm) {
            adminCreateTicketForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const formData = new FormData(form);
                const payload = {
                    title: String(formData.get('title') || '').trim(),
                    description: String(formData.get('description') || '').trim(),
                    priority: String(formData.get('priority') || 'normal'),
                };
                if (!payload.title) {
                    showBanner('Ticket title is required.', 'error');
                    return;
                }
                try {
                    const resp = await requestJson('/api/admin/tickets', {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                    showBanner(resp.message || 'Ticket created.', 'success');
                    form.reset();
                    await loadTicketLedger();
                } catch (err) {
                    showBanner(err.message || 'Failed to create ticket', 'error');
                }
            });
        }

        function formatDate(dateStr) {
            const date = parseServerDate(dateStr);
            if (!date) return 'N/A';
            return date.toLocaleString(undefined, {
                month: 'short',
                day: 'numeric',
                hour: '2-digit',
                minute: '2-digit',
                timeZoneName: 'short'
            });
        }

        function escapeHtml(text) {
            if (!text) return '';
            return String(text).replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;').replace(/"/g, '&quot;');
        }

        function openTechModal() {
            // No longer needed - inline form is used
        }

        function openStatusModal() {
            // No longer needed - inline form is used
        }

        // ── Create Tech Account Form ──
        const createTechForm = document.getElementById('create-tech-form');
        if (createTechForm) {
            createTechForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const formData = new FormData(form);
                const payload = {
                    email: formData.get('email').trim().toLowerCase(),
                    password: formData.get('password'),
                    display_name: formData.get('display_name').trim(),
                    specialty: formData.get('specialty'),
                };

                if (!payload.email || !payload.password) {
                    showBanner('Email and password are required.', 'error');
                    return;
                }
                if (payload.password.length < 6) {
                    showBanner('Password must be at least 6 characters.', 'error');
                    return;
                }

                try {
                    const resp = await requestJson('/api/admin/tech-accounts', {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                    if (resp.success) {
                        showBanner(resp.message || 'User added successfully.', 'success');
                        form.reset();
                        loadTechData();
                    } else {
                        showBanner(resp.error || 'Failed to create account', 'error');
                    }
                } catch (err) {
                    showBanner(err.message, 'error');
                }
            });
        }

        // Ticket status management UI removed from Technical Team tab.

        function editTechMember(id) {
            const tech = adminTechMembers.find((item) => Number(item.id) === Number(id));
            if (!tech) {
                showBanner('Member not found.', 'error');
                return;
            }
            const nextActive = !tech.is_active;
            const actionLabel = nextActive ? 'enable' : 'disable';
            if (!confirm(`${nextActive ? 'Enable' : 'Disable'} this technical team account?`)) {
                return;
            }
            fetch(`/api/admin/tech-accounts/${id}`, {
                method: 'PUT',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ is_active: nextActive })
            })
            .then(r => r.json())
            .then(data => {
                if (data.success) {
                    showBanner(`Member ${actionLabel}d successfully.`, 'success');
                    refreshTechPresence().catch(() => loadTechData());
                } else {
                    showBanner(data.error || 'Failed to update member', 'error');
                }
            })
            .catch(() => showBanner('Failed to update member', 'error'));
        }

        async function refreshTechPresence() {
            const techResp = await requestJson('/api/admin/tech-accounts');
            const techs = techResp.techs || [];
            renderTechMembersTable(techs);
            const setStat = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
            setStat('stat-tech-count', techs.filter((t) => t.is_active && t.is_online).length);
            return techs;
        }

        function deleteTechMember(id) {
            if (confirm('Are you sure you want to delete this technical team member?')) {
                requestJson(`/api/admin/tech-accounts/${id}`, { method: 'DELETE' })
                    .then(data => {
                        if (data.success) {
                            showBanner(data.message || 'Technical team member deleted.', 'success');
                            loadTechData();
                        } else {
                            showBanner(data.error || 'Failed to delete member', 'error');
                        }
                    })
                    .catch((err) => showBanner(err.message || 'Failed to delete member', 'error'));
            }
        }

        window.editTechMember = editTechMember;
        window.deleteTechMember = deleteTechMember;

        if (document.body.dataset.adminPage === 'tech') {
            loadTechData();
            // Fast presence refresh so Online/Offline tracks logout / browser close quickly.
            schedulePoll(() => refreshTechPresence().catch(() => {}), 8000);
            // Full ticket/workload refresh less often.
            schedulePoll(() => loadTechData().catch(() => {}), 45000);
        }

        if (isTicketPage) {
            loadTicketLedger();
            // Current tickets poll lightly; old tickets stay manual-refresh only.
            if (currentPage === 'tickets-current') {
                schedulePoll(() => loadTicketLedger().catch(() => {}), 25000);
            }
        }
