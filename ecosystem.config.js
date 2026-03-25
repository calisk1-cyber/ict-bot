module.exports = {
  apps: [
    {
      name: "trading-bot",
      script: "app.py",
      interpreter: "python3",
      autorestart: true,
      watch: false,
      max_memory_restart: "1G",
      env: {
        NODE_ENV: "production",
      }
    },
    {
      name: "web-server",
      script: "server.js",
      autorestart: true,
      watch: false,
      max_memory_restart: "500M",
      env: {
        PORT: 3000,
        NODE_ENV: "production",
      }
    }
  ]
};
