/**
 * CSR Dashboard Widget
 * 
 * A self-contained Live Chat CSR console widget for the dashboard.
 * Embeds via a single <script> tag, similar to authenticated-chat-widget.js.
 *
 * Config:
 *   - Preferred: pass data-* attributes on the script tag itself
 *   - Backward compatible: set window.CSRDashboardWidgetConfig before loading
 *   - baseUrl:        (string)  Base URL of the central API, e.g. 'http://52.74.227.205:5003'
 *   - csrKey:         (string)  Optional CSR key for standalone/external usage without dashboard session
 *   - containerId:    (string)  ID of the DOM element to render into (default: 'live-chat-section')
 *   - chatListPoll:   (number)  Interval in ms to poll chat list (default: 5000)
 *   - messagePoll:    (number)  Interval in ms to poll messages (default: 3000)
 *   - primaryColor:   (string)  Primary accent color (default: '#2563EB')
 *   - onActivate:     (fn)      Called when the widget section becomes visible
 *   - onDeactivate:   (fn)      Called when the widget section is hidden
 */
(function () {
    'use strict';

    const bootScript = document.currentScript || Array.from(document.scripts || []).find((script) => {
        return script.src && script.src.indexOf('csr-dashboard-widget.js') !== -1;
    }) || null;

    function parseBoolean(value) {
        if (typeof value === 'boolean') return value;
        if (typeof value !== 'string') return null;

        const normalized = value.trim().toLowerCase();
        if (normalized === 'true') return true;
        if (normalized === 'false') return false;
        return null;
    }

    function parseNumber(value, fallback) {
        if (typeof value === 'number' && Number.isFinite(value)) return value;
        if (typeof value !== 'string' || value.trim() === '') return fallback;

        const parsed = Number(value);
        return Number.isFinite(parsed) ? parsed : fallback;
    }

    function getScriptConfig(script) {
        if (!script) return {};

        const scriptConfig = {};
        const autoActivate = parseBoolean(script.dataset.autoActivate);

        if (script.dataset.baseUrl) scriptConfig.baseUrl = script.dataset.baseUrl;
        if (script.dataset.csrKey) scriptConfig.csrKey = script.dataset.csrKey;
        if (script.dataset.containerId) scriptConfig.containerId = script.dataset.containerId;
        if (script.dataset.primaryColor) scriptConfig.primaryColor = script.dataset.primaryColor;

        const chatListPoll = parseNumber(script.dataset.chatListPoll, undefined);
        if (typeof chatListPoll === 'number') scriptConfig.chatListPoll = chatListPoll;

        const messagePoll = parseNumber(script.dataset.messagePoll, undefined);
        if (typeof messagePoll === 'number') scriptConfig.messagePoll = messagePoll;

        if (autoActivate !== null) scriptConfig.autoActivate = autoActivate;

        return scriptConfig;
    }

    // ─── Config ────────────────────────────────────────────────────────
    const config = Object.assign({
        baseUrl: '',
        csrKey: '',
        containerId: 'live-chat-section',
        widgetTitle: 'Live Chat',
        chatListPoll: 5000,
        messagePoll: 3000,
        primaryColor: '#2563EB',
        autoActivate: null,
        onActivate: null,
        onDeactivate: null,
    }, window.CSRDashboardWidgetConfig || {}, getScriptConfig(bootScript));

    // Strip trailing slash
    if (config.baseUrl.endsWith('/')) config.baseUrl = config.baseUrl.slice(0, -1);

    // ─── State ─────────────────────────────────────────────────────────
    let currentSessionId = null;
    let currentVisitorId = null;
    let chatListInterval = null;
    let messageInterval = null;
    let isActive = false;           // Whether the Live Chat section is visible
    let lastRenderedMsgCount = 0;   // Track messages to avoid unnecessary re-renders
    let mobileChatOpen = false;
    let layoutObserver = null;

    function isExternalMode() {
        return !!config.csrKey;
    }

    function externalUrl(path) {
        const joiner = path.includes('?') ? '&' : '?';
        return `${config.baseUrl}${path}${joiner}csr_key=${encodeURIComponent(config.csrKey)}`;
    }

    function withAuth(options, extraJson) {
        const requestOptions = Object.assign({}, options);

        if (isExternalMode()) {
            if (extraJson) {
                requestOptions.body = JSON.stringify(Object.assign({}, extraJson, { csr_key: config.csrKey }));
            }
        } else {
            requestOptions.credentials = 'include';
            if (extraJson) {
                requestOptions.body = JSON.stringify(extraJson);
            }
        }

        return requestOptions;
    }

    // ─── CSS ───────────────────────────────────────────────────────────
    function injectStyles() {
        if (document.getElementById('csr-dw-styles')) return;
        const style = document.createElement('style');
        style.id = 'csr-dw-styles';
        style.textContent = `
            /* ── CSR Dashboard Widget ── */
            .csr-dw-host {
                display: flex !important;
                flex-direction: column;
                width: 100%;
                max-width: 100%;
                min-width: 0;
                height: 100%;
                min-height: 0;
                overflow: hidden;
                margin: 0 !important;
                padding: 0 !important;
            }
            .csr-dw,
            .csr-dw * {
                box-sizing: border-box;
            }
            .csr-dw {
                display: flex;
                flex-direction: column;
                height: 100%;
                min-height: 0;
                width: 100%;
                max-width: 100%;
                overflow: hidden;
                font-family: 'Plus Jakarta Sans', -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, sans-serif;
            }
            .csr-dw-header {
                margin-bottom: 16px;
                flex-shrink: 0;
            }
            .csr-dw-header h1 {
                font-size: 1.875rem;
                font-weight: 700;
                color: #1f2937;
                margin: 0;
                line-height: 1.1;
            }

            .csr-dw-body {
                flex: 1;
                display: flex;
                background: #ffffff;
                border-radius: 12px;
                box-shadow: 0 1px 3px rgba(0,0,0,0.1), 0 1px 2px rgba(0,0,0,0.06);
                overflow: hidden;
                min-height: 0;
                height: 100%;
                position: relative;
                width: 100%;
                max-width: 100%;
            }

            /* ── Sidebar (Chat List) ── */
            .csr-dw-sidebar {
                width: 340px;
                min-width: 280px;
                min-height: 0;
                border-right: 1px solid #e5e7eb;
                display: flex;
                flex-direction: column;
                background: #f9fafb;
            }
            .csr-dw-sidebar-head {
                padding: 16px 20px;
                border-bottom: 1px solid #e5e7eb;
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: #fff;
            }
            .csr-dw-sidebar-head h3 {
                font-size: 1rem;
                font-weight: 600;
                color: #374151;
                margin: 0;
            }
            .csr-dw-badge {
                display: inline-flex;
                align-items: center;
                justify-content: center;
                min-width: 22px;
                height: 22px;
                padding: 0 6px;
                border-radius: 999px;
                font-size: 0.7rem;
                font-weight: 700;
                color: #fff;
                background: ${config.primaryColor};
            }
            .csr-dw-chat-list {
                flex: 1;
                overflow-y: auto;
                padding: 8px;
                min-height: 0;
            }
            .csr-dw-chat-list::-webkit-scrollbar { width: 4px; }
            .csr-dw-chat-list::-webkit-scrollbar-thumb { background: #d1d5db; border-radius: 4px; }

            .csr-dw-chat-card {
                padding: 14px 16px;
                border-radius: 10px;
                cursor: pointer;
                transition: all 0.15s ease;
                border: 1px solid transparent;
                margin-bottom: 4px;
                background: #fff;
            }
            .csr-dw-chat-card:hover {
                background: #f3f4f6;
                border-color: #e5e7eb;
            }
            .csr-dw-chat-card.active {
                background: #eff6ff;
                border-color: #bfdbfe;
            }
            .csr-dw-card-top {
                display: flex;
                justify-content: space-between;
                align-items: center;
                margin-bottom: 6px;
            }
            .csr-dw-card-name {
                font-weight: 600;
                font-size: 0.9rem;
                color: #1f2937;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 180px;
                min-width: 0;
            }
            .csr-dw-card-meta {
                font-size: 0.72rem;
                color: #6b7280;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                max-width: 220px;
                margin-top: 2px;
            }
            .csr-dw-card-time {
                font-size: 0.7rem;
                color: #9ca3af;
            }
            .csr-dw-card-preview {
                font-size: 0.82rem;
                color: #6b7280;
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                margin-bottom: 8px;
                min-width: 0;
            }
            .csr-dw-status-badge {
                display: inline-block;
                font-size: 0.7rem;
                padding: 2px 8px;
                border-radius: 999px;
                font-weight: 600;
            }
            .csr-dw-status-pending {
                background: #fef3c7;
                color: #92400e;
            }
            .csr-dw-status-active {
                background: #d1fae5;
                color: #065f46;
            }
            .csr-dw-empty-list {
                text-align: center;
                color: #9ca3af;
                padding: 40px 20px;
                font-size: 0.9rem;
            }

            /* ── Chat Window ── */
            .csr-dw-window {
                flex: 1;
                display: flex;
                flex-direction: column;
                background: #fff;
                min-width: 0;
                min-height: 0;
                overflow: hidden;
            }
            .csr-dw-active-chat {
                flex: 1;
                display: flex;
                flex-direction: column;
                min-height: 0;
                overflow: hidden;
            }

            /* Empty state */
            .csr-dw-no-chat {
                flex: 1;
                display: flex;
                flex-direction: column;
                align-items: center;
                justify-content: center;
                color: #d1d5db;
            }
            .csr-dw-no-chat i {
                font-size: 4rem;
                margin-bottom: 16px;
                opacity: 0.4;
            }
            .csr-dw-no-chat p {
                font-size: 1.05rem;
                color: #9ca3af;
            }

            /* Chat header */
            .csr-dw-chat-header {
                padding: 14px 24px;
                border-bottom: 1px solid #f3f4f6;
                display: flex;
                justify-content: space-between;
                align-items: center;
                background: #fff;
                flex-shrink: 0;
            }
            .csr-dw-chat-user {
                display: flex;
                align-items: center;
                gap: 12px;
                flex: 1;
                min-width: 0;
            }
            .csr-dw-chat-user > div:last-child {
                min-width: 0;
            }
            .csr-dw-avatar {
                width: 40px;
                height: 40px;
                border-radius: 10px;
                background: linear-gradient(135deg, ${config.primaryColor}, #7c3aed);
                color: #fff;
                display: flex;
                align-items: center;
                justify-content: center;
                font-weight: 700;
                font-size: 1rem;
            }
            .csr-dw-user-name {
                font-weight: 700;
                font-size: 0.95rem;
                color: #1f2937;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .csr-dw-user-auth {
                font-size: 0.72rem;
                color: #4b5563;
                margin-top: 2px;
                white-space: nowrap;
                overflow: hidden;
                text-overflow: ellipsis;
            }
            .csr-dw-user-auth-panel {
                margin: 0 16px 10px;
                padding: 12px;
                border: 1px solid #dbeafe;
                border-radius: 12px;
                background: linear-gradient(135deg, #eff6ff 0%, #f8fafc 100%);
                flex-shrink: 0;
            }
            .csr-dw-user-auth-panel-title {
                font-size: 0.72rem;
                font-weight: 700;
                color: #374151;
                margin-bottom: 8px;
                text-transform: uppercase;
                letter-spacing: 0.04em;
            }
            .csr-dw-auth-grid {
                display: grid;
                grid-template-columns: repeat(2, minmax(0, 1fr));
                gap: 8px;
            }
            .csr-dw-auth-chip {
                background: #fff;
                border: 1px solid #e2e8f0;
                border-radius: 10px;
                padding: 8px 10px;
                min-width: 0;
            }
            .csr-dw-auth-chip-label {
                font-size: 10px;
                font-weight: 700;
                letter-spacing: .04em;
                text-transform: uppercase;
                color: #94a3b8;
                margin-bottom: 3px;
            }
            .csr-dw-auth-chip-value {
                font-size: 12px;
                font-weight: 600;
                color: #0f172a;
                overflow-wrap: anywhere;
                word-break: break-word;
            }
            .csr-dw-auth-chip-value.is-ok { color: #059669; }
            .csr-dw-auth-chip-value.is-bad { color: #dc2626; }
            .csr-dw-user-auth-panel pre {
                margin: 8px 0 0;
                white-space: pre-wrap;
                word-break: break-word;
                font-family: ui-monospace, SFMono-Regular, Menlo, Consolas, monospace;
                font-size: 11px;
                line-height: 1.4;
                color: #334155;
                background: #fff;
                border: 1px solid #e2e8f0;
                border-radius: 8px;
                padding: 8px;
                max-height: 120px;
                overflow: auto;
            }
            .csr-dw-user-status {
                font-size: 0.75rem;
                color: #6b7280;
                display: flex;
                align-items: center;
                gap: 4px;
            }
            .csr-dw-chat-actions {
                display: flex;
                align-items: center;
                gap: 10px;
                flex-shrink: 0;
            }
            .csr-dw-back-btn {
                display: none;
                background: #eff6ff;
                color: #1d4ed8;
                border: 1px solid #bfdbfe;
                padding: 7px 12px;
                border-radius: 8px;
                font-size: 0.82rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.15s;
                align-items: center;
                gap: 6px;
                white-space: nowrap;
            }
            .csr-dw-back-btn:hover {
                background: #dbeafe;
            }
            .csr-dw-dot-online {
                width: 7px;
                height: 7px;
                border-radius: 50%;
                background: #10b981;
            }
            .csr-dw-close-btn {
                background: #fff1f2;
                color: #e11d48;
                border: 1px solid #ffe4e6;
                padding: 7px 16px;
                border-radius: 8px;
                font-size: 0.82rem;
                font-weight: 600;
                cursor: pointer;
                transition: all 0.15s;
                display: flex;
                align-items: center;
                gap: 6px;
                white-space: nowrap;
            }
            .csr-dw-close-btn:hover {
                background: #ffe4e6;
            }

            /* Messages area */
            .csr-dw-messages {
                flex: 1;
                overflow-y: auto;
                padding: 24px;
                display: flex;
                flex-direction: column;
                gap: 12px;
                background: #fafbfc;
                min-height: 0;
            }
            .csr-dw-messages::-webkit-scrollbar { width: 4px; }
            .csr-dw-messages::-webkit-scrollbar-thumb { background: #e5e7eb; border-radius: 4px; }

            .csr-dw-msg {
                max-width: 70%;
                animation: csr-dw-fadeIn 0.25s ease-out;
            }
            @keyframes csr-dw-fadeIn {
                from { opacity: 0; transform: translateY(8px); }
                to   { opacity: 1; transform: translateY(0); }
            }
            .csr-dw-msg-label {
                font-size: 0.68rem;
                color: #9ca3af;
                margin-bottom: 3px;
                padding: 0 4px;
            }
            .csr-dw-msg-bubble {
                padding: 10px 16px;
                border-radius: 16px;
                font-size: 0.9rem;
                line-height: 1.5;
                box-shadow: 0 1px 2px rgba(0,0,0,0.04);
                word-wrap: break-word;
                overflow-wrap: anywhere;
                white-space: pre-wrap;
            }
            .csr-dw-attachments {
                display: grid;
                gap: 8px;
                margin-top: 8px;
            }
            .csr-dw-attachment-image {
                max-width: 240px;
                max-height: 180px;
                border-radius: 12px;
                display: block;
                object-fit: cover;
                border: 1px solid rgba(0,0,0,0.08);
            }
            .csr-dw-msg-time {
                font-size: 0.62rem;
                color: #c4c8cf;
                margin-top: 3px;
                padding: 0 4px;
            }

            /* User message (left) */
            .csr-dw-msg.msg-user {
                align-self: flex-start;
            }
            .csr-dw-msg.msg-user .csr-dw-msg-bubble {
                background: #fff;
                border: 1px solid #e5e7eb;
                color: #1f2937;
                border-bottom-left-radius: 4px;
            }

            /* CSR message (right) */
            .csr-dw-msg.msg-csr {
                align-self: flex-end;
                text-align: right;
            }
            .csr-dw-msg.msg-csr .csr-dw-msg-bubble {
                background: ${config.primaryColor};
                color: #fff;
                border-bottom-right-radius: 4px;
            }
            .csr-dw-msg.msg-csr .csr-dw-msg-time { text-align: right; }

            /* AI message (left, muted) */
            .csr-dw-msg.msg-ai {
                align-self: flex-start;
            }
            .csr-dw-msg.msg-ai .csr-dw-msg-bubble {
                background: #f8fafc;
                border: 1px dashed #e2e8f0;
                color: #64748b;
                font-style: italic;
                font-size: 0.82rem;
                border-bottom-left-radius: 4px;
            }

            /* Input area */
            .csr-dw-input-area {
                padding: 16px 24px;
                border-top: 1px solid #f3f4f6;
                background: #fff;
                flex-shrink: 0;
            }
            .csr-dw-input-wrap {
                display: flex;
                align-items: center;
                gap: 10px;
                background: #f9fafb;
                border: 1px solid #e5e7eb;
                border-radius: 999px;
                padding: 6px 8px 6px 20px;
                transition: border-color 0.15s, background 0.15s;
            }
            .csr-dw-input-wrap:focus-within {
                border-color: ${config.primaryColor};
                background: #fff;
            }
            .csr-dw-input {
                flex: 1;
                border: none;
                background: transparent;
                padding: 10px 0;
                font-family: inherit;
                font-size: 0.9rem;
                outline: none;
                color: #1f2937;
            }
            .csr-dw-input::placeholder { color: #9ca3af; }
            .csr-dw-send-btn {
                background: ${config.primaryColor};
                color: #fff;
                border: none;
                width: 38px;
                height: 38px;
                border-radius: 50%;
                cursor: pointer;
                transition: all 0.15s;
                display: flex;
                align-items: center;
                justify-content: center;
                flex-shrink: 0;
            }
            .csr-dw-send-btn:hover { filter: brightness(1.1); transform: scale(1.05); }
            .csr-dw-send-btn:disabled { opacity: 0.5; cursor: not-allowed; transform: none; }

            .csr-dw.csr-dw-compact .csr-dw-header {
                margin-bottom: 12px;
            }
            .csr-dw.csr-dw-compact .csr-dw-header h1 {
                font-size: 1.5rem;
            }
            .csr-dw.csr-dw-compact .csr-dw-body {
                flex-direction: column;
                min-height: 0;
            }
            .csr-dw.csr-dw-compact .csr-dw-sidebar {
                width: 100%;
                min-width: 0;
                max-height: 260px;
                border-right: none;
                border-bottom: 1px solid #e5e7eb;
            }
            .csr-dw.csr-dw-compact .csr-dw-chat-header {
                padding: 14px 16px;
                gap: 12px;
                flex-wrap: wrap;
            }
            .csr-dw.csr-dw-compact .csr-dw-messages {
                padding: 16px;
            }
            .csr-dw.csr-dw-compact .csr-dw-input-area {
                padding: 14px 16px;
            }
            .csr-dw.csr-dw-compact .csr-dw-msg {
                max-width: 88%;
            }

            .csr-dw.csr-dw-mobile {
                min-height: 0;
            }
            .csr-dw.csr-dw-mobile .csr-dw-body {
                min-height: 0;
            }
            .csr-dw.csr-dw-mobile .csr-dw-sidebar,
            .csr-dw.csr-dw-mobile .csr-dw-window {
                width: 100%;
                max-width: 100%;
            }
            .csr-dw.csr-dw-mobile .csr-dw-sidebar {
                max-height: none;
                border-bottom: none;
            }
            .csr-dw.csr-dw-mobile .csr-dw-window,
            .csr-dw.csr-dw-mobile .csr-dw-active-chat {
                min-height: 0;
                height: 100%;
            }
            .csr-dw.csr-dw-mobile:not(.csr-dw-mobile-chat-open) .csr-dw-window {
                display: none;
            }
            .csr-dw.csr-dw-mobile.csr-dw-mobile-chat-open .csr-dw-sidebar {
                display: none;
            }
            .csr-dw.csr-dw-mobile.csr-dw-mobile-chat-open .csr-dw-window {
                display: flex;
            }
            .csr-dw.csr-dw-mobile .csr-dw-chat-header {
                padding: 12px 14px;
                align-items: flex-start;
            }
            .csr-dw.csr-dw-mobile .csr-dw-chat-user {
                width: 100%;
            }
            .csr-dw.csr-dw-mobile .csr-dw-chat-actions {
                width: 100%;
                justify-content: space-between;
                flex-wrap: wrap;
            }
            .csr-dw.csr-dw-mobile .csr-dw-back-btn {
                display: inline-flex;
            }
            .csr-dw.csr-dw-mobile .csr-dw-close-btn {
                width: auto;
                justify-content: center;
            }
            .csr-dw.csr-dw-mobile .csr-dw-messages {
                padding: 12px;
                gap: 10px;
            }
            .csr-dw.csr-dw-mobile .csr-dw-input-area {
                padding: 12px;
            }
            .csr-dw.csr-dw-mobile .csr-dw-input-wrap {
                padding: 6px 6px 6px 14px;
                border-radius: 20px;
            }
            .csr-dw.csr-dw-mobile .csr-dw-send-btn {
                width: 42px;
                height: 42px;
            }
            .csr-dw.csr-dw-mobile .csr-dw-msg {
                max-width: 100%;
            }

            .csr-dw.csr-dw-narrow .csr-dw-header h1 {
                font-size: 1.3rem;
            }
            .csr-dw.csr-dw-narrow .csr-dw-body {
                border-radius: 10px;
            }
            .csr-dw.csr-dw-narrow .csr-dw-sidebar-head {
                padding: 14px 16px;
            }
            .csr-dw.csr-dw-narrow .csr-dw-chat-list {
                padding: 8px;
            }
            .csr-dw.csr-dw-narrow .csr-dw-chat-card {
                padding: 12px 14px;
            }
            .csr-dw.csr-dw-narrow .csr-dw-card-name {
                max-width: none;
            }
            .csr-dw.csr-dw-narrow .csr-dw-avatar {
                width: 36px;
                height: 36px;
                border-radius: 8px;
            }
            .csr-dw.csr-dw-narrow .csr-dw-user-name {
                font-size: 0.9rem;
            }
            .csr-dw.csr-dw-narrow .csr-dw-messages {
                padding: 14px 12px;
            }
            .csr-dw.csr-dw-narrow .csr-dw-msg {
                max-width: 100%;
            }
            .csr-dw.csr-dw-narrow .csr-dw-input-wrap {
                border-radius: 18px;
                padding-left: 14px;
            }
            .csr-dw.csr-dw-narrow .csr-dw-input {
                min-width: 0;
            }

            .csr-dw.csr-dw-tiny {
                min-height: 0;
            }
            .csr-dw.csr-dw-tiny .csr-dw-body {
                min-height: 0;
                border-radius: 0;
            }
            .csr-dw.csr-dw-tiny .csr-dw-sidebar-head {
                padding: 12px 14px;
            }
            .csr-dw.csr-dw-tiny .csr-dw-card-top {
                gap: 8px;
                align-items: flex-start;
            }
            .csr-dw.csr-dw-tiny .csr-dw-card-time {
                flex-shrink: 0;
            }
            .csr-dw.csr-dw-tiny .csr-dw-chat-header {
                gap: 10px;
            }
            .csr-dw.csr-dw-tiny .csr-dw-chat-actions {
                gap: 8px;
            }
            .csr-dw.csr-dw-tiny .csr-dw-back-btn,
            .csr-dw.csr-dw-tiny .csr-dw-close-btn {
                flex: 1 1 0;
                min-height: 40px;
            }
            .csr-dw.csr-dw-tiny .csr-dw-input-area {
                padding: 10px;
            }

            @media (max-width: 960px) {
                .csr-dw-header {
                    margin-bottom: 12px;
                }
                .csr-dw-header h1 {
                    font-size: 1.5rem;
                }
                .csr-dw-body {
                    flex-direction: column;
                    min-height: 0;
                }
                .csr-dw-sidebar {
                    width: 100%;
                    min-width: 0;
                    max-height: 260px;
                    border-right: none;
                    border-bottom: 1px solid #e5e7eb;
                }
                .csr-dw-chat-header {
                    padding: 14px 16px;
                    gap: 12px;
                    flex-wrap: wrap;
                }
                .csr-dw-messages {
                    padding: 16px;
                }
                .csr-dw-input-area {
                    padding: 14px 16px;
                }
                .csr-dw-msg {
                    max-width: 88%;
                }
            }

            @media (max-width: 768px) {
                .csr-dw {
                    min-height: 0;
                }
                .csr-dw-body {
                    min-height: 0;
                }
                .csr-dw-sidebar,
                .csr-dw-window {
                    width: 100%;
                    max-width: 100%;
                }
                .csr-dw-sidebar {
                    max-height: none;
                    border-bottom: none;
                }
                .csr-dw-window,
                .csr-dw-active-chat {
                    min-height: 0;
                    height: 100%;
                }
                .csr-dw:not(.csr-dw-mobile-chat-open) .csr-dw-window {
                    display: none;
                }
                .csr-dw.csr-dw-mobile-chat-open .csr-dw-sidebar {
                    display: none;
                }
                .csr-dw.csr-dw-mobile-chat-open .csr-dw-window {
                    display: flex;
                }
                .csr-dw-chat-header {
                    padding: 12px 14px;
                    align-items: flex-start;
                }
                .csr-dw-chat-user {
                    width: 100%;
                }
                .csr-dw-chat-actions {
                    width: 100%;
                    justify-content: space-between;
                    flex-wrap: wrap;
                }
                .csr-dw-back-btn {
                    display: inline-flex;
                }
                .csr-dw-close-btn {
                    width: auto;
                    justify-content: center;
                }
                .csr-dw-messages {
                    padding: 12px;
                    gap: 10px;
                }
                .csr-dw-input-area {
                    padding: 12px;
                }
                .csr-dw-input-wrap {
                    padding: 6px 6px 6px 14px;
                    border-radius: 20px;
                }
                .csr-dw-send-btn {
                    width: 42px;
                    height: 42px;
                }
                .csr-dw-msg {
                    max-width: 100%;
                }
            }

            @media (max-width: 640px) {
                .csr-dw-header h1 {
                    font-size: 1.3rem;
                }
                .csr-dw-body {
                    border-radius: 10px;
                }
                .csr-dw-sidebar-head {
                    padding: 14px 16px;
                }
                .csr-dw-chat-list {
                    padding: 8px;
                }
                .csr-dw-chat-card {
                    padding: 12px 14px;
                }
                .csr-dw-card-name {
                    max-width: none;
                }
                .csr-dw-avatar {
                    width: 36px;
                    height: 36px;
                    border-radius: 8px;
                }
                .csr-dw-user-name {
                    font-size: 0.9rem;
                }
                .csr-dw-messages {
                    padding: 14px 12px;
                }
                .csr-dw-msg {
                    max-width: 100%;
                }
                .csr-dw-input-wrap {
                    border-radius: 18px;
                    padding-left: 14px;
                }
                .csr-dw-input {
                    min-width: 0;
                }
            }

            @media (max-width: 480px) {
                .csr-dw {
                    min-height: 0;
                }
                .csr-dw-body {
                    min-height: 0;
                    border-radius: 0;
                }
                .csr-dw-sidebar-head {
                    padding: 12px 14px;
                }
                .csr-dw-card-top {
                    gap: 8px;
                    align-items: flex-start;
                }
                .csr-dw-card-time {
                    flex-shrink: 0;
                }
                .csr-dw-chat-header {
                    gap: 10px;
                }
                .csr-dw-chat-actions {
                    gap: 8px;
                }
                .csr-dw-back-btn,
                .csr-dw-close-btn {
                    flex: 1 1 0;
                    min-height: 40px;
                }
                .csr-dw-input-area {
                    padding: 10px;
                }
            }
        `;
        document.head.appendChild(style);
    }

    function ensureIconStyles() {
        const iconHref = 'https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css';
        const existing = Array.from(document.querySelectorAll('link[rel="stylesheet"]')).find((link) => {
            return link.href && link.href.indexOf('font-awesome') !== -1;
        });

        if (existing) return;

        const link = document.createElement('link');
        link.rel = 'stylesheet';
        link.href = iconHref;
        link.crossOrigin = 'anonymous';
        document.head.appendChild(link);
    }

    function prepareContainer() {
        const container = document.getElementById(config.containerId);
        if (!container) return null;

        container.classList.add('csr-dw-host');
        return container;
    }

    function getWidgetRoot() {
        const container = document.getElementById(config.containerId);
        return container ? container.querySelector('.csr-dw') : null;
    }

    function isCompactViewport() {
        return window.innerWidth <= 768;
    }

    function getResponsiveWidth() {
        const container = document.getElementById(config.containerId);
        if (!container) return window.innerWidth;

        const rectWidth = container.getBoundingClientRect ? container.getBoundingClientRect().width : 0;
        return Math.max(0, Math.min(window.innerWidth, container.clientWidth || rectWidth || window.innerWidth));
    }

    function syncResponsiveLayout(forceOpen) {
        if (typeof forceOpen === 'boolean') {
            mobileChatOpen = forceOpen;
        }

        const responsiveWidth = getResponsiveWidth();
        const viewportWidth = window.innerWidth || responsiveWidth;
        const isCompact = responsiveWidth <= 960 || viewportWidth <= 960;
        const isMobile = responsiveWidth <= 960 || viewportWidth <= 960;
        const isNarrow = responsiveWidth <= 640;
        const isTiny = responsiveWidth <= 480;

        if (!isMobile) {
            mobileChatOpen = false;
        }

        const root = getWidgetRoot();
        if (!root) return;

        root.classList.toggle('csr-dw-compact', isCompact);
        root.classList.toggle('csr-dw-mobile', isMobile);
        root.classList.toggle('csr-dw-narrow', isNarrow);
        root.classList.toggle('csr-dw-tiny', isTiny);
        root.classList.toggle('csr-dw-mobile-chat-open', isMobile && mobileChatOpen && !!currentSessionId);
    }

    function observeResponsiveContainer() {
        const container = document.getElementById(config.containerId);
        if (!container || typeof ResizeObserver === 'undefined') return;

        if (layoutObserver) {
            layoutObserver.disconnect();
        }

        layoutObserver = new ResizeObserver(() => {
            syncResponsiveLayout();
        });
        layoutObserver.observe(container);
    }

    // ─── Render ────────────────────────────────────────────────────────
    function renderSkeleton() {
        const container = prepareContainer();
        if (!container) {
            console.error(`[CSR Widget] Container #${config.containerId} not found`);
            return;
        }

        // Clear any existing content in the section (replaces inline HTML)
        container.innerHTML = `
            <div class="csr-dw">
                <div class="csr-dw-header">
                    <h1>${escapeHtml(config.widgetTitle || 'Live Chat')}</h1>
                </div>
                <div class="csr-dw-body">
                    <!-- Sidebar -->
                    <div class="csr-dw-sidebar">
                        <div class="csr-dw-sidebar-head">
                            <h3>Active Chats</h3>
                            <span class="csr-dw-badge" id="csr-dw-count">0</span>
                        </div>
                        <div class="csr-dw-chat-list" id="csr-dw-chat-list">
                            <div class="csr-dw-empty-list">
                                <i class="fas fa-spinner fa-spin" style="display:block;margin-bottom:8px;"></i>
                                Loading chats...
                            </div>
                        </div>
                    </div>
                    <!-- Chat Window -->
                    <div class="csr-dw-window" id="csr-dw-window">
                        <div class="csr-dw-no-chat" id="csr-dw-no-chat">
                            <i class="fas fa-comments"></i>
                            <p>Select a chat to start messaging</p>
                        </div>
                        <div id="csr-dw-active-chat" class="csr-dw-active-chat" style="display:none;"></div>
                    </div>
                </div>
            </div>
        `;

        syncResponsiveLayout(false);
    }

    // ─── Chat List ─────────────────────────────────────────────────────
    function fetchChats() {
        const url = isExternalMode()
            ? externalUrl('/api/v1/external/csr/chats')
            : `${config.baseUrl}/api/csr/chats`;

        fetch(url, withAuth({}, null))
            .then(r => r.json())
            .then(data => {
                if (data.chats) {
                    renderChatList(data.chats);
                    updateBadge(data.chats.length);
                }
            })
            .catch(err => console.error('[CSR Widget] Fetch chats error:', err));
    }

    function renderChatList(chats) {
        const list = document.getElementById('csr-dw-chat-list');
        if (!list) return;

        if (chats.length === 0) {
            list.innerHTML = '<div class="csr-dw-empty-list">No active chats</div>';
            return;
        }

        list.innerHTML = chats.map(chat => {
            const isActive = chat.id === currentSessionId;
            const isPending = chat.status === 'pending_csr';
            const timeStr = new Date(chat.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const auth = chat.authentication || {};
            const authMode = chat.auth_mode || auth.mode || 'anonymous';
            const userName = chat.authenticated_user_name || auth.user_name || '';
            const userId = chat.authenticated_user_id || auth.user_id || '';
            const displayName = userName
                ? userName
                : `#${String(chat.visitor_id || '').substring(0, 10)}...`;
            const metaBits = [];
            if (userId) metaBits.push(`ID ${userId}`);
            if (authMode === 'authenticated') metaBits.push('authenticated');
            else metaBits.push('anonymous');
            if (chat.user_type) metaBits.push(chat.user_type);
            const metaLine = metaBits.join(' · ');
            const authPayload = encodeURIComponent(JSON.stringify({
                mode: authMode,
                user_id: userId || null,
                user_name: userName || null,
                user: auth.user || null,
                user_type: chat.user_type || null
            }));

            return `
                <div class="csr-dw-chat-card ${isActive ? 'active' : ''}"
                     data-session-id="${chat.id}"
                     data-visitor-id="${escapeHtml(chat.visitor_id || '')}"
                     data-status="${chat.status}"
                     data-auth="${authPayload}">
                    <div class="csr-dw-card-top">
                        <span class="csr-dw-card-name" title="${escapeHtml(userName || chat.visitor_id || '')}">${escapeHtml(displayName)}</span>
                        <span class="csr-dw-card-time">${timeStr}</span>
                    </div>
                    <div class="csr-dw-card-meta" title="${escapeHtml(metaLine)}">${escapeHtml(metaLine)}</div>
                    <div class="csr-dw-card-preview">${escapeHtml(chat.last_message || 'No messages yet')}</div>
                    <span class="csr-dw-status-badge ${isPending ? 'csr-dw-status-pending' : 'csr-dw-status-active'}">
                        ${chat.status.replace('_', ' ')}
                    </span>
                </div>`;
        }).join('');

        // Bind clicks
        list.querySelectorAll('.csr-dw-chat-card').forEach(card => {
            card.addEventListener('click', () => {
                let authInfo = null;
                try {
                    authInfo = JSON.parse(decodeURIComponent(card.dataset.auth || '%7B%7D'));
                } catch (e) {
                    authInfo = null;
                }
                selectChat(
                    parseInt(card.dataset.sessionId),
                    card.dataset.visitorId,
                    card.dataset.status,
                    authInfo
                );
            });
        });
    }

    function updateBadge(count) {
        const badge = document.getElementById('csr-dw-count');
        if (badge) badge.textContent = count;
        // Also update external badge if it exists (e.g. sidebar nav)
        document.querySelectorAll('#active-chat-count').forEach(b => b.textContent = count);
    }

    // ─── Select Chat ───────────────────────────────────────────────────
    function selectChat(sessionId, visitorId, status, authInfo = null) {
        currentSessionId = sessionId;
        currentVisitorId = visitorId;
        lastRenderedMsgCount = 0;
        mobileChatOpen = true;

        const auth = authInfo && typeof authInfo === 'object' ? authInfo : {};
        const authMode = auth.mode || 'anonymous';
        const userName = auth.user_name || (auth.user && auth.user.name) || '';
        const userId = auth.user_id || (auth.user && auth.user.id) || '';
        const displayName = userName || visitorId || 'Visitor';
        const avatarLetter = String(displayName).charAt(0).toUpperCase() || 'V';
        const authSummaryBits = [];
        if (userId) authSummaryBits.push(`User ID: ${userId}`);
        authSummaryBits.push(authMode === 'authenticated' ? 'Authenticated' : 'Anonymous');
        if (auth.user_type) authSummaryBits.push(`Type: ${auth.user_type}`);
        authSummaryBits.push(`Visitor: ${visitorId}`);
        const authSummary = authSummaryBits.join(' · ');

        // Prefer the same raw verification payload the visitor widget shows.
        let authDebugPayload = null;
        if (auth.user && auth.user.verification_response) {
            authDebugPayload = auth.user.verification_response;
        } else if (authMode === 'authenticated' && (userId || userName)) {
            authDebugPayload = {
                valid: true,
                user: {
                    id: userId ? (Number.isNaN(Number(userId)) ? userId : Number(userId)) : null,
                    name: userName || null
                }
            };
        } else {
            authDebugPayload = {
                mode: 'anonymous',
                user: null
            };
        }

        const authUser = (authDebugPayload && authDebugPayload.user) || {};
        const authName = authUser.name || userName || displayName;
        const authId = authUser.id != null ? authUser.id : (userId || '—');
        const authValid = authDebugPayload && authDebugPayload.valid;
        const statusLabel = authMode === 'authenticated'
            ? (authValid === true ? 'Verified' : (authValid === false ? 'Invalid' : 'Authenticated'))
            : 'Anonymous';
        const statusTone = authValid === true ? 'is-ok' : (authValid === false ? 'is-bad' : '');
        const authPanelHtml = authMode === 'authenticated'
            ? `<div class="csr-dw-user-auth-panel">
                    <div class="csr-dw-user-auth-panel-title">Customer profile</div>
                    <div class="csr-dw-auth-grid">
                        <div class="csr-dw-auth-chip">
                            <div class="csr-dw-auth-chip-label">Name</div>
                            <div class="csr-dw-auth-chip-value">${escapeHtml(authName)}</div>
                        </div>
                        <div class="csr-dw-auth-chip">
                            <div class="csr-dw-auth-chip-label">User ID</div>
                            <div class="csr-dw-auth-chip-value">${escapeHtml(authId)}</div>
                        </div>
                        <div class="csr-dw-auth-chip">
                            <div class="csr-dw-auth-chip-label">Status</div>
                            <div class="csr-dw-auth-chip-value ${statusTone}">${escapeHtml(statusLabel)}</div>
                        </div>
                        <div class="csr-dw-auth-chip">
                            <div class="csr-dw-auth-chip-label">Mode</div>
                            <div class="csr-dw-auth-chip-value">Authenticated</div>
                        </div>
                    </div>
               </div>`
            : '';

        // Hide no-chat, show active chat
        const noChat = document.getElementById('csr-dw-no-chat');
        const activeChat = document.getElementById('csr-dw-active-chat');
        if (noChat) noChat.style.display = 'none';
        if (activeChat) {
            activeChat.style.display = 'flex';
            activeChat.style.flexDirection = 'column';
            activeChat.style.flex = '1';
            activeChat.style.minHeight = '0';
            activeChat.style.overflow = 'hidden';
        }

        // Render chat UI
        activeChat.innerHTML = `
            <div class="csr-dw-chat-header">
                <div class="csr-dw-chat-user">
                    <div class="csr-dw-avatar">${escapeHtml(avatarLetter)}</div>
                    <div>
                        <div class="csr-dw-user-name">${escapeHtml(displayName)}</div>
                        <div class="csr-dw-user-auth" title="${escapeHtml(authSummary)}">${escapeHtml(authSummary)}</div>
                        <div class="csr-dw-user-status">
                            <span class="csr-dw-dot-online"></span>
                            <span id="csr-dw-chat-status">${status.replace('_', ' ')}</span>
                        </div>
                    </div>
                </div>
                <div class="csr-dw-chat-actions">
                    <button class="csr-dw-back-btn" id="csr-dw-back-btn" type="button">
                        <i class="fas fa-arrow-left"></i> Back
                    </button>
                    <button class="csr-dw-close-btn" id="csr-dw-close-btn" type="button">
                        <i class="fas fa-times-circle"></i> Close Chat
                    </button>
                </div>
            </div>
            ${authPanelHtml}
            <div class="csr-dw-messages" id="csr-dw-messages"></div>
            <div class="csr-dw-input-area">
                <div class="csr-dw-input-wrap">
                    <input type="text" class="csr-dw-input" id="csr-dw-reply-input" placeholder="Type a reply..." autocomplete="off">
                    <button class="csr-dw-send-btn" id="csr-dw-send-btn">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        `;

        // Bind events
        document.getElementById('csr-dw-back-btn').addEventListener('click', () => {
            syncResponsiveLayout(false);
        });
        document.getElementById('csr-dw-close-btn').addEventListener('click', closeChat);
        document.getElementById('csr-dw-send-btn').addEventListener('click', sendReply);
        document.getElementById('csr-dw-reply-input').addEventListener('keypress', (e) => {
            if (e.key === 'Enter') sendReply();
        });

        // Load messages immediately
        fetchMessages();

        // Start message polling for this chat
        if (messageInterval) clearInterval(messageInterval);
        messageInterval = setInterval(fetchMessages, config.messagePoll);

        // Re-render chat list to show active highlight
        fetchChats();
        syncResponsiveLayout(true);
    }

    // ─── Messages ──────────────────────────────────────────────────────
    function fetchMessages() {
        if (!currentSessionId) return;

        const url = isExternalMode()
            ? externalUrl(`/api/v1/external/csr/messages/${currentSessionId}`)
            : `${config.baseUrl}/api/csr/messages/${currentSessionId}`;

        fetch(url, withAuth({}, null))
            .then(r => r.json())
            .then(data => {
                if (data.messages) {
                    renderMessages(data.messages);
                }
            })
            .catch(err => console.error('[CSR Widget] Fetch messages error:', err));
    }

    function renderMessages(messages) {
        const container = document.getElementById('csr-dw-messages');
        if (!container) return;

        // Only re-render if message count changed (simple optimization)
        if (messages.length === lastRenderedMsgCount) return;
        lastRenderedMsgCount = messages.length;

        const wasAtBottom = container.scrollTop + container.clientHeight >= container.scrollHeight - 20;

        container.innerHTML = messages.map(msg => {
            const isCSR = msg.sender === 'csr';
            const isAI = msg.sender === 'ai';
            const typeClass = isCSR ? 'msg-csr' : (isAI ? 'msg-ai' : 'msg-user');
            const label = isCSR ? 'You' : (isAI ? 'AI' : 'User');
            const timeStr = new Date(msg.timestamp).toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
            const attachmentsHtml = renderImageAttachments(msg.images);

            return `
                <div class="csr-dw-msg ${typeClass}">
                    <div class="csr-dw-msg-label">${label}</div>
                    <div class="csr-dw-msg-bubble">${escapeHtml(msg.content)}${attachmentsHtml}</div>
                    <div class="csr-dw-msg-time">${timeStr}</div>
                </div>`;
        }).join('');

        // Auto-scroll to bottom
        if (wasAtBottom || messages.length !== lastRenderedMsgCount) {
            container.scrollTop = container.scrollHeight;
        }
    }

    // ─── Send Reply ────────────────────────────────────────────────────
    function sendReply() {
        const input = document.getElementById('csr-dw-reply-input');
        const btn = document.getElementById('csr-dw-send-btn');
        if (!input || !btn) return;

        const message = input.value.trim();
        if (!message || !currentSessionId) return;

        input.value = '';
        input.disabled = true;
        btn.disabled = true;

        const url = isExternalMode()
            ? `${config.baseUrl}/api/v1/external/csr/reply`
            : `${config.baseUrl}/api/csr/reply`;

        fetch(url, withAuth({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        }, {
            session_id: currentSessionId,
            message: message
        }))
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                lastRenderedMsgCount = 0; // Force re-render
                fetchMessages();
            } else {
                alert('Failed to send: ' + (data.error || 'Unknown error'));
            }
        })
        .catch(err => {
            console.error('[CSR Widget] Send reply error:', err);
            alert('Error sending reply');
        })
        .finally(() => {
            input.disabled = false;
            btn.disabled = false;
            input.focus();
        });
    }

    // ─── Close / Resolve Chat ──────────────────────────────────────────
    function closeChat() {
        if (!currentSessionId) return;
        if (!confirm('Are you sure you want to close this chat? The user will be returned to AI.')) return;

        const sessionId = currentSessionId;

        const url = isExternalMode()
            ? `${config.baseUrl}/api/v1/external/csr/close`
            : `${config.baseUrl}/api/csr/close`;

        fetch(url, withAuth({
            method: 'POST',
            headers: { 'Content-Type': 'application/json' }
        }, { session_id: sessionId }))
        .then(r => r.json())
        .then(data => {
            if (data.success) {
                // Reset state
                currentSessionId = null;
                currentVisitorId = null;
                lastRenderedMsgCount = 0;
                mobileChatOpen = false;
                if (messageInterval) clearInterval(messageInterval);

                // Show resolved state briefly, then revert to empty
                const activeChat = document.getElementById('csr-dw-active-chat');
                if (activeChat) {
                    activeChat.innerHTML = `
                        <div class="csr-dw-no-chat" style="color: #10b981;">
                            <i class="fas fa-check-circle" style="opacity:0.7;"></i>
                            <p style="color:#10b981;font-weight:600;">Chat resolved & returned to AI</p>
                        </div>`;
                    setTimeout(() => {
                        activeChat.style.display = 'none';
                        const noChat = document.getElementById('csr-dw-no-chat');
                        if (noChat) noChat.style.display = 'flex';
                        syncResponsiveLayout(false);
                    }, 2000);
                }

                fetchChats();
            } else {
                alert('Failed to close: ' + (data.error || 'Unknown error'));
                fetchChats();
            }
        })
        .catch(err => {
            console.error('[CSR Widget] Close chat error:', err);
            alert('Error closing chat');
            fetchChats();
        });
    }

    // ─── Activation (section visibility) ───────────────────────────────
    function activate() {
        if (isActive) return;
        isActive = true;
        fetchChats();
        chatListInterval = setInterval(fetchChats, config.chatListPoll);
        if (config.onActivate) config.onActivate();
    }

    function deactivate() {
        if (!isActive) return;
        isActive = false;
        if (chatListInterval) { clearInterval(chatListInterval); chatListInterval = null; }
        if (messageInterval) { clearInterval(messageInterval); messageInterval = null; }
        if (config.onDeactivate) config.onDeactivate();
    }

    // ─── Utility ───────────────────────────────────────────────────────
    function escapeHtml(str) {
        const div = document.createElement('div');
        div.textContent = str;
        return div.innerHTML;
    }

    function renderImageAttachments(images) {
        if (!Array.isArray(images) || images.length === 0) return '';
        const safeImages = images
            .map(image => image ? { ...image, src: image.image_url || image.imageUrl || image.url || image.data_url } : null)
            .filter(image => image && image.src && (String(image.src).startsWith('data:image/') || String(image.src).startsWith('http')))
            .map(image => `
                <a href="${escapeHtml(image.src)}" target="_blank" rel="noopener noreferrer">
                    <img class="csr-dw-attachment-image" src="${escapeHtml(image.src)}" alt="${escapeHtml(image.name || 'Uploaded image')}">
                </a>
            `)
            .join('');
        return safeImages ? `<div class="csr-dw-attachments">${safeImages}</div>` : '';
    }

    function isContainerVisible() {
        const container = document.getElementById(config.containerId);
        if (!container) return false;

        const style = window.getComputedStyle(container);
        if (style.display === 'none' || style.visibility === 'hidden') return false;

        const section = container.closest('.dashboard-section');
        return !(section && section.classList.contains('hidden'));
    }

    function shouldAutoActivate() {
        // Standalone pages have no dashboard section controller, so the widget
        // should always activate instead of staying on the loading skeleton.
        if (typeof window.showDashboardSection !== 'function') return true;
        if (typeof config.autoActivate === 'boolean') return config.autoActivate;
        return isContainerVisible();
    }

    // ─── Init ──────────────────────────────────────────────────────────
    function init() {
        ensureIconStyles();
        injectStyles();
        renderSkeleton();

        // Hook into showDashboardSection to know when Live Chat is active
        if (typeof window.showDashboardSection === 'function') {
            const _original = window.showDashboardSection;
            window.showDashboardSection = function (section) {
                _original(section);
                if (section === 'live-chat') {
                    activate();
                } else {
                    deactivate();
                }
            };
        }

        if (shouldAutoActivate()) {
            activate();
        }

        window.addEventListener('resize', syncResponsiveLayout);
        window.addEventListener('orientationchange', syncResponsiveLayout);
        observeResponsiveContainer();
        syncResponsiveLayout(false);

        console.log('[CSR Widget] Initialized — container: #' + config.containerId);
    }

    // ─── Public API ────────────────────────────────────────────────────
    window.CSRDashboardWidget = {
        activate: activate,
        deactivate: deactivate,
        fetchChats: fetchChats,
        config: config,
    };

    // Boot
    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();
