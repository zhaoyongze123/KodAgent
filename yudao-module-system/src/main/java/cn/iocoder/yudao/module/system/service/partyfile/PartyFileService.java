package cn.iocoder.yudao.module.system.service.partyfile;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileMyPageReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileRespVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFileSaveReqVO;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.file.PartyFilePageReqVO;

public interface PartyFileService {

    Long createPartyFile(PartyFileSaveReqVO reqVO);

    void updatePartyFile(PartyFileSaveReqVO reqVO);

    void deletePartyFile(Long id);

    PageResult<PartyFileRespVO> getPartyFilePage(PartyFilePageReqVO reqVO);

    PartyFileRespVO getPartyFileDetail(Long id);

    PageResult<PartyFileRespVO> getMyPartyFilePage(Long userId, PartyFileMyPageReqVO reqVO);

    PartyFileRespVO getMyPartyFileDetail(Long id, Long userId, String userNickname);

    PartyFileRespVO getMyPartyFileAttachment(Long id, Long fileId, Long userId, String userNickname, Integer readSource);

    void validateAttachmentAccessible(Long id, Long fileId);
}
