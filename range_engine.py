import math


def new_bar(bar_id, price, time_ms):
    return {
        "id": bar_id,
        "open_time": time_ms,
        "time": time_ms,
        "open": price,
        "high": price,
        "low": price,
        "close": price,
        "volume": 0.0,
        "buy_volume": 0.0,
        "sell_volume": 0.0,
        "closed": False,
    }


class RangeBars:
    def __init__(self, size):
        self.size = float(size)
        self.closed_bars = []
        self.current = None
        self.next_id = 0

    def add_trade(self, trade):
        price = float(trade["price"])
        quantity = float(trade["size"])
        time_ms = int(trade["time_ms"])
        side = trade["side"]
        if self.current is None:
            self.current = new_bar(self.next_id, price, time_ms)
            self.next_id += 1

        self.current["volume"] += quantity
        self.current["buy_volume" if side == "buy" else "sell_volume"] += quantity
        closed = []

        while price >= self.current["open"] + self.size or price <= self.current["open"] - self.size:
            rising = price >= self.current["open"] + self.size
            boundary = self.current["open"] + self.size if rising else self.current["open"] - self.size
            self.current["close"] = boundary
            self.current["high"] = max(self.current["high"], boundary)
            self.current["low"] = min(self.current["low"], boundary)
            self.current["time"] = time_ms
            self.current["closed"] = True
            closed.append(self.current)
            self.closed_bars.append(self.current)
            self.current = new_bar(self.next_id, boundary, time_ms)
            self.next_id += 1

        self.current["high"] = max(self.current["high"], price)
        self.current["low"] = min(self.current["low"], price)
        self.current["close"] = price
        self.current["time"] = time_ms
        self.closed_bars = self.closed_bars[-500:]
        return closed

    def bars(self):
        return self.closed_bars + ([self.current] if self.current is not None else [])


def rma(values, period):
    output = [None] * len(values)
    valid_indices = [index for index, value in enumerate(values) if value is not None]
    if len(valid_indices) < period:
        return output
    seed_indices = valid_indices[:period]
    seed_end = seed_indices[-1]
    average = sum(values[index] for index in seed_indices) / period
    output[seed_end] = average
    for index in range(seed_end + 1, len(values)):
        if values[index] is None:
            continue
        average = (average * (period - 1) + values[index]) / period
        output[index] = average
    return output


def sma(values, period):
    output = [None] * len(values)
    for index in range(period - 1, len(values)):
        window = values[index - period + 1:index + 1]
        if all(value is not None for value in window):
            output[index] = sum(window) / period
    return output


def rsi(closes, period=14):
    gains = [None]
    losses = [None]
    for previous, current in zip(closes, closes[1:]):
        change = current - previous
        gains.append(max(change, 0.0))
        losses.append(max(-change, 0.0))
    average_gains = rma(gains, period)
    average_losses = rma(losses, period)
    output = [None] * len(closes)
    for index, (gain, loss) in enumerate(zip(average_gains, average_losses)):
        if gain is None or loss is None:
            continue
        if gain == 0 and loss == 0:
            output[index] = 50.0
        elif loss == 0:
            output[index] = 100.0
        else:
            output[index] = 100 - 100 / (1 + gain / loss)
    return output


def atr(bars, period=14):
    ranges = []
    previous_close = None
    for bar in bars:
        if previous_close is None:
            ranges.append(bar["high"] - bar["low"])
        else:
            ranges.append(max(
                bar["high"] - bar["low"],
                abs(bar["high"] - previous_close),
                abs(bar["low"] - previous_close),
            ))
        previous_close = bar["close"]
    return rma(ranges, period)


def srsi_series(bars):
    rsi_values = rsi([bar["close"] for bar in bars])
    raw_stoch = [None] * len(bars)
    for index in range(13, len(bars)):
        window = rsi_values[index - 13:index + 1]
        if not all(value is not None for value in window):
            continue
        highest = max(window)
        lowest = min(window)
        price_range = highest - lowest
        raw_stoch[index] = 100 * (rsi_values[index] - lowest) / price_range if price_range > 0 else 50.0
    return sma(raw_stoch, 3), sma(sma(raw_stoch, 3), 3)


def compute_indicators(bars):
    volumes = [bar["volume"] for bar in bars]
    deltas = [bar["buy_volume"] - bar["sell_volume"] for bar in bars]
    absolute_deltas = [abs(value) for value in deltas]
    average_volumes = sma(volumes, 20)
    average_deltas = sma(absolute_deltas, 20)
    k_values, d_values = srsi_series(bars)
    output = []
    for index, bar in enumerate(bars):
        average_volume = average_volumes[index]
        average_delta = average_deltas[index]
        volume = bar["volume"]
        delta = deltas[index]
        output.append({
            "rvol": volume / average_volume if average_volume else None,
            "delta": delta,
            "relative_delta": delta / average_delta if average_delta else None,
            "delta_pct": 100 * delta / volume if volume else 0.0,
            "k": k_values[index],
            "d": d_values[index],
        })
    return output


def compute_weis(bars):
    atr_values = atr(bars)
    committed = {"close": 0.0, "direction": None, "volume": 0.0, "time": None, "high": None, "low": None}
    working = None
    last_bar = None
    completed = []
    for bar, atr_value in zip(bars, atr_values):
        if bar["id"] != last_bar:
            if working is not None:
                committed = working
            last_bar = bar["id"]
        close = bar["close"]
        previous_close = committed["close"]
        if atr_value is None or not math.isfinite(atr_value):
            current_close = previous_close
        elif close > previous_close + atr_value:
            current_close = close
        elif close < previous_close - atr_value:
            current_close = close
        else:
            current_close = previous_close
        previous_direction = committed["direction"]
        if current_close > previous_close:
            direction = 1
        elif current_close < previous_close:
            direction = -1
        else:
            direction = previous_direction
        direction_changed = previous_direction is not None and direction != previous_direction
        cumulative_volume = bar["volume"] if direction_changed else committed["volume"] + bar["volume"]
        working = {
            "close": current_close,
            "direction": direction,
            "volume": cumulative_volume,
            "time": bar["time"],
            "bar_id": bar["id"],
            "high": bar["high"],
            "low": bar["low"],
        }
        if direction_changed and committed["time"] is not None:
            completed.append({
                "key": f"{committed['time']}:{len(completed)}",
                "time": committed["time"],
                "bar_id": committed["bar_id"],
                "direction": "up" if committed["direction"] == 1 else "down",
                "volume": committed["volume"],
                "price": committed["high"] if committed["direction"] == 1 else committed["low"],
            })
    current = None
    if working and working["direction"] in (-1, 1):
        current = {
            "time": bars[-1]["time"],
            "bar_id": bars[-1]["id"],
            "direction": "up" if working["direction"] == 1 else "down",
            "volume": working["volume"],
            "price": bars[-1]["high"] if working["direction"] == 1 else bars[-1]["low"],
        }
    return {"completed": completed, "current": current}
