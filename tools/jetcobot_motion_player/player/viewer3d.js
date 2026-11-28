// 브라우저 3D 뷰어: URDF(로봇·맵)를 three.js 로 그리고 관절 각도를 넣어 움직임
import * as THREE from 'three';
import { STLLoader } from '/vendor/STLLoader.js';
import { OrbitControls } from '/vendor/OrbitControls.js';

const stl = new STLLoader();
const meshCache = new Map();

function loadSTL(url) {
  if (!meshCache.has(url)) meshCache.set(url, new Promise((ok, bad) => stl.load(url, ok, undefined, bad)));
  return meshCache.get(url);
}

const nums = (s, d) => (s ? s.trim().split(/\s+/).map(Number) : d);

function originOf(el) {
  const o = el && el.querySelector(':scope > origin');
  const xyz = nums(o && o.getAttribute('xyz'), [0, 0, 0]);
  const rpy = nums(o && o.getAttribute('rpy'), [0, 0, 0]);
  const g = new THREE.Group();
  g.position.set(...xyz);
  g.rotation.copy(new THREE.Euler(rpy[0], rpy[1], rpy[2], 'ZYX'));   // URDF rpy = 고정축 X→Y→Z
  return g;
}

export class Viewer {
  constructor(canvas) {
    this.canvas = canvas;
    this.renderer = new THREE.WebGLRenderer({ canvas, antialias: true });
    this.renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    this.scene = new THREE.Scene();
    this.camera = new THREE.PerspectiveCamera(40, 1, 0.01, 50);
    this.camera.up.set(0, 0, 1);                                      // ROS: Z 가 위
    this.controls = new OrbitControls(this.camera, canvas);
    this.controls.enableDamping = true;
    this.scene.add(new THREE.HemisphereLight(0xffffff, 0x8a8f99, 1.6));
    const sun = new THREE.DirectionalLight(0xffffff, 1.6);
    sun.position.set(1.5, -1, 3);
    this.scene.add(sun);
    const grid = new THREE.GridHelper(2, 40, 0x9aa1ab, 0xc6cbd2);
    grid.rotation.x = Math.PI / 2;
    this.scene.add(grid);
    this.joints = {};
    this.root = null;
    this.setBackground();
    new ResizeObserver(() => this.resize()).observe(canvas);
    const loop = () => { this.controls.update(); this.renderer.render(this.scene, this.camera); requestAnimationFrame(loop); };
    loop();
  }

  setBackground() {
    const dark = matchMedia('(prefers-color-scheme: dark)').matches;
    this.scene.background = new THREE.Color(dark ? 0x23272e : 0xe9ecf0);
  }

  resize() {
    const w = this.canvas.clientWidth, h = this.canvas.clientHeight;
    if (!w || !h) return;
    this.renderer.setSize(w, h, false);
    this.camera.aspect = w / h;
    this.camera.updateProjectionMatrix();
  }

  // base: URDF 가 있는 폴더 URL (메시 상대 경로 기준)
  async load(urdfUrl, base, view) {
    const xml = new DOMParser().parseFromString(await (await fetch(urdfUrl)).text(), 'application/xml');
    const robot = xml.querySelector('robot');
    const namedMat = {};
    robot.querySelectorAll(':scope > material').forEach(m => {
      const c = m.querySelector('color'); if (c) namedMat[m.getAttribute('name')] = nums(c.getAttribute('rgba'));
    });
    const links = {}, childOf = new Set(), jointsXml = [...robot.querySelectorAll(':scope > joint')];
    const waits = [];
    robot.querySelectorAll(':scope > link').forEach(l => {
      const g = new THREE.Group(); g.name = l.getAttribute('name');
      l.querySelectorAll(':scope > visual').forEach(v => {
        const vo = originOf(v); g.add(vo);
        const geo = v.querySelector('geometry');
        const me = v.querySelector('material');
        let rgba = [0.8, 0.8, 0.82, 1];
        if (me) { const c = me.querySelector('color'); rgba = c ? nums(c.getAttribute('rgba')) : (namedMat[me.getAttribute('name')] || rgba); }
        const mat = new THREE.MeshStandardMaterial({ color: new THREE.Color(rgba[0], rgba[1], rgba[2]), roughness: 0.6, metalness: 0.05,
          transparent: rgba[3] < 1, opacity: rgba[3] });
        const box = geo.querySelector('box'), cyl = geo.querySelector('cylinder'), sph = geo.querySelector('sphere'), msh = geo.querySelector('mesh');
        if (box) { const s = nums(box.getAttribute('size')); vo.add(new THREE.Mesh(new THREE.BoxGeometry(...s), mat)); }
        else if (cyl) {
          const m = new THREE.Mesh(new THREE.CylinderGeometry(+cyl.getAttribute('radius'), +cyl.getAttribute('radius'), +cyl.getAttribute('length'), 40), mat);
          m.rotation.x = Math.PI / 2; vo.add(m);                    // URDF 원기둥 축 = Z
        } else if (sph) vo.add(new THREE.Mesh(new THREE.SphereGeometry(+sph.getAttribute('radius'), 32, 16), mat));
        else if (msh) {
          const sc = nums(msh.getAttribute('scale'), [1, 1, 1]);
          const url = base + msh.getAttribute('filename').replace(/^file:\/\//, '');
          waits.push(loadSTL(url).then(geom => { const m = new THREE.Mesh(geom, mat); m.scale.set(...sc); vo.add(m); }).catch(() => {}));
        }
      });
      links[g.name] = g;
    });
    this.joints = {};
    jointsXml.forEach(j => {
      const parent = links[j.querySelector('parent').getAttribute('link')], child = links[j.querySelector('child').getAttribute('link')];
      if (!parent || !child) return;
      childOf.add(child.name);
      const o = originOf(j); parent.add(o);
      const mover = new THREE.Group(); o.add(mover); mover.add(child);
      const type = j.getAttribute('type');
      if (type === 'revolute' || type === 'continuous') {
        const ax = nums(j.querySelector('axis') && j.querySelector('axis').getAttribute('xyz'), [1, 0, 0]);
        this.joints[j.getAttribute('name')] = { mover, axis: new THREE.Vector3(...ax).normalize() };
      }
    });
    if (this.root) this.scene.remove(this.root);
    this.root = new THREE.Group();
    Object.values(links).filter(l => !childOf.has(l.name)).forEach(l => this.root.add(l));
    this.scene.add(this.root);
    await Promise.all(waits);
    const v = view || { target: [0, 0, 0.15], eye: [0.55, -0.55, 0.45] };
    this.controls.target.set(...v.target);
    this.camera.position.set(...v.eye);
    this.resize();
  }

  // values: {관절이름: 라디안}
  setJoints(values) {
    for (const [n, a] of Object.entries(values)) {
      const j = this.joints[n]; if (j) j.mover.quaternion.setFromAxisAngle(j.axis, a);
    }
  }
}
