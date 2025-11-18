// LabLink Advanced Visualizations - 3D Waveform Display

(function() {
    'use strict';

    // Three.js scene components
    let scene, camera, renderer, controls;
    let waveformMesh, gridHelper, axesHelper;
    let animationId = null;
    let isAnimating = false;
    let waveformHistory = [];
    const MAX_HISTORY = 10;

    // Initialize 3D visualization
    function init() {
        const container = document.getElementById('waveform3D');
        if (!container) {
            console.error('3D waveform container not found');
            return;
        }

        // Set up scene
        scene = new THREE.Scene();
        scene.background = new THREE.Color(getBackgroundColor());

        // Set up camera
        const width = container.clientWidth;
        const height = container.clientHeight;
        camera = new THREE.PerspectiveCamera(75, width / height, 0.1, 1000);
        camera.position.set(5, 5, 5);
        camera.lookAt(0, 0, 0);

        // Set up renderer
        renderer = new THREE.WebGLRenderer({ antialias: true });
        renderer.setSize(width, height);
        renderer.setPixelRatio(window.devicePixelRatio);
        container.appendChild(renderer.domElement);

        // Set up controls
        controls = new THREE.OrbitControls(camera, renderer.domElement);
        controls.enableDamping = true;
        controls.dampingFactor = 0.05;
        controls.screenSpacePanning = false;
        controls.minDistance = 3;
        controls.maxDistance = 20;

        // Add grid
        gridHelper = new THREE.GridHelper(10, 10, getGridColor(), getGridColor());
        gridHelper.visible = false;
        scene.add(gridHelper);

        // Add axes
        axesHelper = new THREE.AxesHelper(5);
        scene.add(axesHelper);

        // Add lights
        const ambientLight = new THREE.AmbientLight(0xffffff, 0.6);
        scene.add(ambientLight);

        const directionalLight = new THREE.DirectionalLight(0xffffff, 0.8);
        directionalLight.position.set(5, 10, 5);
        scene.add(directionalLight);

        // Set up event listeners
        setupEventListeners();

        // Handle window resize
        window.addEventListener('resize', onWindowResize);

        // Start render loop
        animate();

        console.log('3D waveform visualization initialized');
    }

    // Set up event listeners
    function setupEventListeners() {
        // Reset view button
        const resetBtn = document.getElementById('reset3DView');
        if (resetBtn) {
            resetBtn.addEventListener('click', resetView);
        }

        // Animate button
        const animateBtn = document.getElementById('animate3D');
        if (animateBtn) {
            animateBtn.addEventListener('click', toggleAnimation);
        }

        // Show grid checkbox
        const gridCheckbox = document.getElementById('show3DGrid');
        if (gridCheckbox) {
            gridCheckbox.addEventListener('change', (e) => {
                if (gridHelper) {
                    gridHelper.visible = e.target.checked;
                }
            });
        }

        // Show axes checkbox
        const axesCheckbox = document.getElementById('show3DAxes');
        if (axesCheckbox) {
            axesCheckbox.addEventListener('change', (e) => {
                if (axesHelper) {
                    axesHelper.visible = e.target.checked;
                }
            });
        }
    }

    // Animation loop
    function animate() {
        animationId = requestAnimationFrame(animate);

        // Update controls
        if (controls) {
            controls.update();
        }

        // Animate waveform if enabled
        if (isAnimating && waveformMesh) {
            waveformMesh.rotation.z += 0.005;
        }

        // Render scene
        if (renderer && scene && camera) {
            renderer.render(scene, camera);
        }
    }

    // Handle window resize
    function onWindowResize() {
        const container = document.getElementById('waveform3D');
        if (!container || !camera || !renderer) return;

        const width = container.clientWidth;
        const height = container.clientHeight;

        camera.aspect = width / height;
        camera.updateProjectionMatrix();
        renderer.setSize(width, height);
    }

    // Reset camera view
    function resetView() {
        if (!camera || !controls) return;

        camera.position.set(5, 5, 5);
        camera.lookAt(0, 0, 0);
        controls.reset();
    }

    // Toggle animation
    function toggleAnimation() {
        isAnimating = !isAnimating;

        const btn = document.getElementById('animate3D');
        const btnText = document.getElementById('animate3DText');
        if (btn && btnText) {
            btnText.textContent = isAnimating ? 'Stop Animation' : 'Start Animation';
        }
    }

    // Update with new waveform data
    function updateData(data) {
        if (!data || !data.voltage || !data.time) {
            console.error('Invalid waveform data for 3D visualization');
            return;
        }

        // Remove old waveform mesh
        if (waveformMesh) {
            scene.remove(waveformMesh);
            if (waveformMesh.geometry) waveformMesh.geometry.dispose();
            if (waveformMesh.material) waveformMesh.material.dispose();
        }

        // Add to history
        waveformHistory.push(data);
        if (waveformHistory.length > MAX_HISTORY) {
            waveformHistory.shift();
        }

        // Create 3D waveform geometry
        const geometry = createWaveformGeometry(data);

        // Create material
        const material = new THREE.LineBasicMaterial({
            color: getWaveformColor(),
            linewidth: 2
        });

        // Create mesh
        waveformMesh = new THREE.Line(geometry, material);
        scene.add(waveformMesh);

        // If we have history, create surface
        if (waveformHistory.length > 1) {
            createWaveformSurface();
        }

        console.log('3D waveform updated with', data.voltage.length, 'points');
    }

    // Create waveform geometry from data
    function createWaveformGeometry(data) {
        const geometry = new THREE.BufferGeometry();
        const vertices = [];

        // Normalize time and voltage for display
        const timeMin = Math.min(...data.time);
        const timeMax = Math.max(...data.time);
        const voltageMin = Math.min(...data.voltage);
        const voltageMax = Math.max(...data.voltage);

        const timeRange = timeMax - timeMin || 1;
        const voltageRange = voltageMax - voltageMin || 1;

        // Sample points if too many (for performance)
        const maxPoints = 2000;
        const step = Math.max(1, Math.floor(data.voltage.length / maxPoints));

        for (let i = 0; i < data.voltage.length; i += step) {
            const x = ((data.time[i] - timeMin) / timeRange) * 8 - 4; // Map to -4 to 4
            const y = ((data.voltage[i] - voltageMin) / voltageRange) * 4 - 2; // Map to -2 to 2
            const z = 0;

            vertices.push(x, y, z);
        }

        geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));

        return geometry;
    }

    // Create 3D surface from waveform history
    function createWaveformSurface() {
        // Remove old surface meshes
        scene.children.forEach(child => {
            if (child.userData && child.userData.isSurface) {
                scene.remove(child);
                if (child.geometry) child.geometry.dispose();
                if (child.material) child.material.dispose();
            }
        });

        // Create surface geometry from history
        const geometry = new THREE.BufferGeometry();
        const vertices = [];
        const indices = [];
        const colors = [];

        const historyCount = waveformHistory.length;
        const color = new THREE.Color(getWaveformColor());

        for (let h = 0; h < historyCount; h++) {
            const data = waveformHistory[h];
            const timeMin = Math.min(...data.time);
            const timeMax = Math.max(...data.time);
            const voltageMin = Math.min(...data.voltage);
            const voltageMax = Math.max(...data.voltage);
            const timeRange = timeMax - timeMin || 1;
            const voltageRange = voltageMax - voltageMin || 1;

            const maxPoints = 200;
            const step = Math.max(1, Math.floor(data.voltage.length / maxPoints));
            const zOffset = (h - historyCount / 2) * 0.5;

            const baseIndex = vertices.length / 3;

            for (let i = 0; i < data.voltage.length; i += step) {
                const x = ((data.time[i] - timeMin) / timeRange) * 8 - 4;
                const y = ((data.voltage[i] - voltageMin) / voltageRange) * 4 - 2;
                const z = zOffset;

                vertices.push(x, y, z);

                // Color gradient based on time
                const alpha = h / historyCount;
                colors.push(color.r * alpha, color.g * alpha, color.b * alpha);
            }

            // Create indices for triangle strip
            if (h > 0) {
                const prevBase = baseIndex - (data.voltage.length / step);
                const currBase = baseIndex;
                const pointsPerWaveform = Math.floor(data.voltage.length / step);

                for (let i = 0; i < pointsPerWaveform - 1; i++) {
                    // Triangle 1
                    indices.push(prevBase + i, currBase + i, prevBase + i + 1);
                    // Triangle 2
                    indices.push(prevBase + i + 1, currBase + i, currBase + i + 1);
                }
            }
        }

        geometry.setAttribute('position', new THREE.Float32BufferAttribute(vertices, 3));
        geometry.setAttribute('color', new THREE.Float32BufferAttribute(colors, 3));
        geometry.setIndex(indices);
        geometry.computeVertexNormals();

        const material = new THREE.MeshPhongMaterial({
            vertexColors: true,
            side: THREE.DoubleSide,
            transparent: true,
            opacity: 0.7,
            shininess: 30
        });

        const mesh = new THREE.Mesh(geometry, material);
        mesh.userData.isSurface = true;
        scene.add(mesh);
    }

    // Get colors based on theme
    function getBackgroundColor() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? 0x1a202c : 0xf7fafc;
    }

    function getGridColor() {
        const isDark = document.documentElement.getAttribute('data-theme') === 'dark';
        return isDark ? 0x4a5568 : 0xe2e8f0;
    }

    function getWaveformColor() {
        return 0x3b82f6; // Blue
    }

    // Update theme
    function updateTheme() {
        if (!scene) return;

        scene.background = new THREE.Color(getBackgroundColor());

        if (gridHelper) {
            gridHelper.material.color.set(getGridColor());
        }
    }

    // Cleanup
    function destroy() {
        if (animationId) {
            cancelAnimationFrame(animationId);
        }

        if (renderer && renderer.domElement) {
            const container = document.getElementById('waveform3D');
            if (container && container.contains(renderer.domElement)) {
                container.removeChild(renderer.domElement);
            }
            renderer.dispose();
        }

        if (controls) {
            controls.dispose();
        }

        window.removeEventListener('resize', onWindowResize);
    }

    // Export module
    window.Viz3DWaveform = {
        init: init,
        updateData: updateData,
        updateTheme: updateTheme,
        destroy: destroy
    };

})();
