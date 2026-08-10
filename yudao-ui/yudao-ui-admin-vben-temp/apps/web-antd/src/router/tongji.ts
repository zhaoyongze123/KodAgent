import type { Router } from 'vue-router';

import { useAppConfig } from '@vben/hooks';

declare global {
  interface Window {
    _hmt: any[];
  }
}

/**
 * 设置百度统计
 * @param router
 */
function setupBaiduTongJi(router: Router) {
  const { baiduAnalyticsCode: hmId } = useAppConfig(
    import.meta.env,
    import.meta.env.PROD,
  );
  // 如果没有配置百度统计的 ID，则不进行设置
  if (!hmId) {
    return;
  }

  // _hmt：用于 router push
  window._hmt = window._hmt || [];
  if (!document.querySelector('script[data-oa-baidu-tongji]')) {
    const script = document.createElement('script');
    script.dataset.oaBaiduTongji = 'true';
    script.src = `https://hm.baidu.com/hm.js?${hmId}`;
    document.head.append(script);
  }

  router.afterEach((to) => {
    // 添加到 _hmt 中
    window._hmt.push(['_trackPageview', to.fullPath]);
  });
}

export { setupBaiduTongJi };
