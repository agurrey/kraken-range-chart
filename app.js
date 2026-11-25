const chart = echarts.init(document.getElementById('chart'), null, { renderer: 'canvas' });
const statusNode = document.getElementById('status');
const connectionNode = document.getElementById('connection');
const rangeNode = document.getElementById('range');
const alertModeNode = document.getElementById('alert-mode');
let snapshot = { bars: [], waves: { completed: [], current: null } };
let displayedSnapshot = snapshot;
let inspectedBarId = null;
let inspectorX = 0;
let inspectorY = 0;
const inspector = document.createElement('div');
inspector.id = 'inspector';
inspector.className = 'inspector';
document.body.appendChild(inspector);
let socket;
let followLatest = true;
let currentRange = 50;

const white = '#f3f4f6';
const red = '#ef4444';
const gray = '#6b7280';
const blue = '#3b82f6';
const yellow = '#facc15';

function number(value, decimals = 2) {
  return value == null || !Number.isFinite(value) ? '—' : value.toFixed(decimals);
}

function timeLabel(milliseconds) {
  return new Date(milliseconds).toLocaleTimeString('es-ES', { hour: '2-digit', minute: '2-digit' });
}

function barStart(count) {
  return Math.max(0, 100 - (30 / Math.max(1, count)) * 100);
}

function waveSeries(direction, developing = false) {
  const waves = developing
    ? (snapshot.waves.current && snapshot.waves.current.direction === direction ? [snapshot.waves.current] : [])
    : snapshot.waves.completed.filter(wave => wave.direction === direction);
  const visibleIds = new Set(snapshot.bars.map(bar => bar.id));
  return {
    name: developing ? 'Weis actual' : 'Weis completada',
    type: 'scatter',
    xAxisIndex: 0,
    yAxisIndex: 0,
    symbol: 'circle',
    symbolSize: 1,
    itemStyle: { color: 'rgba(0,0,0,0)' },
    data: waves.filter(wave => visibleIds.has(wave.bar_id)).map(wave => ({
      value: [String(wave.bar_id), wave.price, wave.volume],
      label: { color: direction === 'up' ? white : red }
    })),
    label: {
      show: true,
      position: direction === 'up' ? 'top' : 'bottom',
      distance: 8,
      fontSize: developing ? 11 : 12,
      fontWeight: developing ? 400 : 600,
      formatter: point => `${Math.trunc(point.value[2])}${developing ? '_' : ''}`
    },
    silent: true,
    z: 5
  };
}

function tooltipFormatter(bar) {
  if (!bar) return '';
  return [
    `<strong>${timeLabel(bar.time)} · Range ${displayedSnapshot.range_size} USD</strong>`,
    `O ${number(bar.open, 1)} · H ${number(bar.high, 1)} · L ${number(bar.low, 1)} · C ${number(bar.close, 1)}`,
    `Volumen ${number(bar.volume, 3)} BTC · RVOL ${number(bar.rvol)}x`,
    `Delta ${number(bar.delta, 3)} BTC · Rel. Delta ${number(bar.relative_delta)}x`,
    `Delta % ${number(bar.delta_pct, 1)}% · Compra ${number(bar.buy_volume, 3)} · Venta ${number(bar.sell_volume, 3)}`,
    `SRSI K ${number(bar.k, 1)} · D ${number(bar.d, 1)}`
  ].join('<br>');
}

function positionInspector() {
  const width = inspector.offsetWidth || 340;
  const height = inspector.offsetHeight || 100;
  inspector.style.left = `${Math.max(8, Math.min(inspectorX + 16, window.innerWidth - width - 8))}px`;
  inspector.style.top = `${Math.max(8, Math.min(inspectorY + 16, window.innerHeight - height - 8))}px`;
}

function showInspector(barId, clientX, clientY) {
  const bar = displayedSnapshot.bars.find(item => item.id === barId);
  if (!bar) return hideInspector();
  inspectedBarId = barId;
  inspectorX = clientX;
  inspectorY = clientY;
  inspector.innerHTML = tooltipFormatter(bar);
  inspector.classList.add('visible');
  positionInspector();
}

function hideInspector() {
  inspectedBarId = null;
  inspector.classList.remove('visible');
}

function render() {
  displayedSnapshot = snapshot;
  const bars = displayedSnapshot.bars;
  const ids = bars.map(bar => String(bar.id));
  const start = barStart(bars.length);
  const zoom = followLatest ? { start, end: 100 } : {};
  chart.setOption({
    animation: false,
    backgroundColor: '#000',
    textStyle: { fontFamily: '-apple-system, BlinkMacSystemFont, Segoe UI, sans-serif' },
    tooltip: {
      show: false,
      trigger: 'axis',
      axisPointer: { type: 'cross', lineStyle: { color: '#4b5563' }, label: { backgroundColor: '#1f2937' } }
    },
    axisPointer: { link: [{ xAxisIndex: 'all' }] },
    graphic: [
      { type: 'text', left: 65, top: 24, style: { text: 'WWVN ATR 14 · Close', fill: gray, fontSize: 11 } },
      { type: 'text', left: 65, top: '53%', style: { text: 'VOLUME · RVOL', fill: gray, fontSize: 10 } },
      { type: 'text', left: 65, top: '67%', style: { text: 'RELATIVE DELTA · ±3.5x', fill: gray, fontSize: 10 } },
      { type: 'text', left: 65, top: '84%', style: { text: 'SRSI 14 14 3 3', fill: gray, fontSize: 10 } }
    ],
    grid: [
      { left: 62, right: 62, top: 18, height: '47%' },
      { left: 62, right: 62, top: '53%', height: '10%' },
      { left: 62, right: 62, top: '67%', height: '12%' },
      { left: 62, right: 62, top: '84%', height: '11%' }
    ],
    xAxis: [0, 1, 2, 3].map(index => ({
      type: 'category',
      gridIndex: index,
      data: ids,
      boundaryGap: true,
      axisLine: { lineStyle: { color: '#1f2937' } },
      axisTick: { show: false },
      axisLabel: index === 3 ? {
        color: gray,
        fontSize: 10,
        formatter: value => {
          const bar = bars.find(item => String(item.id) === value);
          return bar ? timeLabel(bar.time) : '';
        }
      } : { show: false },
      splitLine: { show: false }
    })),
    yAxis: [
      { scale: true, gridIndex: 0, position: 'right', axisLabel: { color: gray, fontSize: 10 }, splitLine: { lineStyle: { color: '#111827' } } },
      { scale: true, gridIndex: 1, position: 'right', axisLabel: { color: gray, fontSize: 9 }, splitLine: { show: false } },
      { scale: true, gridIndex: 2, position: 'right', axisLabel: { color: gray, fontSize: 9 }, splitLine: { lineStyle: { color: '#111827' } } },
      { min: 0, max: 100, gridIndex: 3, position: 'right', axisLabel: { color: gray, fontSize: 9 }, splitLine: { show: false } }
    ],
    dataZoom: [
      { type: 'inside', xAxisIndex: [0, 1, 2, 3], filterMode: 'none', ...zoom },
      { type: 'slider', xAxisIndex: [0, 1, 2, 3], filterMode: 'none', bottom: 0, height: 12, borderColor: '#1f2937', backgroundColor: '#000', fillerColor: '#1f293755', handleStyle: { color: gray }, textStyle: { color: gray }, ...zoom }
    ],
    series: [
      {
        name: 'BTC', type: 'candlestick', xAxisIndex: 0, yAxisIndex: 0,
        data: bars.map(bar => [bar.open, bar.close, bar.low, bar.high]),
        itemStyle: { color: '#000', color0: '#000', borderColor: white, borderColor0: red, borderWidth: 1.4 },
        barWidth: '65%', z: 3
      },
      waveSeries('up'), waveSeries('down'), waveSeries('up', true), waveSeries('down', true),
      {
        name: 'Volumen', type: 'bar', xAxisIndex: 1, yAxisIndex: 1,
        data: bars.map(bar => ({
          value: bar.volume,
          itemStyle: {
            color: bar.rvol >= 3.5 ? '#d1d5db' : gray,
            borderColor: bar.rvol >= 3.5 ? white : 'transparent',
            borderWidth: bar.rvol >= 3.5 ? 1 : 0
          }
        })),
        barWidth: '65%'
      },
      {
        name: 'Relative Delta', type: 'bar', xAxisIndex: 2, yAxisIndex: 2,
        data: bars.map(bar => ({
          value: bar.relative_delta,
          itemStyle: {
            color: bar.delta >= 0 ? white : red,
            borderColor: Math.abs(bar.relative_delta || 0) >= 3.5 ? yellow : 'transparent',
            borderWidth: Math.abs(bar.relative_delta || 0) >= 3.5 ? 1 : 0
          }
        })),
        barWidth: '65%',
        markLine: {
          silent: true, symbol: 'none', label: { show: false },
          lineStyle: { color: '#4b5563', type: 'dashed' },
          data: [{ yAxis: 3.5 }, { yAxis: -3.5 }]
        }
      },
      { name: 'K', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: bars.map(bar => bar.k), showSymbol: false, lineStyle: { color: blue, width: 1.4 }, itemStyle: { color: blue } },
      {
        name: 'D', type: 'line', xAxisIndex: 3, yAxisIndex: 3, data: bars.map(bar => bar.d), showSymbol: false, lineStyle: { color: yellow, width: 1.2 }, itemStyle: { color: yellow },
        markLine: {
          silent: true, symbol: 'none', label: { show: false },
          lineStyle: { color: '#4b5563', type: 'dashed' },
          data: [{ yAxis: 20 }, { yAxis: 80 }]
        }
      }
    ]
  }, { notMerge: true, lazyUpdate: false });

  const latest = bars[bars.length - 1];
  if (latest) {
    const change = latest.close - latest.open;
    document.getElementById('ohlc').textContent = `O ${number(latest.open, 1)}  H ${number(latest.high, 1)}  L ${number(latest.low, 1)}  C ${number(latest.close, 1)}  ${change >= 0 ? '+' : ''}${number(change, 1)}`;
    connectionNode.textContent = `${bars.length} barras cargadas · ${latest.closed ? 'cerrada' : 'en formación'}`;
  }
  if (inspectedBarId !== null) {
    const inspectedBar = bars.find(bar => bar.id === inspectedBarId);
    if (inspectedBar) inspector.innerHTML = tooltipFormatter(inspectedBar);
    else hideInspector();
  }
}

function updateStatus() {
  statusNode.textContent = snapshot.status || 'CONECTANDO';
  statusNode.className = `status ${snapshot.status === 'EN VIVO' ? 'live' : snapshot.status === 'SINCRONIZANDO' ? 'sync' : ''}`;
}

function connect() {
  socket = new WebSocket(`ws://${location.host}/ws`);
  socket.onmessage = event => {
    const previousRange = currentRange;
    snapshot = JSON.parse(event.data);
    currentRange = snapshot.range_size;
    if (previousRange !== currentRange) followLatest = true;
    if (![...rangeNode.options].some(option => Number(option.value) === currentRange)) {
      rangeNode.add(new Option(`${currentRange} USD`, currentRange));
    }
    rangeNode.value = currentRange;
    alertModeNode.value = snapshot.alert_mode;
    updateStatus();
    render();
  };
  socket.onclose = () => {
    statusNode.textContent = 'RECONECTANDO';
    statusNode.className = 'status';
    setTimeout(connect, 2000);
  };
}

function sendConfig() {
  if (socket && socket.readyState === WebSocket.OPEN) {
    socket.send(JSON.stringify({ type: 'config', range_size: Number(rangeNode.value), alert_mode: alertModeNode.value }));
  }
}

rangeNode.addEventListener('change', () => { followLatest = true; sendConfig(); });
alertModeNode.addEventListener('change', sendConfig);
document.getElementById('reset-zoom').addEventListener('click', () => { followLatest = true; render(); });
chart.on('datazoom', () => { followLatest = false; });
const chartNode = document.getElementById('chart');
const crosshairX = document.createElement('div');
const crosshairY = document.createElement('div');
crosshairX.className = 'crosshair crosshair-x';
crosshairY.className = 'crosshair crosshair-y';
chartNode.append(crosshairX, crosshairY);
chart.getZr().on('mousemove', event => {
  crosshairX.style.left = `${event.offsetX}px`;
  crosshairY.style.top = `${event.offsetY}px`;
  crosshairX.classList.add('visible');
  crosshairY.classList.add('visible');
  const point = [event.offsetX, event.offsetY];
  const grid = chart.getModel().getComponent('grid', 0).coordinateSystem;
  if (!grid.containPoint(point)) return hideInspector();
  const converted = chart.convertFromPixel({ gridIndex: 0 }, point);
  const index = Math.round(Number(converted[0]));
  const bar = displayedSnapshot.bars[index];
  if (bar) showInspector(bar.id, event.event.clientX, event.event.clientY);
  else hideInspector();
});
chartNode.addEventListener('mouseleave', () => {
  hideInspector();
  crosshairX.classList.remove('visible');
  crosshairY.classList.remove('visible');
});
window.addEventListener('resize', () => chart.resize());
connect();
