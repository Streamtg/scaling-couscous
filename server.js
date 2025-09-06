const { createProxyMiddleware } = require('http-proxy-middleware');
const express = require('express');
const app  = express();
const port = process.env.PORT || 10000;

// proxy todo el tráfico a zrok local
app.use('/', createProxyMiddleware({
  target: 'http://127.0.0.1:9191', // puerto por defecto de zrok access
  changeOrigin: true,
  ws: true,
  logLevel: 'info'
}));

app.listen(port, () => console.log(`Bridge listening on ${port}`));
