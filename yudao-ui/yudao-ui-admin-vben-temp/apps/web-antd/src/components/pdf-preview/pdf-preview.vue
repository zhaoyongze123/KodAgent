<script lang="ts" setup>
import { nextTick, onBeforeUnmount, ref, watch } from 'vue';

import * as pdfjsLib from 'pdfjs-dist';
import workerSrc from 'pdfjs-dist/build/pdf.worker.min.mjs?url';

pdfjsLib.GlobalWorkerOptions.workerSrc = workerSrc;

const props = defineProps<{
  source?: BlobPart;
}>();

const loading = ref(false);
const error = ref('');
const pages = ref<number[]>([]);
const pageCanvases = new Map<number, HTMLCanvasElement>();
let pdfDocument: pdfjsLib.PDFDocumentProxy | null = null;
let renderToken = 0;

function setCanvasRef(pageNumber: number, element: Element | null) {
  if (element instanceof HTMLCanvasElement) {
    pageCanvases.set(pageNumber, element);
  } else {
    pageCanvases.delete(pageNumber);
  }
}

async function toArrayBuffer(source: BlobPart) {
  if (source instanceof Blob) {
    return source.arrayBuffer();
  }
  if (source instanceof ArrayBuffer) {
    return source;
  }
  if (ArrayBuffer.isView(source)) {
    return source.buffer.slice(source.byteOffset, source.byteOffset + source.byteLength);
  }
  return new TextEncoder().encode(String(source)).buffer;
}

async function renderDocument(source?: BlobPart) {
  const token = ++renderToken;
  pages.value = [];
  pageCanvases.clear();
  error.value = '';
  if (pdfDocument) {
    await pdfDocument.destroy();
    pdfDocument = null;
  }
  if (!source) {
    return;
  }

  loading.value = true;
  try {
    const loadingTask = pdfjsLib.getDocument({ data: await toArrayBuffer(source) });
    pdfDocument = await loadingTask.promise;
    if (token !== renderToken) {
      return;
    }
    pages.value = Array.from({ length: pdfDocument.numPages }, (_, index) => index + 1);
    await nextTick();
    for (const pageNumber of pages.value) {
      if (token !== renderToken || !pdfDocument) {
        return;
      }
      const page = await pdfDocument.getPage(pageNumber);
      const viewport = page.getViewport({ scale: 1.35 });
      const canvas = pageCanvases.get(pageNumber);
      if (!canvas) {
        continue;
      }
      const context = canvas.getContext('2d');
      if (!context) {
        continue;
      }
      canvas.width = viewport.width;
      canvas.height = viewport.height;
      await page.render({ canvasContext: context, viewport }).promise;
    }
  } catch (renderError) {
    console.error('PDF 预览渲染失败', renderError);
    error.value = 'PDF 预览失败，请尝试下载文件查看';
  } finally {
    if (token === renderToken) {
      loading.value = false;
    }
  }
}

watch(() => props.source, renderDocument, { immediate: true });

onBeforeUnmount(() => {
  renderToken += 1;
  if (pdfDocument) {
    void pdfDocument.destroy();
  }
});
</script>

<template>
  <div class="pdf-preview">
    <div v-if="loading" class="pdf-preview__state">正在生成预览...</div>
    <div v-else-if="error" class="pdf-preview__state pdf-preview__state--error">
      {{ error }}
    </div>
    <div v-else class="pdf-preview__pages">
      <canvas
        v-for="pageNumber in pages"
        :key="pageNumber"
        :ref="(element) => setCanvasRef(pageNumber, element as Element | null)"
        class="pdf-preview__page"
      />
    </div>
  </div>
</template>

<style scoped>
.pdf-preview {
  min-height: 420px;
  overflow: auto;
  background: #f1f3f5;
}

.pdf-preview__state {
  display: grid;
  min-height: 420px;
  place-items: center;
  color: #64748b;
}

.pdf-preview__state--error {
  color: #dc2626;
}

.pdf-preview__pages {
  display: grid;
  justify-items: center;
  gap: 18px;
  padding: 20px;
}

.pdf-preview__page {
  max-width: 100%;
  height: auto;
  background: #fff;
  box-shadow: 0 2px 10px rgb(15 23 42 / 12%);
}
</style>
