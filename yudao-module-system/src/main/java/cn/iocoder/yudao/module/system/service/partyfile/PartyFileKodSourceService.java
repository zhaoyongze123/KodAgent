package cn.iocoder.yudao.module.system.service.partyfile;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodFolderRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodSourcePageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource.PartyFileKodSourceSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileKodSourceDO;

import java.util.List;

public interface PartyFileKodSourceService {

    Long create(PartyFileKodSourceSaveReqVO reqVO);

    void update(PartyFileKodSourceSaveReqVO reqVO);

    void delete(Long id);

    PartyFileKodSourceDO get(Long id);

    List<PartyFileKodSourceDO> getSimpleList();

    PageResult<PartyFileKodSourceDO> getPage(PartyFileKodSourcePageReqVO reqVO);

    List<PartyFileKodFolderRespVO> getFolderTree(Long id);
}
