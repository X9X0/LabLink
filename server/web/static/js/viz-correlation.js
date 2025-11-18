// LabLink Advanced Visualizations - Multi-Instrument Correlation

(function() {
    'use strict';

    let overlayChart, scatterChart, crossCorrChart;
    let dataset1 = null;
    let dataset2 = null;

    // Initialize correlation visualization
    function init() {
        setupEventListeners();
        console.log('Correlation visualization initialized');
    }

    // Set up event listeners
    function setupEventListeners() {
        const calculateBtn = document.getElementById('calculateCorrelation');
        if (calculateBtn) {
            calculateBtn.addEventListener('click', calculateCorrelation);
        }
    }

    // Calculate correlation between two datasets
    async function calculateCorrelation() {
        // Get primary dataset
        dataset1 = window.getCurrentWaveformData();
        if (!dataset1) {
            showAlert('Please load primary waveform data first', 'warning', 'alert');
            return;
        }

        // Get second equipment and channel
        const equipment2Id = document.getElementById('corrEquipment2').value;
        const channel2 = parseInt(document.getElementById('corrChannel2').value);

        if (!equipment2Id) {
            showAlert('Please select second equipment', 'warning', 'alert');
            return;
        }

        const calculateBtn = document.getElementById('calculateCorrelation');
        setButtonLoading(calculateBtn, true);

        try {
            // Capture second waveform
            const response = await api.captureWaveform(equipment2Id, channel2);

            if (response && response.voltage_data && response.time_data) {
                dataset2 = {
                    voltage: response.voltage_data,
                    time: response.time_data,
                    sampleRate: response.sample_rate || (1.0 / (response.time_data[1] - response.time_data[0]))
                };

                // Generate all correlation visualizations
                generateOverlayChart();
                generateScatterPlot();
                generateCrossCorrelation();
                updateCorrelationStats();

                showAlert('Correlation analysis complete', 'success', 'alert');
            } else {
                showAlert('Failed to load second waveform', 'error', 'alert');
            }
        } catch (error) {
            console.error('Failed to calculate correlation:', error);
            showAlert('Failed to calculate correlation: ' + error.message, 'error', 'alert');
        } finally {
            setButtonLoading(calculateBtn, false);
        }
    }

    // Generate time-aligned overlay chart
    function generateOverlayChart() {
        const ctx = document.getElementById('correlationOverlay');
        if (!ctx || !dataset1 || !dataset2) return;

        // Destroy existing chart
        if (overlayChart) {
            overlayChart.destroy();
        }

        // Align datasets by time (interpolate if needed)
        const alignedData = alignDatasets(dataset1, dataset2);

        overlayChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: alignedData.time,
                datasets: [
                    {
                        label: 'Channel 1',
                        data: alignedData.voltage1,
                        borderColor: '#3b82f6',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0,
                        yAxisID: 'y1'
                    },
                    {
                        label: 'Channel 2',
                        data: alignedData.voltage2,
                        borderColor: '#10b981',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0,
                        yAxisID: 'y2'
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                animation: { duration: 500 },
                interaction: {
                    mode: 'index',
                    intersect: false
                },
                plugins: {
                    title: {
                        display: false
                    },
                    legend: {
                        display: true,
                        labels: { color: getTextColor() }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return context.dataset.label + ': ' + context.parsed.y.toFixed(4) + 'V';
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Time (s)',
                            color: getTextColor()
                        },
                        ticks: {
                            color: getTextColor(),
                            maxTicksLimit: 10
                        },
                        grid: { color: getGridColor() }
                    },
                    y1: {
                        type: 'linear',
                        position: 'left',
                        title: {
                            display: true,
                            text: 'Ch1 Voltage (V)',
                            color: '#3b82f6'
                        },
                        ticks: { color: '#3b82f6' },
                        grid: { color: getGridColor() }
                    },
                    y2: {
                        type: 'linear',
                        position: 'right',
                        title: {
                            display: true,
                            text: 'Ch2 Voltage (V)',
                            color: '#10b981'
                        },
                        ticks: { color: '#10b981' },
                        grid: { display: false }
                    }
                }
            }
        });
    }

    // Generate scatter plot
    function generateScatterPlot() {
        const ctx = document.getElementById('correlationScatter');
        if (!ctx || !dataset1 || !dataset2) return;

        // Destroy existing chart
        if (scatterChart) {
            scatterChart.destroy();
        }

        // Align datasets and create scatter points
        const alignedData = alignDatasets(dataset1, dataset2);
        const scatterData = alignedData.voltage1.map((v1, i) => ({
            x: v1,
            y: alignedData.voltage2[i]
        }));

        // Calculate regression line
        const regression = calculateLinearRegression(alignedData.voltage1, alignedData.voltage2);
        const regressionLine = [
            { x: Math.min(...alignedData.voltage1), y: regression.slope * Math.min(...alignedData.voltage1) + regression.intercept },
            { x: Math.max(...alignedData.voltage1), y: regression.slope * Math.max(...alignedData.voltage1) + regression.intercept }
        ];

        scatterChart = new Chart(ctx, {
            type: 'scatter',
            data: {
                datasets: [
                    {
                        label: 'Data Points',
                        data: scatterData,
                        backgroundColor: 'rgba(59, 130, 246, 0.5)',
                        borderColor: '#3b82f6',
                        borderWidth: 1,
                        pointRadius: 3
                    },
                    {
                        label: 'Regression Line',
                        data: regressionLine,
                        type: 'line',
                        borderColor: '#ef4444',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0,
                        borderDash: [5, 5]
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                animation: { duration: 500 },
                plugins: {
                    title: {
                        display: false
                    },
                    legend: {
                        display: true,
                        labels: { color: getTextColor() }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                if (context.dataset.label === 'Data Points') {
                                    return `Ch1: ${context.parsed.x.toFixed(4)}V, Ch2: ${context.parsed.y.toFixed(4)}V`;
                                }
                                return context.dataset.label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Channel 1 Voltage (V)',
                            color: getTextColor()
                        },
                        ticks: { color: getTextColor() },
                        grid: { color: getGridColor() }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Channel 2 Voltage (V)',
                            color: getTextColor()
                        },
                        ticks: { color: getTextColor() },
                        grid: { color: getGridColor() }
                    }
                }
            }
        });
    }

    // Generate cross-correlation plot
    function generateCrossCorrelation() {
        const ctx = document.getElementById('correlationCross');
        if (!ctx || !dataset1 || !dataset2) return;

        // Destroy existing chart
        if (crossCorrChart) {
            crossCorrChart.destroy();
        }

        // Calculate cross-correlation
        const alignedData = alignDatasets(dataset1, dataset2);
        const crossCorr = calculateCrossCorrelation(alignedData.voltage1, alignedData.voltage2);

        // Create lag array (in samples)
        const maxLag = Math.floor(crossCorr.length / 2);
        const lags = Array.from({ length: crossCorr.length }, (_, i) => i - maxLag);

        crossCorrChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: lags,
                datasets: [
                    {
                        label: 'Cross-Correlation',
                        data: crossCorr,
                        borderColor: '#8b5cf6',
                        backgroundColor: 'rgba(139, 92, 246, 0.1)',
                        borderWidth: 2,
                        fill: true,
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                animation: { duration: 500 },
                plugins: {
                    title: {
                        display: false
                    },
                    legend: {
                        display: true,
                        labels: { color: getTextColor() }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                return `Correlation: ${context.parsed.y.toFixed(4)} at lag ${context.label}`;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Lag (samples)',
                            color: getTextColor()
                        },
                        ticks: {
                            color: getTextColor(),
                            maxTicksLimit: 15
                        },
                        grid: { color: getGridColor() }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Correlation',
                            color: getTextColor()
                        },
                        ticks: { color: getTextColor() },
                        grid: { color: getGridColor() }
                    }
                }
            }
        });
    }

    // Align two datasets by time (simple interpolation)
    function alignDatasets(data1, data2) {
        // Find common time range
        const minTime = Math.max(Math.min(...data1.time), Math.min(...data2.time));
        const maxTime = Math.min(Math.max(...data1.time), Math.max(...data2.time));

        // Sample at regular intervals
        const numPoints = Math.min(1000, Math.min(data1.voltage.length, data2.voltage.length));
        const timeStep = (maxTime - minTime) / (numPoints - 1);

        const alignedTime = [];
        const alignedVoltage1 = [];
        const alignedVoltage2 = [];

        for (let i = 0; i < numPoints; i++) {
            const t = minTime + i * timeStep;
            alignedTime.push(t.toFixed(6));

            // Linear interpolation for both datasets
            alignedVoltage1.push(interpolate(data1.time, data1.voltage, t));
            alignedVoltage2.push(interpolate(data2.time, data2.voltage, t));
        }

        return {
            time: alignedTime,
            voltage1: alignedVoltage1,
            voltage2: alignedVoltage2
        };
    }

    // Linear interpolation
    function interpolate(xArray, yArray, x) {
        // Find surrounding points
        let i = 0;
        while (i < xArray.length - 1 && xArray[i] < x) {
            i++;
        }

        if (i === 0) return yArray[0];
        if (i === xArray.length) return yArray[yArray.length - 1];

        // Linear interpolation
        const x0 = xArray[i - 1];
        const x1 = xArray[i];
        const y0 = yArray[i - 1];
        const y1 = yArray[i];

        return y0 + (y1 - y0) * (x - x0) / (x1 - x0);
    }

    // Calculate linear regression
    function calculateLinearRegression(x, y) {
        const n = x.length;
        const sumX = x.reduce((a, b) => a + b, 0);
        const sumY = y.reduce((a, b) => a + b, 0);
        const sumXY = x.reduce((sum, xi, i) => sum + xi * y[i], 0);
        const sumX2 = x.reduce((sum, xi) => sum + xi * xi, 0);
        const sumY2 = y.reduce((sum, yi) => sum + yi * yi, 0);

        const slope = (n * sumXY - sumX * sumY) / (n * sumX2 - sumX * sumX);
        const intercept = (sumY - slope * sumX) / n;

        // Calculate R²
        const meanY = sumY / n;
        const ssTotal = y.reduce((sum, yi) => sum + Math.pow(yi - meanY, 2), 0);
        const ssResidual = y.reduce((sum, yi, i) => {
            const predicted = slope * x[i] + intercept;
            return sum + Math.pow(yi - predicted, 2);
        }, 0);
        const rSquared = 1 - (ssResidual / ssTotal);

        // Calculate correlation coefficient
        const r = Math.sign(slope) * Math.sqrt(rSquared);

        return { slope, intercept, r, rSquared };
    }

    // Calculate cross-correlation
    function calculateCrossCorrelation(signal1, signal2) {
        const n = Math.min(signal1.length, signal2.length);
        const maxLag = Math.min(100, Math.floor(n / 4)); // Limit lag range for performance

        // Normalize signals
        const mean1 = signal1.reduce((a, b) => a + b, 0) / signal1.length;
        const mean2 = signal2.reduce((a, b) => a + b, 0) / signal2.length;
        const norm1 = signal1.map(v => v - mean1);
        const norm2 = signal2.map(v => v - mean2);

        const std1 = Math.sqrt(norm1.reduce((sum, v) => sum + v * v, 0) / norm1.length);
        const std2 = Math.sqrt(norm2.reduce((sum, v) => sum + v * v, 0) / norm2.length);

        const crossCorr = [];

        for (let lag = -maxLag; lag <= maxLag; lag++) {
            let sum = 0;
            let count = 0;

            for (let i = 0; i < n; i++) {
                const j = i + lag;
                if (j >= 0 && j < n) {
                    sum += norm1[i] * norm2[j];
                    count++;
                }
            }

            const corr = count > 0 ? sum / (count * std1 * std2) : 0;
            crossCorr.push(corr);
        }

        return crossCorr;
    }

    // Update correlation statistics
    function updateCorrelationStats() {
        if (!dataset1 || !dataset2) return;

        const alignedData = alignDatasets(dataset1, dataset2);
        const regression = calculateLinearRegression(alignedData.voltage1, alignedData.voltage2);

        // Find peak correlation and time lag
        const crossCorr = calculateCrossCorrelation(alignedData.voltage1, alignedData.voltage2);
        const maxCorrIdx = crossCorr.indexOf(Math.max(...crossCorr));
        const maxLag = Math.floor(crossCorr.length / 2);
        const timeLag = maxCorrIdx - maxLag;
        const peakCorr = crossCorr[maxCorrIdx];

        // Update display
        document.getElementById('corrCoefficient').textContent = regression.r.toFixed(4);
        document.getElementById('corrRSquared').textContent = regression.rSquared.toFixed(4);
        document.getElementById('corrPeak').textContent = peakCorr.toFixed(4);

        // Convert sample lag to time lag
        const samplePeriod = (dataset1.time[1] - dataset1.time[0]) || 0;
        const timeLagValue = timeLag * samplePeriod;
        document.getElementById('corrTimeLag').textContent =
            `${timeLag} samples (${(timeLagValue * 1e6).toFixed(2)} µs)`;
    }

    // Get colors based on theme
    function getTextColor() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? '#f7fafc' : '#1a202c';
    }

    function getGridColor() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? '#4a5568' : '#e2e8f0';
    }

    // Update theme
    function updateTheme() {
        // Redraw all charts with new theme
        const charts = [overlayChart, scatterChart, crossCorrChart];

        charts.forEach(chart => {
            if (chart) {
                // Update text colors
                if (chart.options.plugins.legend) {
                    chart.options.plugins.legend.labels.color = getTextColor();
                }

                // Update scale colors
                Object.keys(chart.options.scales).forEach(scaleKey => {
                    const scale = chart.options.scales[scaleKey];
                    if (scale.title) {
                        scale.title.color = getTextColor();
                    }
                    if (scale.ticks && scaleKey !== 'y1' && scaleKey !== 'y2') {
                        scale.ticks.color = getTextColor();
                    }
                    if (scale.grid) {
                        scale.grid.color = getGridColor();
                    }
                });

                chart.update();
            }
        });
    }

    // Export module
    window.VizCorrelation = {
        init: init,
        updateTheme: updateTheme
    };

})();
