import React, { useEffect, useRef } from 'react';
import * as THREE from 'three';
import { geoEquirectangular, geoPath } from 'd3-geo';
import { feature } from 'topojson-client';
import land from 'world-atlas/land-110m.json';
import { reducedMotion } from './viz.jsx';

const toVec = (lat, lon, r) => {
  const p = (lat * Math.PI) / 180; const l = (lon * Math.PI) / 180;
  return new THREE.Vector3(r * Math.cos(p) * Math.sin(l), r * Math.sin(p), r * Math.cos(p) * Math.cos(l));
};

function landDots() {
  const W = 720; const H = 360;
  const c = document.createElement('canvas'); c.width = W; c.height = H;
  const g = c.getContext('2d', { willReadFrequently: true });
  g.fillStyle = '#fff';
  g.beginPath();
  geoPath(geoEquirectangular().translate([W / 2, H / 2]).scale(W / (2 * Math.PI)), g)(feature(land, land.objects.land));
  g.fill();
  const px = g.getImageData(0, 0, W, H).data;
  const pts = [];
  for (let lat = -84; lat <= 84; lat += 1.15) {
    const n = Math.max(1, Math.round(Math.cos((lat * Math.PI) / 180) * 313));
    for (let i = 0; i < n; i++) {
      const lon = -180 + (i * 360) / n;
      const x = Math.floor(((lon + 180) / 360) * W); const y = Math.floor(((90 - lat) / 180) * H);
      if (px[(y * W + x) * 4 + 3] > 120) { const v = toVec(lat, lon, 1.002); pts.push(v.x, v.y, v.z); }
    }
  }
  return pts;
}

/** Earth with the 19-cell footprint and the beams BRIDGE really chose in the flood-relief run. Orbit scale is illustrative. */
export default function Globe({ cells, lit, emergencyFrom = 28 }) {
  const ref = useRef(null);
  useEffect(() => {
    const canvas = ref.current;
    let renderer;
    try { renderer = new THREE.WebGLRenderer({ canvas, antialias: true, alpha: true }); } catch { return undefined; }
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(32, 1, 0.1, 50);
    const center = { lat: 21, lon: 88 };          // Bay of Bengal: the demo footprint is a placeholder location
    scene.rotation.y = -(center.lon * Math.PI) / 180 + 0.12;
    scene.rotation.x = (center.lat * Math.PI) / 180 - 0.1;
    scene.add(new THREE.Mesh(new THREE.SphereGeometry(0.995, 64, 64), new THREE.MeshBasicMaterial({ color: 0x10151a })));
    const dots = new THREE.BufferGeometry();
    dots.setAttribute('position', new THREE.Float32BufferAttribute(landDots(), 3));
    scene.add(new THREE.Points(dots, new THREE.PointsMaterial({ color: 0x69767f, size: 0.0085 })));
    const rim = new THREE.Mesh(new THREE.SphereGeometry(1.012, 64, 64), new THREE.ShaderMaterial({
      transparent: true, side: THREE.BackSide, depthWrite: false,
      vertexShader: 'varying vec3 n; void main(){ n = normalize(normalMatrix*normal); gl_Position = projectionMatrix*modelViewMatrix*vec4(position,1.); }',
      fragmentShader: 'varying vec3 n; void main(){ float a = pow(max(0., .5 - abs(n.z)), 3.); gl_FragColor = vec4(.37,.89,.75, a*.55); }',
    }));
    rim.scale.setScalar(1.05);
    scene.add(rim);

    const xs = cells.map((c) => c.x); const ys = cells.map((c) => c.y);
    const mx = (Math.min(...xs) + Math.max(...xs)) / 2; const my = (Math.min(...ys) + Math.max(...ys)) / 2;
    const span = Math.max(Math.max(...xs) - Math.min(...xs), 1);
    const deg = 15 / span;                         // footprint exaggerated so the cells are visible at globe scale
    const pos = cells.map((c) => ({ lat: center.lat + (c.y - my) * deg, lon: center.lon + ((c.x - mx) * deg) / Math.cos((center.lat * Math.PI) / 180) }));
    const hexR = (15 / Math.sqrt(cells.length)) * 0.52 * Math.min(1, (Math.hypot(cells[1].x - cells[0].x, cells[1].y - cells[0].y) * deg) / (15 / Math.sqrt(cells.length)));
    const fills = pos.map((p) => {
      const shape = [];
      for (let i = 0; i <= 6; i++) {
        const a = Math.PI / 6 + (i * Math.PI) / 3;
        shape.push(toVec(p.lat + hexR * Math.sin(a) * 0.96, p.lon + (hexR * Math.cos(a) * 0.96) / Math.cos((p.lat * Math.PI) / 180), 1.006));
      }
      const c = toVec(p.lat, p.lon, 1.006);
      const v = [];
      for (let i = 0; i < 6; i++) v.push(c.x, c.y, c.z, shape[i].x, shape[i].y, shape[i].z, shape[i + 1].x, shape[i + 1].y, shape[i + 1].z);
      const g = new THREE.BufferGeometry(); g.setAttribute('position', new THREE.Float32BufferAttribute(v, 3));
      const mesh = new THREE.Mesh(g, new THREE.MeshBasicMaterial({ color: 0x5fe3c0, transparent: true, opacity: 0.08, side: THREE.DoubleSide, depthWrite: false }));
      scene.add(mesh);
      const outline = new THREE.Line(new THREE.BufferGeometry().setFromPoints(shape), new THREE.LineBasicMaterial({ color: 0x5fe3c0, transparent: true, opacity: 0.4 }));
      scene.add(outline);
      return mesh;
    });

    const satOrbit = 1.34;
    const sat = new THREE.Group();
    sat.add(new THREE.Mesh(new THREE.OctahedronGeometry(0.018), new THREE.MeshBasicMaterial({ color: 0xece7dc })));
    const panel = new THREE.Mesh(new THREE.BoxGeometry(0.1, 0.002, 0.024), new THREE.MeshBasicMaterial({ color: 0x3c9bdc }));
    sat.add(panel);
    scene.add(sat);
    const orbitPts = [];
    for (let i = 0; i <= 100; i++) orbitPts.push(toVec(center.lat - 26 + i * 0.52, center.lon - 34 + i * 0.68, satOrbit));
    scene.add(new THREE.Line(new THREE.BufferGeometry().setFromPoints(orbitPts), new THREE.LineDashedMaterial({ color: 0x868e94, dashSize: 0.018, gapSize: 0.018 })).computeLineDistances());
    const beams = [0, 1, 2, 3].map(() => {
      const geom = new THREE.BufferGeometry().setFromPoints([new THREE.Vector3(), new THREE.Vector3()]);
      const l = new THREE.Line(geom, new THREE.LineBasicMaterial({ color: 0x5fe3c0, transparent: true, opacity: 0.85 }));
      scene.add(l); return l;
    });

    const resize = () => {
      const { clientWidth: w, clientHeight: h } = canvas;
      renderer.setSize(w, h, false);
      camera.aspect = w / h; camera.position.set(0, 0, 3.9); camera.lookAt(0, 0, 0);
      camera.updateProjectionMatrix();
    };
    const ro = new ResizeObserver(resize); ro.observe(canvas); resize();

    let raf; let visible = true;
    const io = new IntersectionObserver(([e]) => { visible = e.isIntersecting; }); io.observe(canvas);
    const still = reducedMotion();
    const start = performance.now();
    const frame = (now) => {
      raf = requestAnimationFrame(frame);
      if (!visible) return;
      const secs = (now - start) / 1000;
      const slot = still ? 52 : Math.floor(secs / 0.2) % lit.length;     // 200 ms per slot: 20x slower than real time
      const f = still ? 0.55 : 0.35 + 0.35 * ((secs / 40) % 1);    // stay above the footprint
      const satP = toVec(center.lat - 26 + f * 52, center.lon - 34 + f * 68, satOrbit);
      sat.position.copy(satP);
      const now_lit = lit[slot] || [];
      fills.forEach((m, i) => { const target = now_lit.includes(i) ? 0.82 : 0.07; m.material.opacity += (target - m.material.opacity) * 0.35; });
      beams.forEach((b, i) => {
        const c = now_lit[i];
        b.visible = c != null;
        if (c != null) { const e = toVec(pos[c].lat, pos[c].lon, 1.006); b.geometry.setFromPoints([satP, e]); }
      });
      renderer.render(scene, camera);
    };
    raf = requestAnimationFrame(frame);
    return () => { cancelAnimationFrame(raf); ro.disconnect(); io.disconnect(); renderer.dispose(); };
  }, [cells, lit, emergencyFrom]);
  return <canvas ref={ref} className="globe" aria-hidden="true" />;
}
