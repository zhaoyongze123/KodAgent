package cn.iocoder.yudao.module.bpm.service.oa;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import cn.iocoder.yudao.module.bpm.api.task.BpmProcessInstanceApi;
import cn.iocoder.yudao.module.bpm.api.task.dto.BpmProcessInstanceCreateReqDTO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOADocumentCreateReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.oa.vo.BpmOADocumentPageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.oa.BpmOADocumentDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.oa.BpmOADocumentMapper;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import cn.iocoder.yudao.module.system.api.dept.DeptApi;
import cn.iocoder.yudao.module.system.api.dept.dto.DeptRespDTO;
import cn.iocoder.yudao.module.system.api.user.AdminUserApi;
import cn.iocoder.yudao.module.system.api.user.dto.AdminUserRespDTO;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.HashMap;
import java.util.Map;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.OA_DOCUMENT_NOT_EXISTS;

@Service
@Validated
public class BpmOADocumentServiceImpl implements BpmOADocumentService {

    public static final String PROCESS_KEY = "oa_document";

    @Resource
    private BpmOADocumentMapper documentMapper;
    @Resource
    private BpmProcessInstanceApi processInstanceApi;
    @Resource
    private AdminUserApi adminUserApi;
    @Resource
    private DeptApi deptApi;

    @Override
    @Transactional(rollbackFor = Exception.class)
    public Long createDocument(Long userId, BpmOADocumentCreateReqVO createReqVO) {
        AdminUserRespDTO user = adminUserApi.getUser(userId);
        DeptRespDTO dept = user != null && user.getDeptId() != null ? deptApi.getDept(user.getDeptId()) : null;
        BpmOADocumentDO document = BpmOADocumentDO.builder()
                .userId(userId)
                .applicantName(user != null ? user.getNickname() : null)
                .deptId(user != null ? user.getDeptId() : null)
                .deptName(dept != null ? dept.getName() : null)
                .fileType(createReqVO.getFileType())
                .title(createReqVO.getTitle())
                .relatedProject(createReqVO.getRelatedProject())
                .counterpartUnit(createReqVO.getCounterpartUnit())
                .amount(createReqVO.getAmount())
                .reason(createReqVO.getReason())
                .attachmentBodyUrls(JsonUtils.toJsonString(createReqVO.getAttachmentBodyUrls()))
                .attachmentExtraUrls(JsonUtils.toJsonString(createReqVO.getAttachmentExtraUrls()))
                .remark(createReqVO.getRemark())
                .status(BpmTaskStatusEnum.RUNNING.getStatus())
                .build();
        documentMapper.insert(document);

        Map<String, Object> processInstanceVariables = new HashMap<>();
        processInstanceVariables.put("amount", createReqVO.getAmount());
        String processInstanceId = processInstanceApi.createProcessInstance(userId,
                new BpmProcessInstanceCreateReqDTO().setProcessDefinitionKey(PROCESS_KEY)
                        .setVariables(processInstanceVariables).setBusinessKey(String.valueOf(document.getId()))
                        .setStartUserSelectAssignees(createReqVO.getStartUserSelectAssignees()));
        documentMapper.updateById(new BpmOADocumentDO().setId(document.getId()).setProcessInstanceId(processInstanceId));
        return document.getId();
    }

    @Override
    public void updateDocumentStatus(Long id, Integer status) {
        validateDocumentExists(id);
        documentMapper.updateById(new BpmOADocumentDO().setId(id).setStatus(status));
    }

    private void validateDocumentExists(Long id) {
        if (documentMapper.selectById(id) == null) {
            throw exception(OA_DOCUMENT_NOT_EXISTS);
        }
    }

    @Override
    public BpmOADocumentDO getDocument(Long id) {
        return documentMapper.selectById(id);
    }

    @Override
    public PageResult<BpmOADocumentDO> getDocumentPage(Long userId, BpmOADocumentPageReqVO pageReqVO) {
        return documentMapper.selectPage(userId, pageReqVO);
    }

}
