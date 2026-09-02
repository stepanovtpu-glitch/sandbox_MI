import { useEffect, useRef } from 'react';
import * as THREE from 'three';

type PipelineSceneProps = {
  status: 'pass' | 'fail' | 'warn';
  flowmeterLabel: string;
};

const STATUS_COLORS: Record<PipelineSceneProps['status'], number> = {
  pass: 0x46b578,
  warn: 0xd4a041,
  fail: 0xe06e63,
};

export function PipelineScene({ status, flowmeterLabel }: PipelineSceneProps) {
  const mountRef = useRef<HTMLDivElement>(null);
  const statusRef = useRef(status);
  statusRef.current = status;

  useEffect(() => {
    const mount = mountRef.current;
    if (!mount) return;

    let renderer: THREE.WebGLRenderer;
    try {
      renderer = new THREE.WebGLRenderer({ antialias: true, alpha: true });
    } catch {
      return; // без WebGL остаётся SVG-схема под сценой
    }
    const reduced = window.matchMedia('(prefers-reduced-motion: reduce)').matches;
    renderer.setPixelRatio(Math.min(window.devicePixelRatio, 2));
    mount.appendChild(renderer.domElement);

    const scene = new THREE.Scene();
    const camera = new THREE.PerspectiveCamera(35, 2, 0.1, 60);
    camera.position.set(0, 1.4, 8.2);
    camera.lookAt(0, 0, 0);

    scene.add(new THREE.AmbientLight(0x51646f, 1.15));
    const key = new THREE.DirectionalLight(0xcfe4ee, 1.35);
    key.position.set(4, 7, 5);
    scene.add(key);
    const rim = new THREE.PointLight(0x2eb08f, 1.3, 26);
    rim.position.set(-6, 2.5, 3.5);
    scene.add(rim);
    const cool = new THREE.PointLight(0x4f9dc9, 0.9, 26);
    cool.position.set(6, -2.5, 3);
    scene.add(cool);

    const group = new THREE.Group();
    const steel = new THREE.MeshStandardMaterial({ color: 0x9aa8b1, metalness: 0.92, roughness: 0.3 });
    const housing = new THREE.MeshStandardMaterial({ color: 0x344855, metalness: 0.82, roughness: 0.42 });
    const lampMaterial = new THREE.MeshStandardMaterial({
      color: STATUS_COLORS[status],
      emissive: STATUS_COLORS[status],
      emissiveIntensity: 0.9,
      roughness: 0.4,
    });

    const pipe = new THREE.Mesh(new THREE.CylinderGeometry(0.5, 0.5, 13, 48), steel);
    pipe.rotation.z = Math.PI / 2;
    group.add(pipe);

    [-4.2, -2.1, 2.1, 4.2].forEach((x) => {
      const flange = new THREE.Mesh(new THREE.CylinderGeometry(0.74, 0.74, 0.2, 48), housing);
      flange.rotation.z = Math.PI / 2;
      flange.position.x = x;
      group.add(flange);
    });

    const body = new THREE.Mesh(new THREE.CylinderGeometry(0.78, 0.78, 1.4, 48), housing);
    body.rotation.z = Math.PI / 2;
    group.add(body);
    const neck = new THREE.Mesh(new THREE.CylinderGeometry(0.24, 0.3, 1.0, 32), steel);
    neck.position.y = 0.95;
    group.add(neck);
    const head = new THREE.Mesh(new THREE.BoxGeometry(1.05, 0.68, 0.78), housing);
    head.position.y = 1.7;
    group.add(head);
    const lamp = new THREE.Mesh(new THREE.SphereGeometry(0.085, 24, 24), lampMaterial);
    lamp.position.set(0.38, 1.9, 0.4);
    group.add(lamp);

    const sensorGeometry = new THREE.CylinderGeometry(0.16, 0.2, 0.7, 24);
    [-2.9, 2.9].forEach((x) => {
      const sensor = new THREE.Mesh(sensorGeometry, steel);
      sensor.position.set(x, 0.75, 0);
      group.add(sensor);
    });

    group.rotation.set(0.1, -0.32, 0.02);
    group.position.set(0.2, -0.25, 0);
    scene.add(group);

    let mouseX = 0;
    let mouseY = 0;
    const onMove = (event: MouseEvent) => {
      const rect = mount.getBoundingClientRect();
      mouseX = (event.clientX - rect.left) / rect.width - 0.5;
      mouseY = (event.clientY - rect.top) / rect.height - 0.5;
    };
    if (!reduced) mount.addEventListener('mousemove', onMove);

    const resize = () => {
      const width = mount.clientWidth;
      const height = mount.clientHeight;
      if (!width || !height) return;
      renderer.setSize(width, height, false);
      camera.aspect = width / height;
      camera.updateProjectionMatrix();
    };
    const observer = new ResizeObserver(resize);
    observer.observe(mount);
    resize();

    let frameId = 0;
    let t = 0;
    const renderFrame = () => {
      const color = STATUS_COLORS[statusRef.current];
      lampMaterial.color.setHex(color);
      lampMaterial.emissive.setHex(color);
      if (!reduced) {
        t += 0.004;
        group.rotation.y = -0.32 + Math.sin(t) * 0.08 + mouseX * 0.2;
        group.rotation.x = 0.1 + mouseY * 0.1;
        lampMaterial.emissiveIntensity = 0.7 + Math.sin(t * 5) * 0.35;
      }
      renderer.render(scene, camera);
      if (!reduced) frameId = requestAnimationFrame(renderFrame);
    };
    renderFrame();
    if (reduced) renderer.render(scene, camera);

    return () => {
      cancelAnimationFrame(frameId);
      observer.disconnect();
      if (!reduced) mount.removeEventListener('mousemove', onMove);
      renderer.dispose();
      mount.removeChild(renderer.domElement);
      scene.traverse((object) => {
        if (object instanceof THREE.Mesh) {
          object.geometry.dispose();
          const material = object.material;
          (Array.isArray(material) ? material : [material]).forEach((item) => item.dispose());
        }
      });
    };
    // Сцена собирается один раз; статус лампы обновляется через statusRef без пересоздания.
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, []);

  return (
    <div className="pipeline-scene" ref={mountRef} aria-label={`3D-модель измерительной линии: ${flowmeterLabel}`} role="img" />
  );
}
