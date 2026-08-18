package cn.iocoder.yudao.module.bpm.service.definition;

import cn.hutool.core.collection.CollUtil;
import cn.hutool.core.date.LocalDateTimeUtil;
import cn.hutool.core.util.ObjectUtil;
import cn.iocoder.yudao.framework.common.pojo.PageResult;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.process.BpmProcessDefinitionRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplatePageReqVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplateRespVO;
import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.template.BpmApprovalTemplateUpdateReqVO;
import cn.iocoder.yudao.module.bpm.convert.definition.BpmProcessDefinitionConvert;
import cn.iocoder.yudao.module.bpm.dal.dataobject.definition.BpmApprovalTemplateDO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.definition.BpmCategoryDO;
import cn.iocoder.yudao.module.bpm.dal.dataobject.definition.BpmProcessDefinitionInfoDO;
import cn.iocoder.yudao.module.bpm.dal.mysql.template.BpmApprovalTemplateMapper;
import org.flowable.common.engine.impl.db.SuspensionState;
import org.flowable.engine.repository.Deployment;
import org.flowable.engine.repository.ProcessDefinition;
import org.springframework.stereotype.Service;
import org.springframework.transaction.annotation.Transactional;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.*;
import java.util.stream.Collectors;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.framework.common.util.collection.CollectionUtils.convertList;
import static cn.iocoder.yudao.framework.common.util.collection.CollectionUtils.convertSet;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.APPROVAL_TEMPLATE_NOT_EXISTS;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.PROCESS_DEFINITION_NOT_EXISTS;
import static cn.iocoder.yudao.module.bpm.enums.ErrorCodeConstants.PROCESS_DEFINITION_IS_SUSPENDED;

/**
 * BPM 审批模板 Service 实现类
 *
 * @author Codex
 */
@Service
@Validated
public class BpmApprovalTemplateServiceImpl implements BpmApprovalTemplateService {

    private static final String TEMPLATE_CODE_PREFIX = "tpl:";

    @Resource
    private BpmApprovalTemplateMapper approvalTemplateMapper;
    @Resource
    private BpmProcessDefinitionService processDefinitionService;
    @Resource
    private BpmCategoryService categoryService;

    @Override
    public PageResult<BpmApprovalTemplateRespVO> getApprovalTemplatePage(BpmApprovalTemplatePageReqVO pageReqVO) {
        syncTemplatesFromActiveDefinitions();
        PageResult<BpmApprovalTemplateDO> pageResult = approvalTemplateMapper.selectPage(pageReqVO);
        if (CollUtil.isEmpty(pageResult.getList())) {
            return PageResult.empty(pageResult.getTotal());
        }
        return buildTemplatePage(pageResult);
    }

    @Override
    public BpmApprovalTemplateRespVO getApprovalTemplate(Long id) {
        syncTemplatesFromActiveDefinitions();
        BpmApprovalTemplateDO template = validateApprovalTemplateExists(id);
        return buildTemplateRespVOList(Collections.singletonList(template)).get(0);
    }

    @Override
    @Transactional(rollbackFor = Exception.class)
    public void updateApprovalTemplate(BpmApprovalTemplateUpdateReqVO reqVO) {
        BpmApprovalTemplateDO template = validateApprovalTemplateExists(reqVO.getId());
        ProcessDefinition processDefinition = processDefinitionService.getProcessDefinition(reqVO.getProcessDefinitionId());
        if (processDefinition == null) {
            throw exception(PROCESS_DEFINITION_NOT_EXISTS);
        }
        if (processDefinition.isSuspended()) {
            throw exception(PROCESS_DEFINITION_IS_SUSPENDED);
        }
        BpmProcessDefinitionInfoDO processDefinitionInfo = processDefinitionService.getProcessDefinitionInfo(processDefinition.getId());
        if (processDefinitionInfo == null) {
            throw exception(PROCESS_DEFINITION_NOT_EXISTS);
        }

        BpmApprovalTemplateDO updateObj = new BpmApprovalTemplateDO();
        updateObj.setId(template.getId());
        updateObj.setName(reqVO.getName());
        updateObj.setDescription(reqVO.getDescription());
        updateObj.setIcon(reqVO.getIcon());
        updateObj.setVisible(reqVO.getVisible());
        updateObj.setSort(reqVO.getSort());
        updateObj.setCategory(processDefinitionInfo.getCategory());
        updateObj.setProcessDefinitionId(processDefinition.getId());
        updateObj.setProcessDefinitionKey(processDefinition.getKey());
        updateObj.setModelId(processDefinitionInfo.getModelId());
        approvalTemplateMapper.updateById(updateObj);
    }

    @Override
    public void updateApprovalTemplateVisible(Long id, Boolean visible) {
        validateApprovalTemplateExists(id);
        BpmApprovalTemplateDO updateObj = new BpmApprovalTemplateDO();
        updateObj.setId(id);
        updateObj.setVisible(visible);
        approvalTemplateMapper.updateById(updateObj);
    }

    @Override
    public List<BpmProcessDefinitionRespVO> getApprovalTemplateList(Long userId) {
        syncTemplatesFromActiveDefinitions();
        List<BpmApprovalTemplateDO> templates = approvalTemplateMapper.selectAllOrderBySort();
        if (CollUtil.isEmpty(templates)) {
            return Collections.emptyList();
        }
        Set<String> processDefinitionIds = convertSet(templates, BpmApprovalTemplateDO::getProcessDefinitionId);
        Map<String, ProcessDefinition> processDefinitionMap = processDefinitionService.getProcessDefinitionMap(processDefinitionIds);
        Map<String, BpmProcessDefinitionInfoDO> processDefinitionInfoMap = processDefinitionService.getProcessDefinitionInfoMap(processDefinitionIds);
        Map<String, Deployment> deploymentMap = processDefinitionService.getDeploymentMap(
                convertSet(processDefinitionMap.values(), ProcessDefinition::getDeploymentId));
        Map<String, BpmCategoryDO> categoryMap = categoryService.getCategoryMap(
                convertSet(templates, BpmApprovalTemplateDO::getCategory));
        List<BpmProcessDefinitionRespVO> result = new ArrayList<>();
        for (BpmApprovalTemplateDO template : templates) {
            ProcessDefinition processDefinition = processDefinitionMap.get(template.getProcessDefinitionId());
            BpmProcessDefinitionInfoDO processDefinitionInfo = processDefinitionInfoMap.get(template.getProcessDefinitionId());
            if (processDefinition == null || processDefinitionInfo == null) {
                continue;
            }
            if (Boolean.FALSE.equals(template.getVisible())
                    || !processDefinitionService.canUserStartProcessDefinition(processDefinitionInfo, userId)) {
                continue;
            }
            Deployment deployment = deploymentMap.get(processDefinition.getDeploymentId());
            BpmCategoryDO category = categoryMap.get(template.getCategory());
            BpmProcessDefinitionRespVO respVO = BpmProcessDefinitionConvert.INSTANCE.buildProcessDefinition(
                    processDefinition, deployment, processDefinitionInfo, null, category, null);
            overlayTemplate(respVO, template, category);
            result.add(respVO);
        }
        result.sort(Comparator.comparing(item -> ObjectUtil.defaultIfNull(item.getSort(), 0L)));
        return result;
    }

    private PageResult<BpmApprovalTemplateRespVO> buildTemplatePage(PageResult<BpmApprovalTemplateDO> pageResult) {
        List<BpmApprovalTemplateRespVO> list = buildTemplateRespVOList(pageResult.getList());
        return new PageResult<>(list, pageResult.getTotal());
    }

    private List<BpmApprovalTemplateRespVO> buildTemplateRespVOList(List<BpmApprovalTemplateDO> templates) {
        Set<String> processDefinitionIds = convertSet(templates, BpmApprovalTemplateDO::getProcessDefinitionId);
        Map<String, ProcessDefinition> processDefinitionMap = processDefinitionService.getProcessDefinitionMap(processDefinitionIds);
        Map<String, BpmProcessDefinitionInfoDO> processDefinitionInfoMap = processDefinitionService.getProcessDefinitionInfoMap(processDefinitionIds);
        Map<String, Deployment> deploymentMap = processDefinitionService.getDeploymentMap(
                convertSet(processDefinitionMap.values(), ProcessDefinition::getDeploymentId));
        Map<String, BpmCategoryDO> categoryMap = categoryService.getCategoryMap(convertSet(templates, BpmApprovalTemplateDO::getCategory));
        return convertList(templates, template -> {
            BpmApprovalTemplateRespVO respVO = BeanUtils.toBean(template, BpmApprovalTemplateRespVO.class);
            ProcessDefinition processDefinition = processDefinitionMap.get(template.getProcessDefinitionId());
            BpmProcessDefinitionInfoDO processDefinitionInfo = processDefinitionInfoMap.get(template.getProcessDefinitionId());
            BpmCategoryDO category = categoryMap.get(template.getCategory());
            if (category != null) {
                respVO.setCategoryName(category.getName());
            }
            if (processDefinition != null) {
                respVO.setProcessDefinitionName(processDefinition.getName());
                respVO.setSuspensionState(processDefinition.isSuspended()
                        ? SuspensionState.SUSPENDED.getStateCode()
                        : SuspensionState.ACTIVE.getStateCode());
                Deployment deployment = deploymentMap.get(processDefinition.getDeploymentId());
                if (deployment != null) {
                    respVO.setDeploymentTime(LocalDateTimeUtil.of(deployment.getDeploymentTime()));
                }
            }
            if (processDefinitionInfo != null) {
                respVO.setModelId(processDefinitionInfo.getModelId());
                respVO.setModelType(processDefinitionInfo.getModelType());
                respVO.setFormType(processDefinitionInfo.getFormType());
            }
            return respVO;
        });
    }

    @Transactional(rollbackFor = Exception.class)
    protected void syncTemplatesFromActiveDefinitions() {
        List<ProcessDefinition> activeDefinitions = processDefinitionService.getProcessDefinitionListBySuspensionState(
                SuspensionState.ACTIVE.getStateCode());
        if (CollUtil.isEmpty(activeDefinitions)) {
            return;
        }
        Map<String, BpmProcessDefinitionInfoDO> processDefinitionInfoMap = processDefinitionService.getProcessDefinitionInfoMap(
                convertSet(activeDefinitions, ProcessDefinition::getId));
        List<BpmApprovalTemplateDO> templates = approvalTemplateMapper.selectAllOrderBySort();
        Map<String, BpmApprovalTemplateDO> templateByProcessKey = templates.stream()
                .filter(item -> item.getProcessDefinitionKey() != null)
                .collect(Collectors.toMap(BpmApprovalTemplateDO::getProcessDefinitionKey, item -> item, (left, right) -> left));
        Set<String> existingCodes = templates.stream()
                .map(BpmApprovalTemplateDO::getCode)
                .filter(Objects::nonNull)
                .collect(Collectors.toSet());
        int nextSort = templates.stream()
                .map(BpmApprovalTemplateDO::getSort)
                .filter(Objects::nonNull)
                .max(Integer::compareTo)
                .orElse(0) + 1;
        for (ProcessDefinition definition : activeDefinitions) {
            BpmProcessDefinitionInfoDO info = processDefinitionInfoMap.get(definition.getId());
            if (info == null) {
                continue;
            }
            BpmApprovalTemplateDO existed = templateByProcessKey.get(definition.getKey());
            if (existed == null) {
                String code = buildUniqueCode(definition.getKey(), existingCodes);
                approvalTemplateMapper.insert(BpmApprovalTemplateDO.builder()
                        .code(code)
                        .name(definition.getName())
                        .description(info.getDescription())
                        .icon(info.getIcon())
                        .category(info.getCategory())
                        .visible(Boolean.TRUE.equals(info.getVisible()))
                        .sort(nextSort++)
                        .processDefinitionId(definition.getId())
                        .processDefinitionKey(definition.getKey())
                        .modelId(info.getModelId())
                        .build());
                existingCodes.add(code);
                continue;
            }
            boolean needUpdate = !Objects.equals(existed.getProcessDefinitionId(), definition.getId())
                    || !Objects.equals(existed.getModelId(), info.getModelId())
                    || !Objects.equals(existed.getCategory(), info.getCategory());
            if (!needUpdate) {
                continue;
            }
            BpmApprovalTemplateDO updateObj = new BpmApprovalTemplateDO();
            updateObj.setId(existed.getId());
            updateObj.setProcessDefinitionId(definition.getId());
            updateObj.setProcessDefinitionKey(definition.getKey());
            updateObj.setModelId(info.getModelId());
            updateObj.setCategory(info.getCategory());
            approvalTemplateMapper.updateById(updateObj);
        }
    }

    private String buildUniqueCode(String processDefinitionKey, Set<String> existingCodes) {
        String base = TEMPLATE_CODE_PREFIX + processDefinitionKey;
        if (!existingCodes.contains(base)) {
            return base;
        }
        int index = 2;
        while (existingCodes.contains(base + "-" + index)) {
            index++;
        }
        return base + "-" + index;
    }

    private void overlayTemplate(BpmProcessDefinitionRespVO respVO, BpmApprovalTemplateDO template, BpmCategoryDO category) {
        respVO.setName(template.getName());
        respVO.setDescription(template.getDescription());
        respVO.setIcon(template.getIcon());
        respVO.setCategory(template.getCategory());
        respVO.setVisible(template.getVisible());
        respVO.setSort(template.getSort() == null ? 0L : template.getSort().longValue());
        if (category != null) {
            respVO.setCategoryName(category.getName());
        }
    }

    private BpmApprovalTemplateDO validateApprovalTemplateExists(Long id) {
        BpmApprovalTemplateDO template = approvalTemplateMapper.selectById(id);
        if (template == null) {
            throw exception(APPROVAL_TEMPLATE_NOT_EXISTS);
        }
        return template;
    }

}
