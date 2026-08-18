package cn.iocoder.yudao.module.bpm.dal.mysql.template;

import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplatePageReqVO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.definition.BpmApprovalTemplateDO;
import org.apache.ibatis.annotations.Mapper;

import java.util.Collection;
import java.util.List;

/**
 * BPM 审批模板 Mapper
 *
 * @author Codex
 */
@Mapper
public interface BpmApprovalTemplateMapper extends BaseMapperX<BpmApprovalTemplateDO> {

    default PageResult<BpmApprovalTemplateDO> selectPage(BpmApprovalTemplatePageReqVO reqVO) {
        return selectPage(reqVO, new LambdaQueryWrapperX<BpmApprovalTemplateDO>()
                .likeIfPresent(BpmApprovalTemplateDO::getName, reqVO.getName())
                .eqIfPresent(BpmApprovalTemplateDO::getCategory, reqVO.getCategory())
                .eqIfPresent(BpmApprovalTemplateDO::getVisible, reqVO.getVisible())
                .likeIfPresent(BpmApprovalTemplateDO::getProcessDefinitionKey, reqVO.getProcessDefinitionKey())
                .betweenIfPresent(BpmApprovalTemplateDO::getCreateTime, reqVO.getCreateTime())
                .orderByAsc(BpmApprovalTemplateDO::getSort)
                .orderByDesc(BpmApprovalTemplateDO::getId));
    }

    default BpmApprovalTemplateDO selectByCode(String code) {
        return selectOne(BpmApprovalTemplateDO::getCode, code);
    }

    default BpmApprovalTemplateDO selectByProcessDefinitionId(String processDefinitionId) {
        return selectOne(BpmApprovalTemplateDO::getProcessDefinitionId, processDefinitionId);
    }

    default List<BpmApprovalTemplateDO> selectListByProcessDefinitionIds(Collection<String> processDefinitionIds) {
        return selectList(BpmApprovalTemplateDO::getProcessDefinitionId, processDefinitionIds);
    }

    default List<BpmApprovalTemplateDO> selectListByProcessDefinitionKeys(Collection<String> processDefinitionKeys) {
        return selectList(BpmApprovalTemplateDO::getProcessDefinitionKey, processDefinitionKeys);
    }

    default List<BpmApprovalTemplateDO> selectAllOrderBySort() {
        return selectList(new LambdaQueryWrapperX<BpmApprovalTemplateDO>()
                .orderByAsc(BpmApprovalTemplateDO::getSort)
                .orderByDesc(BpmApprovalTemplateDO::getId));
    }

}
