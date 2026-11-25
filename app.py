#!/usr/bin/env python3
import asyncio
import fcntl
import json
import sqlite3
import subprocess
import time
import urllib.parse
import urllib.request
from datetime import datetime, timezone
from pathlib import Path

import websockets
from aiohttp import WSMsgType, web

from range_engine import RangeBars, compute_indicators, compute_weis

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data"
DATABASE = DATA / "range_chart.db"
LOCK_FILE = DATA / "app.lock"
SYMBOL = "PF_XBTUSD"
HISTORY_URL = "https://futures.kraken.com/derivatives/api/v3/history"
KRAKEN_WS = "wss://futures.kraken.com/ws/v1"
HOST = "127.0.0.1"
PORT = 8790
THRESHOLD = 3.5
SOUNDS = {
    "rvol": ROOT / "sounds" / "rvol.wav",
    "srsi_long": ROOT / "sounds" / "srsi.wav",
    "srsi_short": ROOT / "sounds" / "srsi.wav",
    "wave": ROOT / "sounds" / "weis.wav",
    "delta_positive": ROOT / "sounds" / "delta-positive.wav",
    "delta_negative": ROOT / "sounds" / "delta-negative.wav",
}


def log(message):
    print(f"{datetime.now().strftime('%H:%M:%S')} · {message}", flush=True)


def parse_time(value):
    return int(datetime.fromisoformat(value.replace("Z", "+00:00")).timestamp() * 1000)


def normalize_history(trade):
    return {
        "uid": trade["uid"],
        "time_ms": parse_time(trade["time"]),
        "sequence_id": str(trade.get("sequence_id", "")),
        "price": float(trade["price"]),
        "size": float(trade["size"]),
        "side": trade["side"],
    }


def normalize_live(trade):
    return {
        "uid": trade["uid"],
        "time_ms": int(trade["time"]),
        "sequence_id": str(trade.get("seq", "")),
        "price": float(trade["price"]),
        "size": float(trade["qty"]),
        "side": trade["side"],
    }


class TradeStore:
    def __init__(self, path):
        self.connection = sqlite3.connect(path)
        self.connection.execute("""
            CREATE TABLE IF NOT EXISTS trades (
                uid TEXT PRIMARY KEY,
                time_ms INTEGER NOT NULL,
                sequence_id TEXT,
                price REAL NOT NULL,
                size REAL NOT NULL,
                side TEXT NOT NULL
            )
        """)
        self.connection.execute("CREATE INDEX IF NOT EXISTS trades_time ON trades(time_ms, sequence_id)")
        self.connection.commit()

    def add(self, trades):
        added = 0
        for trade in trades:
            cursor = self.connection.execute(
                "INSERT OR IGNORE INTO trades VALUES (:uid, :time_ms, :sequence_id, :price, :size, :side)",
                trade,
            )
            added += cursor.rowcount
        self.connection.commit()
        return added

    def all(self):
        rows = self.connection.execute(
            "SELECT uid, time_ms, sequence_id, price, size, side FROM trades ORDER BY time_ms, sequence_id, uid"
        ).fetchall()
        keys = ("uid", "time_ms", "sequence_id", "price", "size", "side")
        return [dict(zip(keys, row)) for row in rows]


def fetch_history_page(last_time=None):
    params = {"symbol": SYMBOL}
    if last_time:
        params["lastTime"] = last_time
    request = urllib.request.Request(
        HISTORY_URL + "?" + urllib.parse.urlencode(params),
        headers={"User-Agent": "kraken-range-chart/1.0"},
    )
    with urllib.request.urlopen(request, timeout=20) as response:
        data = json.load(response)
    if data.get("result") != "success":
        raise RuntimeError("Kraken no devolvio historial")
    return data.get("history", [])


def build_bars(trades, range_size):
    engine = RangeBars(range_size)
    for trade in trades:
        engine.add_trade(trade)
    return engine


async def load_history(store, range_size):
    existing = store.all()
    existing_engine = build_bars(existing, range_size)
    pages_needed = len(existing_engine.closed_bars) < 110
    pages = 0
    last_time = None
    while pages < (250 if pages_needed else 1):
        raw = await asyncio.to_thread(fetch_history_page, last_time)
        if not raw:
            break
        store.add([normalize_history(trade) for trade in raw])
        pages += 1
        if not pages_needed:
            break
        if pages % 3 == 0:
            engine = build_bars(store.all(), range_size)
            if len(engine.closed_bars) >= 110:
                break
        oldest = min(parse_time(trade["time"]) for trade in raw)
        last_time = datetime.fromtimestamp((oldest - 1000) / 1000, timezone.utc).isoformat()
        if len(raw) < 100:
            break
        await asyncio.sleep(0.05)
    log(f"Historial: {pages} paginas, {len(store.all())} trades")


def indicator_states(bars, indicators, index):
    if index < 0 or index >= len(bars):
        return {}
    current = indicators[index]
    k = current["k"]
    d = current["d"]
    long_signal = False
    short_signal = False
    if index > 0 and k is not None and d is not None:
        previous = indicators[index - 1]
        previous_k = previous["k"]
        previous_d = previous["d"]
        if previous_k is not None and previous_d is not None:
            long_signal = k > d and previous_k <= previous_d and min(k, d) <= 20
            short_signal = k < d and previous_k >= previous_d and max(k, d) >= 80
    relative_delta = current["relative_delta"]
    rvol = current["rvol"]
    return {
        "rvol": rvol is not None and rvol >= THRESHOLD,
        "delta_positive": relative_delta is not None and relative_delta >= THRESHOLD,
        "delta_negative": relative_delta is not None and relative_delta <= -THRESHOLD,
        "srsi_long": long_signal,
        "srsi_short": short_signal,
    }


class AlertManager:
    def __init__(self):
        self.mode = "closed"
        self.fired = set()
        self.previous = {}
        self.seen_waves = set()
        self.last_closed = None

    def reset(self, bars, indicators, waves):
        self.fired.clear()
        self.previous = indicator_states(bars, indicators, len(bars) - 1)
        self.seen_waves = {wave["key"] for wave in waves["completed"]}
        self.last_closed = bars[-2]["id"] if len(bars) > 1 and bars[-1]["closed"] is False else None

    def evaluate(self, bars, indicators, waves, closed_events):
        if not bars:
            return []
        if self.mode == "closed":
            if not closed_events:
                return []
            target = closed_events[-1]
            index = next((i for i, bar in enumerate(bars) if bar["id"] == target["id"]), -1)
            if index < 0 or target["id"] == self.last_closed:
                return []
            self.last_closed = target["id"]
            states = indicator_states(bars, indicators, index)
            events = [(name, active, index) for name, active in states.items() if active]
        else:
            index = len(bars) - 1
            states = indicator_states(bars, indicators, index)
            bar_id = bars[index]["id"]
            events = []
            for name, active in states.items():
                key = (bar_id, name)
                if active and not self.previous.get(name, False) and key not in self.fired:
                    self.fired.add(key)
                    events.append((name, True, index))
            self.previous = states

        alerts = []
        for name, _, event_index in events:
            alerts.append(self.make_alert(name, bars[event_index], indicators[event_index]))
        for wave in waves["completed"]:
            if wave["time"] <= bars[index]["time"] and wave["key"] not in self.seen_waves:
                self.seen_waves.add(wave["key"])
                alerts.append(("wave", f"WEIS {wave['direction'].upper()} · volumen {wave['volume']:.2f} BTC"))
        return alerts

    @staticmethod
    def make_alert(name, bar, values):
        if name == "rvol":
            return name, f"RVOL {values['rvol']:.2f}x · volumen {bar['volume']:.2f} BTC"
        if name == "delta_positive":
            return name, f"DELTA +{values['relative_delta']:.2f}x · {values['delta']:.3f} BTC"
        if name == "delta_negative":
            return name, f"DELTA {values['relative_delta']:.2f}x · {values['delta']:.3f} BTC"
        direction = "LONG" if name == "srsi_long" else "SHORT"
        return name, f"SRSI {direction} · K {values['k']:.1f} / D {values['d']:.1f}"


def play_sound(name):
    path = SOUNDS[name]
    if path.is_file():
        subprocess.Popen(["paplay", str(path)], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)


class ChartHub:
    def __init__(self):
        self.store = TradeStore(DATABASE)
        self.range_size = 50.0
        self.engine = RangeBars(self.range_size)
        self.alerts = AlertManager()
        self.clients = set()
        self.status = "CONECTANDO"
        self.broadcast_scheduled = False
        self.lock = asyncio.Lock()

    def snapshot(self):
        all_bars = self.engine.bars()
        indicators = compute_indicators(all_bars) if all_bars else []
        waves = compute_weis(all_bars) if all_bars else {"completed": [], "current": None}
        bars = []
        for bar, values in zip(all_bars[-120:], indicators[-120:]):
            item = dict(bar)
            item.update(values)
            bars.append(item)
        return {
            "type": "snapshot",
            "symbol": "BTCUSD Multi Collateral Perpetual · Kraken",
            "range_size": self.range_size,
            "alert_mode": self.alerts.mode,
            "threshold": THRESHOLD,
            "status": self.status,
            "bars": bars,
            "waves": {
                "completed": waves["completed"][-80:],
                "current": waves["current"],
            },
        }

    def rebuild(self):
        self.engine = build_bars(self.store.all(), self.range_size)
        snapshot = self.snapshot()
        bars = self.engine.bars()
        indicators = compute_indicators(bars) if bars else []
        waves = compute_weis(bars) if bars else {"completed": [], "current": None}
        self.alerts.reset(bars, indicators, waves)
        return snapshot

    async def broadcast(self, immediate=False):
        if self.broadcast_scheduled and not immediate:
            return
        self.broadcast_scheduled = True
        if not immediate:
            await asyncio.sleep(0.08)
        if self.clients:
            message = json.dumps(self.snapshot(), allow_nan=False)
            await asyncio.gather(*(client.send_str(message) for client in list(self.clients)), return_exceptions=True)
        self.broadcast_scheduled = False

    async def process_live(self, trade):
        if not self.store.add([trade]):
            return
        closed = self.engine.add_trade(trade)
        bars = self.engine.bars()
        indicators = compute_indicators(bars)
        waves = compute_weis(bars)
        for name, message in self.alerts.evaluate(bars, indicators, waves, closed):
            log(message)
            play_sound(name)
        await self.broadcast()

    async def collector(self):
        while True:
            try:
                async with websockets.connect(
                    KRAKEN_WS,
                    open_timeout=15,
                    close_timeout=3,
                    ping_interval=20,
                    ping_timeout=20,
                ) as ws:
                    await ws.send(json.dumps({
                        "event": "subscribe",
                        "feed": "trade",
                        "product_ids": [SYMBOL],
                    }))
                    while True:
                        message = json.loads(await ws.recv())
                        if message.get("event") == "subscribed":
                            break
                        if message.get("event") == "error":
                            raise RuntimeError(message.get("message", "Error de suscripcion"))
                    self.status = "SINCRONIZANDO"
                    await self.broadcast(True)
                    await load_history(self.store, self.range_size)
                    self.rebuild()
                    self.status = "EN VIVO"
                    log(f"EN VIVO · {len(self.engine.closed_bars)} range bars · rango {self.range_size:g} USD")
                    await self.broadcast(True)
                    async for raw in ws:
                        message = json.loads(raw)
                        if message.get("feed") == "trade" and "event" not in message:
                            await self.process_live(normalize_live(message))
            except asyncio.CancelledError:
                raise
            except Exception as error:
                self.status = "RECONECTANDO"
                log(f"Conexion interrumpida: {error}. Reintentando...")
                await self.broadcast(True)
                await asyncio.sleep(3)

    async def websocket(self, request):
        client = web.WebSocketResponse(heartbeat=20)
        await client.prepare(request)
        self.clients.add(client)
        await client.send_str(json.dumps(self.snapshot(), allow_nan=False))
        try:
            async for message in client:
                if message.type != WSMsgType.TEXT:
                    continue
                data = json.loads(message.data)
                if data.get("type") == "config":
                    async with self.lock:
                        mode = data.get("alert_mode")
                        if mode in ("live", "closed"):
                            self.alerts.mode = mode
                        new_range = float(data.get("range_size", self.range_size))
                        if 1 <= new_range <= 5000 and new_range != self.range_size:
                            self.range_size = new_range
                            self.rebuild()
                        await self.broadcast(True)
        finally:
            self.clients.discard(client)
        return client


async def main():
    DATA.mkdir(exist_ok=True)
    lock_handle = LOCK_FILE.open("w")
    try:
        fcntl.flock(lock_handle, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        log("El grafico ya esta en ejecucion")
        return

    hub = ChartHub()
    app = web.Application()
    app.router.add_get("/", lambda request: web.FileResponse(ROOT / "index.html"))
    app.router.add_get("/app.js", lambda request: web.FileResponse(ROOT / "app.js"))
    app.router.add_get("/styles.css", lambda request: web.FileResponse(ROOT / "styles.css"))
    app.router.add_get("/vendor/echarts.min.js", lambda request: web.FileResponse(ROOT / "vendor" / "echarts.min.js"))
    app.router.add_get("/ws", hub.websocket)
    runner = web.AppRunner(app)
    await runner.setup()
    site = web.TCPSite(runner, HOST, PORT)
    await site.start()
    log(f"Grafico disponible en http://{HOST}:{PORT}")
    try:
        await hub.collector()
    finally:
        await runner.cleanup()
        hub.store.connection.close()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
