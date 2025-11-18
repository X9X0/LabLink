// LabLink Advanced Visualizations - FFT Waterfall Display

(function() {
    'use strict';

    let canvas, ctx;
    let waterfallData = [];
    let maxWaterfallLines = 200;
    let colormap = [];
    let fftSize = 512;
    let windowType = 'hann';

    // Initialize waterfall visualization
    function init() {
        canvas = document.getElementById('waterfallCanvas');
        if (!canvas) {
            console.error('Waterfall canvas not found');
            return;
        }

        ctx = canvas.getContext('2d');

        // Set canvas size
        resizeCanvas();
        window.addEventListener('resize', resizeCanvas);

        // Generate colormap
        generateColormap();

        // Set up event listeners
        setupEventListeners();

        console.log('Waterfall visualization initialized');
    }

    // Set up event listeners
    function setupEventListeners() {
        const updateBtn = document.getElementById('updateWaterfall');
        if (updateBtn) {
            updateBtn.addEventListener('click', updateSettings);
        }

        const clearBtn = document.getElementById('clearWaterfall');
        if (clearBtn) {
            clearBtn.addEventListener('click', clearWaterfall);
        }
    }

    // Resize canvas to fit container
    function resizeCanvas() {
        if (!canvas) return;

        const container = canvas.parentElement;
        canvas.width = container.clientWidth;
        canvas.height = container.clientHeight;

        // Redraw waterfall after resize
        drawWaterfall();
    }

    // Generate colormap (from blue to red through green/yellow)
    function generateColormap() {
        colormap = [];
        const steps = 256;

        for (let i = 0; i < steps; i++) {
            const t = i / (steps - 1);
            let r, g, b;

            if (t < 0.25) {
                // Blue to cyan
                const t2 = t / 0.25;
                r = 0;
                g = Math.floor(t2 * 255);
                b = 255;
            } else if (t < 0.5) {
                // Cyan to green
                const t2 = (t - 0.25) / 0.25;
                r = 0;
                g = 255;
                b = Math.floor((1 - t2) * 255);
            } else if (t < 0.75) {
                // Green to yellow
                const t2 = (t - 0.5) / 0.25;
                r = Math.floor(t2 * 255);
                g = 255;
                b = 0;
            } else {
                // Yellow to red
                const t2 = (t - 0.75) / 0.25;
                r = 255;
                g = Math.floor((1 - t2) * 255);
                b = 0;
            }

            colormap.push({ r, g, b });
        }
    }

    // Update settings
    function updateSettings() {
        const windowSelect = document.getElementById('waterfallWindow');
        const fftSelect = document.getElementById('waterfallFFTSize');

        if (windowSelect) {
            windowType = windowSelect.value;
        }

        if (fftSelect) {
            fftSize = parseInt(fftSelect.value);
        }

        // Reprocess current data with new settings
        const currentData = window.getCurrentWaveformData();
        if (currentData) {
            updateData(currentData);
        }
    }

    // Clear waterfall display
    function clearWaterfall() {
        waterfallData = [];
        drawWaterfall();
        updateStats(null);
    }

    // Update with new waveform data
    function updateData(data) {
        if (!data || !data.voltage || !data.time) {
            console.error('Invalid waveform data for waterfall');
            return;
        }

        // Calculate FFT
        const fftResult = calculateFFT(data.voltage, fftSize, windowType);

        if (fftResult && fftResult.magnitude) {
            // Add to waterfall data
            waterfallData.push({
                magnitude: fftResult.magnitude,
                frequencies: fftResult.frequencies,
                timestamp: Date.now()
            });

            // Keep only recent data
            if (waterfallData.length > maxWaterfallLines) {
                waterfallData.shift();
            }

            // Draw waterfall
            drawWaterfall();

            // Update stats
            updateStats(fftResult, data.sampleRate);
        }

        console.log('Waterfall updated with FFT data');
    }

    // Calculate FFT using basic algorithm
    function calculateFFT(signal, nfft, window) {
        // Pad or truncate signal to FFT size
        let paddedSignal = new Array(nfft).fill(0);
        const copyLen = Math.min(signal.length, nfft);
        for (let i = 0; i < copyLen; i++) {
            paddedSignal[i] = signal[i];
        }

        // Apply window function
        paddedSignal = applyWindow(paddedSignal, window);

        // Perform FFT (simplified DFT for demo)
        const magnitude = [];
        const frequencies = [];
        const halfN = Math.floor(nfft / 2);

        for (let k = 0; k < halfN; k++) {
            let real = 0;
            let imag = 0;

            for (let n = 0; n < nfft; n++) {
                const angle = -2 * Math.PI * k * n / nfft;
                real += paddedSignal[n] * Math.cos(angle);
                imag += paddedSignal[n] * Math.sin(angle);
            }

            const mag = Math.sqrt(real * real + imag * imag) / nfft;
            magnitude.push(mag);
            frequencies.push(k);
        }

        return { magnitude, frequencies };
    }

    // Apply window function
    function applyWindow(signal, windowType) {
        const n = signal.length;
        const windowed = new Array(n);

        for (let i = 0; i < n; i++) {
            let w = 1;

            switch (windowType) {
                case 'hann':
                    w = 0.5 * (1 - Math.cos(2 * Math.PI * i / (n - 1)));
                    break;
                case 'hamming':
                    w = 0.54 - 0.46 * Math.cos(2 * Math.PI * i / (n - 1));
                    break;
                case 'blackman':
                    w = 0.42 - 0.5 * Math.cos(2 * Math.PI * i / (n - 1)) +
                        0.08 * Math.cos(4 * Math.PI * i / (n - 1));
                    break;
                case 'bartlett':
                    w = 1 - Math.abs((i - (n - 1) / 2) / ((n - 1) / 2));
                    break;
                case 'none':
                default:
                    w = 1;
                    break;
            }

            windowed[i] = signal[i] * w;
        }

        return windowed;
    }

    // Draw waterfall display
    function drawWaterfall() {
        if (!ctx || !canvas) return;

        const width = canvas.width;
        const height = canvas.height;

        // Clear canvas
        ctx.fillStyle = getBackgroundColor();
        ctx.fillRect(0, 0, width, height);

        if (waterfallData.length === 0) {
            // Show empty state
            ctx.fillStyle = getTextColor();
            ctx.font = '16px sans-serif';
            ctx.textAlign = 'center';
            ctx.fillText('No data - load waveform to generate waterfall', width / 2, height / 2);
            return;
        }

        // Calculate dimensions
        const lineHeight = height / maxWaterfallLines;
        const binWidth = width / (fftSize / 2);

        // Find min/max for normalization
        let minMag = Infinity;
        let maxMag = -Infinity;

        waterfallData.forEach(line => {
            line.magnitude.forEach(mag => {
                minMag = Math.min(minMag, mag);
                maxMag = Math.max(maxMag, mag);
            });
        });

        const range = maxMag - minMag || 1;

        // Draw each line
        waterfallData.forEach((line, lineIdx) => {
            const y = height - (lineIdx + 1) * lineHeight;

            line.magnitude.forEach((mag, binIdx) => {
                // Normalize magnitude to 0-1
                const normalized = (mag - minMag) / range;

                // Map to colormap
                const colorIdx = Math.floor(normalized * (colormap.length - 1));
                const color = colormap[colorIdx];

                ctx.fillStyle = `rgb(${color.r}, ${color.g}, ${color.b})`;

                const x = binIdx * binWidth;
                ctx.fillRect(x, y, Math.ceil(binWidth), Math.ceil(lineHeight));
            });
        });

        // Draw frequency axis
        drawFrequencyAxis();
    }

    // Draw frequency axis labels
    function drawFrequencyAxis() {
        if (!ctx || waterfallData.length === 0) return;

        const width = canvas.width;
        const height = canvas.height;

        ctx.fillStyle = getTextColor();
        ctx.font = '12px sans-serif';
        ctx.textAlign = 'center';

        // Draw a few frequency labels
        const numLabels = 5;
        for (let i = 0; i <= numLabels; i++) {
            const x = (i / numLabels) * width;
            const freqLabel = `${((i / numLabels) * 100).toFixed(0)}%`;
            ctx.fillText(freqLabel, x, height - 5);
        }
    }

    // Update statistics display
    function updateStats(fftResult, sampleRate) {
        const freqRangeEl = document.getElementById('waterfallFreqRange');
        const timeSpanEl = document.getElementById('waterfallTimeSpan');
        const resolutionEl = document.getElementById('waterfallResolution');

        if (!fftResult || !sampleRate) {
            if (freqRangeEl) freqRangeEl.textContent = 'Frequency Range: -';
            if (timeSpanEl) timeSpanEl.textContent = 'Time Span: -';
            if (resolutionEl) resolutionEl.textContent = 'Resolution: -';
            return;
        }

        const maxFreq = sampleRate / 2;
        const freqResolution = maxFreq / (fftSize / 2);
        const timeSpan = waterfallData.length > 1 ?
            (waterfallData[waterfallData.length - 1].timestamp - waterfallData[0].timestamp) / 1000 :
            0;

        if (freqRangeEl) {
            freqRangeEl.textContent = `Frequency Range: 0 - ${formatFrequency(maxFreq)}`;
        }

        if (timeSpanEl) {
            timeSpanEl.textContent = `Time Span: ${timeSpan.toFixed(1)}s`;
        }

        if (resolutionEl) {
            resolutionEl.textContent = `Resolution: ${formatFrequency(freqResolution)}/bin`;
        }
    }

    // Format frequency value
    function formatFrequency(freq) {
        if (freq >= 1e6) {
            return `${(freq / 1e6).toFixed(2)} MHz`;
        } else if (freq >= 1e3) {
            return `${(freq / 1e3).toFixed(2)} kHz`;
        } else {
            return `${freq.toFixed(2)} Hz`;
        }
    }

    // Get colors based on theme
    function getBackgroundColor() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? '#1a202c' : '#f7fafc';
    }

    function getTextColor() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? '#f7fafc' : '#1a202c';
    }

    // Update theme
    function updateTheme() {
        drawWaterfall();
    }

    // Export module
    window.VizWaterfall = {
        init: init,
        updateData: updateData,
        updateTheme: updateTheme,
        clear: clearWaterfall
    };

})();
