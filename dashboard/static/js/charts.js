/* Prometheus ECharts theme + helpers */

const PROMETHEUS_THEME = {
  color: ['#58a6ff', '#3fb950', '#f85149', '#d29922', '#db6d28', '#8b949e', '#a371f7'],
  backgroundColor: '#0d1117',
  textStyle: { color: '#c9d1d9', fontFamily: '-apple-system, BlinkMacSystemFont, "Segoe UI", Helvetica, Arial, sans-serif' },
  title: { textStyle: { color: '#c9d1d9', fontSize: 13, fontWeight: 600 }, subtextStyle: { color: '#8b949e' } },
  legend: {
    textStyle: { color: '#8b949e', fontSize: 11 },
    inactiveColor: '#4d5158',
  },
  grid: { containLabel: true },
  categoryAxis: {
    axisLine: { lineStyle: { color: '#30363d' } },
    axisLabel: { color: '#8b949e', fontSize: 11 },
    splitLine: { lineStyle: { color: '#21262d' } },
    axisTick: { show: false },
  },
  valueAxis: {
    axisLine: { show: false },
    axisLabel: { color: '#8b949e', fontSize: 11 },
    splitLine: { lineStyle: { color: '#21262d', type: 'dashed' } },
  },
  tooltip: {
    backgroundColor: '#1c2128',
    borderColor: '#30363d',
    borderWidth: 1,
    textStyle: { color: '#c9d1d9', fontSize: 12 },
    extraCssText: 'border-radius:6px;box-shadow:0 4px 12px rgba(0,0,0,0.4)',
  },
  line: {
    smooth: false,
    symbol: 'circle',
    symbolSize: 4,
    lineStyle: { width: 2 },
  },
  bar: {
    itemStyle: { borderRadius: [3, 3, 0, 0] },
  },
};

// Register the theme with ECharts
if (typeof echarts !== 'undefined') {
  echarts.registerTheme('prometheus', PROMETHEUS_THEME);
}

/**
 * Initialize an ECharts instance on a container element.
 * Registers a ResizeObserver so the chart auto-resizes.
 *
 * @param {string} containerId - DOM element ID
 * @param {object} [opts] - optional echarts init options
 * @returns {echarts.ECharts} chart instance
 */
function initChart(containerId, opts = {}) {
  const el = document.getElementById(containerId);
  if (!el) {
    console.warn(`initChart: element #${containerId} not found`);
    return null;
  }
  const chart = echarts.init(el, 'prometheus', { renderer: 'canvas', ...opts });

  // Auto-resize
  if (typeof ResizeObserver !== 'undefined') {
    const ro = new ResizeObserver(() => chart.resize());
    ro.observe(el);
  } else {
    window.addEventListener('resize', () => chart.resize());
  }

  return chart;
}

/**
 * Format american odds for display.
 * @param {number} price - american odds value
 * @returns {string}
 */
function fmtOdds(price) {
  if (price == null) return '--';
  return price > 0 ? `+${price}` : `${price}`;
}

/**
 * Format a percentage float 0.0-1.0 for display.
 * @param {number} val
 * @param {number} [decimals=1]
 * @returns {string}
 */
function fmtPct(val, decimals = 1) {
  if (val == null) return '--';
  return `${(val * 100).toFixed(decimals)}%`;
}

/**
 * Format ISO datetime string to short local date.
 * @param {string} iso
 * @returns {string}
 */
function fmtDate(iso) {
  if (!iso) return '--';
  const d = new Date(iso);
  return isNaN(d) ? iso.slice(0, 10) : d.toLocaleDateString('en-US', { month: 'short', day: 'numeric' });
}

/**
 * Color value by sign (bull=green, bear=red, neutral=muted).
 * @param {number} val
 * @returns {string} CSS color variable reference
 */
function signColor(val) {
  if (val > 0.15) return 'var(--green)';
  if (val < -0.15) return 'var(--red)';
  return 'var(--text-muted)';
}
