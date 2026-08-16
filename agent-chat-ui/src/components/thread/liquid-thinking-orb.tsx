"use client";

/**
 * 对话运行中的液态玻璃球。
 *
 * 作用：这是一个纯展示组件，只根据运行状态决定是否播放视觉反馈。它不读取
 * ``report_progress``、工具参数或模型文本，业务过程仍由摘要与工具事件区域展示。
 *
 * 渲染策略：优先使用一个小型、项目自有的 WebGPU Shader 表现液态折射；浏览器不
 * 支持 WebGPU 时持续使用原始 Shader。球体离开视口、用户启用“减少动态效果”、
 * 标签页隐藏或设备丢失时才停止帧循环并保留 CSS 静态玻璃球。运行结束只会收起
 * Thinking 胶囊，不会把已完成回合的球体降级为另一套视觉效果。
 */

import { motion } from "framer-motion";
import { useEffect, useRef, useState } from "react";

import { cn } from "@/lib/utils";
import {
  LIQUID_GLASS_SHADER,
  LIQUID_GLASS_UNIFORM_SEED,
  LIQUID_THINKING_FRAGMENT_ENTRY_POINT,
  LIQUID_THINKING_VERTEX_ENTRY_POINT,
} from "./liquid-thinking-shader";

type WebGpuCanvasContext = {
  configure(descriptor: unknown): void;
  getCurrentTexture(): { createView(): unknown };
};

type WebGpuDevice = {
  createShaderModule(descriptor: unknown): unknown;
  createRenderPipeline(descriptor: unknown): {
    getBindGroupLayout(index: number): unknown;
  };
  createBuffer(descriptor: unknown): unknown;
  createBindGroup(descriptor: unknown): unknown;
  createCommandEncoder(): {
    beginRenderPass(descriptor: unknown): {
      setPipeline(pipeline: unknown): void;
      setBindGroup(index: number, bindGroup: unknown): void;
      draw(vertexCount: number): void;
      end(): void;
    };
    finish(): unknown;
  };
  queue: {
    writeBuffer(buffer: unknown, offset: number, data: ArrayBufferView): void;
    submit(commandBuffers: unknown[]): void;
  };
  lost?: Promise<unknown>;
};

type WebGpuAdapter = {
  requestDevice(): Promise<WebGpuDevice>;
};

type WebGpuApi = {
  getPreferredCanvasFormat(): string;
  requestAdapter(): Promise<WebGpuAdapter | null>;
};

type WebGpuRuntime = {
  device: WebGpuDevice;
  format: string;
  usage: { COPY_DST: number; UNIFORM: number };
};

let sharedRuntime: Promise<WebGpuRuntime | null> | undefined;

function getWebGpuRuntime(): Promise<WebGpuRuntime | null> {
  if (sharedRuntime) return sharedRuntime;

  sharedRuntime = (async () => {
    const gpu = (navigator as Navigator & { gpu?: WebGpuApi }).gpu;
    const usage = (
      globalThis as typeof globalThis & {
        GPUBufferUsage?: { COPY_DST: number; UNIFORM: number };
      }
    ).GPUBufferUsage;
    if (!gpu || !usage) return null;

    const adapter = await gpu.requestAdapter();
    if (!adapter) return null;

    return {
      device: await adapter.requestDevice(),
      format: gpu.getPreferredCanvasFormat(),
      usage,
    };
  })().catch(() => null);

  return sharedRuntime;
}

export function LiquidThinkingOrb({
  fullSize,
  animate,
  failed,
}: {
  /** 运行与完成态均使用完整球体，只有紧凑嵌入场景才允许缩小。 */
  fullSize: boolean;
  animate: boolean;
  failed: boolean;
}) {
  const canvasRef = useRef<HTMLCanvasElement>(null);
  const [webGpuReady, setWebGpuReady] = useState(false);
  // 尺寸和 Shader 生命周期独立：完成态移除 Thinking 文案，但保留同样大小的
  // 液态球。只有不可见、减少动态效果或失败状态才停止原始 Shader。
  const shouldAnimate = animate && !failed;

  useEffect(() => {
    const canvas = canvasRef.current;
    if (!canvas || !shouldAnimate) {
      setWebGpuReady(false);
      return;
    }

    let cancelled = false;
    let frameId = 0;
    let resizeObserver: ResizeObserver | undefined;
    let removeVisibilityListener: (() => void) | undefined;
    let draw: (now: number) => void = () => undefined;

    void (async () => {
      try {
        const runtime = await getWebGpuRuntime();
        if (!runtime || cancelled) return;

        const context = canvas.getContext(
          "webgpu",
        ) as unknown as WebGpuCanvasContext | null;
        if (!context) return;

        const { device, format, usage } = runtime;
        context.configure({ device, format, alphaMode: "premultiplied" });
        const shader = device.createShaderModule({ code: LIQUID_GLASS_SHADER });
        const pipeline = device.createRenderPipeline({
          layout: "auto",
          vertex: {
            module: shader,
            entryPoint: LIQUID_THINKING_VERTEX_ENTRY_POINT,
          },
          fragment: {
            module: shader,
            entryPoint: LIQUID_THINKING_FRAGMENT_ENTRY_POINT,
            targets: [{ format }],
          },
          primitive: { topology: "triangle-list" },
        });
        const values = new Float32Array(LIQUID_GLASS_UNIFORM_SEED);
        const uniformBuffer = device.createBuffer({
          size: values.byteLength,
          usage: usage.UNIFORM | usage.COPY_DST,
        });
        const bindGroup = device.createBindGroup({
          layout: pipeline.getBindGroupLayout(0),
          entries: [{ binding: 0, resource: { buffer: uniformBuffer } }],
        });

        const resize = () => {
          const bounds = canvas.getBoundingClientRect();
          const ratio = Math.min(window.devicePixelRatio || 1, 2);
          const width = Math.max(1, Math.round(bounds.width * ratio));
          const height = Math.max(1, Math.round(bounds.height * ratio));
          if (canvas.width !== width || canvas.height !== height) {
            canvas.width = width;
            canvas.height = height;
          }
          values[0] = width;
          values[1] = height;
        };

        resize();
        if (typeof ResizeObserver !== "undefined") {
          resizeObserver = new ResizeObserver(resize);
          resizeObserver.observe(canvas);
        }
        setWebGpuReady(true);

        void device.lost?.then(() => {
          sharedRuntime = undefined;
          if (!cancelled) setWebGpuReady(false);
        });

        draw = (now: number) => {
          frameId = 0;
          if (cancelled || document.visibilityState === "hidden") return;
          try {
            values[2] = now / 1000;
            device.queue.writeBuffer(uniformBuffer, 0, values);
            const encoder = device.createCommandEncoder();
            const pass = encoder.beginRenderPass({
              colorAttachments: [
                {
                  view: context.getCurrentTexture().createView(),
                  clearValue: { r: 0, g: 0, b: 0, a: 0 },
                  loadOp: "clear",
                  storeOp: "store",
                },
              ],
            });
            pass.setPipeline(pipeline);
            pass.setBindGroup(0, bindGroup);
            pass.draw(3);
            pass.end();
            device.queue.submit([encoder.finish()]);
            frameId = requestAnimationFrame(draw);
          } catch {
            // 设备在运行中丢失时回落为静态球，不保留透明画布。
            setWebGpuReady(false);
          }
        };

        const syncVisibility = () => {
          if (document.visibilityState === "hidden") {
            cancelAnimationFrame(frameId);
            frameId = 0;
            return;
          }
          if (!cancelled && frameId === 0)
            frameId = requestAnimationFrame(draw);
        };

        document.addEventListener("visibilitychange", syncVisibility);
        removeVisibilityListener = () =>
          document.removeEventListener("visibilitychange", syncVisibility);
        syncVisibility();
        if (cancelled) removeVisibilityListener();
      } catch {
        // WebGPU 只是增强效果。初始化失败时保留 CSS 玻璃球，不能影响聊天运行。
        if (!cancelled) setWebGpuReady(false);
      }
    })();

    return () => {
      cancelled = true;
      cancelAnimationFrame(frameId);
      resizeObserver?.disconnect();
      removeVisibilityListener?.();
    };
  }, [shouldAnimate]);

  return (
    <motion.span
      aria-hidden="true"
      className={cn(
        "relative flex shrink-0 items-center justify-center",
        // 原始效果依赖球内的连续纹理。运行和完成均保留 40px 画布，避免缩小
        // 后只剩一块难以辨认的高光；完成态只移除 Thinking 胶囊。
        fullSize ? "size-10" : "size-7",
      )}
      animate={{ opacity: 1, scale: fullSize ? 1 : 0.72 }}
      transition={{ duration: 0.18, ease: "easeOut" }}
    >
      <span
        className={cn(
          "absolute inset-0 rounded-full border shadow-[inset_0_1px_1px_rgb(255_255_255_/_0.95),0_1px_3px_rgb(14_116_144_/_0.18)] transition-opacity duration-150",
          failed
            ? "border-red-200 bg-red-50"
            : "border-sky-100 bg-[radial-gradient(circle_at_30%_24%,rgba(255,255,255,0.98)_0_14%,rgba(224,242,254,0.94)_34%,rgba(125,211,252,0.72)_100%)]",
          webGpuReady && "opacity-0",
        )}
      />
      <canvas
        ref={canvasRef}
        className={cn(
          "absolute inset-0 size-full transition-opacity duration-150",
          webGpuReady ? "opacity-100" : "opacity-0",
        )}
      />
    </motion.span>
  );
}
