import * as THREE from 'three';
/** Presentation only. Never changes physics radius, pickup or scoring. */
export function ballPresentation(depth: number, fov: number, height: number) {
  const metresPerPixel = 2 * Math.max(0.5, depth) * Math.tan(fov * Math.PI / 360) / Math.max(1, height);
  const scale = Math.min(2.5, Math.max(1, 6 * metresPerPixel / 0.167));
  return { scale, minorPixels: 0.167 * scale / metresPerPixel, locatorMetres: metresPerPixel * 14 };
}
export class BallReadability {
  readonly locator: THREE.Sprite;
  minorPixels = 0;
  constructor(scene: THREE.Scene, ball: THREE.Group) {
    const canvas = document.createElement('canvas'); canvas.width = canvas.height = 64;
    const ctx = canvas.getContext('2d')!;
    ctx.beginPath(); ctx.arc(32, 32, 22, 0, Math.PI * 2);
    ctx.strokeStyle = '#151515'; ctx.lineWidth = 11; ctx.stroke();
    ctx.strokeStyle = '#ffef66'; ctx.lineWidth = 5; ctx.stroke();
    this.locator = new THREE.Sprite(new THREE.SpriteMaterial({ map: new THREE.CanvasTexture(canvas), depthTest: false, depthWrite: false }));
    this.locator.renderOrder = 50;
    scene.add(this.locator);
    ball.traverse(node => {
      if (node instanceof THREE.Mesh) {
        const materials = Array.isArray(node.material) ? node.material : [node.material];
        for (const mat of materials) if (mat.name === 'leather' && 'color' in mat) (mat as THREE.MeshStandardMaterial).color.set('#f1ce32');
      }
    });
  }
  update(ball: THREE.Group, camera: THREE.PerspectiveCamera, height: number, active: boolean): void {
    camera.updateMatrixWorld(true);
    const view = ball.position.clone().applyMatrix4(camera.matrixWorldInverse);
    const policy = ballPresentation(-view.z, camera.fov, height);
    ball.scale.setScalar(0.19 * policy.scale);
    this.minorPixels = policy.minorPixels;
    // Locator remains available where occlusion or a tiny silhouette loses the ball.
    this.locator.visible = active && view.z < -camera.near;
    this.locator.position.copy(ball.position);
    this.locator.scale.setScalar(policy.locatorMetres);
  }
}
