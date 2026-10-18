// Draws every <canvas data-chart="<id>"> with the vendored Chart.js, in the
// design system's colours. The canvas names a json_script element holding
// {"title": ..., "columns": [[type, label], ...], "data": [[x, y1, y2...], ...]}
// (the shape the stats helpers already build). Options on the canvas:
//   data-chart-type   "doughnut" or "bar" (default "bar")
//   data-columns      a JSON list of [type, label] when the data has none
//   data-stacked      stack the series
//   data-horizontal   bars run left to right
//   data-legend       show the legend for a bar chart
//   data-label-every  label every nth category on the x axis
(function () {
  "use strict";

  var PALETTE = [
    "--accent",
    "--night-700",
    "--ok-500",
    "--warn-500",
    "--night-400",
    "--stop-500",
    "--beam-600",
    "--night-200",
  ];

  function token(style, name, fallback) {
    return style.getPropertyValue(name).trim() || fallback;
  }

  function draw(canvas) {
    var source = document.getElementById(canvas.dataset.chart);
    if (!source) {
      return;
    }
    var chart = JSON.parse(source.textContent);
    var columns = chart.columns || JSON.parse(canvas.dataset.columns || "[]");
    var rows = chart.data || chart;
    var style = getComputedStyle(document.documentElement);
    var colours = PALETTE.map(function (name) {
      return token(style, name, "#706c62");
    });
    var text = token(style, "--text-muted", "#524f47");
    var grid = token(style, "--border-subtle", "#e2dfd5");
    var card = token(style, "--surface-card", "#ffffff");
    var type = canvas.dataset.chartType || "bar";
    var doughnut = type === "doughnut";
    var labels = rows.map(function (row) {
      return String(row[0]);
    });
    var datasets = columns.slice(1).map(function (column, index) {
      return {
        label: column[1],
        data: rows.map(function (row) {
          return Number(row[index + 1]);
        }),
        backgroundColor: doughnut ? colours.slice(0, rows.length) : colours[index % colours.length],
        borderColor: doughnut ? card : colours[index % colours.length],
        borderWidth: doughnut ? 2 : 0,
        borderRadius: doughnut ? 0 : 4,
      };
    });

    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily;
    Chart.defaults.color = text;
    var options = {
      responsive: true,
      maintainAspectRatio: false,
      plugins: {
        title: { display: Boolean(chart.title), text: chart.title, color: text },
        legend: {
          display: doughnut || "legend" in canvas.dataset,
          position: doughnut ? "right" : "top",
        },
      },
    };
    if (!doughnut) {
      var stacked = "stacked" in canvas.dataset;
      var every = Number(canvas.dataset.labelEvery || 1);
      var category = {
        stacked: stacked,
        grid: { display: false },
        ticks: {
          autoSkip: every === 1,
          maxRotation: 0,
          callback: function (value, index) {
            return index % every === 0 ? this.getLabelForValue(value) : "";
          },
        },
      };
      var value = {
        stacked: stacked,
        beginAtZero: true,
        grid: { color: grid },
        ticks: { precision: 0 },
        title: { display: columns.length === 2, text: columns.length === 2 ? columns[1][1] : "" },
      };
      options.indexAxis = "horizontal" in canvas.dataset ? "y" : "x";
      options.scales = options.indexAxis === "y" ? { x: value, y: category } : { x: category, y: value };
    }
    new Chart(canvas, { type: type, data: { labels: labels, datasets: datasets }, options: options });
  }

  // "load", not DOMContentLoaded: the colours and the font come from the
  // stylesheets, which are linked after this script.
  window.addEventListener("load", function () {
    document.querySelectorAll("canvas[data-chart]").forEach(draw);
  });
})();
