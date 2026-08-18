package cn.iocoder.yudao.module.system.service.auth;

import cn.iocoder.yudao.module.system.controller.admin.auth.vo.KodDeptSyncRespVO;

public interface KodDeptSyncService {

    KodDeptSyncRespVO sync(Long tenantId);
}
