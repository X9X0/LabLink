// LabLink Advanced Visualizations - SPC Charts

(function() {
    'use strict';

    let mainChart, rangeChart;
    let spcData = null;
    let chartType = 'xbar-r';
    let subgroupSize = 5;

    // SPC Constants
    const A2_CONSTANTS = {
        2: 1.880, 3: 1.023, 4: 0.729, 5: 0.577,
        6: 0.483, 7: 0.419, 8: 0.373, 9: 0.337, 10: 0.308
    };

    const D3_CONSTANTS = {
        2: 0, 3: 0, 4: 0, 5: 0, 6: 0,
        7: 0.076, 8: 0.136, 9: 0.184, 10: 0.223
    };

    const D4_CONSTANTS = {
        2: 3.267, 3: 2.574, 4: 2.282, 5: 2.114,
        6: 2.004, 7: 1.924, 8: 1.864, 9: 1.816, 10: 1.777
    };

    // Initialize SPC visualization
    function init() {
        setupEventListeners();
        console.log('SPC visualization initialized');
    }

    // Set up event listeners
    function setupEventListeners() {
        const generateBtn = document.getElementById('generateSPC');
        if (generateBtn) {
            generateBtn.addEventListener('click', generateCharts);
        }

        const chartTypeSelect = document.getElementById('spcChartType');
        if (chartTypeSelect) {
            chartTypeSelect.addEventListener('change', (e) => {
                chartType = e.target.value;
            });
        }

        const subgroupInput = document.getElementById('spcSubgroupSize');
        if (subgroupInput) {
            subgroupInput.addEventListener('change', (e) => {
                subgroupSize = parseInt(e.target.value);
            });
        }
    }

    // Generate SPC charts
    function generateCharts() {
        const currentData = window.getCurrentWaveformData();
        if (currentData) {
            updateData(currentData);
        }
    }

    // Update with new waveform data
    function updateData(data) {
        if (!data || !data.voltage) {
            console.error('Invalid data for SPC charts');
            return;
        }

        // Process data based on chart type
        if (chartType === 'xbar-r') {
            processXbarR(data.voltage);
        } else if (chartType === 'xbar-s') {
            processXbarS(data.voltage);
        } else if (chartType === 'individuals') {
            processIndividuals(data.voltage);
        } else if (chartType === 'p-chart') {
            processPChart(data.voltage);
        } else if (chartType === 'c-chart') {
            processCChart(data.voltage);
        }

        console.log('SPC charts updated');
    }

    // Process X-bar and R chart
    function processXbarR(data) {
        // Divide data into subgroups
        const subgroups = divideIntoSubgroups(data, subgroupSize);

        // Calculate X-bar and R for each subgroup
        const xbars = [];
        const ranges = [];

        subgroups.forEach(subgroup => {
            const mean = subgroup.reduce((a, b) => a + b, 0) / subgroup.length;
            const range = Math.max(...subgroup) - Math.min(...subgroup);
            xbars.push(mean);
            ranges.push(range);
        });

        // Calculate control limits
        const xbarMean = xbars.reduce((a, b) => a + b, 0) / xbars.length;
        const rMean = ranges.reduce((a, b) => a + b, 0) / ranges.length;

        const A2 = A2_CONSTANTS[subgroupSize] || 0.577;
        const D3 = D3_CONSTANTS[subgroupSize] || 0;
        const D4 = D4_CONSTANTS[subgroupSize] || 2.114;

        const xbarUCL = xbarMean + A2 * rMean;
        const xbarLCL = xbarMean - A2 * rMean;
        const rUCL = D4 * rMean;
        const rLCL = D3 * rMean;

        // Find violations
        const violations = findViolations(xbars, xbarUCL, xbarLCL);

        // Draw charts
        drawMainChart(xbars, xbarMean, xbarUCL, xbarLCL, 'X-bar Chart', violations);
        drawRangeChart(ranges, rMean, rUCL, rLCL, 'R Chart');

        // Update stats
        updateStats({
            ucl: xbarUCL,
            cl: xbarMean,
            lcl: xbarLCL,
            violations: violations.length
        }, xbars, xbarUCL, xbarLCL);
    }

    // Process X-bar and S chart
    function processXbarS(data) {
        const subgroups = divideIntoSubgroups(data, subgroupSize);

        const xbars = [];
        const stdevs = [];

        subgroups.forEach(subgroup => {
            const mean = subgroup.reduce((a, b) => a + b, 0) / subgroup.length;
            const variance = subgroup.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / (subgroup.length - 1);
            const stdev = Math.sqrt(variance);
            xbars.push(mean);
            stdevs.push(stdev);
        });

        const xbarMean = xbars.reduce((a, b) => a + b, 0) / xbars.length;
        const sMean = stdevs.reduce((a, b) => a + b, 0) / stdevs.length;

        // Simplified constants (actual values depend on subgroup size)
        const A3 = 1.427 / Math.sqrt(subgroupSize);
        const xbarUCL = xbarMean + A3 * sMean;
        const xbarLCL = xbarMean - A3 * sMean;

        const violations = findViolations(xbars, xbarUCL, xbarLCL);

        drawMainChart(xbars, xbarMean, xbarUCL, xbarLCL, 'X-bar Chart (S)', violations);
        drawRangeChart(stdevs, sMean, sMean * 2, 0, 'S Chart');

        updateStats({
            ucl: xbarUCL,
            cl: xbarMean,
            lcl: xbarLCL,
            violations: violations.length
        }, xbars, xbarUCL, xbarLCL);
    }

    // Process Individuals chart
    function processIndividuals(data) {
        // Calculate moving ranges
        const movingRanges = [];
        for (let i = 1; i < data.length; i++) {
            movingRanges.push(Math.abs(data[i] - data[i - 1]));
        }

        const mean = data.reduce((a, b) => a + b, 0) / data.length;
        const mRMean = movingRanges.reduce((a, b) => a + b, 0) / movingRanges.length;

        const ucl = mean + 2.66 * mRMean;
        const lcl = mean - 2.66 * mRMean;

        const violations = findViolations(data, ucl, lcl);

        // Sample data for display (to keep chart readable)
        const sampledData = sampleData(data, 100);

        drawMainChart(sampledData, mean, ucl, lcl, 'Individuals Chart', violations);
        drawRangeChart(sampleData(movingRanges, 100), mRMean, mRMean * 3.267, 0, 'Moving Range Chart');

        updateStats({ ucl, cl: mean, lcl, violations: violations.length }, data, ucl, lcl);
    }

    // Process P Chart (proportion defective)
    function processPChart(data) {
        // Treat data as binary outcomes (above/below median)
        const median = [...data].sort((a, b) => a - b)[Math.floor(data.length / 2)];
        const subgroups = divideIntoSubgroups(data, subgroupSize);

        const proportions = subgroups.map(subgroup => {
            const defective = subgroup.filter(v => v > median).length;
            return defective / subgroup.length;
        });

        const pBar = proportions.reduce((a, b) => a + b, 0) / proportions.length;
        const ucl = pBar + 3 * Math.sqrt(pBar * (1 - pBar) / subgroupSize);
        const lcl = Math.max(0, pBar - 3 * Math.sqrt(pBar * (1 - pBar) / subgroupSize));

        const violations = findViolations(proportions, ucl, lcl);

        drawMainChart(proportions, pBar, ucl, lcl, 'P Chart', violations);

        updateStats({ ucl, cl: pBar, lcl, violations: violations.length }, proportions, ucl, lcl);
    }

    // Process C Chart (count of defects)
    function processCChart(data) {
        // Count "defects" as values exceeding certain thresholds
        const threshold = Math.max(...data) * 0.8;
        const subgroups = divideIntoSubgroups(data, subgroupSize);

        const counts = subgroups.map(subgroup => {
            return subgroup.filter(v => v > threshold).length;
        });

        const cBar = counts.reduce((a, b) => a + b, 0) / counts.length;
        const ucl = cBar + 3 * Math.sqrt(cBar);
        const lcl = Math.max(0, cBar - 3 * Math.sqrt(cBar));

        const violations = findViolations(counts, ucl, lcl);

        drawMainChart(counts, cBar, ucl, lcl, 'C Chart', violations);

        updateStats({ ucl, cl: cBar, lcl, violations: violations.length }, counts, ucl, lcl);
    }

    // Divide data into subgroups
    function divideIntoSubgroups(data, size) {
        const subgroups = [];
        for (let i = 0; i < data.length; i += size) {
            const subgroup = data.slice(i, i + size);
            if (subgroup.length === size) {
                subgroups.push(subgroup);
            }
        }
        return subgroups;
    }

    // Sample data for display
    function sampleData(data, maxPoints) {
        if (data.length <= maxPoints) {
            return data;
        }
        const step = Math.floor(data.length / maxPoints);
        return data.filter((_, i) => i % step === 0);
    }

    // Find violations (points outside control limits)
    function findViolations(data, ucl, lcl) {
        const violations = [];
        data.forEach((value, index) => {
            if (value > ucl || value < lcl) {
                violations.push(index);
            }
        });
        return violations;
    }

    // Draw main SPC chart
    function drawMainChart(data, centerLine, ucl, lcl, title, violations = []) {
        const ctx = document.getElementById('spcMainChart');
        if (!ctx) return;

        // Destroy existing chart
        if (mainChart) {
            mainChart.destroy();
        }

        const labels = data.map((_, i) => i + 1);

        mainChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Data',
                        data: data,
                        borderColor: getDataColor(),
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 4,
                        pointBackgroundColor: data.map((v, i) =>
                            violations.includes(i) ? '#ef4444' : getDataColor()
                        ),
                        pointBorderColor: data.map((v, i) =>
                            violations.includes(i) ? '#dc2626' : getDataColor()
                        ),
                        pointBorderWidth: 2
                    },
                    {
                        label: 'UCL',
                        data: Array(data.length).fill(ucl),
                        borderColor: '#ef4444',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 0
                    },
                    {
                        label: 'CL',
                        data: Array(data.length).fill(centerLine),
                        borderColor: '#10b981',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0
                    },
                    {
                        label: 'LCL',
                        data: Array(data.length).fill(lcl),
                        borderColor: '#ef4444',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                animation: {
                    duration: 750,
                    easing: 'easeInOutQuart'
                },
                plugins: {
                    title: {
                        display: true,
                        text: title,
                        color: getTextColor(),
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: {
                        display: true,
                        labels: { color: getTextColor() }
                    },
                    tooltip: {
                        callbacks: {
                            label: function(context) {
                                let label = context.dataset.label || '';
                                if (label) {
                                    label += ': ';
                                }
                                label += context.parsed.y.toFixed(4);
                                return label;
                            }
                        }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Sample Number',
                            color: getTextColor()
                        },
                        ticks: { color: getTextColor() },
                        grid: { color: getGridColor() }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Value',
                            color: getTextColor()
                        },
                        ticks: { color: getTextColor() },
                        grid: { color: getGridColor() }
                    }
                }
            }
        });
    }

    // Draw range chart
    function drawRangeChart(data, centerLine, ucl, lcl, title) {
        const ctx = document.getElementById('spcRangeChart');
        if (!ctx) return;

        // Destroy existing chart
        if (rangeChart) {
            rangeChart.destroy();
        }

        const labels = data.map((_, i) => i + 1);

        rangeChart = new Chart(ctx, {
            type: 'line',
            data: {
                labels: labels,
                datasets: [
                    {
                        label: 'Range/Stdev',
                        data: data,
                        borderColor: '#8b5cf6',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 4,
                        pointBackgroundColor: '#8b5cf6'
                    },
                    {
                        label: 'UCL',
                        data: Array(data.length).fill(ucl),
                        borderColor: '#ef4444',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 0
                    },
                    {
                        label: 'CL',
                        data: Array(data.length).fill(centerLine),
                        borderColor: '#10b981',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        pointRadius: 0
                    },
                    {
                        label: 'LCL',
                        data: Array(data.length).fill(lcl),
                        borderColor: '#ef4444',
                        backgroundColor: 'transparent',
                        borderWidth: 2,
                        borderDash: [5, 5],
                        pointRadius: 0
                    }
                ]
            },
            options: {
                responsive: true,
                maintainAspectRatio: true,
                animation: {
                    duration: 750,
                    easing: 'easeInOutQuart'
                },
                plugins: {
                    title: {
                        display: true,
                        text: title,
                        color: getTextColor(),
                        font: { size: 14, weight: 'bold' }
                    },
                    legend: {
                        display: true,
                        labels: { color: getTextColor() }
                    }
                },
                scales: {
                    x: {
                        title: {
                            display: true,
                            text: 'Sample Number',
                            color: getTextColor()
                        },
                        ticks: { color: getTextColor() },
                        grid: { color: getGridColor() }
                    },
                    y: {
                        title: {
                            display: true,
                            text: 'Range',
                            color: getTextColor()
                        },
                        ticks: { color: getTextColor() },
                        grid: { color: getGridColor() }
                    }
                }
            }
        });
    }

    // Update statistics display
    function updateStats(limits, data, ucl, lcl) {
        document.getElementById('spcUCL').textContent = limits.ucl.toFixed(4);
        document.getElementById('spcCL').textContent = limits.cl.toFixed(4);
        document.getElementById('spcLCL').textContent = limits.lcl.toFixed(4);
        document.getElementById('spcViolations').textContent = limits.violations;

        // Calculate process capability
        const mean = data.reduce((a, b) => a + b, 0) / data.length;
        const variance = data.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / (data.length - 1);
        const sigma = Math.sqrt(variance);

        const cp = (ucl - lcl) / (6 * sigma);
        const cpk = Math.min(
            (ucl - mean) / (3 * sigma),
            (mean - lcl) / (3 * sigma)
        );

        document.getElementById('spcCp').textContent = cp.toFixed(3);
        document.getElementById('spcCpk').textContent = cpk.toFixed(3);
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

    function getDataColor() {
        return '#3b82f6';
    }

    // Update theme
    function updateTheme() {
        // Redraw charts with new theme
        if (mainChart) {
            mainChart.options.plugins.title.color = getTextColor();
            mainChart.options.plugins.legend.labels.color = getTextColor();
            mainChart.options.scales.x.title.color = getTextColor();
            mainChart.options.scales.x.ticks.color = getTextColor();
            mainChart.options.scales.x.grid.color = getGridColor();
            mainChart.options.scales.y.title.color = getTextColor();
            mainChart.options.scales.y.ticks.color = getTextColor();
            mainChart.options.scales.y.grid.color = getGridColor();
            mainChart.update();
        }

        if (rangeChart) {
            rangeChart.options.plugins.title.color = getTextColor();
            rangeChart.options.plugins.legend.labels.color = getTextColor();
            rangeChart.options.scales.x.title.color = getTextColor();
            rangeChart.options.scales.x.ticks.color = getTextColor();
            rangeChart.options.scales.x.grid.color = getGridColor();
            rangeChart.options.scales.y.title.color = getTextColor();
            rangeChart.options.scales.y.ticks.color = getTextColor();
            rangeChart.options.scales.y.grid.color = getGridColor();
            rangeChart.update();
        }
    }

    // Export module
    window.VizSPC = {
        init: init,
        updateData: updateData,
        updateTheme: updateTheme
    };

})();
