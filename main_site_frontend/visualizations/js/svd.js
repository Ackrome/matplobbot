(function () {
  "use strict";

  const stage = document.getElementById("svd-stage");
  const phaseInput = document.getElementById("phase");
  const sigmaInput = document.getElementById("sigma3");
  const phaseValue = document.getElementById("phase-value");
  const sigmaValue = document.getElementById("sigma-value");
  const phaseLabel = document.getElementById("phase-label");
  const status = document.getElementById("svd-status");

  function setStatus(message, state) {
    status.textContent = message;
    status.dataset.state = state || "";
  }

  if (!window.THREE) {
    setStatus("3D-движок не загрузился. Откройте страницу онлайн ещё раз.", "error");
    return;
  }

  let renderer;
  try {
    renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
  } catch (_error) {
    setStatus("Браузер не предоставил WebGL для этой сцены.", "error");
    return;
  }

  const scene = new THREE.Scene();
  const camera = new THREE.PerspectiveCamera(38, 1, 0.1, 100);
  camera.position.set(4.4, 3.4, 5.4);
  camera.lookAt(0, 0, 0);

  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.setAttribute("aria-hidden", "true");
  stage.appendChild(renderer.domElement);

  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minDistance = 3;
  controls.maxDistance = 10;

  scene.add(new THREE.AmbientLight(0xffffff, 1.8));
  const keyLight = new THREE.DirectionalLight(0xffffff, 2.2);
  keyLight.position.set(4, 6, 5);
  scene.add(keyLight);
  scene.add(new THREE.GridHelper(8, 16, 0x8fb7bc, 0xc6dcdd));
  scene.add(new THREE.AxesHelper(2.4));

  const geometry = new THREE.SphereGeometry(1.35, 34, 22);
  const sourcePositions = new Float32Array(geometry.attributes.position.array);
  const material = new THREE.MeshStandardMaterial({
    color: 0xc86b4a,
    roughness: 0.74,
    metalness: 0.02,
    wireframe: true,
    transparent: true,
    opacity: 0.92
  });
  const mesh = new THREE.Mesh(geometry, material);
  scene.add(mesh);

  const sourceMaterial = new THREE.MeshBasicMaterial({
    color: 0x1d7585,
    wireframe: true,
    transparent: true,
    opacity: 0.12
  });
  const sourceMesh = new THREE.Mesh(new THREE.SphereGeometry(1.35, 24, 16), sourceMaterial);
  scene.add(sourceMesh);

  const sigma = new THREE.Vector3(1.55, 1.02, Number(sigmaInput.value));
  const temp = new THREE.Vector3();

  function smoothstep(value) {
    return value * value * (3 - 2 * value);
  }

  function phaseName(phase) {
    if (phase < 1) return "Поворот Vᵀ";
    if (phase < 2) return "Растяжение Σ";
    return "Поворот U";
  }

  function updateGeometry() {
    const phase = Number(phaseInput.value);
    sigma.z = Number(sigmaInput.value);
    const firstRotation = new THREE.Euler(0, phase < 1 ? phase * Math.PI / 2 : Math.PI / 2, 0);
    const lastProgress = phase < 2 ? 0 : smoothstep(Math.min(1, phase - 2));
    const lastRotation = new THREE.Euler(lastProgress * 0.55, lastProgress * 0.85, lastProgress * 0.45);
    const stretchProgress = phase < 1 ? 0 : smoothstep(Math.min(1, phase - 1));
    const scale = new THREE.Vector3(1 + (sigma.x - 1) * stretchProgress, 1 + (sigma.y - 1) * stretchProgress, 1 + (sigma.z - 1) * stretchProgress);
    const values = geometry.attributes.position.array;

    for (let index = 0; index < values.length; index += 3) {
      temp.set(sourcePositions[index], sourcePositions[index + 1], sourcePositions[index + 2]);
      temp.applyEuler(firstRotation);
      temp.multiply(scale);
      temp.applyEuler(lastRotation);
      values[index] = temp.x;
      values[index + 1] = temp.y;
      values[index + 2] = temp.z;
    }

    geometry.attributes.position.needsUpdate = true;
    geometry.computeVertexNormals();
    phaseValue.value = `${Math.round((phase / 3) * 100)}%`;
    sigmaValue.value = sigma.z.toFixed(2);
    phaseLabel.textContent = phaseName(phase);
    setStatus(`Фаза: ${phaseName(phase)} · σ = (${sigma.x.toFixed(2)}, ${sigma.y.toFixed(2)}, ${sigma.z.toFixed(2)})`, "success");
  }

  function resize() {
    const width = Math.max(1, stage.clientWidth);
    const height = Math.max(360, Math.min(620, Math.round(width * 0.62)));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  phaseInput.addEventListener("input", updateGeometry);
  sigmaInput.addEventListener("input", updateGeometry);
  const observer = new ResizeObserver(resize);
  observer.observe(stage);
  resize();
  updateGeometry();

  function animate() {
    requestAnimationFrame(animate);
    controls.update();
    renderer.render(scene, camera);
  }
  animate();
})();
