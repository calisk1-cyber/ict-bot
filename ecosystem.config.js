module.exports = {
  apps: [
    {
      name: "bot1-backtester",
      script: "bot1_backtester.py",
      interpreter: "python3",
      cwd: "/root/bot",
      env_file: "/root/bot/.env",
      out_file: "/root/bot/logs/bot1-out.log",
      error_file: "/root/bot/logs/bot1-err.log",
      autorestart: true,
      restart_delay: 15000,
      max_restarts: 20,
      watch: false
    },
    {
      name: "bot2-hunter",
      script: "bot2_hunter.py",
      interpreter: "python3",
      cwd: "/root/bot",
      env_file: "/root/bot/.env",
      out_file: "/root/bot/logs/bot2-out.log",
      error_file: "/root/bot/logs/bot2-err.log",
      autorestart: true,
      restart_delay: 15000,
      max_restarts: 20,
      watch: false
    },
    {
      name: "bot3-evaluator",
      script: "bot3_evaluator.py",
      interpreter: "python3",
      cwd: "/root/bot",
      env_file: "/root/bot/.env",
      out_file: "/root/bot/logs/bot3-out.log",
      error_file: "/root/bot/logs/bot3-err.log",
      autorestart: true,
      restart_delay: 15000,
      max_restarts: 20,
      watch: false
    },
    {
      name: "bot4-trader",
      script: "bot4_trader.py",
      interpreter: "python3",
      cwd: "/root/bot",
      env_file: "/root/bot/.env",
      out_file: "/root/bot/logs/bot4-out.log",
      error_file: "/root/bot/logs/bot4-err.log",
      autorestart: true,
      restart_delay: 15000,
      max_restarts: 20,
      watch: false
    },
    {
      name: "bot-api",
      script: "app.py",
      interpreter: "python3",
      cwd: "/root/bot",
      env_file: "/root/bot/.env",
      out_file: "/root/bot/logs/api-out.log",
      error_file: "/root/bot/logs/api-err.log",
      autorestart: true,
      restart_delay: 15000,
      max_restarts: 20,
      watch: false
    },
    {
      name: "node-proxy",
      script: "server.js",
      interpreter: "node",
      cwd: "/root/bot",
      env_file: "/root/bot/.env",
      out_file: "/root/bot/logs/proxy-out.log",
      error_file: "/root/bot/logs/proxy-err.log",
      autorestart: true,
      restart_delay: 5000,
      max_restarts: 20,
      watch: false,
      env: {
        PORT: 3000
      }
    }
  ]
};
