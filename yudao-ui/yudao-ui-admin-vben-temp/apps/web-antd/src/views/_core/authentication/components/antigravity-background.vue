<script lang="ts" setup>
import { onBeforeUnmount, onMounted, ref } from 'vue';

type Particle = {
  alpha: number;
  angle: number;
  baseSpeed: number;
  color: string;
  length: number;
  speed: number;
  width: number;
  x: number;
  y: number;
};

const canvasRef = ref<HTMLCanvasElement>();

let animationFrameId = 0;
let resizeHandler: (() => void) | null = null;
let mouseMoveHandler: ((event: MouseEvent) => void) | null = null;

onMounted(() => {
  const canvas = canvasRef.value;
  if (!canvas) {
    return;
  }
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return;
  }

  let width = window.innerWidth;
  let height = window.innerHeight;
  canvas.width = width;
  canvas.height = height;

  const mouse = {
    targetX: width / 2,
    targetY: height / 2,
    x: width / 2,
    y: height / 2,
  };
  const colors = [
    '#2563eb',
    '#60a5fa',
    '#9333ea',
    '#db2777',
    '#f59e0b',
    '#ef4444',
    '#10b981',
  ];

  const initParticle = (
    particle: Partial<Particle> = {},
    centerX = width / 2,
    centerY = height / 2,
  ): Particle => {
    const angle = Math.random() * Math.PI * 2;
    const distance = Math.random() * (Math.max(width, height) / 2);
    return {
      alpha: Math.random() * 0.6 + 0.2,
      angle,
      baseSpeed: Math.random() * 0.5 + 0.1,
      color: colors[Math.floor(Math.random() * colors.length)]!,
      length: Math.random() * 4 + 2,
      speed: Math.random() * 0.5 + 0.1,
      width: Math.random() * 1.5 + 0.5,
      x: centerX + Math.cos(angle) * distance,
      y: centerY + Math.sin(angle) * distance,
      ...particle,
    };
  };

  const particles: Particle[] = [];
  const particleCount = Math.floor((width * height) / 3000);
  for (let index = 0; index < particleCount; index += 1) {
    particles.push(initParticle());
  }

  mouseMoveHandler = (event: MouseEvent) => {
    mouse.targetX = event.clientX;
    mouse.targetY = event.clientY;
  };

  const render = () => {
    mouse.x += (mouse.targetX - mouse.x) * 0.05;
    mouse.y += (mouse.targetY - mouse.y) * 0.05;

    ctx.fillStyle = 'rgba(255, 255, 255, 0.28)';
    ctx.fillRect(0, 0, width, height);

    const centerX = mouse.x;
    const centerY = mouse.y;
    const maxDistance = Math.max(width, height) / 1.5;

    particles.forEach((particle, index) => {
      const dx = particle.x - centerX;
      const dy = particle.y - centerY;
      const currentDistance = Math.sqrt(dx * dx + dy * dy);
      const targetAngle = Math.atan2(dy, dx);

      let angleDiff = targetAngle - particle.angle;
      while (angleDiff > Math.PI) {
        angleDiff -= Math.PI * 2;
      }
      while (angleDiff < -Math.PI) {
        angleDiff += Math.PI * 2;
      }

      particle.angle += angleDiff * 0.03;
      particle.speed = particle.baseSpeed * (1 + currentDistance / 150);
      particle.x += Math.cos(particle.angle) * particle.speed;
      particle.y += Math.sin(particle.angle) * particle.speed;

      const fadeOut = Math.max(0, 1 - currentDistance / maxDistance);
      if (currentDistance > maxDistance) {
        particles[index] = initParticle(
          {
            x: centerX + Math.cos(particle.angle) * (Math.random() * 50 + 20),
            y: centerY + Math.sin(particle.angle) * (Math.random() * 50 + 20),
          },
          centerX,
          centerY,
        );
        return;
      }

      ctx.save();
      ctx.translate(particle.x, particle.y);
      ctx.rotate(particle.angle);
      ctx.beginPath();
      ctx.moveTo(0, 0);
      ctx.lineTo(particle.length, 0);
      ctx.lineWidth = particle.width;
      ctx.strokeStyle = particle.color;
      ctx.globalAlpha = particle.alpha * fadeOut;
      ctx.lineCap = 'round';
      ctx.stroke();
      ctx.restore();
    });

    animationFrameId = window.requestAnimationFrame(render);
  };

  resizeHandler = () => {
    width = window.innerWidth;
    height = window.innerHeight;
    canvas.width = width;
    canvas.height = height;
  };

  window.addEventListener('mousemove', mouseMoveHandler);
  window.addEventListener('resize', resizeHandler);
  render();
});

onBeforeUnmount(() => {
  window.cancelAnimationFrame(animationFrameId);
  if (mouseMoveHandler) {
    window.removeEventListener('mousemove', mouseMoveHandler);
  }
  if (resizeHandler) {
    window.removeEventListener('resize', resizeHandler);
  }
});
</script>

<template>
  <canvas ref="canvasRef" class="auth-bg-canvas" />
</template>

<style scoped>
.auth-bg-canvas {
  background: #ffffff;
  inset: 0;
  pointer-events: none;
  position: fixed;
  z-index: 0;
}
</style>
