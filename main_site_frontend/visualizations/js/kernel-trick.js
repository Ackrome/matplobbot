(function () {
  "use strict";

  const stage = document.getElementById("kernel-stage");
  const planeInput = document.getElementById("plane-height");
  const planeValue = document.getElementById("plane-value");
  const spaceValue = document.getElementById("space-value");
  const status = document.getElementById("kernel-status");
  const detail = document.getElementById("kernel-detail");
  const button2d = document.getElementById("space-2d");
  const button3d = document.getElementById("space-3d");

  function setStatus(message, tone) {
    status.textContent = message;
    status.dataset.state = tone || "";
  }

  if (!window.THREE || !window.THREE.OrbitControls) {
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
  camera.position.set(3.9, 3.1, 4.7);
  camera.lookAt(0, 0, 0.35);
  renderer.setPixelRatio(Math.min(window.devicePixelRatio || 1, 2));
  renderer.setClearColor(0x000000, 0);
  renderer.domElement.setAttribute("aria-hidden", "true");
  stage.appendChild(renderer.domElement);

  const controls = new THREE.OrbitControls(camera, renderer.domElement);
  controls.enableDamping = true;
  controls.enablePan = false;
  controls.minDistance = 2.8;
  controls.maxDistance = 9;

  scene.add(new THREE.AmbientLight(0xffffff, 1.9));
  const keyLight = new THREE.DirectionalLight(0xffffff, 2.4);
  keyLight.position.set(4, 6, 5);
  scene.add(keyLight);
  scene.add(new THREE.GridHelper(5.5, 14, 0x8fb7bc, 0xc6dcdd));
  scene.add(new THREE.AxesHelper(2.1));

  const redPoints = [];
  const bluePoints = [];
  for (let index = 0; index < 18; index += 1) {
    const angle = (index / 18) * Math.PI * 2;
    const radius = 0.18 + (index % 3) * 0.055;
    redPoints.push({ x: radius * Math.cos(angle), y: radius * Math.sin(angle) });
  }
  for (let index = 0; index < 24; index += 1) {
    const angle = (index / 24) * Math.PI * 2 + 0.04;
    const radius = 0.98 + (index % 4) * 0.045;
    bluePoints.push({ x: radius * Math.cos(angle), y: radius * Math.sin(angle) });
  }

  const pointGeometry = new THREE.SphereGeometry(0.065, 12, 8);
  const redMaterial = new THREE.MeshStandardMaterial({ color: 0xc86b4a, roughness: 0.7 });
  const blueMaterial = new THREE.MeshStandardMaterial({ color: 0x1d7585, roughness: 0.7 });
  const pointMeshes = [];
  function addPoints(points, material, label) {
    points.forEach((point) => {
      const mesh = new THREE.Mesh(pointGeometry, material);
      mesh.userData = { point, label };
      scene.add(mesh);
      pointMeshes.push(mesh);
    });
  }
  addPoints(redPoints, redMaterial, "красный диск");
  addPoints(bluePoints, blueMaterial, "синее кольцо");

  const boundaryPoints = [];
  const boundaryGeometry = new THREE.BufferGeometry();
  const boundaryMaterial = new THREE.LineBasicMaterial({ color: 0xc86b4a, transparent: true, opacity: 0.82 });
  const boundaryLine = new THREE.LineLoop(boundaryGeometry, boundaryMaterial);
  scene.add(boundaryLine);

  const plane = new THREE.Mesh(
    new THREE.PlaneGeometry(3.2, 3.2),
    new THREE.MeshStandardMaterial({ color: 0x245bea, transparent: true, opacity: 0.18, side: THREE.DoubleSide })
  );
  plane.rotation.x = -Math.PI / 2;
  scene.add(plane);

  let space = "3d";

  function updateButtons() {
    const is3d = space === "3d";
    button2d.setAttribute("aria-pressed", String(!is3d));
    button3d.setAttribute("aria-pressed", String(is3d));
    button2d.classList.toggle("lab-button--primary", !is3d);
    button3d.classList.toggle("lab-button--primary", is3d);
    spaceValue.textContent = is3d ? "3D" : "2D";
  }

  function updateScene() {
    const c = Number(planeInput.value);
    planeValue.textContent = c.toFixed(2);
    const is3d = space === "3d";
    pointMeshes.forEach((mesh) => {
      const { point } = mesh.userData;
      mesh.position.set(point.x, is3d ? point.x * point.x + point.y * point.y : 0, point.y);
    });
    boundaryPoints.length = 0;
    const radius = Math.sqrt(c);
    for (let index = 0; index < 96; index += 1) {
      const angle = (index / 96) * Math.PI * 2;
      boundaryPoints.push(new THREE.Vector3(radius * Math.cos(angle), is3d ? c + 0.008 : 0.02, radius * Math.sin(angle)));
    }
    boundaryGeometry.setFromPoints(boundaryPoints);
    boundaryLine.visible = !is3d;
    plane.visible = is3d;
    plane.position.y = c;
    updateButtons();
    if (is3d) {
      setStatus(`3D: классы разделены плоскостью z = ${c.toFixed(2)}.`, "success");
      detail.textContent = "Высота c находится внутри зазора: красные точки ниже, синие выше.";
    } else {
      setStatus(`2D: граница классов — окружность r ≈ ${radius.toFixed(2)}.`, "");
      detail.textContent = "В исходной плоскости эта окружность не является прямой границей.";
    }
  }

  function resize() {
    const width = Math.max(320, stage.clientWidth);
    const height = Math.max(360, Math.min(560, Math.round(width * 0.52)));
    renderer.setSize(width, height, false);
    camera.aspect = width / height;
    camera.updateProjectionMatrix();
  }

  button2d.addEventListener("click", () => { space = "2d"; updateScene(); });
  button3d.addEventListener("click", () => { space = "3d"; updateScene(); });
  planeInput.addEventListener("input", updateScene);
  window.addEventListener("resize", resize);
  resize();
  updateScene();

  function animate() {
    controls.update();
    renderer.render(scene, camera);
    window.requestAnimationFrame(animate);
  }
  animate();
})();
