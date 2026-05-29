# Crypto Crash Bot

Bot de Telegram que monitorea el mercado de criptomonedas en tiempo real usando la API de CoinGecko. Detecta caídas bruscas (dumps), envía alertas por niveles de gravedad y proporciona reportes detallados del portafolio.

## Funcionalidades

### Alerta de Dumps Multi-Nivel
- **⚠️ Dump Alert**: caída >= 15%
- **🚨 Severe Dump**: caída >= 25%
- **🩸 Extreme Crash**: caída >= 40%

### Ventanas de Tiempo
- 5 minutos (con snapshots locales)
- 15 minutos (con snapshots locales)
- 1 hora (con snapshots locales)
- 24 horas (CoinGecko)

### Anti-Spam
- Cooldown configurable por moneda/ventana/severidad
- No repite alertas de la misma severidad dentro del cooldown
- Sí alerta si la severidad aumenta

### Filtros
- Volumen mínimo 24h configurable (default: $500k)
- Market cap mínimo configurable (default: $1M)
- Exclusión automática de stablecoins (USDT, USDC, DAI, FDUSD, TUSD, USDE, BUSD)
- Exclusión de wrapped assets (WBTC, WETH)
- Lista de exclusión manual configurable

### Watchlist Personal
- Vigila tokens específicos aunque no estén en top 500
- Umbrales de alerta personalizados por token

### Reporte de Portafolio
- Resumen profesional cada hora
- Valor total, P&L no realizado, cambio 24h
- Posición individual por token: precio, cantidad, valor, entry, P&L, asignación
- Mejor y peor token del portafolio

### Comandos Telegram

| Comando | Descripción |
|---|---|
| `/portafolio` | Resumen completo del portafolio |
| `/precio <coin>` | Precio, cambios 1h/24h/7d, volumen, market cap |
| `/search <texto>` | Buscar token por nombre o símbolo |
| `/top` | Top 10 criptos por market cap |
| `/gainers` | Top 10 ganadores 24h |
| `/losers` | Top 10 perdedores 24h |
| `/alerts` | Últimas alertas registradas |
| `/watchlist` | Tokens bajo vigilancia |
| `/addwatch <coin_id>` | Agregar token a watchlist |
| `/removewatch <coin_id>` | Remover de watchlist |
| `/setentry <SIMB> <precio>` | Definir precio de entrada |
| `/setqty <SIMB> <cant>` | Definir cantidad del token |
| `/settotal <usd>` | Definir total invertido |
| `/setthreshold <coin_id> <window> <percent>` | Umbral personalizado |
| `/status` | Estado del bot |
| `/help` | Todos los comandos |

## Requisitos

- Python 3.8+
- `requests`

## Instalación Local

```bash
git clone https://github.com/tuusuario/crypto-bot.git
cd crypto-bot
python3 -m venv venv
source venv/bin/activate  # Linux/Mac
# .\venv\Scripts\activate  # Windows
pip install -r requirements.txt
```

Configurar variables de entorno:

```bash
export TELEGRAM_BOT_TOKEN="tu_token"
export TELEGRAM_CHAT_ID="tu_chat_id"
# Opcionales:
export MONITOR_INTERVAL_SECONDS=300
export PORTFOLIO_REPORT_INTERVAL_SECONDS=3600
export MIN_VOLUME_USD=500000
export MIN_MARKET_CAP_USD=1000000
export DEFAULT_ALERT_COOLDOWN_MINUTES=60
```

Ejecutar:

```bash
python -m crypto_crash_bot.main
```

## Despliegue en Railway

1. Sube el código a GitHub
2. Ve a [Railway](https://railway.app) → New Project → Deploy from GitHub
3. Selecciona el repositorio
4. Añade las variables de entorno en Settings → Variables:

| Variable | Valor |
|---|---|
| `TELEGRAM_BOT_TOKEN` | Token de tu bot |
| `TELEGRAM_CHAT_ID` | Tu chat ID |
| `MONITOR_INTERVAL_SECONDS` | `300` |
| `PORTFOLIO_REPORT_INTERVAL_SECONDS` | `3600` |
| `MIN_VOLUME_USD` | `500000` |
| `MIN_MARKET_CAP_USD` | `1000000` |
| `DEFAULT_ALERT_COOLDOWN_MINUTES` | `60` |

5. Railway iniciará el bot automáticamente

## Variables de Entorno

| Variable | Default | Descripción |
|---|---|---|
| `TELEGRAM_BOT_TOKEN` | — | Token del bot de Telegram |
| `TELEGRAM_CHAT_ID` | — | ID del chat donde enviar mensajes |
| `MONITOR_INTERVAL_SECONDS` | `300` | Intervalo de monitoreo (5 min) |
| `PORTFOLIO_REPORT_INTERVAL_SECONDS` | `3600` | Intervalo reporte portafolio (1h) |
| `MIN_VOLUME_USD` | `500000` | Volumen mínimo para alertas |
| `MIN_MARKET_CAP_USD` | `1000000` | Market cap mínimo |
| `DEFAULT_ALERT_COOLDOWN_MINUTES` | `60` | Cooldown entre alertas |

## Arquitectura

```
crypto_crash_bot/
  __init__.py
  main.py           - Punto de entrada
  config.py         - Configuración y variables de entorno
  coingecko_client.py - API Client CoinGecko con retry y rate limiting
  telegram_bot.py   - Comandos, callbacks y envío de mensajes
  portfolio.py      - Cálculos de portafolio y P&L
  alerts.py         - Detección de dumps, severidad, cooldown y filtros
  storage.py        - I/O seguro de archivos JSON
  formatter.py      - Formato HTML para mensajes Telegram
  scheduler.py      - Ciclo principal y temporizadores
  logger.py         - Logging estructurado
data/
  portfolio_data.json   - Precios de entrada, cantidades, total invertido
  alerted_coins.json    - Historial de alertas y cooldowns
  price_snapshots.json  - Snapshots locales para cambios 5m/15m/1h
  settings.json         - Watchlist y configuraciones
  history.log           - Registro de actividad
requirements.txt
Procfile
README.md
```

## Límites de API CoinGecko

- **Plan gratuito**: 10-30 llamadas/minuto
- **Uso actual**: ~3 llamadas por ciclo de monitoreo
- **Estimado mensual**: ~26,000 llamadas (ciclo cada 5 min)
- **Recomendación**: Intervalo mínimo de 60 segundos entre ciclos

## Ejemplos de Mensajes

### Alerta de Dump
```
🚨 SEVERE DUMP DETECTED

Token: TAO — Bittensor
Price: $256.27
Trigger: -26.40% in 15m

Changes:
  5m: 🔴 -8.20%
  15m: 🔴 -26.40%
  1h: 🔴 -31.10%
  24h: 🔴 -34.50%

Market:
  Volume 24h: $18.4M
  Market Cap: $3.1B
  Rank: #42

🔗 View on CoinGecko
🕐 Detected: 2026-05-29 15:31 UTC

⚠️ Not financial advice.
```

### Reporte de Portafolio
```
📊 Portfolio Snapshot
🕒 2026-05-29 15:31 UTC

🔴 24h Change: -0.27%

───────────────────────────────────

🟢 TAO — Bittensor
   Price: $256.27 | 24h: +0.10%
   Allocation: 35.72%

🔴 ARIA — Aria.AI
   Price: $0.0372 | 24h: -1.20%
   Allocation: 28.92%
...
```

## Disclaimer

Este bot es una herramienta informativa. No constituye consejo financiero. Verifica siempre la liquidez, noticias y spreads de exchange antes de tomar decisiones de trading.

## Licencia

MIT
