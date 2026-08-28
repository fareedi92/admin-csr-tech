(function() {
    // --- Styles ---
    const styles = `
        :root {
            --primary: #6366f1;
            --primary-dark: #4f46e5;
            --bg-page: #f8fafc;
            --bg-card: #ffffff;
            --text-main: #1e293b;
            --text-muted: #64748b;
            --sidebar-width: 320px;
            --accent: #f43f5e;
            --success: #10b981;
        }

        #csr-console-root { 
            font-family: 'Plus Jakarta Sans', sans-serif; 
            color: var(--text-main);
            height: 100vh;
            display: flex;
            overflow: hidden;
            background: var(--bg-page);
        }

        /* Sidebar Styling */
        .csr-sidebar {
            width: var(--sidebar-width);
            background: var(--bg-card);
            border-right: 1px solid #e2e8f0;
            display: flex;
            flex-direction: column;
            z-index: 10;
        }

        .csr-sidebar-header {
            padding: 24px;
            border-bottom: 1px solid #f1f5f9;
            display: flex;
            justify-content: space-between;
            align-items: center;
        }

        .csr-sidebar-header h2 { font-size: 1.25rem; font-weight: 700; color: var(--primary); }
        
        .csr-new-chat-btn {
            background: #f1f5f9;
            border: none;
            width: 36px;
            height: 36px;
            border-radius: 8px;
            cursor: pointer;
            color: var(--text-main);
            transition: all 0.2s;
        }
        .csr-new-chat-btn:hover { background: #e2e8f0; transform: scale(1.05); }

        .csr-session-list {
            flex: 1;
            overflow-y: auto;
            padding: 12px;
        }

        .csr-session-card {
            padding: 16px;
            border-radius: 12px;
            margin-bottom: 8px;
            cursor: pointer;
            transition: all 0.2s;
            border: 1px solid transparent;
            position: relative;
        }

        .csr-session-card:hover { background: #f8fafc; border-color: #f1f5f9; }
        .csr-session-card.active { background: #eff6ff; border-color: #dbeafe; }

        .csr-session-card .name { font-weight: 600; font-size: 0.95rem; margin-bottom: 4px; display: block; }
        .csr-session-card .last-msg { font-size: 0.85rem; color: var(--text-muted); white-space: nowrap; overflow: hidden; text-overflow: ellipsis; display: block; }
        .csr-session-card .time { font-size: 0.75rem; color: var(--text-muted); position: absolute; top: 16px; right: 16px; }

        /* Main Console Styling */
        .csr-main-console {
            flex: 1;
            display: flex;
            flex-direction: column;
            background: #ffffff;
            position: relative;
        }

        .csr-console-header {
            padding: 20px 32px;
            border-bottom: 1px solid #f1f5f9;
            display: flex;
            justify-content: space-between;
            align-items: center;
            background: rgba(255, 255, 255, 0.8);
            backdrop-filter: blur(10px);
        }

        .csr-user-info { display: flex; align-items: center; gap: 12px; }
        .csr-avatar { 
            width: 40px; height: 40px; border-radius: 12px; 
            background: linear-gradient(135deg, #6366f1, #a855f7);
            color: white; display: flex; align-items: center; justify-content: center; font-weight: bold;
        }

        .csr-header-actions { display: flex; gap: 12px; }
        .csr-btn-action {
            padding: 8px 16px;
            border-radius: 8px;
            font-size: 0.9rem;
            font-weight: 600;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            gap: 8px;
        }

        .csr-btn-close { background: #fff1f2; color: #e11d48; border: 1px solid #ffe4e6; }
        .csr-btn-close:hover { background: #ffe4e6; }

        /* Chat Display */
        #csr-chatMessages {
            flex: 1;
            padding: 32px;
            overflow-y: auto;
            display: flex;
            flex-direction: column;
            gap: 16px;
            background-color: #fcfcfd;
        }

        .csr-message-bubble {
            max-width: 65%;
            padding: 14px 18px;
            border-radius: 18px;
            font-size: 0.95rem;
            line-height: 1.5;
            position: relative;
            animation: csr-fadeIn 0.3s ease-out;
        }

        @keyframes csr-fadeIn { from { opacity: 0; transform: translateY(10px); } to { opacity: 1; transform: translateY(0); } }

        .csr-message-bubble.user {
            align-self: flex-start;
            background: #ffffff;
            color: var(--text-main);
            border: 1px solid #f1f5f9;
            border-bottom-left-radius: 4px;
            box-shadow: 0 4px 6px -1px rgba(0,0,0,0.02);
        }

        .csr-message-bubble.csr {
            align-self: flex-end;
            background: var(--primary);
            color: white;
            border-bottom-right-radius: 4px;
            box-shadow: 0 10px 15px -3px rgba(99, 102, 241, 0.2);
        }
        
        .csr-message-bubble.ai {
            align-self: flex-start;
            background: #f8fafc;
            color: var(--text-muted);
            border: 1px dashed #e2e8f0;
            font-style: italic;
            font-size: 0.85rem;
        }

        .csr-timestamp {
            font-size: 0.7rem;
            margin-top: 6px;
            opacity: 0.7;
            display: block;
        }

        .csr-attachments {
            display: grid;
            gap: 8px;
            margin-top: 8px;
        }

        .csr-attachment-image {
            max-width: 260px;
            max-height: 190px;
            border-radius: 12px;
            display: block;
            object-fit: cover;
            border: 1px solid rgba(0,0,0,0.08);
            background: rgba(255,255,255,0.08);
        }

        /* Input Area */
        .csr-input-area {
            padding: 24px 32px;
            background: white;
            border-top: 1px solid #f1f5f9;
        }

        .csr-input-wrapper {
            background: #f8fafc;
            border: 1px solid #e2e8f0;
            border-radius: 16px;
            padding: 8px 16px;
            display: flex;
            align-items: center;
            gap: 12px;
            transition: border-color 0.2s;
        }

        .csr-input-wrapper:focus-within { border-color: var(--primary); background: white; }

        #csr-replyInput {
            flex: 1;
            border: none;
            background: transparent;
            padding: 12px 0;
            font-family: inherit;
            font-size: 0.95rem;
            outline: none;
        }

        .csr-send-btn {
            background: var(--primary);
            color: white;
            border: none;
            width: 40px;
            height: 40px;
            border-radius: 12px;
            cursor: pointer;
            transition: all 0.2s;
            display: flex;
            align-items: center;
            justify-content: center;
        }

        .csr-send-btn:hover { background: var(--primary-dark); transform: scale(1.05); }
        .csr-send-btn:disabled { opacity: 0.5; cursor: not-allowed; }

        /* Empty State */
        .csr-empty-state {
            flex: 1;
            display: flex;
            flex-direction: column;
            align-items: center;
            justify-content: center;
            color: var(--text-muted);
            text-align: center;
            padding: 40px;
        }
        .csr-empty-state i { font-size: 4rem; margin-bottom: 20px; opacity: 0.2; }
        
        /* Modal */
        .csr-modal-overlay {
            position: fixed; top: 0; left: 0; width: 100%; height: 100%;
            background: rgba(0,0,0,0.4); backdrop-filter: blur(4px);
            display: none; align-items: center; justify-content: center; z-index: 1000;
        }
        .csr-modal {
            background: white; padding: 32px; border-radius: 20px; width: 400px;
            box-shadow: 0 25px 50px -12px rgba(0,0,0,0.25);
        }
        .csr-modal h3 { margin-bottom: 16px; }
        .csr-modal-btn { 
            width: 100%; padding: 12px; margin-top: 12px; border-radius: 10px; border: none; font-weight: 600; cursor: pointer;
        }
    `;

    // --- Logic ---
    let config = window.HostCSRConsoleConfig || { apiUrl: '' };
    let currentVisitorId = null;
    let lastMsgId = 0;

    function init() {
        const root = document.getElementById('csr-console-root');
        if (!root) {
            console.error('CSR Console root element (#csr-console-root) not found.');
            return;
        }

        // Inject Styles
        const styleSheet = document.createElement("style");
        styleSheet.innerText = styles;
        document.head.appendChild(styleSheet);

        // Render Base UI
        root.innerHTML = `
            <div class="csr-sidebar">
                <div class="csr-sidebar-header">
                    <h2>Support</h2>
                    <button class="csr-new-chat-btn" id="csr-show-new-chat" title="Start New Chat">
                        <i class="fas fa-plus"></i>
                    </button>
                </div>
                <div class="csr-session-list" id="csr-sessionList">
                    <div style="text-align: center; color: #aaa; margin-top: 40px;">Loading chats...</div>
                </div>
            </div>
            <div class="csr-main-console" id="csr-mainConsole">
                <div class="csr-empty-state">
                    <i class="fas fa-comments"></i>
                    <h3>Select a Conversation</h3>
                    <p>Choose a session from the sidebar to begin helping your customers.</p>
                </div>
            </div>
            <div class="csr-modal-overlay" id="csr-newChatModal">
                <div class="csr-modal">
                    <h3>Start New Chat</h3>
                    <p style="color: var(--text-muted); margin-bottom: 20px; font-size: 0.9rem;">Enter a Visitor ID to initiate a proactive session.</p>
                    <input type="text" id="csr-newVisitorId" placeholder="Unique Visitor ID" style="width: 100%; padding: 12px; border: 1px solid #e2e8f0; border-radius: 10px; margin-bottom: 16px;">
                    <button class="csr-modal-btn" style="background: var(--primary); color: white;" id="csr-create-chat-submit">Create Session</button>
                    <button class="csr-modal-btn" style="background: #f1f5f9; color: var(--text-main);" id="csr-hide-modal">Cancel</button>
                </div>
            </div>
        `;

        // Event Listeners
        document.getElementById('csr-show-new-chat').onclick = () => showModal('csr-newChatModal');
        document.getElementById('csr-hide-modal').onclick = () => hideModals();
        document.getElementById('csr-create-chat-submit').onclick = createNewChat;

        loadSessions();
        setInterval(loadSessions, 5000);
        setInterval(fetchMessages, 3000);
    }

    async function loadSessions() {
        try {
            const res = await fetch(`${config.apiUrl}/sessions`);
            const sessions = await res.json();
            const list = document.getElementById('csr-sessionList');
            if (!list) return;

            if (sessions.length === 0) {
                list.innerHTML = '<div style="text-align: center; color: #aaa; margin-top: 40px;">No active chats</div>';
                return;
            }

            list.innerHTML = '';
            sessions.forEach(s => {
                const card = document.createElement('div');
                card.className = `csr-session-card ${s.visitor_id === currentVisitorId ? 'active' : ''}`;
                card.onclick = () => selectSession(s.visitor_id);
                
                const time = s.last_updated ? new Date(s.last_updated).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'}) : '--:--';
                
                card.innerHTML = `
                    <span class="name">${s.visitor_id.substring(0, 15)}${s.visitor_id.length > 15 ? '...' : ''}</span>
                    <span class="last-msg">Active support session</span>
                    <span class="time">${time}</span>
                `;
                list.appendChild(card);
            });
        } catch (e) { console.error("Error loading sessions", e); }
    }

    async function selectSession(id) {
        currentVisitorId = id;
        lastMsgId = 0;
        
        const consoleEl = document.getElementById('csr-mainConsole');
        consoleEl.innerHTML = `
            <div class="csr-console-header">
                <div class="csr-user-info">
                    <div class="csr-avatar">${id.charAt(0).toUpperCase()}</div>
                    <div>
                        <div style="font-weight: 700; font-size: 1.1rem;">Customer ${id.substring(0,8)}</div>
                        <div style="font-size: 0.8rem; color: var(--text-muted); display: flex; align-items: center; gap: 4px;">
                            <span style="width: 8px; height: 8px; background: var(--success); border-radius: 50%;"></span> Online
                        </div>
                    </div>
                </div>
                <div class="csr-header-actions">
                    <button class="csr-btn-action csr-btn-close" id="csr-resolve-btn">
                        <i class="fas fa-check-circle"></i> Resolve & Sync
                    </button>
                </div>
            </div>
            <div id="csr-chatMessages"></div>
            <div class="csr-input-area">
                <div class="csr-input-wrapper">
                    <input type="text" id="csr-replyInput" placeholder="Message Customer...">
                    <button class="csr-send-btn" id="csr-sendBtn">
                        <i class="fas fa-paper-plane"></i>
                    </button>
                </div>
            </div>
        `;
        
        document.getElementById('csr-resolve-btn').onclick = closeChat;
        document.getElementById('csr-sendBtn').onclick = sendReply;
        document.getElementById('csr-replyInput').onkeypress = (e) => { if (e.key === 'Enter') sendReply(); };

        loadSessions();
        fetchMessages(true);
    }

    async function fetchMessages(clear = false) {
        if (!currentVisitorId) return;
        try {
            const res = await fetch(`${config.apiUrl}/messages/${currentVisitorId}`);
            const messages = await res.json();
            const box = document.getElementById('csr-chatMessages');
            if (!box) return;

            if (clear) box.innerHTML = '';
            
            messages.forEach(m => {
                if (m.id > lastMsgId) {
                    const bubble = document.createElement('div');
                    bubble.className = `csr-message-bubble ${m.sender}`;
                    bubble.innerHTML = `
                        ${escapeHtml(m.content || '')}
                        ${renderImageAttachments(m)}
                        <span class="csr-timestamp">${new Date(m.timestamp).toLocaleTimeString([], {hour: '2-digit', minute:'2-digit'})}</span>
                    `;
                    box.appendChild(bubble);
                    lastMsgId = m.id;
                    box.scrollTop = box.scrollHeight;
                }
            });
        } catch (e) { console.error("Error fetching messages", e); }
    }

    async function sendReply() {
        const input = document.getElementById('csr-replyInput');
        const btn = document.getElementById('csr-sendBtn');
        const content = input.value.trim();
        if (!content || !currentVisitorId) return;

        input.disabled = true;
        btn.disabled = true;

        try {
            await fetch(`${config.apiUrl}/reply`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ visitor_id: currentVisitorId, content: content })
            });
            input.value = '';
            fetchMessages();
        } catch (e) { alert("Failed to send message."); }
        
        input.disabled = false;
        btn.disabled = false;
        input.focus();
    }

    async function closeChat() {
        if (!confirm("Are you sure you want to resolve this chat and transfer the transcript back to the AI?")) return;
        
        try {
            const res = await fetch(`${config.apiUrl}/close_and_transfer`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ visitor_id: currentVisitorId })
            });
            const result = await res.json();
            if (result.success) {
                currentVisitorId = null;
                document.getElementById('csr-mainConsole').innerHTML = `
                    <div class="csr-empty-state">
                        <i class="fas fa-check-circle" style="color: var(--success); opacity: 0.8;"></i>
                        <h3>Chat Resolved</h3>
                        <p>Conversation has been synced with the central AI system.</p>
                    </div>
                `;
                loadSessions();
            } else {
                alert("Error syncing chat: " + result.message);
            }
        } catch (e) { console.error("Closure error", e); alert("Failed to connect to central server."); }
    }

    function escapeHtml(value) {
        const div = document.createElement('div');
        div.textContent = value || '';
        return div.innerHTML;
    }

    function getImageSources(message) {
        const images = Array.isArray(message.images)
            ? message.images
            : (Array.isArray(message.attachments) ? message.attachments : []);
        const imageUrls = Array.isArray(message.image_urls) ? message.image_urls : [];
        const sources = [];

        images.forEach(image => {
            if (!image) return;
            const src = image.image_url || image.imageUrl || image.url || image.data_url;
            if (src) {
                sources.push({ src, name: image.name || 'Uploaded image' });
            }
        });

        imageUrls.forEach(url => {
            if (url) sources.push({ src: url, name: 'Uploaded image' });
        });

        if (message.image_url) sources.push({ src: message.image_url, name: 'Uploaded image' });
        if (message.imageUrl) sources.push({ src: message.imageUrl, name: 'Uploaded image' });

        const seen = new Set();
        return sources.filter(image => {
            if (!image.src || seen.has(image.src)) return false;
            const src = String(image.src);
            if (!src.startsWith('http') && !src.startsWith('data:image/')) return false;
            seen.add(image.src);
            return true;
        });
    }

    function renderImageAttachments(message) {
        const images = getImageSources(message);
        if (!images.length) return '';

        return `
            <div class="csr-attachments">
                ${images.map(image => `
                    <a href="${escapeHtml(image.src)}" target="_blank" rel="noopener noreferrer">
                        <img class="csr-attachment-image" src="${escapeHtml(image.src)}" alt="${escapeHtml(image.name)}">
                    </a>
                `).join('')}
            </div>
        `;
    }

    async function createNewChat() {
        const idInput = document.getElementById('csr-newVisitorId');
        const id = idInput.value.trim();
        if (!id) return;
        try {
            await fetch(`${config.apiUrl}/init`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ visitor_id: id })
            });
            idInput.value = '';
            hideModals();
            selectSession(id);
        } catch (e) { alert("Failed to create session."); }
    }

    function showModal(id) { document.getElementById(id).style.display = 'flex'; }
    function hideModals() { document.querySelectorAll('.csr-modal-overlay').forEach(m => m.style.display = 'none'); }

    // Start
    if (document.readyState === 'complete') {
        init();
    } else {
        window.addEventListener('load', init);
    }
})();
