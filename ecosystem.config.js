module.exports = {
  apps: [
    {
      name: "csr-widget-app",
      script: "/home/ubuntu/QSTP_New/venv/bin/python",
      args: "app.py",
      cwd: "/home/ubuntu/csr_widget_app",
      interpreter: "none",
      env: {
        FLASK_APP: "app.py",
        FLASK_ENV: "production",
        VIRTUAL_ENV: "/home/ubuntu/QSTP_New/venv",
        PATH: "/home/ubuntu/QSTP_New/venv/bin:" + process.env.PATH,
      },
      watch: false,
      autorestart: true,
      max_restarts: 10,
      restart_delay: 3000,
    },
  ],
};
