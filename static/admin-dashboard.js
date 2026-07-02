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
            activityLoading: false
        };

        const ACTIVITY_DEFAULT_BATCH = 5;

        const flashBanner = document.getElementById('flash-banner');
        let flashTimer = null;
        let refreshInterval = null;
        const currentPage = document.body.dataset.adminPage || 'overview';
        const dashboardEnabled = document.body.dataset.dashboardEnabled === 'true';
        function buildDashboardApiUrl() {
            if (!dashboardEnabled) return null;
            const params = new URLSearchParams({ page: currentPage });
            if (currentPage === 'chats') {
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

        function formatDateTime(value) {
            if (!value) return 'Not available';
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) return value;
            return date.toLocaleString();
        }

        function formatRelative(value) {
            if (!value) return 'Not available';
            const date = new Date(value);
            if (Number.isNaN(date.getTime())) return value;
            const seconds = Math.floor((Date.now() - date.getTime()) / 1000);
            if (seconds < 60) return 'Just now';
            if (seconds < 3600) return `${Math.floor(seconds / 60)} min ago`;
            if (seconds < 86400) return `${Math.floor(seconds / 3600)} hr ago`;
            return `${Math.floor(seconds / 86400)} day ago`;
        }

        function formatPresence(csr) {
            if (csr.is_online) return 'Online now';
            const reference = csr.last_seen_at || csr.last_assigned_at;
            return reference ? `Last seen ${formatRelative(reference)}` : 'No heartbeat yet';
        }

        function showBanner(message, tone = 'success') {
            flashBanner.textContent = message;
            flashBanner.className = `flash-banner show ${tone}`;
            window.clearTimeout(flashTimer);
            flashTimer = window.setTimeout(() => {
                flashBanner.className = 'flash-banner';
            }, 4500);
        }

        async function requestJson(url, options = {}) {
            const response = await fetch(url, {
                credentials: 'same-origin',
                headers: {
                    'Content-Type': 'application/json',
                    'X-Admin-Page': currentPage,
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
                        <div class="tiny-note">Open ${csr.active_chat_count}/${csr.max_concurrent_chats}</div>
                        <div class="tiny-note">${escapeHtml(formatPresence(csr))}</div>
                    </div>
                    <div class="load-bar"><span style="width:${Math.max(8, Math.round((csr.active_chat_count / Math.max(1, csr.max_concurrent_chats)) * 100))}%"></span></div>
                </article>
            `).join('');
        }

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
            fillRoundedRect(ctx, 18, 18, w - 36, h - 36, 16, 'rgba(15, 23, 42, 0.7)');
            ctx.textAlign = 'center';
            ctx.fillStyle = '#e2e8f0';
            ctx.font = '700 15px Inter';
            ctx.fillText(title, w / 2, h / 2 - 10);
            ctx.fillStyle = '#94a3b8';
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
            if (!rows.length) {
                drawChartEmptyState(ctx, w, h, 'No resolution data yet', 'CSR activity will appear here once chats are handled.');
                return;
            }

            const maxValue = Math.max(...rows.flatMap((row) => metrics.map((metric) => Number(row[metric.key] || 0))));
            if (!maxValue) {
                drawChartEmptyState(ctx, w, h, 'No comparable workload yet', 'No CSR has resolved or opened chats in this reporting window.');
                return;
            }

            const compact = w < 760;
            const legendRowHeight = compact ? 22 : 0;
            const padding = { top: compact ? 60 : 42, right: 18, bottom: 38, left: 44 };
            const chartWidth = w - padding.left - padding.right;
            const slotPx = 108;
            const plotWidth = Math.min(chartWidth, Math.max(200, rows.length * slotPx));
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
                ctx.fillStyle = '#cbd5e1';
                ctx.fillText(metric.label, legendX + 18, legendY);
            });

            for (let index = 0; index <= gridLines; index += 1) {
                const y = padding.top + (chartHeight / gridLines) * index;
                const value = scaleMax - (scaleMax / gridLines) * index;
                ctx.beginPath();
                ctx.strokeStyle = index === gridLines ? 'rgba(148, 163, 184, 0.3)' : 'rgba(148, 163, 184, 0.12)';
                ctx.lineWidth = 1;
                ctx.moveTo(plotLeft, y);
                ctx.lineTo(plotLeft + plotWidth, y);
                ctx.stroke();

                ctx.fillStyle = '#64748b';
                ctx.font = '11px Inter';
                ctx.textAlign = 'right';
                ctx.fillText(Number.isInteger(value) ? String(value) : value.toFixed(1), padding.left - 8, y);
            }

            const groupWidth = plotWidth / rows.length;
            const groupGap = Math.max(12, groupWidth * 0.12);
            const availableBarWidth = Math.max(30, groupWidth - groupGap);
            const barGap = Math.max(6, Math.min(10, availableBarWidth * 0.08));
            const barWidth = Math.max(10, Math.min(24, (availableBarWidth - barGap * (metrics.length - 1)) / metrics.length));

            ctx.beginPath();
            ctx.strokeStyle = 'rgba(148, 163, 184, 0.18)';
            ctx.lineWidth = 1.2;
            ctx.moveTo(plotLeft, padding.top + chartHeight);
            ctx.lineTo(plotLeft + plotWidth, padding.top + chartHeight);
            ctx.stroke();

            rows.forEach((row, index) => {
                const totalBarsWidth = metrics.length * barWidth + (metrics.length - 1) * barGap;
                const groupStartX = plotLeft + index * groupWidth + (groupWidth - totalBarsWidth) / 2;
                const laneX = plotLeft + index * groupWidth + 6;
                const laneWidth = Math.max(groupWidth - 12, totalBarsWidth + 14);

                fillRoundedRect(
                    ctx,
                    laneX,
                    padding.top + 10,
                    laneWidth,
                    chartHeight - 10,
                    12,
                    'rgba(148, 163, 184, 0.04)'
                );

                metrics.forEach((metric, metricIndex) => {
                    const rawValue = Number(row[metric.key] || 0);
                    const barHeight = rawValue ? (rawValue / scaleMax) * chartHeight : 0;
                    const x = groupStartX + metricIndex * (barWidth + barGap);
                    const y = padding.top + chartHeight - barHeight;

                    if (barHeight > 0) {
                        fillRoundedRect(ctx, x, y, barWidth, barHeight, 8, metric.color);
                        ctx.fillStyle = '#f8fafc';
                        ctx.font = '600 11px Inter';
                        ctx.textAlign = 'center';
                        ctx.fillText(String(rawValue), x + barWidth / 2, Math.max(padding.top - 10, y - 8));
                    }
                });

                ctx.fillStyle = '#94a3b8';
                ctx.font = '11px Inter';
                ctx.textAlign = 'center';
                const label = truncateLabel(ctx, row.display_name || 'CSR', groupWidth - 10);
                ctx.fillText(label, plotLeft + index * groupWidth + groupWidth / 2, h - 18);
            });

            ctx.textAlign = 'left';
        }

        function drawDonutChart(canvas, statusBreakdown) {
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
            const centerY = compact ? 82 : h / 2;
            const radius = compact ? 48 : Math.min(72, h * 0.29);
            const ringWidth = Math.max(16, radius * 0.34);
            const segmentRadius = radius - ringWidth / 2;
            const legendX = compact ? 18 : Math.max(228, w * 0.58);
            const legendStartY = compact ? centerY + radius + 22 : 40;
            let startAngle = -Math.PI / 2;

            ctx.beginPath();
            ctx.strokeStyle = 'rgba(148, 163, 184, 0.12)';
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
            ctx.fillStyle = '#f8fafc';
            ctx.font = '700 22px Inter';
            ctx.fillText(String(total), centerX, centerY - 4);
            ctx.fillStyle = '#94a3b8';
            ctx.font = '12px Inter';
            ctx.fillText('Tracked chats', centerX, centerY + 18);

            entries.forEach((entry, index) => {
                const legendY = legendStartY + index * 34;
                const percent = total ? Math.round((entry.value / total) * 100) : 0;

                fillRoundedRect(ctx, legendX, legendY - 10, compact ? w - 36 : Math.max(120, w - legendX - 18), 24, 10, 'rgba(15, 23, 42, 0.58)');
                fillRoundedRect(ctx, legendX + 10, legendY - 3, 10, 10, 4, entry.color);
                ctx.textAlign = 'left';
                ctx.fillStyle = '#e2e8f0';
                ctx.font = '600 12px Inter';
                ctx.fillText(entry.label, legendX + 28, legendY + 1);
                ctx.fillStyle = '#94a3b8';
                ctx.font = '11px Inter';
                ctx.fillText(`${entry.value} chats`, legendX + 28, legendY + 13);
                ctx.textAlign = 'right';
                ctx.fillStyle = '#cbd5e1';
                ctx.font = '700 11px Inter';
                ctx.fillText(`${percent}%`, compact ? w - 30 : w - 24, legendY + 1);
            });

            ctx.textAlign = 'left';
        }

        function renderLeaderboard() {
            const container = document.getElementById('leaderboard-list');
            const rows = state.dashboard.reports.resolution_leaderboard || [];

            if (!rows.length) {
                container.innerHTML = '<div class="tiny-note">No CSR resolution activity has been recorded yet.</div>';
                return;
            }

            container.innerHTML = rows.map((row) => `
                <article class="leaderboard-item">
                    <div class="item-head">
                        <div>
                            <div style="font-size:14px;font-weight:800;">${escapeHtml(row.display_name)}</div>
                            <div class="tiny-note">${escapeHtml(row.email)}</div>
                        </div>
                        <span class="badge ${row.is_online ? 'online' : 'offline'}">${row.is_online ? 'Online' : 'Offline'}</span>
                    </div>
                    <div class="row" style="margin-top:10px;">
                        <div class="tiny-note">Today ${row.resolved_today}</div>
                        <div class="tiny-note">Yesterday ${row.resolved_yesterday}</div>
                        <div class="tiny-note">Open ${row.open_chats}/${row.max_concurrent_chats}</div>
                    </div>
                    <div class="load-bar"><span style="width:${Math.max(8, Math.round((row.open_chats / Math.max(1, row.max_concurrent_chats)) * 100))}%"></span></div>
                </article>
            `).join('');

            drawBarChart(document.getElementById('resolution-chart'), rows);
        }

        function renderCharts() {
            drawDonutChart(document.getElementById('status-chart'), state.dashboard.reports.status_breakdown || {});
            renderLeaderboard();
            renderCoverageList();
        }

        function renderCoverageList() {
            const container = document.getElementById('coverage-list');
            const rows = state.dashboard.csr_users || [];
            const leaderboard = new Map((state.dashboard.reports.resolution_leaderboard || []).map((row) => [row.id, row]));

            if (!rows.length) {
                container.innerHTML = '<div class="tiny-note">No CSR accounts are available yet.</div>';
                return;
            }

            container.innerHTML = rows.map((csr) => {
                const report = leaderboard.get(csr.id) || { resolved_today: 0 };
                const activeChats = Number(csr.active_chat_count || 0);
                const maxChats = Math.max(1, Number(csr.max_concurrent_chats || 0));
                const remainingCapacity = Math.max(0, maxChats - activeChats);
                return `
                    <article class="coverage-row">
                        <div>
                            <div class="item-head">
                                <div class="coverage-name">${escapeHtml(csr.display_name)}</div>
                                <span class="badge ${csr.is_online ? 'online' : 'offline'}">${csr.is_online ? 'Online' : 'Offline'}</span>
                            </div>
                            <div class="tiny-note" style="margin-top:6px;">${csr.is_available ? 'Available' : 'Paused'} · Resolved today ${report.resolved_today || 0}</div>
                        </div>
                        <div class="coverage-stat">Open ${activeChats}/${maxChats}</div>
                        <div class="coverage-stat">Free ${remainingCapacity}</div>
                    </article>
                `;
            }).join('');
        }

        function renderCsrTable() {
            const tbody = document.getElementById('csr-table-body');
            const rows = state.dashboard.csr_users || [];
            const availableNow = state.dashboard.available_csr_users || [];
            const leaderboard = new Map((state.dashboard.reports.resolution_leaderboard || []).map((row) => [row.id, row]));
            document.getElementById('roster-count').textContent = `${rows.length} registered · ${availableNow.length} available now`;

            if (!rows.length) {
                tbody.innerHTML = '<tr><td colspan="6" class="tiny-note" style="padding:24px;">No CSR accounts have been registered yet.</td></tr>';
                return;
            }

            tbody.innerHTML = rows.map((csr) => {
                const report = leaderboard.get(csr.id) || { resolved_today: 0, resolved_yesterday: 0 };
                const unlimited = Boolean(csr.unlimited_chats);
                const loadCell = unlimited
                    ? `${csr.active_chat_count} <span class="badge unlimited">Unlimited</span>`
                    : `${csr.active_chat_count}/${csr.max_concurrent_chats}`;
                return `
                    <tr>
                        <td>
                            <strong>${escapeHtml(csr.display_name)}</strong><br>
                            <span class="cell-subtle">${escapeHtml(csr.email)}</span>
                        </td>
                        <td>
                            <span class="badge ${csr.is_online ? 'online' : 'offline'}">${csr.is_online ? 'Online' : 'Offline'}</span><br>
                            <span class="cell-subtle">${escapeHtml(formatPresence(csr))}</span>
                        </td>
                        <td>
                            ${loadCell}<br>
                            <span class="cell-subtle">${csr.is_available ? 'Available' : 'Paused'}</span>
                        </td>
                        <td>${report.resolved_today}</td>
                        <td>${report.resolved_yesterday}</td>
                        <td>
                            <form class="settings-form" data-csr-id="${csr.id}">
                                <label>
                                    <span>Max chats</span>
                                    <select class="input" name="max_concurrent_chats_sel">
                                        ${[1,2,3,4,5,10,20,30,40,50,75,100,200,500,1000].map((n) => {
                                            const sel = !unlimited && Number(csr.max_concurrent_chats) === n ? 'selected' : '';
                                            return `<option value="${n}" ${sel}>${n}</option>`;
                                        }).join('')}
                                        <option value="custom" ${!unlimited && ![1,2,3,4,5,10,20,30,40,50,75,100,200,500,1000].includes(Number(csr.max_concurrent_chats)) ? 'selected' : ''}>Custom...</option>
                                        <option value="unlimited" ${unlimited ? 'selected' : ''}>∞ Unlimited</option>
                                    </select>
                                    <input class="input" type="number" min="1" name="max_concurrent_chats" value="${csr.max_concurrent_chats}" style="${unlimited || [1,2,3,4,5,10,20,30,40,50,75,100,200,500,1000].includes(Number(csr.max_concurrent_chats)) ? 'display:none;' : ''}margin-top:6px;" placeholder="Enter number">
                                </label>
                                <label class="checkbox-row unlimited-row">
                                    <input type="checkbox" name="unlimited_chats" ${unlimited ? 'checked' : ''}>
                                    <span>Unlimited</span>
                                </label>
                                <label class="checkbox-row">
                                    <input type="checkbox" name="is_available" ${csr.is_available ? 'checked' : ''}>
                                    <span>Available</span>
                                </label>
                                <button class="mini-btn primary" type="submit">Save</button>
                            </form>
                        </td>
                    </tr>
                `;
            }).join('');

            tbody.querySelectorAll('.settings-form').forEach((form) => {
                const unlimitedCheckbox = form.querySelector('input[name="unlimited_chats"]');
                const maxChatsInput = form.querySelector('input[name="max_concurrent_chats"]');
                const maxChatsSel = form.querySelector('select[name="max_concurrent_chats_sel"]');

                // Helper: sync UI state from select value
                function applySelChange(val) {
                    if (val === 'unlimited') {
                        if (unlimitedCheckbox) unlimitedCheckbox.checked = true;
                        if (maxChatsInput) maxChatsInput.style.display = 'none';
                    } else if (val === 'custom') {
                        if (unlimitedCheckbox) unlimitedCheckbox.checked = false;
                        if (maxChatsInput) { maxChatsInput.style.display = ''; maxChatsInput.focus(); }
                    } else {
                        if (unlimitedCheckbox) unlimitedCheckbox.checked = false;
                        if (maxChatsInput) { maxChatsInput.style.display = 'none'; maxChatsInput.value = val; }
                    }
                }

                if (maxChatsSel) {
                    maxChatsSel.addEventListener('change', () => applySelChange(maxChatsSel.value));
                }

                if (unlimitedCheckbox && maxChatsSel) {
                    unlimitedCheckbox.addEventListener('change', () => {
                        if (unlimitedCheckbox.checked) {
                            maxChatsSel.value = 'unlimited';
                            if (maxChatsInput) maxChatsInput.style.display = 'none';
                        } else {
                            maxChatsSel.value = maxChatsInput ? (maxChatsInput.value || '4') : '4';
                            applySelChange(maxChatsSel.value);
                        }
                    });
                }
                form.addEventListener('submit', async (event) => {
                    event.preventDefault();
                    const csrId = form.dataset.csrId;
                    const selVal = maxChatsSel ? maxChatsSel.value : null;
                    const isUnlimited = selVal === 'unlimited' || (unlimitedCheckbox ? unlimitedCheckbox.checked : false);
                    // For custom or preset values, read from the number input; for unlimited use 0 as sentinel
                    const maxConcurrentChats = isUnlimited ? 0
                        : (selVal === 'custom' ? (maxChatsInput ? maxChatsInput.value : 4) : (selVal || (maxChatsInput ? maxChatsInput.value : 4)));
                    const isAvailable = form.querySelector('input[name="is_available"]').checked;
                    try {
                        const response = await requestJson(`/api/csrs/${csrId}/settings`, {
                            method: 'POST',
                            body: JSON.stringify({
                                max_concurrent_chats: maxConcurrentChats,
                                is_available: isAvailable,
                                unlimited_chats: isUnlimited
                            })
                        });
                        state.dashboard = response.dashboard;
                        renderCurrentPage();
                        showBanner('CSR settings updated.', 'success');
                    } catch (error) {
                        showBanner(error.message, 'error');
                    }
                });
            });
        }

        function renderChatTable() {
            const tbody = document.getElementById('chat-table-body');
            const chats = state.dashboard.chats || [];
            const pagination = state.dashboard.chats_pagination || null;
            const total = pagination ? pagination.total : chats.length;
            document.getElementById('chat-count').textContent = `${total} chat${total === 1 ? '' : 's'}`;

            if (!chats.length) {
                tbody.innerHTML = '<tr><td colspan="7" class="tiny-note" style="padding:24px;">No chats have been stored yet.</td></tr>';
                renderChatPagination(pagination);
                return;
            }

            tbody.innerHTML = chats.map((chat) => `
                <tr class="${state.selectedChatId === chat.id ? 'is-selected' : ''}">
                    <td>
                        <strong>${escapeHtml(chat.customer_name || chat.visitor_id)}</strong><br>
                        <span class="cell-subtle">${escapeHtml(chat.visitor_id)}</span>
                    </td>
                    <td>${escapeHtml(chat.status.replace('_', ' '))}</td>
                    <td>${escapeHtml(chat.assigned_label || 'Waiting queue')}</td>
                    <td>${chat.message_count}</td>
                    <td>
                        ${escapeHtml(formatRelative(chat.last_activity_at))}<br>
                        <span class="cell-subtle">${escapeHtml(formatDateTime(chat.last_activity_at))}</span>
                    </td>
                    <td>${escapeHtml(chat.last_customer_message || chat.preview || 'No customer message yet.')}</td>
                    <td>
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

            return messages.map((message) => `
                <div class="message ${escapeHtml(message.sender_type)}">
                    <div class="message-label">${escapeHtml(message.sender_type.toUpperCase())}</div>
                    <div class="message-bubble">${escapeHtml(message.content)}</div>
                    <div class="message-time">${escapeHtml(formatDateTime(message.created_at))}</div>
                </div>
            `).join('');
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
            detailSubtitle.textContent = `${chat.visitor_id} · ${chat.message_count} messages · ${chat.status.replace('_', ' ')}`;
            detailActions.innerHTML = `
                <button class="mini-btn danger" id="detail-delete-btn" type="button">Delete Chat</button>
            `;
            detailGrid.innerHTML = `
                <div class="chat-meta-card">
                    <div class="meta-label">Status</div>
                    <div class="meta-value">${escapeHtml(chat.status.replace('_', ' '))}</div>
                </div>
                <div class="chat-meta-card">
                    <div class="meta-label">Assigned CSR</div>
                    <div class="meta-value">${escapeHtml(chat.assigned_label || 'Waiting queue')}</div>
                </div>
                <div class="chat-meta-card">
                    <div class="meta-label">Customer Email</div>
                    <div class="meta-value">${escapeHtml(chat.customer_email || 'Not available')}</div>
                </div>
                <div class="chat-meta-card">
                    <div class="meta-label">Last Activity</div>
                    <div class="meta-value">${escapeHtml(formatDateTime(chat.last_activity_at))}</div>
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

        function renderCurrentPage(forceIntegrationSync = false) {
            if (!state.dashboard) {
                return;
            }
            if (currentPage === 'overview') {
                renderSummary();
                renderCharts();
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
            if (currentPage === 'chats') {
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
            if (currentPage === 'chats' && reloadSelectedChat && state.selectedChatId && chats.some((chat) => chat.id === state.selectedChatId)) {
                try {
                    const detailPayload = await requestJson(`/api/chats/${state.selectedChatId}/messages`, { method: 'GET' });
                    state.selectedMessages = detailPayload.messages || [];
                    state.selectedEvents = detailPayload.events || [];
                } catch (_error) {
                    state.selectedChatId = null;
                    state.selectedMessages = [];
                    state.selectedEvents = [];
                }
            } else if (currentPage === 'chats' && (!state.selectedChatId || !chats.some((chat) => chat.id === state.selectedChatId))) {
                state.selectedChatId = null;
                state.selectedMessages = [];
                state.selectedEvents = [];
            }
            renderCurrentPage();
        }

        const createCsrForm = document.getElementById('create-csr-form');
        if (createCsrForm) {
            const unlimitedBox = createCsrForm.querySelector('input[name="unlimited_chats"]');
            const maxChatsSel = createCsrForm.querySelector('select[name="max_concurrent_chats_sel"]');
            const maxChatsCustom = createCsrForm.querySelector('input[name="max_concurrent_chats"]');

            function applyCreateSelChange(val) {
                if (val === 'unlimited') {
                    if (unlimitedBox) unlimitedBox.checked = true;
                    if (maxChatsCustom) maxChatsCustom.style.display = 'none';
                } else if (val === 'custom') {
                    if (unlimitedBox) unlimitedBox.checked = false;
                    if (maxChatsCustom) { maxChatsCustom.style.display = ''; maxChatsCustom.focus(); }
                } else {
                    if (unlimitedBox) unlimitedBox.checked = false;
                    if (maxChatsCustom) { maxChatsCustom.style.display = 'none'; maxChatsCustom.value = val; }
                }
            }

            if (maxChatsSel) {
                maxChatsSel.addEventListener('change', () => applyCreateSelChange(maxChatsSel.value));
            }

            if (unlimitedBox && maxChatsSel) {
                unlimitedBox.addEventListener('change', () => {
                    if (unlimitedBox.checked) {
                        maxChatsSel.value = 'unlimited';
                        if (maxChatsCustom) maxChatsCustom.style.display = 'none';
                    } else {
                        maxChatsSel.value = '4';
                        if (maxChatsCustom) { maxChatsCustom.style.display = 'none'; maxChatsCustom.value = '4'; }
                    }
                });
            }

            createCsrForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const formData = new FormData(form);
                const selVal = maxChatsSel ? maxChatsSel.value : '4';
                const isUnlimited = selVal === 'unlimited' || formData.get('unlimited_chats') === 'on';
                const maxConcurrentChats = isUnlimited ? 0
                    : (selVal === 'custom' ? (maxChatsCustom ? maxChatsCustom.value : 4) : (selVal || 4));
                try {
                    const response = await requestJson('/api/admin/csrs/create', {
                        method: 'POST',
                        body: JSON.stringify({
                            display_name: formData.get('display_name'),
                            email: formData.get('email'),
                            password: formData.get('password'),
                            max_concurrent_chats: maxConcurrentChats,
                            is_available: formData.get('is_available') === 'on',
                            unlimited_chats: isUnlimited
                        })
                    });
                    form.reset();
                    if (maxChatsSel) maxChatsSel.value = '4';
                    if (maxChatsCustom) { maxChatsCustom.style.display = 'none'; maxChatsCustom.value = '4'; }
                    form.querySelector('input[name="is_available"]').checked = true;
                    if (unlimitedBox) unlimitedBox.checked = false;
                    state.dashboard = response.dashboard;
                    renderCurrentPage();
                    showBanner(response.message || 'CSR account created.', 'success');
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

        document.getElementById('refresh-btn').addEventListener('click', async () => {
            try {
                if (currentPage === 'activity') {
                    await loadActivityEvents({ append: false, limit: ACTIVITY_DEFAULT_BATCH });
                    showBanner('Activity timeline refreshed.', 'success');
                    return;
                }
                if (!dashboardEnabled) {
                    window.location.reload();
                    return;
                }
                await refreshDashboard(true);
                showBanner('Dashboard refreshed.', 'success');
            } catch (error) {
                showBanner(error.message, 'error');
            }
        });

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
            if (state.dashboard && currentPage === 'overview') {
                renderCharts();
            }
        });

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

        if (dashboardEnabled) {
            refreshDashboard(true).catch((error) => {
                showBanner(error.message, 'error');
            });

            refreshInterval = window.setInterval(() => {
                refreshDashboard(currentPage === 'chats' && Boolean(state.selectedChatId)).catch(() => {});
            }, 8000);
        }

        // ── Technical Team Section ──
        function showTechSection() {
            document.querySelectorAll('.section').forEach(s => s.style.display = 'none');
            document.getElementById('tech-section').style.display = 'block';
            document.querySelectorAll('.nav-btn').forEach(btn => btn.classList.remove('active'));
            document.querySelectorAll('.nav-btn').forEach(btn => {
                if (btn.textContent.includes('Technical Team')) btn.classList.add('active');
            });
            loadTechData();
        }

        let adminTicketStatuses = [];

        function setTechDataLoadError(message) {
            const err = escapeHtml(message || 'Failed to load data');
            const wl = document.getElementById('tech-workload-body');
            const tb = document.getElementById('admin-ticket-table-body');
            if (wl) wl.innerHTML = `<tr><td colspan="7" class="px-4 py-8 text-center text-red-400">${err}</td></tr>`;
            if (tb) tb.innerHTML = `<tr><td colspan="10" class="px-4 py-8 text-center text-red-400">${err}</td></tr>`;
        }

        async function loadTechData() {
            const workloadBody = document.getElementById('tech-workload-body');
            const ticketBody = document.getElementById('admin-ticket-table-body');
            if (workloadBody) workloadBody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-slate-500">Loading workload...</td></tr>';
            if (ticketBody) ticketBody.innerHTML = '<tr><td colspan="10" class="px-4 py-8 text-center text-slate-500">Loading tickets...</td></tr>';

            try {
                const statusFilter = document.getElementById('admin-ticket-status-filter')?.value || 'all';
                const ticketUrl = statusFilter === 'all'
                    ? '/api/admin/tickets?view=list'
                    : `/api/admin/tickets?view=list&status=${encodeURIComponent(statusFilter)}`;

                const [techResp, ticketsResp] = await Promise.all([
                    requestJson('/api/admin/tech-accounts'),
                    requestJson(ticketUrl),
                ]);

                const techs = techResp.techs || [];
                const tickets = ticketsResp.tickets || [];
                const statuses = ticketsResp.statuses || [];
                const stats = ticketsResp.stats || {};
                const workload = ticketsResp.tech_workload || [];
                adminTicketStatuses = statuses;

                const setStat = (id, val) => { const el = document.getElementById(id); if (el) el.textContent = val; };
                setStat('stat-tech-count', techs.filter(t => t.is_active).length);
                setStat('stat-open-tickets', stats.open ?? 0);
                setStat('stat-progress-tickets', stats.in_progress ?? 0);
                setStat('stat-closed-tickets', stats.closed ?? 0);
                setStat('stat-total-tickets', stats.total ?? 0);
                setStat('stat-unassigned-tickets', stats.unassigned ?? 0);

                populateAdminTicketStatusFilter(statuses);

                // Render tech table
                const techBody = document.getElementById('tech-table-body');
                if (techs.length === 0) {
                    techBody.innerHTML = '<tr><td colspan="6" class="tiny-note" style="padding:24px;">No technical team members yet. Use the form above to add one.</td></tr>';
                } else {
                    document.getElementById('tech-count').textContent = `${techs.length} member${techs.length !== 1 ? 's' : ''}`;
                    techBody.innerHTML = techs.map(tech => `
                        <tr>
                            <td><strong>${escapeHtml(tech.display_name || 'Unnamed')}</strong></td>
                            <td>${escapeHtml(tech.email)}</td>
                            <td>${escapeHtml(tech.specialty || 'General')}</td>
                            <td>${tech.is_active ? '<span class="chip chip-active">Active</span>' : '<span class="chip chip-inactive">Inactive</span>'}</td>
                            <td>${tech.last_seen_at ? formatDate(tech.last_seen_at) : 'Never'}</td>
                            <td>
                                <button class="mini-btn" onclick="editTechMember(${tech.id})" title="Toggle active"><i class="fa-solid fa-power-off"></i></button>
                                <button class="mini-btn danger" onclick="deleteTechMember(${tech.id})" title="Delete member"><i class="fa-solid fa-trash"></i></button>
                            </td>
                        </tr>
                    `).join('');
                }

                // Render statuses
                const statusList = document.getElementById('status-list');
                if (statuses.length === 0) {
                    statusList.innerHTML = '<div class="tiny-note">No statuses configured.</div>';
                } else {
                    statusList.innerHTML = statuses.map(s => `
                        <div class="status-item">
                            <div class="status-color" style="background:${s.color}"></div>
                            <div class="status-label">${escapeHtml(s.label)}</div>
                            <div class="status-badge" style="background:${s.color}22;color:${s.color}">${escapeHtml(s.name)}</div>
                            ${s.is_resolved ? '<span class="status-badge" style="background:#10b98122;color:#10b981">Resolved</span>' : ''}
                        </div>
                    `).join('');
                }

                if (workloadBody) {
                    if (!workload.length) {
                        workloadBody.innerHTML = '<tr><td colspan="7" class="px-4 py-8 text-center text-slate-500">No technical team members yet.</td></tr>';
                    } else {
                        workloadBody.innerHTML = workload.map(row => `
                            <tr class="hover:bg-slate-800/40">
                                <td class="px-4 py-3"><strong class="text-white">${escapeHtml(row.display_name)}</strong><div class="text-xs text-slate-500">${escapeHtml(row.email)}</div></td>
                                <td class="px-4 py-3">${escapeHtml(row.specialty || 'General')}</td>
                                <td class="px-4 py-3">${row.is_active ? '<span class="inline-flex rounded-full bg-emerald-500/15 px-2 py-0.5 text-xs font-semibold text-emerald-300">Active</span>' : '<span class="inline-flex rounded-full bg-slate-600/30 px-2 py-0.5 text-xs text-slate-400">Inactive</span>'}</td>
                                <td class="px-4 py-3 font-bold text-teal-300">${row.active}</td>
                                <td class="px-4 py-3">${row.in_progress}</td>
                                <td class="px-4 py-3">${row.open}</td>
                                <td class="px-4 py-3">${row.total_assigned}</td>
                            </tr>
                        `).join('');
                    }
                }

                const countEl = document.getElementById('admin-ticket-count');
                if (countEl) countEl.textContent = `${tickets.length} ticket${tickets.length !== 1 ? 's' : ''}`;
                if (ticketBody) {
                    if (!tickets.length) {
                        ticketBody.innerHTML = '<tr><td colspan="10" class="px-4 py-8 text-center text-slate-500">No tickets match this filter.</td></tr>';
                    } else {
                        ticketBody.innerHTML = tickets.map(t => {
                            const status = statuses.find(s => s.name === t.status) || {};
                            const csrName = t.created_by_csr ? (t.created_by_csr.display_name || t.created_by_csr.email) : '—';
                            const statusColor = status.color || '#64748b';
                            const lastNote = t.last_status_update?.notes
                                ? `<div class="text-xs text-slate-500 mt-1" title="${escapeHtml(t.last_status_update.notes)}">${escapeHtml(t.last_status_update.notes).slice(0, 50)}${t.last_status_update.notes.length > 50 ? '…' : ''}</div>`
                                : '';
                            const lastAssignment = t.last_assignment_update;
                            const assignmentTrail = lastAssignment
                                ? `<div class="mt-1 text-xs text-amber-300/90" title="${escapeHtml(lastAssignment.notes || '')}">
                                    <i class="fa-solid fa-share-nodes mr-1"></i>${escapeHtml(lastAssignment.old_assigned_tech ? (lastAssignment.old_assigned_tech.display_name || lastAssignment.old_assigned_tech.email) : 'Unassigned')}
                                    <span class="text-slate-500">&rarr;</span>
                                    ${escapeHtml(lastAssignment.new_assigned_tech ? (lastAssignment.new_assigned_tech.display_name || lastAssignment.new_assigned_tech.email) : 'Unassigned')}
                                    ${lastAssignment.changed_by_name ? `<div class="text-slate-500">By ${escapeHtml(lastAssignment.changed_by_name)}</div>` : ''}
                                </div>`
                                : '';
                            return `
                                <tr class="hover:bg-slate-800/40 align-top">
                                    <td class="px-4 py-3 font-mono font-bold text-teal-300 whitespace-nowrap">${escapeHtml(t.ticket_number || ('#' + t.id))}</td>
                                    <td class="px-4 py-3"><div class="font-semibold text-white">${escapeHtml(t.title)}</div>${t.description ? `<div class="text-xs text-slate-500 mt-0.5">${escapeHtml(t.description).slice(0, 60)}${t.description.length > 60 ? '…' : ''}</div>` : ''}${lastNote}</td>
                                    <td class="px-4 py-3"><span class="inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold" style="background:${statusColor}22;color:${statusColor}">${escapeHtml(status.label || t.status)}</span></td>
                                    <td class="px-4 py-3 capitalize">${escapeHtml(t.priority || 'normal')}</td>
                                    <td class="px-4 py-3">${escapeHtml(csrName)}</td>
                                    <td class="px-4 py-3">${t.assigned_tech ? `<span class="text-white">${escapeHtml(t.assigned_tech.display_name || 'Tech')}</span><div class="text-xs text-slate-500">${escapeHtml(t.assigned_tech.specialty || '')}</div>${assignmentTrail}` : '<span class="inline-flex rounded-full bg-slate-600/30 px-2 py-0.5 text-xs text-slate-400">Unassigned</span>'}</td>
                                    <td class="px-4 py-3">${t.message_count ?? 0}</td>
                                    <td class="px-4 py-3 text-slate-400">${formatDate(t.created_at)}</td>
                                    <td class="px-4 py-3 text-slate-400">${formatDate(t.updated_at)}</td>
                                    <td class="px-4 py-3 text-slate-400">${t.resolved_at ? formatDate(t.resolved_at) : '—'}</td>
                                </tr>
                            `;
                        }).join('');
                    }
                }
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
            adminTicketStatusFilter.addEventListener('change', () => loadTechData());
        }
        const adminTicketRefreshBtn = document.getElementById('admin-ticket-refresh-btn');
        if (adminTicketRefreshBtn) {
            adminTicketRefreshBtn.addEventListener('click', () => loadTechData());
        }

        function formatDate(dateStr) {
            if (!dateStr) return 'N/A';
            const date = new Date(dateStr);
            return date.toLocaleDateString('en-US', { month: 'short', day: 'numeric', hour: '2-digit', minute: '2-digit' });
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
                        showBanner(resp.message, 'success');
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

        // ── Create Ticket Status Form ──
        const createStatusForm = document.getElementById('create-status-form');
        if (createStatusForm) {
            createStatusForm.addEventListener('submit', async (event) => {
                event.preventDefault();
                const form = event.currentTarget;
                const formData = new FormData(form);
                const payload = {
                    name: formData.get('name').trim().toLowerCase(),
                    label: formData.get('label').trim(),
                    color: formData.get('color'),
                    sort_order: parseInt(formData.get('sort_order')) || 10,
                    is_resolved: formData.has('is_resolved'),
                };

                if (!payload.name || !payload.label) {
                    showBanner('Status name and label are required.', 'error');
                    return;
                }

                try {
                    const resp = await requestJson('/api/admin/ticket-statuses', {
                        method: 'POST',
                        body: JSON.stringify(payload),
                    });
                    if (resp.success) {
                        showBanner(resp.message, 'success');
                        form.reset();
                        loadTechData();
                    } else {
                        showBanner(resp.error || 'Failed to create status', 'error');
                    }
                } catch (err) {
                    showBanner(err.message, 'error');
                }
            });
        }

        function editTechMember(id) {
            // Toggle active/inactive
            if (confirm('Toggle this member\'s active status?')) {
                fetch(`/api/admin/tech-accounts/${id}`, {
                    method: 'PUT',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ is_active: false })
                })
                .then(r => r.json())
                .then(data => {
                    if (data.success) {
                        showBanner('Member status updated.', 'success');
                        loadTechData();
                    } else {
                        showBanner(data.error || 'Failed to update member', 'error');
                    }
                })
                .catch(() => showBanner('Failed to update member', 'error'));
            }
        }

        function deleteTechMember(id) {
            if (confirm('Are you sure you want to delete this technical team member?')) {
                requestJson(`/api/admin/tech-accounts/${id}`, { method: 'DELETE' })
                    .then(data => {
                        if (data.success) {
                            showBanner('Technical team member deleted.', 'success');
                            loadTechData();
                        } else {
                            showBanner(data.error || 'Failed to delete member', 'error');
                        }
                    })
                    .catch((err) => showBanner(err.message || 'Failed to delete member', 'error'));
            }
        }

        if (document.body.dataset.adminPage === 'tech') {
            loadTechData();
            window.setInterval(() => loadTechData().catch(() => {}), 30000);
        }