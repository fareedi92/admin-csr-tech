(function() {
    // Default configuration
    const defaultConfig = {
        // Position and Layout
        position: 'bottom-right', // 'bottom-right', 'bottom-left', 'top-right', 'top-left'
        width: '380px',
        height: '500px',
        mobileWidth: '100%',
        mobileHeight: '100%',
        
        // Colors and Styling
        primaryColor: '#3B82F6',
        backgroundColor: '#ffffff',
        textColor: '#1f2937',
        userMessageColor: '#3B82F6',
        userMessageTextColor: '#ffffff',
        aiMessageColor: '#f3f4f6',
        aiMessageTextColor: '#1f2937',
        borderColor: '#e5e7eb',
        shadowColor: 'rgba(0, 0, 0, 0.1)',
        
        // Typography
        fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Roboto, sans-serif',
        fontSize: '14px',
        headerFontSize: '16px',
        
        // Content
        widgetTitle: 'AI Assistant',
        welcomeMessage: 'Hello! I\'m your AI assistant. How can I help you today?',
        userTypePrompt: 'Are you a Buyer or Organizer?',
        buyerLabel: 'Buyer',
        organizerLabel: 'Organizer',
        userTypePlaceholder: 'Select Buyer or Organizer to start chatting',
        userAvatar: '👤',
        aiAvatar: '🤖',
        sendButtonIcon: '➤',
        closeButtonIcon: '×',
        toggleButtonIcon: '💬',
        
        // Behavior
        autoOpen: false,
        openDelay: 1000,
        closeOnOutsideClick: true,
        focusInputOnOpen: true,
        
        // API Configuration
        webhookUrl: 'https://aidevv.3utilities.com/webhook/65350c02-df88-49d9-983d-8aaf691d7ad1/chat',
        namespaceEndpoint: '/get_user_namespace',
        requestTimeout: 60000,
        
        // Animations
        animationDuration: '0.3s',
        enableAnimations: true,
        
        // Responsive
        mobileBreakpoint: '768px',
        
        // Custom CSS
        customCSS: '',
        
        // Callbacks
        onOpen: null,
        onClose: null,
        onSendMessage: null,
        onReceiveMessage: null,
        onError: null
    };

    // Global configuration object that developers can modify
    window.ChatWidgetConfig = window.ChatWidgetConfig || {};

    // Merge default config with user config
    const config = { ...defaultConfig, ...window.ChatWidgetConfig };

    // Inject CSS with customizable variables
    const style = document.createElement('style');
    style.innerHTML = `
        :root {
            --chat-widget-primary-color: ${config.primaryColor};
            --chat-widget-bg-color: ${config.backgroundColor};
            --chat-widget-text-color: ${config.textColor};
            --chat-widget-user-msg-color: ${config.userMessageColor};
            --chat-widget-user-msg-text-color: ${config.userMessageTextColor};
            --chat-widget-ai-msg-color: ${config.aiMessageColor};
            --chat-widget-ai-msg-text-color: ${config.aiMessageTextColor};
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
        }

        .chat-widget-hidden {
            display: none !important;
        }

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
            background-color: var(--chat-widget-primary-color);
            color: white;
            border: none;
            border-radius: 50%;
            width: 60px;
            height: 60px;
            cursor: pointer;
            box-shadow: 0 4px 12px var(--chat-widget-shadow-color);
            transition: all var(--chat-widget-animation-duration) ease;
            display: flex;
            align-items: center;
            justify-content: center;
            font-size: 24px;
            z-index: 10000;
        }

        #chat-toggle:hover {
            transform: scale(1.05);
            box-shadow: 0 6px 20px var(--chat-widget-shadow-color);
        }

        #chat-box {
            position: absolute;
            ${config.position.includes('bottom') ? 'bottom: 80px;' : 'top: 80px;'}
            ${config.position.includes('right') ? 'right: 0;' : 'left: 0;'}
            width: var(--chat-widget-width);
            max-width: 90vw;
            height: var(--chat-widget-height);
            background: var(--chat-widget-bg-color);
            border-radius: 12px;
            box-shadow: 0 10px 40px var(--chat-widget-shadow-color);
            border: 1px solid var(--chat-widget-border-color);
            display: flex;
            flex-direction: column;
            overflow: hidden;
            transition: all var(--chat-widget-animation-duration) ease;
        }

        #chat-widget-container.chat-widget-open #chat-toggle {
            display: none;
        }

        #chat-widget-container.chat-widget-open #chat-box {
            ${config.position.includes('bottom') ? 'bottom: 20px;' : 'top: 20px;'}
        }

        #chat-header {
            background-color: var(--chat-widget-primary-color);
            color: white;
            padding: 16px;
            display: flex;
            justify-content: space-between;
            align-items: center;
            font-weight: 600;
            font-size: var(--chat-widget-header-font-size);
        }

        #chat-close {
            background: none;
            border: none;
            color: white;
            font-size: 20px;
            cursor: pointer;
            padding: 4px;
            border-radius: 4px;
            transition: background-color 0.2s;
        }

        #chat-close:hover {
            background-color: rgba(255, 255, 255, 0.1);
        }

        #chat-messages {
            flex: 1 1 auto;
            padding: 16px;
            overflow-y: auto;
            background-color: #f9fafb;
            min-height: 0;
            max-height: none !important;
        }

        .chat-message {
            margin-bottom: 12px;
            display: flex;
            align-items: flex-start;
        }

        .chat-message.user {
            justify-content: flex-end;
        }

        .chat-bubble {
            max-width: 80%;
            padding: 10px 14px;
            border-radius: 18px;
            word-wrap: break-word;
        }

        .chat-message.user .chat-bubble {
            background-color: var(--chat-widget-user-msg-color);
            color: var(--chat-widget-user-msg-text-color);
            border-bottom-right-radius: 4px;
        }

        .chat-message.ai .chat-bubble {
            background-color: var(--chat-widget-ai-msg-color);
            color: var(--chat-widget-ai-msg-text-color);
            border: 1px solid var(--chat-widget-border-color);
            border-bottom-left-radius: 4px;
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
            border-color: var(--chat-widget-primary-color);
            background: rgba(59, 130, 246, 0.12);
        }

        .chat-role-option.selected {
            background: var(--chat-widget-primary-color);
            border-color: var(--chat-widget-primary-color);
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

        .chat-avatar {
            width: 32px;
            height: 32px;
            border-radius: 50%;
            display: flex;
            align-items: center;
            justify-content: center;
            margin: 0 8px;
            font-size: 14px;
            flex-shrink: 0;
        }

        .chat-message.user .chat-avatar {
            background-color: #e5e7eb;
            color: #6b7280;
            order: 2;
        }

        .chat-message.ai .chat-avatar {
            background-color: rgba(59, 130, 246, 0.1);
            color: var(--chat-widget-primary-color);
        }

        #chat-input-container {
            padding: 16px;
            border-top: 1px solid var(--chat-widget-border-color);
            background-color: var(--chat-widget-bg-color);
            display: flex;
            gap: 8px;
        }

        #chat-input {
            flex: 1;
            border: 1px solid var(--chat-widget-border-color);
            border-radius: 20px;
            padding: 10px 16px;
            font-size: var(--chat-widget-font-size);
            outline: none;
            transition: border-color 0.2s;
            font-family: var(--chat-widget-font-family);
        }

        #chat-input:focus {
            border-color: var(--chat-widget-primary-color);
        }

        #chat-input:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        #chat-send {
            background-color: var(--chat-widget-primary-color);
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
        }

        #chat-send:hover {
            opacity: 0.9;
        }

        #chat-send:disabled {
            opacity: 0.6;
            cursor: not-allowed;
        }

        #chat-input[readonly] {
            opacity: 0.7;
            cursor: wait;
        }

        .typing-indicator {
            display: flex;
            align-items: center;
            padding: 8px 12px;
            background-color: var(--chat-widget-ai-msg-color);
            border: 1px solid var(--chat-widget-border-color);
            border-radius: 18px;
            border-bottom-left-radius: 4px;
            margin-bottom: 12px;
            width: fit-content;
        }

        .typing-indicator span {
            height: 8px;
            width: 8px;
            background-color: #9ca3af;
            border-radius: 50%;
            display: inline-block;
            margin: 0 2px;
            animation: typing 1.4s infinite;
        }

        .typing-indicator span:nth-child(2) {
            animation-delay: 0.2s;
        }

        .typing-indicator span:nth-child(3) {
            animation-delay: 0.4s;
        }

        @keyframes typing {
            0%, 60%, 100% {
                transform: translateY(0);
            }
            30% {
                transform: translateY(-10px);
            }
        }

        @media (max-width: ${config.mobileBreakpoint}) {
            #chat-box {
                width: var(--chat-widget-mobile-width);
                height: var(--chat-widget-mobile-height);
                bottom: 0;
                ${config.position.includes('right') ? 'right: 0;' : 'left: 0;'}
                border-radius: 0;
                max-width: 100%;
            }
            
            #chat-widget-container {
                bottom: 10px;
                ${config.position.includes('right') ? 'right: 10px;' : 'left: 10px;'}
            }

            #chat-widget-container.chat-widget-open #chat-box {
                bottom: 0;
            }
        }

        /* Custom CSS provided by developer */
        ${config.customCSS}
    `;
    document.head.appendChild(style);

    // Create chat widget HTML
    const chatWidgetContainer = document.createElement('div');
    chatWidgetContainer.id = 'chat-widget-container';
    chatWidgetContainer.innerHTML = `
        <button id="chat-toggle" aria-label="Open chat">
            ${config.toggleButtonIcon}
        </button>
        
        <div id="chat-box" class="chat-widget-hidden">
            <div id="chat-header">
                <div style="display: flex; align-items: center; gap: 8px;">
                    <div style="width: 8px; height: 8px; background-color: #10b981; border-radius: 50%;"></div>
                    <span>${config.widgetTitle}</span>
                </div>
                <button id="chat-close" aria-label="Close chat">
                    ${config.closeButtonIcon}
                </button>
            </div>
            
            <div id="chat-messages"></div>
            
            <div id="chat-input-container">
                <input 
                    type="text" 
                    id="chat-input" 
                    placeholder="Type your message..."
                    aria-label="Type your message"
                >
                <button id="chat-send" aria-label="Send message">
                    ${config.sendButtonIcon}
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
    const chatSend = document.getElementById('chat-send');
    const chatMessages = document.getElementById('chat-messages');
    let isAwaitingResponse = false;
    let selectedUserType = normalizeUserType(config.userType);

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
        chatInput.disabled = !hasSelectedUserType;
        chatInput.readOnly = isAwaitingResponse;
        chatInput.placeholder = hasSelectedUserType
            ? 'Type your message...'
            : config.userTypePlaceholder;
        chatInput.setAttribute('aria-busy', isAwaitingResponse ? 'true' : 'false');
        chatSend.disabled = !hasSelectedUserType || isAwaitingResponse;
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
            <div class="chat-bubble role-selector-bubble" data-role-selector="true">
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
            <div class="chat-avatar">${config.aiAvatar}</div>
            ${buildRoleSelectorMarkup()}
        `;
    }

    function renderConversationShell(showWelcomeMessage = false) {
        chatMessages.innerHTML = '';
        ensureRoleSelectorMessage();

        if (selectedUserType && showWelcomeMessage) {
            addMessage(config.welcomeMessage, 'ai');
        }
    }

    function applyUserType(userType, showWelcomeMessage = false) {
        const normalized = normalizeUserType(userType);
        if (!normalized) return;

        selectedUserType = normalized;
        config.userType = normalized;
        ensureRoleSelectorMessage();

        if (showWelcomeMessage && !chatMessages.querySelector('.chat-message:not([data-role-selector-wrapper="true"])')) {
            addMessage(config.welcomeMessage, 'ai');
        }

        updateComposerState();

        if (!chatBox.classList.contains('chat-widget-hidden') && config.focusInputOnOpen) {
            chatInput.focus();
        }
    }

    renderConversationShell(Boolean(selectedUserType));
    updateComposerState();

    // Toggle chat box
    function toggleChat() {
        const isOpen = !chatBox.classList.contains('chat-widget-hidden');
        
        if (isOpen) {
            chatBox.classList.add('chat-widget-hidden');
            chatWidgetContainer.classList.remove('chat-widget-open');
            if (config.onClose) config.onClose();
        } else {
            chatBox.classList.remove('chat-widget-hidden');
            chatWidgetContainer.classList.add('chat-widget-open');
            if (config.focusInputOnOpen && selectedUserType && !isAwaitingResponse) {
                chatInput.focus();
            }
            if (config.onOpen) config.onOpen();
        }
    }

    // Event listeners
    chatToggle.addEventListener('click', toggleChat);
    chatClose.addEventListener('click', toggleChat);

    // Close on outside click if enabled
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
        applyUserType(roleButton.dataset.userType, true);
    });

    // Add message to chat
    function addMessage(message, sender) {
        const messageDiv = document.createElement('div');
        messageDiv.className = `chat-message ${sender}`;
        
        if (sender === 'user') {
            messageDiv.innerHTML = `
                <div class="chat-bubble">${message}</div>
                <div class="chat-avatar">${config.userAvatar}</div>
            `;
        } else {
            messageDiv.innerHTML = `
                <div class="chat-avatar">${config.aiAvatar}</div>
                <div class="chat-bubble">${message}</div>
            `;
        }
        
        chatMessages.appendChild(messageDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
        
        if (config.onReceiveMessage && sender === 'ai') {
            config.onReceiveMessage(message);
        }
    }

    // Show typing indicator
    function showTypingIndicator() {
        const typingDiv = document.createElement('div');
        typingDiv.id = 'typing-indicator';
        typingDiv.className = 'chat-message ai';
        typingDiv.innerHTML = `
            <div class="chat-avatar">${config.aiAvatar}</div>
            <div class="typing-indicator">
                <span></span>
                <span></span>
                <span></span>
            </div>
        `;
        chatMessages.appendChild(typingDiv);
        chatMessages.scrollTop = chatMessages.scrollHeight;
    }

    // Remove typing indicator
    function removeTypingIndicator() {
        const typingIndicator = document.getElementById('typing-indicator');
        if (typingIndicator) {
            typingIndicator.remove();
        }
    }

    // Send message function
    function sendMessage() {
        if (isAwaitingResponse) return;
        if (!selectedUserType) return;

        const message = chatInput.value.trim();
        if (message === '') return;

        // Trigger callback
        if (config.onSendMessage) {
            config.onSendMessage(message);
        }

        // Add user message to chat
        addMessage(message, 'user');

        // Clear input
        chatInput.value = '';
        setComposerBusy(true);

        // Show typing indicator
        showTypingIndicator();

        // Get the user's namespace
        let namespace = "default";
        
        fetch(config.namespaceEndpoint)
            .then(response => response.json())
            .then(data => {
                if (data.namespace) {
                    namespace = data.namespace;
                }
                
                // Send message to webhook with namespace
                return fetch(config.webhookUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        action: 'sendMessage',
                        chatInput: message,
                        prompt: message,
                        namespace: namespace,
                        user_type: selectedUserType
                    })
                });
            })
            .catch(error => {
                console.error('Error getting namespace:', error);
                
                // Send message to webhook without namespace if there's an error
                return fetch(config.webhookUrl, {
                    method: 'POST',
                    headers: {
                        'Content-Type': 'application/json',
                    },
                    body: JSON.stringify({
                        action: 'sendMessage',
                        chatInput: message,
                        prompt: message,
                        user_type: selectedUserType
                    })
                });
            })
            .then(response => response.json())
            .then(data => {
                // Remove typing indicator
                removeTypingIndicator();

                // Add AI response to chat
                if (data.output) {
                    addMessage(data.output, 'ai');
                } else {
                    addMessage('Sorry, I encountered an error. Please try again.', 'ai');
                }
            })
            .catch(error => {
                console.error('Error:', error);
                removeTypingIndicator();
                addMessage('Sorry, I encountered an error. Please try again.', 'ai');
                
                if (config.onError) {
                    config.onError(error);
                }
            })
            .finally(() => {
                setComposerBusy(false);
            });
    }

    // Event listeners
    chatSend.addEventListener('click', sendMessage);

    chatInput.addEventListener('keypress', function(e) {
        if (e.key === 'Enter') {
            sendMessage();
        }
    });

    // Auto-open if enabled
    if (config.autoOpen) {
        setTimeout(() => {
            if (chatBox.classList.contains('chat-widget-hidden')) {
                toggleChat();
            }
        }, config.openDelay);
    }

    // Global API for advanced control
    window.ChatWidget = {
        show: () => {
            if (chatBox.classList.contains('chat-widget-hidden')) {
                toggleChat();
            }
        },
        hide: () => {
            if (!chatBox.classList.contains('chat-widget-hidden')) {
                toggleChat();
            }
        },
        toggle: toggleChat,
        sendMessage: sendMessage,
        addMessage: addMessage,
        config: config,
        updateConfig: (newConfig) => {
            Object.assign(config, newConfig);
            // Reload CSS with new config
            document.head.removeChild(style);
            document.head.appendChild(style);
        }
    };

    // Notify that widget is ready
    if (config.onOpen && config.autoOpen) {
        setTimeout(() => config.onOpen(), config.openDelay + 100);
    }
})();
