module.exports = {
  apps: [
    // bot1, bot2, bot3 ve bot5 devre dışı bırakıldı (Kaynak tasarrufu için)
    {
      name: "bot4-trader",
      script: "bot4_trader.py",
      interpreter: "python3",
      cwd: "./",
      env_file: ".env",
      out_file: "/root/logs/bot4-out.log",
      error_file: "/root/logs/bot4-err.log",
      autorestart: true,
      restart_delay: 15000,
      max_memory_restart: "400M",
      watch: false
    },
    {
      name: "bot-api",
      script: "app.py",
      interpreter: "python3",
      cwd: "./",
      env_file: ".env",
      out_file: "/root/logs/api-out.log",
      error_file: "/root/logs/api-err.log",
      autorestart: true,
      restart_delay: 15000,
      max_memory_restart: "350M",
      watch: false
    },
    {
      name: "node-proxy",
      script: "server.js",
      interpreter: "node",
      cwd: "./",
      env_file: ".env",
      out_file: "/root/logs/proxy-out.log",
      error_file: "/root/logs/proxy-err.log",
      autorestart: true,
      restart_delay: 5000,
      max_memory_restart: "100M",
      watch: false,
      env: {
        PORT: 3000
      }
    }
  ]
};
