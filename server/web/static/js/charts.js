// LabLink Web Dashboard - Live Charts Manager

// Chart instances
let charts = {
    voltage: null,
    current: null,
    temperature: null,
    power: null
};

// Chart data buffers (keep last 50 points)
const MAX_DATA_POINTS = 50;
let chartData = {
    voltage: { labels: [], data: [] },
    current: { labels: [], data: [] },
    temperature: { labels: [], data: [] },
    power: { labels: [], data: [] }
};

// Selected equipment for charting
let selectedChartEquipment = null;

// Initialize charts
function initializeCharts() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#f7fafc' : '#1a202c';
    const gridColor = isDark ? '#4a5568' : '#e2e8f0';

    const commonOptions = {
        responsive: true,
        maintainAspectRatio: true,
        animation: {
            duration: 200
        },
        scales: {
            x: {
                display: true,
                title: {
                    display: true,
                    text: 'Time',
                    color: textColor
                },
                ticks: {
                    color: textColor,
                    maxRotation: 0,
                    autoSkip: true,
                    maxTicksLimit: 10
                },
                grid: {
                    color: gridColor
                }
            },
            y: {
                display: true,
                ticks: {
                    color: textColor
                },
                grid: {
                    color: gridColor
                }
            }
        },
        plugins: {
            legend: {
                display: false
            },
            tooltip: {
                mode: 'index',
                intersect: false
            }
        }
    };

    // Voltage Chart
    const voltageCtx = document.getElementById('voltageChart').getContext('2d');
    charts.voltage = new Chart(voltageCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Voltage (V)',
                data: [],
                borderColor: '#3b82f6',
                backgroundColor: 'rgba(59, 130, 246, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    title: {
                        display: true,
                        text: 'Voltage (V)',
                        color: textColor
                    }
                }
            }
        }
    });

    // Current Chart
    const currentCtx = document.getElementById('currentChart').getContext('2d');
    charts.current = new Chart(currentCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Current (A)',
                data: [],
                borderColor: '#10b981',
                backgroundColor: 'rgba(16, 185, 129, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    title: {
                        display: true,
                        text: 'Current (A)',
                        color: textColor
                    }
                }
            }
        }
    });

    // Temperature Chart
    const temperatureCtx = document.getElementById('temperatureChart').getContext('2d');
    charts.temperature = new Chart(temperatureCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Temperature (°C)',
                data: [],
                borderColor: '#f59e0b',
                backgroundColor: 'rgba(245, 158, 11, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    title: {
                        display: true,
                        text: 'Temperature (°C)',
                        color: textColor
                    }
                }
            }
        }
    });

    // Power Chart
    const powerCtx = document.getElementById('powerChart').getContext('2d');
    charts.power = new Chart(powerCtx, {
        type: 'line',
        data: {
            labels: [],
            datasets: [{
                label: 'Power (W)',
                data: [],
                borderColor: '#8b5cf6',
                backgroundColor: 'rgba(139, 92, 246, 0.1)',
                borderWidth: 2,
                tension: 0.4,
                fill: true
            }]
        },
        options: {
            ...commonOptions,
            scales: {
                ...commonOptions.scales,
                y: {
                    ...commonOptions.scales.y,
                    title: {
                        display: true,
                        text: 'Power (W)',
                        color: textColor
                    }
                }
            }
        }
    });

    console.log('Charts initialized');
}

// Update chart data with new readings
function updateChartData(readings) {
    if (!selectedChartEquipment || !readings) {
        return;
    }

    const timestamp = new Date().toLocaleTimeString();

    // Helper function to add data point
    function addDataPoint(chartName, value) {
        chartData[chartName].labels.push(timestamp);
        chartData[chartName].data.push(value);

        // Keep only last MAX_DATA_POINTS
        if (chartData[chartName].labels.length > MAX_DATA_POINTS) {
            chartData[chartName].labels.shift();
            chartData[chartName].data.shift();
        }

        // Update chart
        if (charts[chartName]) {
            charts[chartName].data.labels = chartData[chartName].labels;
            charts[chartName].data.datasets[0].data = chartData[chartName].data;
            charts[chartName].update('none'); // Update without animation for smoother real-time
        }
    }

    // Extract readings and update charts
    if (readings.voltage !== undefined) {
        addDataPoint('voltage', readings.voltage);
    }

    if (readings.current !== undefined) {
        addDataPoint('current', readings.current);
    }

    if (readings.temperature !== undefined) {
        addDataPoint('temperature', readings.temperature);
    }

    if (readings.power !== undefined) {
        addDataPoint('power', readings.power);
    } else if (readings.voltage !== undefined && readings.current !== undefined) {
        // Calculate power if not provided
        const power = readings.voltage * readings.current;
        addDataPoint('power', power);
    }
}

// Clear all chart data
function clearChartData() {
    Object.keys(chartData).forEach(key => {
        chartData[key].labels = [];
        chartData[key].data = [];
    });

    Object.values(charts).forEach(chart => {
        if (chart) {
            chart.data.labels = [];
            chart.data.datasets[0].data = [];
            chart.update();
        }
    });
}

// Populate equipment select dropdown
function populateChartEquipmentSelect(equipment) {
    const select = document.getElementById('chartEquipmentSelect');
    const currentValue = select.value;

    // Clear existing options except first
    select.innerHTML = '<option value="">Select equipment...</option>';

    // Add connected equipment
    equipment.filter(e => e.status === 'connected').forEach(eq => {
        const option = document.createElement('option');
        option.value = eq.id;
        option.textContent = `${eq.name} (${eq.equipment_type})`;
        select.appendChild(option);
    });

    // Restore previous selection if still available
    if (currentValue) {
        select.value = currentValue;
    }
}

// Start monitoring equipment for charts
async function startChartMonitoring(equipmentId) {
    selectedChartEquipment = equipmentId;

    // Clear existing data
    clearChartData();

    // Show charts section
    document.getElementById('chartsSection').style.display = 'block';

    console.log('Started chart monitoring for:', equipmentId);

    // If using WebSocket, subscribe to readings
    if (websocket && websocket.readyState === WebSocket.OPEN) {
        websocket.send(JSON.stringify({
            type: 'subscribe',
            channel: 'equipment_readings',
            equipment_id: equipmentId
        }));
    }
}

// Stop monitoring equipment for charts
function stopChartMonitoring() {
    if (selectedChartEquipment) {
        console.log('Stopped chart monitoring for:', selectedChartEquipment);

        // Unsubscribe from WebSocket if connected
        if (websocket && websocket.readyState === WebSocket.OPEN) {
            websocket.send(JSON.stringify({
                type: 'unsubscribe',
                channel: 'equipment_readings',
                equipment_id: selectedChartEquipment
            }));
        }

        selectedChartEquipment = null;
    }

    // Hide charts section
    document.getElementById('chartsSection').style.display = 'none';
}

// Update chart colors for dark mode
function updateChartColors() {
    const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
    const textColor = isDark ? '#f7fafc' : '#1a202c';
    const gridColor = isDark ? '#4a5568' : '#e2e8f0';

    Object.values(charts).forEach(chart => {
        if (chart) {
            // Update scale colors
            chart.options.scales.x.title.color = textColor;
            chart.options.scales.x.ticks.color = textColor;
            chart.options.scales.x.grid.color = gridColor;
            chart.options.scales.y.title.color = textColor;
            chart.options.scales.y.ticks.color = textColor;
            chart.options.scales.y.grid.color = gridColor;

            chart.update();
        }
    });
}

// Export functions
window.initializeCharts = initializeCharts;
window.updateChartData = updateChartData;
window.clearChartData = clearChartData;
window.populateChartEquipmentSelect = populateChartEquipmentSelect;
window.startChartMonitoring = startChartMonitoring;
window.stopChartMonitoring = stopChartMonitoring;
window.updateChartColors = updateChartColors;
