package cn.iocoder.yudao.module.system.service.partyfile;

import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.category.PartyFileCategorySaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileCategoryDO;

import java.util.List;

public interface PartyFileCategoryService {

    Long createCategory(PartyFileCategorySaveReqVO reqVO);

    void updateCategory(PartyFileCategorySaveReqVO reqVO);

    void deleteCategory(Long id);

    List<PartyFileCategoryDO> getCategoryList(Integer status);

    PartyFileCategoryDO getCategory(Long id);
}
