module.exports = {
  apps: [
    {
      name: "chat-widget-manager",
      cwd: "/home/ubuntu/chat-widget-manager",
      script: ".venv/bin/python",
      args: "app.py",
      interpreter: "none",
      autorestart: true,
      max_restarts: 20,
      min_uptime: "5s",
      env: {
        FLASK_DEBUG: "0",
        PORT: "5004",
        DATABASE_URL: "sqlite:////home/ubuntu/chat-widget-manager/instance/widget_manager.db",
        CSR_DATABASE_URL: "sqlite:////home/ubuntu/chat-widget-manager/instance/widget_manager_csr.db",
        CHATBOT_VERIFY_BASE_URL: "https://beta-tj1.frontlineticketing.com",
        CHATBOT_SERVICE_SECRET: "682be0af23d4bdf216504fa2778398475c75214670adf8dabac4a3bd4158fceb",
        WIDGET_TOKEN_AUTH_ENABLED: "true",
        DEFAULT_WEBHOOK_URL: "https://aidevv.3utilities.com/webhook/65350c02-df88-49d9-983d-8aaf691d7ad1/chat",
        DEFAULT_N8N_INSTANCE_ID: "0d120a8625980c6399396b35943a7a9e81902ca30dc8b7df12b06110cad66c23",
      },
    },
  ],
};
