# Kraken BTC Range Chart

A local, real-time range-bar chart for the Kraken `PF_XBTUSD` multi-collateral perpetual. Built with public market data only: no API key, account access, or order execution.

## Features

- Live range bars built from individual Kraken trades.
- 30 bars visible by default, with historical warm-up for indicators.
- Weis Waves with cumulative volume numbers.
- Volume and RVOL spikes at 3.5x.
- Relative Delta, Delta %, and positive/negative delta spikes at ±3.5x.
- Stochastic RSI (14/14/3/3) with 20/80 levels.
- Sound alerts on bar close by default, with distinct sounds per signal.
- Live or bar-close alert modes.
- Crosshair and a stable, detailed candle inspector.
- Configurable range size: 25, 50, 100, or 250 USD.
- Local SQLite persistence, reconnects, and trade deduplication.
- TradingView-inspired dark theme.

The server listens only on `127.0.0.1`. Sound alerts continue while the browser tab is in the background.

## Requirements

- Linux with Python 3.10 or newer.
- `python3-venv` and `curl`.
- `paplay` for sound alerts, usually provided by `pulseaudio-utils`.
- `xdg-open` is optional; it opens the chart automatically.

On Debian/Ubuntu, the system packages can be installed with:

```bash
sudo apt install python3-venv curl pulseaudio-utils xdg-utils
```

## Install

```bash
git clone https://github.com/agurrey/kraken-range-chart.git
cd kraken-range-chart
chmod +x install.sh start.sh stop.sh
./install.sh
```

The installer creates an isolated `.venv` and installs the exact Python dependencies from `requirements.txt`. No global Python packages or sudo access are used by the installer.

## Run

```bash
./start.sh
```

Open [http://localhost:8790](http://localhost:8790) if it does not open automatically.

To start without opening a browser:

```bash
NO_OPEN=1 ./start.sh
```

To stop the chart:

```bash
./stop.sh
```

To inspect application and alert logs:

```bash
tail -f data/app.log
```

The background process survives closing the terminal. It must be started again after a reboot.

## How it works

Kraken trades are fetched from the public Futures API and streamed over its public WebSocket. Each trade updates the current range bar. With a 50 USD range, a bar closes when price reaches either its open +50 USD or its open -50 USD, and the next bar opens at that boundary.

The application stores trades locally in `data/range_chart.db`. On reconnect it backfills recent trades, removes duplicates by trade UID, rebuilds the bars, and only then resumes alerts. Historical signals are never replayed as sound alerts.

Indicators per bar:

```text
RVOL           = Volume / SMA20(Volume)
Delta          = Aggressive buy volume - Aggressive sell volume
Relative Delta = Delta / SMA20(|Delta|)
Delta %        = Delta / Volume × 100
```

Weis Waves use ATR(14), and SRSI uses RSI 14, Stochastic 14, K 3, D 3. Values update while a range bar is developing; alerts fire on bar close unless live mode is selected.

## Data and privacy

- No credentials or API keys are required or requested.
- No orders can be placed by this application.
- The chart only connects to Kraken public endpoints and localhost.
- `data/`, `.venv/`, logs, and Python caches are excluded from Git.
- Kraken volume and delta are specific to `PF_XBTUSD`; they may differ from other exchanges or aggregated charts.

## Third-party software

The UI uses Apache ECharts 5.6.0, bundled locally under `vendor/`. Its Apache License 2.0 is included at `vendor/LICENSE.echarts`.

## License

MIT. See [LICENSE](LICENSE).
