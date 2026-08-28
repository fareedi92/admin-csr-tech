(function() {
    // Visitor ID is initialized after config is available.
    let visitorId = null;

    // Default configuration
    const defaultConfig = {
        // Position and Layout
        position: 'bottom-right',
        width: '380px',
        height: 'min(640px, calc(100vh - 100px))',
        mobileWidth: '100%',
        mobileHeight: '100%',
        visitorIdKey: 'chat_visitor_id',
        storageKey: 'chat_history',
        
        // Colors and Styling
        primaryColor: '#5B50E7',            // Accent color fallback
        buttonColor: '#5B50E7',             // Toggle button & send button
        headerBackground: 'linear-gradient(to right, #5D5CFF, #7A2EE6)', // Header background (supports gradient)
        backgroundColor: '#121826',         // Chat box background
        messageAreaBgColor: '#0d1520',      // Messages scrollable area bg
        textColor: '#ffffff',               // General text color
        userMessageColor: '#fcb41a',        // User message bubble (yellowish)
        userMessageTextColor: '#15253e',    // Text on user message bubble
        aiMessageColor: '#1A2332',          // AI / reply message bubble
        aiMessageTextColor: '#e2e8f0',      // Text on AI message bubble
        csrMessageColor: '#1A2332',         // CSR / support message bubble
        csrMessageTextColor: '#e2e8f0',     // Text on CSR message bubble
        inputBgColor: '#1A2332',            // Input field background
        inputTextColor: '#ffffff',          // Input field text
        inputPlaceholderColor: '#64748b',   // Input placeholder text
        borderColor: '#2a3444',
        shadowColor: 'rgba(0, 0, 0, 0.3)',
        
        // Typography
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, "Helvetica Neue", Arial, sans-serif',
        fontSize: '14px',
        headerFontSize: '16px',
        
        // Content
        widgetTitle: 'FLT Chat',
        welcomeMessage: 'Hello! Welcome to FLT Chat Agent, How can we help you today?',
        csrResolvedMessage: 'You are connected back to AI. How can I help you?',
        userTypePrompt: 'Are you a Buyer or Organizer?',
        buyerLabel: 'Buyer',
        organizerLabel: 'Organizer',
        userTypePlaceholder: 'Select Buyer or Organizer to start chatting',
        userAvatar: 'user', // Options: 'user', 'person', or image URL
        aiAvatar: 'bot', // Options: 'bot', 'support', or image URL
        agentIcon: 'https://beta-tj1.frontlineticketing.com/images/logo.png',
        agentIconSize: '32px',
        agentIconFallback: 'user',
        
        // SVG Icons
        sendButtonIcon: 'send',
        closeButtonIcon: 'close',
        toggleButtonIcon: 'chat',
        
        // Behavior
        autoOpen: false,
        openDelay: 1000,
        closeOnOutsideClick: true,
        focusInputOnOpen: true,
        clearChatOnReload: true,
        
        // API Configuration
        widgetKey: '',
        apiUrl: '/api/chat', // Use internal API
        pollUrl: '/api/chat/poll',
        pollInterval: 3000,
        requestTimeout: 60000,
        maxImageUploads: 3,
        maxImageSizeBytes: 2 * 1024 * 1024,
        // Visitor auth payload from host page (web team)
        // auth.mode: 'anonymous' | 'authenticated'
        // auth.token: FLT chatbot token (required only for authenticated)
        auth: {
            mode: 'anonymous',
            token: null
        },
        // Show verified user JSON / anonymous mode in chat.
        showAuthDebug: true,
        
        // Base URL for API calls
        baseUrl: '',
        
        // Animations
        animationDuration: '0.3s',
        enableAnimations: true,
        
        // Responsive
        mobileBreakpoint: '768px',
        
        // Custom CSS
        customCSS: `
            .chat-avatar svg {
                width: 20px;
                height: 20px;
            }
            
            #chat-toggle svg, #chat-send svg, #chat-close svg {
                width: 24px;
                height: 24px;
                fill: currentColor;
            }
            
            .chat-avatar {
                display: flex;
                align-items: center;
                justify-content: center;
            }
            
            .icon-wrapper {
                display: flex;
                align-items: center;
                justify-content: center;
            }
        `,
        
        // Callbacks
        onOpen: null,
        onClose: null,
        onSendMessage: null,
        onReceiveMessage: null,
        onError: null,
        onAuthenticated: null,
        onAuthenticationFailed: null
    };

    // SVG Icon definitions
    const svgIcons = {
        // Chat/Message icons
        chat: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
        </svg>`,
        message: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M4 4h16c1.1 0 2 .9 2 2v12c0 1.1-.9 2-2 2H4c-1.1 0-2-.9-2-2V6c0-1.1.9-2 2-2z"></path>
            <polyline points="22,6 12,13 2,6"></polyline>
        </svg>`,
        bubbles: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M8 12h.01M12 12h.01M16 12h.01M21 12c0 4.418-4.03 8-9 8a9.863 9.863 0 01-4.255-.949L3 20l1.395-3.72C3.512 15.042 3 13.574 3 12c0-4.418 4.03-8 9-8s9 3.582 9 8z"></path>
        </svg>`,
        
        // Send icons
        send: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>`,
        arrow: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="12" x2="2" y2="12"></line>
            <polyline points="16,6 22,12 16,18"></polyline>
        </svg>`,
        'paper-plane': `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="22" y1="2" x2="11" y2="13"></line>
            <polygon points="22 2 15 22 11 13 2 9 22 2"></polygon>
        </svg>`,
        
        // Close icons
        close: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>`,
        x: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>`,
        times: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <line x1="18" y1="6" x2="6" y2="18"></line>
            <line x1="6" y1="6" x2="18" y2="18"></line>
        </svg>`,
        
        // Avatar icons
        user: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
        </svg>`,
        person: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M20 21v-2a4 4 0 0 0-4-4H8a4 4 0 0 0-4 4v2"></path>
            <circle cx="12" cy="7" r="4"></circle>
        </svg>`,
        bot: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="3" y="11" width="18" height="10" rx="2" ry="2"></rect>
            <path d="M7 11V7a5 5 0 0110 0v4"></path>
        </svg>`,
        support: `<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M21 12a9 9 0 01-9 9m9-9a9 9 0 00-9-9m9 9H3m9 9a9 9 0 01-9-9m9 9c1.657 0 3-4.03 3-9s-1.343-9-3-9m0 18c-1.657 0-3-4.03-3-9s1.343-9 3-9m-9 9a9 9 0 019-9"></path>
        </svg>`
    };

    // Global configuration object that developers can modify
    window.AuthenticatedChatWidgetConfig = window.AuthenticatedChatWidgetConfig || {};

    // Merge default config with user config
    const config = { ...defaultConfig, ...window.AuthenticatedChatWidgetConfig };
    
    // Determine base URL - store it immediately when script loads
    let widgetBaseUrl = config.baseUrl || '';
    
    // If no base URL provided, try to determine from script source
    if (!widgetBaseUrl) {
        // Method 1: Try document.currentScript (works in most modern browsers)
        if (document.currentScript && document.currentScript.src) {
            try {
                widgetBaseUrl = new URL(document.currentScript.src).origin;
            } catch (e) {
                console.error('Error parsing script URL:', e);
            }
        }
        // Method 2: Fallback to query scripts array
        else {
            const scripts = document.getElementsByTagName('script');
            for (let i = 0; i < scripts.length; i++) {
                if (scripts[i].src && scripts[i].src.includes('authenticated-chat-widget.js')) {
                    try {
                        widgetBaseUrl = new URL(scripts[i].src).origin;
                        break;
                    } catch (e) {
                        console.error('Error parsing script URL:', e);
                    }
                }
            }
        }
    }
    
    // Final fallback if still no URL
    if (!widgetBaseUrl) {
        console.warn('Could not determine widget base URL. Using fallback. Consider setting baseUrl in config.');
        widgetBaseUrl = window.location.origin;
    }

    function initializeVisitorId() {
        const storageKey = config.visitorIdKey || 'chat_visitor_id';

        if (config.clearChatOnReload) {
            localStorage.removeItem(storageKey);
        }

        visitorId = localStorage.getItem(storageKey);
        if (!visitorId) {
            visitorId = 'v_' + Math.random().toString(36).substr(2, 9);
            localStorage.setItem(storageKey, visitorId);
        }
    }

    initializeVisitorId();

    function buildAuthPayload() {
        const configuredAuth = (config.auth && typeof config.auth === 'object') ? config.auth : {};
        const token = configuredAuth.token || null;
        const tokenValue = token ? String(token).trim() : '';
        let mode = String(
            configuredAuth.mode || (tokenValue ? 'authenticated' : 'anonymous')
        ).trim().toLowerCase();

        // No token => always anonymous
        if (!tokenValue) {
            mode = 'anonymous';
        }

        return {
            mode: mode === 'authenticated' ? 'authenticated' : 'anonymous',
            token: mode === 'authenticated' ? tokenValue : null
        };
    }

    function rememberVisitorAuth(authInfo) {
        if (!authInfo || typeof authInfo !== 'object') {
            visitorAuthInfo = {
                mode: buildAuthPayload().mode,
                user: null
            };
            return visitorAuthInfo;
        }
        visitorAuthInfo = {
            mode: authInfo.mode || buildAuthPayload().mode,
            user: authInfo.user || null
        };
        return visitorAuthInfo;
    }
    
    // Authentication state
    let isAuthenticated = false;
    let businessInfo = null;
    let visitorAuthInfo = {
        mode: 'anonymous',
        user: null
    };
    let pollInterval = null;
    let isPolling = false;
    let isCSRMode = false;
    let isExternalCsrMode = false;
    let externalCsrInitialized = false;
    
    // Function to determine if agent icon is an image URL
    function isImageUrl(icon) {
        return icon && (icon.startsWith('http') || icon.startsWith('data:image') || icon.startsWith('/'));
    }
    
    // Function to get icon HTML
    function getIcon(iconKey) {
        // If it's an image URL, return img tag
        if (isImageUrl(iconKey)) {
            return `<img src="${iconKey}" alt="Icon" style="width: 100%; height: 100%; object-fit: contain;" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"><div class="icon-wrapper" style="display: none;">${svgIcons.question || svgIcons.chat}</div>`;
        }
        
        // If it's a known SVG icon, return it
        if (svgIcons[iconKey]) {
            return svgIcons[iconKey];
        }
        
        // If it's HTML (like Font Awesome), return as is
        if (iconKey && (iconKey.includes('<i ') || iconKey.includes('<svg '))) {
            return iconKey;
        }
        
        // Fallback to chat icon
        return svgIcons.chat || '<span>ðŸ’¬</span>';
    }
    
    // Function to generate agent avatar HTML
    function generateAgentAvatar() {
        const agentIcon = config.agentIcon || config.aiAvatar;
        
        if (isImageUrl(agentIcon)) {
            return `<img src="${agentIcon}" alt="Agent" style="width: 100%; height: 100%; object-fit: cover; border-radius: 50%;" onerror="this.style.display='none'; this.nextElementSibling.style.display='flex';"><div class="icon-wrapper" style="display: none; width: 100%; height: 100%;">${getIcon(config.agentIconFallback)}</div>`;
        } else {
            return `<div class="icon-wrapper">${getIcon(agentIcon)}</div>`;
        }
    }
    
    // Function to validate widget with the server
    function validateWidget() {
        if (!config.widgetKey) {
            console.error('Widget key is required for authentication');
            if (config.onAuthenticationFailed) {
                config.onAuthenticationFailed('Widget key is required');
            }
            return Promise.reject(new Error('Widget key is required'));
        }
        
        const currentDomain = window.location.hostname;
        
        // Use the internal endpoint for widget validation if available, OR reuse existing validation
        // Assuming /validate_widget exists as per original code
        return fetch(`${widgetBaseUrl}/validate_widget`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ 
                widget_key: config.widgetKey, 
                domain: currentDomain,
                visitor_id: visitorId,
                auth: buildAuthPayload()
            })
        })
        .then(async response => {
            let data = null;
            try {
                data = await response.json();
            } catch (parseError) {
                data = null;
            }
            if (!response.ok) {
                const detail = (data && (data.message || data.error)) || `Server responded with ${response.status}`;
                throw new Error(detail);
            }
            return data || {};
        })
        .then(data => {
            if (data.valid) {
                isAuthenticated = true;
                businessInfo = data;
                rememberVisitorAuth(data.authentication);
                if (data.widget_config) Object.assign(config, data.widget_config);
                if (config.onAuthenticated) config.onAuthenticated(data);
                
                // Check for existing CSR session — resume CSR mode if needed
                if (data.session_mode === 'pending_csr' || data.session_mode === 'active_csr') {
                    isCSRMode = true;
                }
                config.sessionMode = data.session_mode || 'active_ai';
                return data;
            } else {
                throw new Error(data.message || 'Authentication failed');
            }
        })
        .catch(error => {
            console.error('Widget authentication failed:', error);
            if (config.onAuthenticationFailed) config.onAuthenticationFailed(error.message);
            throw error;
        });
    }


    
    // Function to show authentication error
    function showAuthenticationError(message) {
        const errorDiv = document.createElement('div');
        errorDiv.style.cssText = `
            position: fixed; bottom: 20px; right: 20px; background-color: #f8d7da; color: #721c24;
            padding: 15px; border-radius: 5px; border: 1px solid #f5c6cb; box-shadow: 0 4px 8px rgba(0,0,0,0.1);
            z-index: 10000; max-width: 300px; font-family: ${config.fontFamily}; font-size: ${config.fontSize};
        `;
        errorDiv.innerHTML = `
            <div style="display: flex; align-items: center; margin-bottom: 10px;">
                <strong>Authentication Error</strong>
                <button onclick="this.parentElement.parentElement.remove()" style="margin-left: auto; background: none; border: none; color: inherit; cursor: pointer;">&times;</button>
            </div>
            <div>${message}</div>
        `;
        document.body.appendChild(errorDiv);
        setTimeout(() => { if (errorDiv.parentNode) errorDiv.parentNode.removeChild(errorDiv); }, 10000);
    }

    // Function to inject CSS
    function injectCSS() {
        const style = document.createElement('style');
        style.innerHTML = `
            :root {
                --chat-widget-primary-color: ${config.primaryColor};
                --chat-widget-button-color: ${config.buttonColor || config.primaryColor};
                --chat-widget-header-bg: ${config.headerBackground || config.primaryColor};
                --chat-widget-bg-color: ${config.backgroundColor};
                --chat-widget-msg-area-bg: ${config.messageAreaBgColor || config.backgroundColor};
                --chat-widget-text-color: ${config.textColor};
                --chat-widget-user-msg-color: ${config.userMessageColor};
                --chat-widget-user-msg-text-color: ${config.userMessageTextColor};
                --chat-widget-ai-msg-color: ${config.aiMessageColor};
                --chat-widget-ai-msg-text-color: ${config.aiMessageTextColor};
                --chat-widget-csr-msg-color: ${config.csrMessageColor || config.aiMessageColor};
                --chat-widget-csr-msg-text-color: ${config.csrMessageTextColor || config.aiMessageTextColor};
                --chat-widget-input-bg: ${config.inputBgColor || config.backgroundColor};
                --chat-widget-input-text: ${config.inputTextColor || config.textColor};
                --chat-widget-input-placeholder: ${config.inputPlaceholderColor || '#64748b'};
                --chat-widget-border-color: ${config.borderColor};
                --chat-widget-shadow-color: ${config.shadowColor};
                --chat-widget-font-family: ${config.fontFamily};
                --chat-widget-font-size: ${config.fontSize};
                --chat-widget-header-font-size: ${config.headerFontSize};
                --chat-widget-animation-duration: ${config.animationDuration};
                --chat-widget-width: ${config.width};
                --chat-widget-height: ${config.height};
                --chat-widget-mobile-width: ${config.mobileWidth};
                --chat-widget-mobile-height: ${config.mobileHeight};
                --chat-widget-agent-icon-size: ${config.agentIconSize};
            }

            .chat-widget-hidden { display: none !important; }

            #chat-widget-container {
                position: fixed;
                ${config.position.includes('bottom') ? 'bottom: 20px;' : 'top: 20px;'}
                ${config.position.includes('right') ? 'right: 20px;' : 'left: 20px;'}
                z-index: 9999;
                font-family: var(--chat-widget-font-family);
                font-size: var(--chat-widget-font-size);
                color: var(--chat-widget-text-color);
            }

            #chat-toggle {
                background-color: var(--chat-widget-button-color) !important;
                color: white !important;
                border: none !important;
                border-radius: 50% !important;
                width: 60px !important;
                height: 60px !important;
                cursor: pointer !important;
                box-shadow: 0 4px 16px var(--chat-widget-shadow-color) !important;
                transition: all var(--chat-widget-animation-duration) ease !important;
                display: flex !important;
                align-items: center !important;
                justify-content: center !important;
                font-size: 24px !important;
                z-index: 10000 !important;
            }

            #chat-toggle:hover {
                transform: scale(1.05) !important;
                box-shadow: 0 6px 24px var(--chat-widget-shadow-color) !important;
            }

            /* Hide the toggle bubble when the chat box is open */
            #chat-widget-container.chat-widget-open #chat-toggle {
                display: none !important;
            }

            /* Reposition chat-box to sit at the same level as the toggle when open */
            #chat-widget-container.chat-widget-open #chat-box {
                ${config.position.includes('bottom') ? 'bottom: 20px;' : 'top: 20px;'}
            }

            #chat-box {
                position: absolute;
                ${config.position.includes('bottom') ? 'bottom: 80px;' : 'top: 80px;'}
                ${config.position.includes('right') ? 'right: 0;' : 'left: 0;'}
                width: var(--chat-widget-width);
                max-width: min(92vw, 420px);
                height: var(--chat-widget-height);
                max-height: calc(100vh - 100px);
                max-height: calc(100dvh - 100px);
                background: var(--chat-widget-bg-color);
                border-radius: 16px;
                box-shadow: 0 10px 40px var(--chat-widget-shadow-color);
                border: 1px solid var(--chat-widget-border-color);
                display: flex;
                flex-direction: column;
                overflow: hidden;
                transition: all var(--chat-widget-animation-duration) ease;
                container-type: inline-size;
                container-name: chat-box;
            }

            #chat-header {
                background: var(--chat-widget-header-bg);
                color: white;
                padding: 14px 16px;
                display: flex;
                justify-content: space-between;
                align-items: center;
                gap: 10px;
                font-weight: 600;
                font-size: var(--chat-widget-header-font-size);
                border-bottom: 1px solid var(--chat-widget-border-color);
                flex-shrink: 0;
                min-width: 0;
            }

            #chat-header-title {
                display: flex;
                align-items: center;
                gap: 8px;
                min-width: 0;
                flex: 1 1 auto;
            }

            #chat-header-title span {
                overflow: hidden;
                text-overflow: ellipsis;
                white-space: nowrap;
                font-size: 14px;
                line-height: 1.3;
            }

            #chat-header-actions {
                display: flex;
                align-items: center;
                gap: 4px;
                flex-shrink: 0;
            }

            #chat-close, #chat-new {
                background: none;
                border: none;
                color: white;
                font-size: 18px;
                cursor: pointer;
                padding: 8px;
                border-radius: 8px;
                transition: background-color 0.2s;
                display: flex;
                align-items: center;
                justify-content: center;
                min-width: 36px;
                min-height: 36px;
            }

            #chat-close:hover, #chat-new:hover { background-color: rgba(255, 255, 255, 0.15); }

            #chat-messages {
                flex: 1 1 auto !important;
                padding: 14px 12px;
                overflow-y: auto;
                overflow-x: hidden;
                background-color: var(--chat-widget-msg-area-bg);
                display: block;
                min-height: 0;
                max-height: none !important;
                -webkit-overflow-scrolling: touch;
            }

            /* Scrollbar styling for dark theme */
            #chat-messages::-webkit-scrollbar { width: 6px; }
            #chat-messages::-webkit-scrollbar-track { background: transparent; }
            #chat-messages::-webkit-scrollbar-thumb { background: var(--chat-widget-border-color); border-radius: 3px; }

            .chat-message {
                margin-bottom: 12px;
                display: flex;
                align-items: flex-end;
                gap: 8px;
                max-width: 100%;
                min-width: 0;
            }

            .chat-message.user { justify-content: flex-end; }
            .chat-message.ai,
            .chat-message.support { justify-content: flex-start; }

            .chat-bubble {
                width: fit-content;
                max-width: calc(100% - 44px);
                word-wrap: break-word;
                overflow-wrap: anywhere;
                word-break: break-word;
                position: relative;
                line-height: 1.45;
                font-size: 14px;
                min-width: 0;
            }

            .chat-message.user .chat-bubble {
                background-color: var(--chat-widget-user-msg-color);
                color: var(--chat-widget-user-msg-text-color);
                padding: 10px 14px;
                border-radius: 16px;
                border-bottom-right-radius: 4px;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
                text-align: left;
            }

            .chat-message.ai .chat-bubble {
                background-color: var(--chat-widget-ai-msg-color);
                color: var(--chat-widget-ai-msg-text-color);
                padding: 10px 14px;
                border-radius: 16px;
                border-bottom-left-radius: 4px;
                border: 1px solid var(--chat-widget-border-color);
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
                margin-left: 0;
            }

            .role-selector-bubble {
                display: flex;
                flex-direction: column;
                gap: 12px;
            }

            .role-selector-title {
                font-weight: 600;
            }

            .role-options {
                display: flex;
                flex-wrap: wrap;
                gap: 10px;
            }

            .chat-role-option {
                border: 1px solid var(--chat-widget-border-color);
                background: transparent;
                color: var(--chat-widget-ai-msg-text-color);
                border-radius: 999px;
                padding: 8px 14px;
                cursor: pointer;
                transition: all 0.2s ease;
                font: inherit;
            }

            .chat-role-option:hover:not(:disabled) {
                border-color: var(--chat-widget-button-color);
                color: white;
                background: rgba(91, 80, 231, 0.18);
            }

            .chat-role-option.selected {
                background: var(--chat-widget-button-color);
                border-color: var(--chat-widget-button-color);
                color: white;
            }

            .chat-role-option:disabled {
                cursor: default;
                opacity: 1;
            }

            .role-selection-note {
                font-size: 12px;
                opacity: 0.8;
            }
            
            .chat-message.support .chat-bubble {
                background-color: var(--chat-widget-csr-msg-color);
                border: 1px solid var(--chat-widget-button-color);
                color: var(--chat-widget-csr-msg-text-color);
                padding: 10px 14px;
                border-radius: 16px;
                border-bottom-left-radius: 4px;
                margin-left: 0;
                position: relative;
                z-index: 10;
                opacity: 1;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }

            .chat-avatar {
                width: 28px;
                height: 28px;
                border-radius: 50%;
                display: flex;
                align-items: center;
                justify-content: center;
                margin: 0;
                font-size: 12px;
                flex-shrink: 0;
                overflow: hidden;
                background-color: var(--chat-widget-ai-msg-color);
                color: var(--chat-widget-button-color);
                border: 1.5px solid var(--chat-widget-border-color);
                box-shadow: 0 1px 3px rgba(0, 0, 0, 0.15);
            }
            
            .chat-message.support .chat-avatar {
                background-color: var(--chat-widget-csr-msg-color);
                color: var(--chat-widget-button-color);
                border-color: var(--chat-widget-button-color);
            }

            #chat-input-container {
                padding: 12px;
                border-top: 1px solid var(--chat-widget-border-color);
                background-color: var(--chat-widget-bg-color);
                display: flex;
                align-items: center;
                gap: 8px;
                position: relative;
                z-index: 1;
                flex-shrink: 0;
                min-width: 0;
            }

            #chat-upload {
                display: none;
            }

            #chat-upload-btn {
                background: var(--chat-widget-input-bg);
                color: var(--chat-widget-input-placeholder);
                border: 1px solid var(--chat-widget-border-color);
                border-radius: 50%;
                width: 40px;
                height: 40px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
                z-index: 2;
                position: relative;
                flex-shrink: 0;
                font-size: 18px;
            }

            #chat-upload-btn:hover {
                color: var(--chat-widget-button-color);
                border-color: var(--chat-widget-button-color);
            }

            #chat-upload-btn:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            #chat-image-preview {
                display: none;
                padding: 10px 16px 0;
                background-color: var(--chat-widget-bg-color);
                border-top: 1px solid var(--chat-widget-border-color);
                gap: 8px;
                flex-wrap: wrap;
            }

            .chat-image-chip {
                position: relative;
                width: 64px;
                height: 64px;
                border-radius: 12px;
                overflow: hidden;
                border: 1px solid var(--chat-widget-border-color);
                background: var(--chat-widget-input-bg);
            }

            .chat-image-chip img {
                width: 100%;
                height: 100%;
                object-fit: cover;
                display: block;
            }

            .chat-image-remove {
                position: absolute;
                top: 3px;
                right: 3px;
                width: 20px;
                height: 20px;
                border: none;
                border-radius: 50%;
                background: rgba(0, 0, 0, 0.65);
                color: #fff;
                cursor: pointer;
                font-size: 14px;
                line-height: 20px;
                padding: 0;
            }

            #chat-input {
                flex: 1 1 auto;
                min-width: 0;
                border: 1px solid var(--chat-widget-border-color);
                border-radius: 20px;
                padding: 10px 14px;
                font-size: 14px;
                outline: none;
                transition: border-color 0.2s, box-shadow 0.2s;
                font-family: var(--chat-widget-font-family);
                z-index: 2;
                position: relative;
                background-color: var(--chat-widget-input-bg);
                color: var(--chat-widget-input-text);
            }

            #chat-input::placeholder { color: var(--chat-widget-input-placeholder); }

            #chat-input:focus {
                border-color: var(--chat-widget-button-color);
                box-shadow: 0 0 0 2px rgba(91, 80, 231, 0.2);
            }

            #chat-input:disabled {
                opacity: 0.6;
                cursor: not-allowed;
            }

            #chat-send {
                background-color: var(--chat-widget-button-color);
                color: white;
                border: none;
                border-radius: 50%;
                width: 40px;
                height: 40px;
                cursor: pointer;
                display: flex;
                align-items: center;
                justify-content: center;
                transition: all 0.2s;
                z-index: 2;
                position: relative;
                flex-shrink: 0;
            }

            #chat-send:hover { opacity: 0.85; transform: scale(1.05); }

            #chat-send:disabled {
                opacity: 0.6;
                cursor: not-allowed;
                transform: none;
            }

            #chat-input[readonly] {
                opacity: 0.7;
                cursor: wait;
            }

            .typing-indicator {
                display: flex;
                align-items: center;
                padding: 10px 14px;
                background-color: var(--chat-widget-ai-msg-color);
                border: 1px solid var(--chat-widget-border-color);
                border-radius: 16px;
                border-bottom-left-radius: 4px;
                margin-left: 0;
                width: fit-content;
                box-shadow: 0 2px 8px rgba(0, 0, 0, 0.1);
            }

            .typing-indicator span {
                height: 8px;
                width: 8px;
                background-color: var(--chat-widget-input-placeholder);
                border-radius: 50%;
                display: inline-block;
                margin: 0 2px;
                animation: typing 1.4s infinite;
            }
            .typing-indicator span:nth-child(2) { animation-delay: 0.2s; }
            .typing-indicator span:nth-child(3) { animation-delay: 0.4s; }

            .chat-attachments {
                display: grid;
                gap: 8px;
                margin-top: 8px;
            }

            .chat-attachment-image {
                max-width: 220px;
                max-height: 180px;
                border-radius: 12px;
                display: block;
                object-fit: cover;
                border: 1px solid rgba(255, 255, 255, 0.12);
            }
            @keyframes typing { 0%, 60%, 100% { transform: translateY(0); } 30% { transform: translateY(-10px); } }

            /* ── Tablet / medium screens ── */
            @media (max-width: 1100px) {
                #chat-box {
                    width: min(360px, 92vw) !important;
                    max-height: calc(100vh - 96px) !important;
                    max-height: calc(100dvh - 96px) !important;
                }
            }

            /* ── Mobile / small-screen overrides ── */
            @media (max-width: ${config.mobileBreakpoint}) {

                /* --- Closed state: just the floating toggle button --- */
                #chat-widget-container {
                    bottom: max(16px, env(safe-area-inset-bottom)) !important;
                    right: max(16px, env(safe-area-inset-right)) !important;
                    left: auto !important;
                    top: auto !important;
                    width: auto !important;
                    height: auto !important;
                }

                #chat-toggle {
                    position: relative !important;
                    bottom: auto !important;
                    right: auto !important;
                }

                /* --- Open state: full-screen chat --- */
                #chat-widget-container.chat-widget-open {
                    top: 0 !important;
                    left: 0 !important;
                    right: 0 !important;
                    bottom: 0 !important;
                    width: 100% !important;
                    height: 100% !important;
                    z-index: 99999 !important;
                }

                body.chat-widget-fullscreen-open {
                    overflow: hidden !important;
                    touch-action: none;
                }

                #chat-widget-container.chat-widget-open #chat-toggle {
                    display: none !important;
                }

                #chat-widget-container.chat-widget-open #chat-box {
                    position: fixed !important;
                    top: 0 !important;
                    left: 0 !important;
                    right: 0 !important;
                    bottom: 0 !important;
                    width: 100vw !important;
                    width: 100dvw !important;
                    height: 100vh !important;
                    height: 100dvh !important;
                    max-width: 100% !important;
                    max-height: none !important;
                    border-radius: 0 !important;
                    z-index: 99999 !important;
                }

                #chat-header {
                    padding: 12px 12px 12px 14px !important;
                    padding-top: max(12px, env(safe-area-inset-top)) !important;
                }

                #chat-header-title span {
                    font-size: 13px !important;
                }

                #chat-messages {
                    padding: 12px 10px !important;
                }

                .chat-message {
                    margin-bottom: 10px !important;
                    gap: 6px !important;
                }

                /* Hide avatars on small screens so bubbles get full readable width */
                .chat-avatar {
                    display: none !important;
                }

                .chat-bubble {
                    max-width: 88% !important;
                    font-size: 14px !important;
                }

                .chat-message.user .chat-bubble,
                .chat-message.ai .chat-bubble,
                .chat-message.support .chat-bubble {
                    padding: 10px 12px !important;
                }

                #chat-input-container {
                    padding: 10px 10px max(10px, env(safe-area-inset-bottom)) !important;
                    gap: 8px !important;
                }

                #chat-upload-btn,
                #chat-send {
                    width: 40px !important;
                    height: 40px !important;
                }

                #chat-input {
                    font-size: 15px !important;
                    padding: 11px 14px !important;
                }

                .role-options { gap: 8px !important; }
                .chat-role-option {
                    padding: 8px 12px !important;
                    font-size: 13px !important;
                }
            }

            /* ── Extra-small screens (phones ≤ 480px) ── */
            @media (max-width: 480px) {
                #chat-widget-container {
                    bottom: max(12px, env(safe-area-inset-bottom)) !important;
                    right: max(12px, env(safe-area-inset-right)) !important;
                }

                #chat-toggle {
                    width: 52px !important;
                    height: 52px !important;
                    font-size: 20px !important;
                }

                #chat-header-title span {
                    font-size: 12.5px !important;
                }

                .chat-avatar {
                    display: none !important;
                }

                .chat-bubble {
                    max-width: 92% !important;
                    font-size: 13.5px !important;
                    line-height: 1.4 !important;
                }

                #chat-messages {
                    padding: 10px 8px !important;
                }

                #chat-input-container {
                    padding: 8px 8px max(8px, env(safe-area-inset-bottom)) !important;
                }
            }

            /* Cramped floating panel (narrow desktop / embed) */
            @media (max-width: 420px) {
                .chat-avatar { display: none !important; }
                .chat-message.ai .chat-bubble,
                .chat-message.support .chat-bubble,
                .typing-indicator { margin-left: 0 !important; }
                .chat-bubble { max-width: 92% !important; }
            }

            /* When the chat panel itself is narrow (even on a wide desktop) */
            @container chat-box (max-width: 420px) {
                #chat-header {
                    padding: 12px 12px 12px 14px;
                }
                #chat-header-title span {
                    font-size: 13px;
                }
                #chat-messages {
                    padding: 12px 10px;
                }
                .chat-avatar {
                    display: none !important;
                }
                .chat-message.ai .chat-bubble,
                .chat-message.support .chat-bubble,
                .typing-indicator { margin-left: 0 !important; }
                .chat-bubble {
                    max-width: 92% !important;
                }
                .chat-message.user .chat-bubble,
                .chat-message.ai .chat-bubble,
                .chat-message.support .chat-bubble {
                    padding: 10px 12px;
                }
                #chat-input-container {
                    padding: 10px;
                    gap: 8px;
                }
            }

            /* Custom CSS provided by developer */
            ${config.customCSS}
        `;
        document.head.appendChild(style);
    }

    // Function to create chat widget HTML
    function createChatWidget() {
        const chatWidgetContainer = document.createElement('div');
        chatWidgetContainer.id = 'chat-widget-container';
        chatWidgetContainer.innerHTML = `
            <button id="chat-toggle" aria-label="Open chat">
                ${getIcon(config.toggleButtonIcon)}
            </button>
            <div id="chat-box" class="chat-widget-hidden">
                <div id="chat-header">
                    <div id="chat-header-title">
                        <div style="width: 8px; height: 8px; background-color: #10b981; border-radius: 50%; flex-shrink: 0;"></div>
                        <span title="${config.widgetTitle}">${config.widgetTitle}</span>
                    </div>
                    <div id="chat-header-actions">
                        <button id="chat-new" aria-label="Start New Chat" title="New Chat">
                             <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round"><line x1="12" y1="5" x2="12" y2="19"></line><line x1="5" y1="12" x2="19" y2="12"></line></svg>
                        </button>
                        <button id="chat-close" aria-label="Close chat">
                            ${getIcon(config.closeButtonIcon)}
                        </button>
                    </div>
                </div>
                <div id="chat-messages">
                </div>
                <div id="chat-image-preview"></div>
                <div id="chat-input-container">
                    <input type="file" id="chat-upload" accept="image/*" multiple aria-label="Upload images">
                    <button id="chat-upload-btn" type="button" aria-label="Upload images" title="Upload images">+</button>
                    <input type="text" id="chat-input" placeholder="Type your message..." aria-label="Type your message">
                    <button id="chat-send" aria-label="Send message">
                        ${getIcon(config.sendButtonIcon)}
                    </button>
                </div>
            </div>
        `;
        document.body.appendChild(chatWidgetContainer);

        // Get DOM elements
        const chatToggle = document.getElementById('chat-toggle');
        const chatBox = document.getElementById('chat-box');
        const chatClose = document.getElementById('chat-close');
        const chatInput = document.getElementById('chat-input');
        const chatUpload = document.getElementById('chat-upload');
        const chatUploadBtn = document.getElementById('chat-upload-btn');
        const chatImagePreview = document.getElementById('chat-image-preview');
        const chatSend = document.getElementById('chat-send');
        const chatMessages = document.getElementById('chat-messages');
        let isAwaitingResponse = false;
        let selectedUserType = normalizeUserType(config.userType);
        let pendingImages = [];
        let currentSessionStatus = config.sessionMode || (isCSRMode ? 'pending_csr' : 'active_ai');

        function normalizeUserType(value) {
            if (!value) return null;
            const normalized = String(value).trim().toLowerCase();
            return ['buyer', 'organizer'].includes(normalized) ? normalized : null;
        }

        function getUserTypeLabel(userType) {
            return userType === 'organizer' ? config.organizerLabel : config.buyerLabel;
        }

        function updateComposerState() {
            const hasSelectedUserType = Boolean(selectedUserType);
            const canUploadImages = currentSessionStatus === 'active_csr';
            chatInput.disabled = !hasSelectedUserType;
            chatInput.readOnly = isAwaitingResponse;
            chatInput.placeholder = hasSelectedUserType
                ? 'Type your message...'
                : config.userTypePlaceholder;
            chatInput.setAttribute('aria-busy', isAwaitingResponse ? 'true' : 'false');
            chatUploadBtn.disabled = !hasSelectedUserType || isAwaitingResponse || !canUploadImages;
            chatUploadBtn.title = canUploadImages
                ? 'Upload images'
                : 'Image upload is available after you are connected to an agent';
            chatSend.disabled = !hasSelectedUserType || isAwaitingResponse;
        }

        function setSessionStatus(status) {
            currentSessionStatus = status || 'active_ai';
            isCSRMode = ['pending_csr', 'active_csr'].includes(currentSessionStatus);
            if (currentSessionStatus !== 'active_csr' && pendingImages.length > 0) {
                pendingImages = [];
                renderPendingImagePreview();
            }
            updateComposerState();
        }

        function setComposerBusy(isBusy) {
            isAwaitingResponse = isBusy;
            updateComposerState();
        }

        function buildRoleSelectorMarkup() {
            const buyerSelected = selectedUserType === 'buyer';
            const organizerSelected = selectedUserType === 'organizer';
            const isLocked = Boolean(selectedUserType);

            return `
                <div class="chat-bubble role-selector-bubble ai-message-content" data-role-selector="true">
                    <div class="role-selector-title">${config.userTypePrompt}</div>
                    <div class="role-options">
                        <button
                            type="button"
                            class="chat-role-option${buyerSelected ? ' selected' : ''}"
                            data-user-type="buyer"
                            aria-pressed="${buyerSelected ? 'true' : 'false'}"
                            ${isLocked ? 'disabled' : ''}
                        >
                            ${config.buyerLabel}
                        </button>
                        <button
                            type="button"
                            class="chat-role-option${organizerSelected ? ' selected' : ''}"
                            data-user-type="organizer"
                            aria-pressed="${organizerSelected ? 'true' : 'false'}"
                            ${isLocked ? 'disabled' : ''}
                        >
                            ${config.organizerLabel}
                        </button>
                    </div>
                    ${isLocked ? `<div class="role-selection-note">Selected: ${getUserTypeLabel(selectedUserType)}</div>` : ''}
                </div>
            `;
        }

        function ensureRoleSelectorMessage() {
            let selectorMessage = chatMessages.querySelector('[data-role-selector-wrapper="true"]');

            if (!selectorMessage) {
                selectorMessage = document.createElement('div');
                selectorMessage.className = 'chat-message ai';
                selectorMessage.setAttribute('data-role-selector-wrapper', 'true');
                chatMessages.prepend(selectorMessage);
            }

            selectorMessage.innerHTML = `
                <div class="chat-avatar">${generateAgentAvatar()}</div>
                ${buildRoleSelectorMarkup()}
            `;
        }

        function normalizeChatText(text) {
            return String(text || '').replace(/\s+/g, ' ').trim();
        }

        function isGenericWelcomeMessage(text) {
            const normalized = normalizeChatText(text).toLowerCase();
            if (!normalized) return false;
            const configured = normalizeChatText(config.welcomeMessage).toLowerCase();
            if (configured && normalized === configured) return true;
            return normalized.includes('how can we help you today');
        }

        function isOpeningGreetingMessage(text) {
            return /^hello(?: .+)?, how's your day going\?$/i.test(normalizeChatText(text));
        }

        function renderConversationShell() {
            chatMessages.innerHTML = '';
            ensureRoleSelectorMessage();
        }

        function applyUserType(userType) {
            const normalized = normalizeUserType(userType);
            if (!normalized) return;

            selectedUserType = normalized;
            config.userType = normalized;
            ensureRoleSelectorMessage();

            // One personalized greeting only — never the generic welcome.
            showAuthDebugMessage();

            updateComposerState();

            if (!chatBox.classList.contains('chat-widget-hidden') && config.focusInputOnOpen) {
                chatInput.focus();
            }
        }

        const chatNew = document.getElementById('chat-new');

        renderConversationShell();
        updateComposerState();

        function startNewChat() {
            if (confirm("Start a new chat? This will clear your current conversation.")) {
                // 1. Clear Local Storage using the correct keys
                localStorage.removeItem(config.visitorIdKey || 'chat_visitor_id');
                
                // 2. Generate NEW Visitor ID (closure variable)
                visitorId = 'v_' + Math.random().toString(36).substr(2, 9);
                localStorage.setItem(config.visitorIdKey || 'chat_visitor_id', visitorId);
                
                // 3. Reset state variables
                lastSeenMessageId = 0;
                setSessionStatus('active_ai');
                csrResolvedMessageShown = false;
                if (renderedMessageIds && renderedMessageIds.clear) {
                    renderedMessageIds.clear(); // Clear the Set
                }

                // 4. Reset the selected user type and UI shell
                selectedUserType = null;
                config.userType = null;
                renderConversationShell();
                // 5. Reload messages for the new ID (will be empty) and ensure polling is correct
                loadExistingMessages();
                
                console.log('[Widget] New Chat started with visitorId:', visitorId);
            }
        }

        if (chatNew) {
            chatNew.addEventListener('click', startNewChat);
        }

        // Toggle chat box
        function toggleChat() {
            const isOpen = !chatBox.classList.contains('chat-widget-hidden');
            if (isOpen) {
                chatBox.classList.add('chat-widget-hidden');
                chatWidgetContainer.classList.remove('chat-widget-open');
                document.body.classList.remove('chat-widget-fullscreen-open');
                if (config.onClose) config.onClose();
            } else {
                chatBox.classList.remove('chat-widget-hidden');
                chatWidgetContainer.classList.add('chat-widget-open');
                if (window.matchMedia(`(max-width: ${config.mobileBreakpoint})`).matches) {
                    document.body.classList.add('chat-widget-fullscreen-open');
                }
                if (config.focusInputOnOpen && selectedUserType && !isAwaitingResponse) chatInput.focus();
                if (config.onOpen) config.onOpen();
                // Start polling if we were in CSR mode
                if (isCSRMode) startPolling();
            }
        }

        // Load existing messages from the server on init, then start polling
        function loadExistingMessages() {
            // Fetch all messages with since_id=0 to get everything
            fetch(`${widgetBaseUrl}${config.pollUrl}`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    visitor_id: visitorId,
                    since_id: 0,
                    widget_key: config.widgetKey,
                    auth: buildAuthPayload()
                })
            })
            .then(res => res.json())
            .then(data => {
                const restoredUserType = normalizeUserType(data.user_type) || selectedUserType;
                if (restoredUserType) {
                    selectedUserType = restoredUserType;
                    config.userType = restoredUserType;
                }

                if (data.messages && data.messages.length > 0) {
                    renderConversationShell();

                    // Render all existing messages to restore conversation history
                    data.messages.forEach(msg => {
                        if (isGenericWelcomeMessage(msg.content)) {
                            if (msg.id) {
                                renderedMessageIds.add(`central_${msg.id}`);
                                if (msg.id > lastSeenMessageId) lastSeenMessageId = msg.id;
                            }
                            return;
                        }
                        const sender = msg.sender === 'csr' ? 'support' : (msg.sender === 'user' ? 'user' : 'ai');
                        const messageEl = addMessage(msg.content, sender, msg.images || []);
                        if (messageEl && sender !== 'user' && isOpeningGreetingMessage(msg.content)) {
                            messageEl.setAttribute('data-auth-debug', 'true');
                        }
                        // Track the highest message ID and mark as rendered
                        if (msg.id) {
                            renderedMessageIds.add(`central_${msg.id}`);
                            if (msg.id > lastSeenMessageId) lastSeenMessageId = msg.id;
                        }
                    });
                    console.log('[Widget] Loaded', data.messages.length, 'existing messages. lastSeenMessageId:', lastSeenMessageId);

                    // Keep a single greeting only when the thread is otherwise empty.
                    if (restoredUserType) {
                        showAuthDebugMessage();
                    }
                } else {
                    renderConversationShell();
                    if (selectedUserType) {
                        showAuthDebugMessage();
                    }
                }

                // Detect if already in CSR mode from loaded session
                setSessionStatus(data.session_status || 'active_ai');
                if (isCSRMode) csrResolvedMessageShown = false;
                if (data.authentication) {
                    rememberVisitorAuth(data.authentication);
                }
                // Always start polling after loading - it will only fetch NEW messages (since_id > lastSeenMessageId)
                startPolling();
            })
            .catch(err => {
                console.error('[Widget] Load existing messages error:', err);
                renderConversationShell();
                updateComposerState();
                if (selectedUserType) {
                    showAuthDebugMessage();
                }
                // Still start polling even if load fails
                startPolling();
            });
        }

        chatToggle.addEventListener('click', toggleChat);
        chatClose.addEventListener('click', toggleChat);
        if (config.closeOnOutsideClick) {
            document.addEventListener('click', function(event) {
                if (chatBox.classList.contains('chat-widget-hidden')) return;
                if (chatWidgetContainer.contains(event.target)) return;
                if (!document.body.contains(event.target)) return;
                toggleChat();
            });
        }

        chatMessages.addEventListener('click', function(event) {
            const roleButton = event.target.closest('.chat-role-option');
            if (!roleButton || selectedUserType) return;
            applyUserType(roleButton.dataset.userType);
        });

        // ---- Rich-text formatter for AI / CSR messages ----
        function formatMessage(raw) {
            if (!raw) return '';
            let text = raw;

            // 1. Escape HTML entities to prevent XSS
            text = text.replace(/&/g, '&amp;').replace(/</g, '&lt;').replace(/>/g, '&gt;');

            // 2. Normalise line breaks: literal two-char \n → real newline
            text = text.replace(/\\n/g, '\n');

            // 3. Smart line-break insertion for inline list markers
            //    Detect " - Uppercase…" mid-sentence and insert a newline before the dash
            //    e.g.  "…your ticket. - Approved refunds…" → "…your ticket.\n- Approved refunds…"
            //    Avoid false positives like "5 - 10" (digit-dash-digit) or " - " that's just a dash in prose
            text = text.replace(/([.!?:;])\s+- /g, '$1\n- ');
            //    Also catch inline numbered lists:  "…text. 1. First item…"
            text = text.replace(/([.!?:;])\s+(\d+[.)]\s)/g, '$1\n$2');

            // 4. Bold:  **text** or __text__
            text = text.replace(/\*\*(.+?)\*\*/g, '<strong>$1</strong>');
            text = text.replace(/__(.+?)__/g, '<strong>$1</strong>');

            // 5. Italic: *text* or _text_  (but not inside <strong>)
            text = text.replace(/(?<!\*)\*(?!\*)(.+?)(?<!\*)\*(?!\*)/g, '<em>$1</em>');

            // 6. Inline code: `code`
            text = text.replace(/`([^`]+)`/g, '<code style="background:rgba(255,255,255,0.1);padding:1px 5px;border-radius:4px;font-size:0.9em;">$1</code>');

            // 7. Convert lines into paragraphs, lists, etc.
            const lines = text.split('\n');
            let html = '';
            let inUl = false;
            let inOl = false;

            for (let i = 0; i < lines.length; i++) {
                const trimmed = lines[i].trim();
                if (!trimmed && !inUl && !inOl) { html += '<br>'; continue; }

                // Unordered list item: starts with - or • or *
                const ulMatch = trimmed.match(/^[-•*]\s+(.*)/);
                // Ordered list item: starts with 1. 2. etc.
                const olMatch = trimmed.match(/^(\d+)[.)]\s+(.*)/);

                if (ulMatch) {
                    if (inOl) { html += '</ol>'; inOl = false; }
                    if (!inUl) { html += '<ul style="margin:6px 0 6px 16px;padding:0;list-style:disc;">'; inUl = true; }
                    html += '<li style="margin:3px 0;line-height:1.5;">' + ulMatch[1] + '</li>';
                } else if (olMatch) {
                    if (inUl) { html += '</ul>'; inUl = false; }
                    if (!inOl) { html += '<ol style="margin:6px 0 6px 16px;padding:0;">'; inOl = true; }
                    html += '<li style="margin:3px 0;line-height:1.5;">' + olMatch[2] + '</li>';
                } else {
                    // Close any open list
                    if (inUl) { html += '</ul>'; inUl = false; }
                    if (inOl) { html += '</ol>'; inOl = false; }
                    html += '<p style="margin:4px 0;line-height:1.5;">' + trimmed + '</p>';
                }
            }
            // Close any dangling list
            if (inUl) html += '</ul>';
            if (inOl) html += '</ol>';

            return html;
        }

        function escapeHtml(raw) {
            return String(raw || '')
                .replace(/&/g, '&amp;')
                .replace(/</g, '&lt;')
                .replace(/>/g, '&gt;')
                .replace(/"/g, '&quot;');
        }

        function renderImageAttachments(images) {
            if (!Array.isArray(images) || images.length === 0) return '';
            const safeImages = images
                .map(image => image ? { ...image, src: image.image_url || image.imageUrl || image.url || image.data_url } : null)
                .filter(image => image && image.src && (String(image.src).startsWith('data:image/') || String(image.src).startsWith('http')))
                .map(image => `
                    <a href="${escapeHtml(image.src)}" target="_blank" rel="noopener noreferrer">
                        <img class="chat-attachment-image" src="${escapeHtml(image.src)}" alt="${escapeHtml(image.name || 'Uploaded image')}">
                    </a>
                `)
                .join('');
            return safeImages ? `<div class="chat-attachments">${safeImages}</div>` : '';
        }

        function renderPendingImagePreview() {
            if (!chatImagePreview) return;
            if (pendingImages.length === 0) {
                chatImagePreview.style.display = 'none';
                chatImagePreview.innerHTML = '';
                return;
            }

            chatImagePreview.style.display = 'flex';
            chatImagePreview.innerHTML = pendingImages.map((image, index) => `
                <div class="chat-image-chip">
                    <img src="${escapeHtml(image.data_url)}" alt="${escapeHtml(image.name || 'Selected image')}">
                    <button type="button" class="chat-image-remove" data-image-index="${index}" aria-label="Remove image">×</button>
                </div>
            `).join('');
        }

        function readImageFile(file) {
            return new Promise((resolve, reject) => {
                if (!file || !file.type || !file.type.startsWith('image/')) {
                    reject(new Error('Only image files can be uploaded.'));
                    return;
                }
                if (file.size > config.maxImageSizeBytes) {
                    reject(new Error(`Image ${file.name} is too large.`));
                    return;
                }

                const reader = new FileReader();
                reader.onload = () => resolve({
                    name: file.name,
                    mime_type: file.type,
                    data_url: reader.result
                });
                reader.onerror = () => reject(new Error(`Could not read ${file.name}.`));
                reader.readAsDataURL(file);
            });
        }

        async function handleImageSelection(files) {
            if (currentSessionStatus !== 'active_csr') {
                addMessage('Image upload is available after you are connected to an agent.', 'ai');
                chatUpload.value = '';
                return;
            }
            const slotsAvailable = Math.max(0, config.maxImageUploads - pendingImages.length);
            const selectedFiles = Array.from(files || []).slice(0, slotsAvailable);
            if (selectedFiles.length === 0) return;

            try {
                const images = await Promise.all(selectedFiles.map(readImageFile));
                pendingImages = pendingImages.concat(images);
                renderPendingImagePreview();
            } catch (error) {
                addMessage(error.message || 'Could not attach that image.', 'ai');
            } finally {
                chatUpload.value = '';
            }
        }

        // Add message to chat
        function addMessage(message, sender, images = []) {
            const messageDiv = document.createElement('div');
            messageDiv.className = `chat-message ${sender}`;
            
            // Format AI/support messages; keep user messages plain
            const displayMessage = (sender === 'user') ? escapeHtml(message) : formatMessage(message);
            const attachmentsHtml = renderImageAttachments(images);
            const bubbleContent = `${displayMessage}${attachmentsHtml}`;

            let avatarHtml;
            if (sender === 'user') {
                avatarHtml = `<div class="chat-avatar">${getIcon(config.userAvatar)}</div>`;
            } else if (sender === 'support') {
                avatarHtml = `<div class="chat-avatar">${getIcon('support')}</div>`;
            } else {
                avatarHtml = `<div class="chat-avatar">${generateAgentAvatar()}</div>`;
            }

            if (sender === 'user') {
                messageDiv.innerHTML = `
                    <div class="chat-bubble">${bubbleContent}</div>
                    ${avatarHtml}
                `;
            } else {
                messageDiv.innerHTML = `
                    ${avatarHtml}
                    <div class="chat-bubble ai-message-content">${bubbleContent}</div>
                `;
            }
            
            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
            if (config.onReceiveMessage && sender !== 'user') config.onReceiveMessage(message);
            return messageDiv;
        }

        function showAuthDebugMessage(authInfo = visitorAuthInfo, force = false) {
            if (!selectedUserType) return;
            const auth = authInfo || visitorAuthInfo || { mode: 'anonymous', user: null };
            const rawVerificationResponse = auth.user && auth.user.verification_response;
            const user = auth.user || (rawVerificationResponse && rawVerificationResponse.user) || null;
            const name = (user && user.name) ? String(user.name).trim() : '';
            const greeting = name
                ? `Hello ${name}, how's your day going?`
                : 'Hello, how\'s your day going?';

            const existing = chatMessages.querySelector('[data-auth-debug="true"]');
            if (existing) {
                const bubble = existing.querySelector('.chat-bubble');
                if (bubble && bubble.textContent === greeting && !force) return;
                if (bubble) bubble.textContent = greeting;
                return;
            }

            const hasOtherMessages = Boolean(
                chatMessages.querySelector('.chat-message:not([data-role-selector-wrapper="true"]):not([data-auth-debug="true"])')
            );
            if (hasOtherMessages && !force) return;

            const messageDiv = document.createElement('div');
            messageDiv.className = 'chat-message ai';
            messageDiv.setAttribute('data-auth-debug', 'true');
            messageDiv.innerHTML = `
                <div class="chat-avatar">${generateAgentAvatar()}</div>
                <div class="chat-bubble ai-message-content">${escapeHtml(greeting)}</div>
            `;

            chatMessages.appendChild(messageDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        // Show/Remove typing indicator
        function showTypingIndicator() {
            if(document.getElementById('typing-indicator')) return;
            const typingDiv = document.createElement('div');
            typingDiv.id = 'typing-indicator';
            typingDiv.className = 'chat-message ai';
            typingDiv.innerHTML = `
                <div class="chat-avatar">${generateAgentAvatar()}</div>
                <div class="typing-indicator"><span></span><span></span><span></span></div>
            `;
            chatMessages.appendChild(typingDiv);
            chatMessages.scrollTop = chatMessages.scrollHeight;
        }

        function removeTypingIndicator() {
            const typingIndicator = document.getElementById('typing-indicator');
            if (typingIndicator) typingIndicator.remove();
        }

        // ---- MOVED Polling Functions (Inside createChatWidget to fix scoping) ----
        // Track rendered IDs to prevent duplicates
        const renderedMessageIds = new Set();
        let lastSeenMessageId = 0;
        let csrResolvedMessageShown = false;

        function startPolling() {
            if (isPolling) return;
            isPolling = true;
            pollMessages(); // Poll immediately
            pollInterval = setInterval(pollMessages, config.pollInterval);
            console.log('[Widget] Polling started, lastSeenMessageId:', lastSeenMessageId);
        }

        function stopPolling() {
            if (pollInterval) clearInterval(pollInterval);
            isPolling = false;
        }

        function pollMessages() {
            if (!visitorId) return;
            
            // ALWAYS poll central API — it is the single source of truth
            const targetUrl = `${widgetBaseUrl}${config.pollUrl}`;

            fetch(targetUrl, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({
                    visitor_id: visitorId,
                    since_id: lastSeenMessageId,
                    widget_key: config.widgetKey,
                    auth: buildAuthPayload()
                })
            })
            .then(res => res.json())
            .then(data => {
                const status = data.session_status || 'none';
                const wasCsrMode = isCSRMode;
                const isBackToAi = (status === 'active_ai');
                const isCsrStatus = ['pending_csr', 'active_csr'].includes(status);

                // CSR resolved → switch to AI and notify the visitor once.
                if (isBackToAi && wasCsrMode) {
                    console.log('[Widget] CSR resolved — back to AI mode');
                    setSessionStatus('active_ai');
                    isExternalCsrMode = false;
                    externalCsrInitialized = false;
                    if (!csrResolvedMessageShown) {
                        addMessage(config.csrResolvedMessage, 'ai');
                        csrResolvedMessageShown = true;
                    }
                } else if (isBackToAi && !wasCsrMode) {
                    // Keep AI mode in sync even if we already left CSR mode.
                    setSessionStatus('active_ai');
                }

                // Entered / still in CSR mode
                if (isCsrStatus) {
                    setSessionStatus(status);
                    csrResolvedMessageShown = false;
                    if (!isPolling) startPolling();
                }

                if (data.messages && data.messages.length > 0) {
                    data.messages.forEach(msg => {
                        if (msg.id && msg.id > lastSeenMessageId) lastSeenMessageId = msg.id;
                        
                        const dedupeKey = `central_${msg.id}`;
                        if (renderedMessageIds.has(dedupeKey)) return;
                        renderedMessageIds.add(dedupeKey);
                        
                        // Render non-user messages
                        if (msg.sender !== 'user') {
                            if (isGenericWelcomeMessage(msg.content)) return;
                            const trimmed = String(msg.content || '').trim();
                            const isResolvedNotice = trimmed === String(config.csrResolvedMessage || '').trim()
                                || /connected back to (the )?ai/i.test(trimmed);

                            if (isResolvedNotice) {
                                // Ensure we leave CSR mode when the resolve notice arrives.
                                if (isCSRMode) {
                                    setSessionStatus('active_ai');
                                    isExternalCsrMode = false;
                                    externalCsrInitialized = false;
                                }
                                if (csrResolvedMessageShown) return;
                                csrResolvedMessageShown = true;
                            }

                            // Content safety net for the handoff notice only.
                            if (trimmed === 'You will be connected by our agent shortly.') {
                                const alreadyVisible = Array.from(chatMessages.querySelectorAll('.chat-bubble'))
                                    .some((el) => (el.textContent || '').trim() === trimmed);
                                if (alreadyVisible) return;
                            }

                            console.log('[Widget] New message:', dedupeKey, msg.sender);
                            addMessage(msg.content, msg.sender === 'csr' ? 'support' : 'ai', msg.images || []);
                        }
                    });
                }
            })
            .catch(err => console.error('[Widget] Poll error:', err));
        }


        // Send message function
        function sendMessage() {
            if (isAwaitingResponse) return;
            if (!selectedUserType) return;

            const message = chatInput.value.trim();
            const imagesToSend = pendingImages.slice();
            if (imagesToSend.length > 0 && currentSessionStatus !== 'active_csr') {
                addMessage('Image upload is available after you are connected to an agent.', 'ai');
                pendingImages = [];
                renderPendingImagePreview();
                return;
            }
            if (message === '' && imagesToSend.length === 0) return;
            
            // Check authentication
            // Note: For now we allow even if not authenticated for testing, or enforce it. 
            // The Original code had strict auth. We should arguably keep it if configured.
            // if (!isAuthenticated && config.widgetKey) {
            //      ...
            // }

            if (config.onSendMessage) config.onSendMessage(message);

            addMessage(message, 'user', imagesToSend);
            chatInput.value = '';
            pendingImages = [];
            renderPendingImagePreview();
            setComposerBusy(true);
            
            // Don't show typing indicator in CSR mode (agent replies asynchronously)
            if (!isCSRMode) showTypingIndicator();
            
            // ALWAYS send through central API — it handles CSR relay if needed
            fetch(`${widgetBaseUrl}${config.apiUrl}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    message: message,
                    prompt: message,
                    widget_key: config.widgetKey,
                    visitor_id: visitorId,
                    user_type: selectedUserType,
                    images: imagesToSend,
                    auth: buildAuthPayload()
                })
            })
            .then(res => res.json())
            .then(data => {
                const responseUserType = normalizeUserType(data.user_type);
                if (responseUserType) {
                    selectedUserType = responseUserType;
                    config.userType = responseUserType;
                    ensureRoleSelectorMessage();
                    updateComposerState();
                }

                if (data.authentication) {
                    rememberVisitorAuth(data.authentication);
                    // Greeting is shown once at chat start — do not re-append here.
                } else if (data.auth_mode) {
                    rememberVisitorAuth({
                        mode: data.auth_mode,
                        user: visitorAuthInfo.user
                    });
                }

                removeTypingIndicator();
                if (data.error) {
                    addMessage('Error: ' + data.message, 'ai');
                    return;
                }

                // Reserve message IDs before polling so the same AI reply is not rendered twice.
                if (data.user_msg_id) {
                    renderedMessageIds.add(`central_${data.user_msg_id}`);
                    if (data.user_msg_id > lastSeenMessageId) lastSeenMessageId = data.user_msg_id;
                }

                let aiAlreadyRendered = false;
                if (data.ai_msg_id) {
                    const aiKey = `central_${data.ai_msg_id}`;
                    aiAlreadyRendered = renderedMessageIds.has(aiKey);
                    renderedMessageIds.add(aiKey);
                    if (data.ai_msg_id > lastSeenMessageId) lastSeenMessageId = data.ai_msg_id;
                }

                if (data.output && !aiAlreadyRendered) {
                    const trimmedOutput = String(data.output).trim();
                    const duplicateByContent = Array.from(chatMessages.querySelectorAll('.chat-bubble'))
                        .some((el) => (el.textContent || '').trim() === trimmedOutput);
                    if (!duplicateByContent) {
                        const isCsr = ['active_csr', 'csr_active'].includes(data.mode);
                        addMessage(data.output, isCsr ? 'support' : 'ai');
                    }
                }

                // Start CSR polling only after local render + ID reservation.
                const csrModes = ['pending_csr', 'csr_pending', 'active_csr', 'csr_active'];
                if (csrModes.includes(data.mode)) {
                    setSessionStatus(['active_csr', 'csr_active'].includes(data.mode) ? 'active_csr' : 'pending_csr');
                    csrResolvedMessageShown = false;
                    if (!isPolling) startPolling();
                } else if (data.mode === 'active_ai') {
                    if (isCSRMode) {
                        setSessionStatus('active_ai');
                        isExternalCsrMode = false;
                        externalCsrInitialized = false;
                        if (!csrResolvedMessageShown) {
                            addMessage(config.csrResolvedMessage, 'ai');
                            csrResolvedMessageShown = true;
                        }
                    } else {
                        setSessionStatus('active_ai');
                    }
                }
            })
            .catch(error => {
                console.error('Error:', error);
                removeTypingIndicator();
                addMessage('Sorry, I encountered an error. Please try again.', 'ai');
                if (config.onError) config.onError(error);
            })
            .finally(() => {
                setComposerBusy(false);
            });
        }

        chatUploadBtn.addEventListener('click', function() {
            if (!chatUploadBtn.disabled) chatUpload.click();
        });
        chatUpload.addEventListener('change', function(event) {
            handleImageSelection(event.target.files);
        });
        chatImagePreview.addEventListener('click', function(event) {
            const removeButton = event.target.closest('.chat-image-remove');
            if (!removeButton) return;
            const index = Number(removeButton.dataset.imageIndex);
            if (!Number.isNaN(index)) {
                pendingImages.splice(index, 1);
                renderPendingImagePreview();
            }
        });
        chatSend.addEventListener('click', sendMessage);
        chatInput.addEventListener('keypress', function(e) {
            if (e.key === 'Enter') sendMessage();
        });

        // Auto-open
        if (config.autoOpen) {
            setTimeout(() => {
                if (chatBox.classList.contains('chat-widget-hidden')) toggleChat();
            }, config.openDelay);
        }
        
        // Return API functions
        return {
            toggleChat: toggleChat,
            sendMessage: sendMessage,
            addMessage: addMessage,
            showAuthDebugMessage: showAuthDebugMessage,
            loadExistingMessages: loadExistingMessages,
            show: () => { if (chatBox.classList.contains('chat-widget-hidden')) toggleChat(); },
            hide: () => { if (!chatBox.classList.contains('chat-widget-hidden')) toggleChat(); }
        };
        
        if (config.onOpen && config.autoOpen) setTimeout(() => config.onOpen(), config.openDelay + 100);
    }

    // Global API for advanced control
    window.AuthenticatedChatWidget = {
        show: () => {
             if (window.AuthenticatedChatWidget._internal && window.AuthenticatedChatWidget._internal.show) {
                 window.AuthenticatedChatWidget._internal.show();
             } else if (window.AuthenticatedChatWidget._internal && window.AuthenticatedChatWidget._internal.toggleChat) {
                  // Fallback if show is not defined
                  const chatBox = document.getElementById('chat-box');
                  if (chatBox && chatBox.classList.contains('chat-widget-hidden')) window.AuthenticatedChatWidget._internal.toggleChat();
             }
        },
        hide: () => {
             if (window.AuthenticatedChatWidget._internal && window.AuthenticatedChatWidget._internal.hide) {
                 window.AuthenticatedChatWidget._internal.hide();
             } else if (window.AuthenticatedChatWidget._internal && window.AuthenticatedChatWidget._internal.toggleChat) {
                  const chatBox = document.getElementById('chat-box');
                  if (chatBox && !chatBox.classList.contains('chat-widget-hidden')) window.AuthenticatedChatWidget._internal.toggleChat();
             }
        },
        toggle: () => {
             if (window.AuthenticatedChatWidget._internal && window.AuthenticatedChatWidget._internal.toggleChat) 
                 window.AuthenticatedChatWidget._internal.toggleChat();
        },
        sendMessage: (message) => {
             if (window.AuthenticatedChatWidget._internal && window.AuthenticatedChatWidget._internal.sendMessage) 
                 window.AuthenticatedChatWidget._internal.sendMessage(message);
        },
        addMessage: (message, sender) => {
             if (window.AuthenticatedChatWidget._internal && window.AuthenticatedChatWidget._internal.addMessage) 
                 window.AuthenticatedChatWidget._internal.addMessage(message, sender);
        },
        config: config,
        updateConfig: (newConfig) => {
            Object.assign(config, newConfig);
            // Reload CSS with new config
            // Find our style tag - simple heuristic
            const styles = document.getElementsByTagName('style');
            for(let style of styles) {
                if(style.innerHTML.includes('--chat-widget-primary-color')) {
                    style.remove();
                    break;
                }
            }
            injectCSS();
        },
        setAuthentication: (modeOrAuth, token = null) => {
            let nextMode = 'anonymous';
            let nextToken = null;
            if (modeOrAuth && typeof modeOrAuth === 'object') {
                nextMode = modeOrAuth.mode === 'authenticated' ? 'authenticated' : 'anonymous';
                nextToken = nextMode === 'authenticated' ? (modeOrAuth.token || null) : null;
            } else {
                nextMode = modeOrAuth === 'authenticated' ? 'authenticated' : 'anonymous';
                nextToken = nextMode === 'authenticated' ? token : null;
            }
            config.auth = {
                mode: nextMode,
                token: nextToken
            };
            rememberVisitorAuth({
                mode: config.auth.mode,
                user: nextMode === 'authenticated' ? visitorAuthInfo.user : null
            });
            if (
                window.AuthenticatedChatWidget._internal &&
                window.AuthenticatedChatWidget._internal.showAuthDebugMessage
            ) {
                window.AuthenticatedChatWidget._internal.showAuthDebugMessage();
            }
        },
        isAuthenticated: () => isAuthenticated,
        businessInfo: () => businessInfo,
        visitorAuth: () => visitorAuthInfo,
        _internal: null
    };

    // Initialize
    function init() {
         function mountWidget() {
             injectCSS();
             window.AuthenticatedChatWidget._internal = createChatWidget();
             window.AuthenticatedChatWidget._internal.loadExistingMessages();
         }

         if (config.widgetKey) {
             validateWidget().then(() => {
                 mountWidget();
             }).catch(err => {
                 // Temporary: still show the widget if token auth fails.
                 console.warn("Auth failed; mounting widget in fallback mode:", err);
                 isAuthenticated = true;
                 rememberVisitorAuth({ mode: 'anonymous', user: null });
                 mountWidget();
             });
         } else {
             // Development mode or no key
             mountWidget();
         }
    }

    if (document.readyState === 'loading') {
        document.addEventListener('DOMContentLoaded', init);
    } else {
        init();
    }

})();        
