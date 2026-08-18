package cn.iocoder.yudao.module.system.service.partyfile;

import cn.iocoder.yudao.framework.common.enums.CommonStatusEnum;
import cn.iocoder.yudao.framework.common.util.object.BeanUtils;
import cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.category.PartyFileCategorySaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileCategoryDO;
import cn.iocoder.yudao.module.system.dal.mysql.partyfile.PartyFileCategoryMapper;
import org.springframework.stereotype.Service;
import org.springframework.validation.annotation.Validated;

import javax.annotation.Resource;
import java.util.Collection;
import java.util.Collections;
import java.util.List;
import java.util.Objects;

import static cn.iocoder.yudao.framework.common.exception.util.ServiceExceptionUtil.exception;
import static cn.iocoder.yudao.module.system.enums.ErrorCodeConstants.*;

@Service
@Validated
public class PartyFileCategoryServiceImpl implements PartyFileCategoryService {

    private static final Long ROOT_PARENT_ID = 0L;

    @Resource
    private PartyFileCategoryMapper categoryMapper;

    @Override
    public Long createCategory(PartyFileCategorySaveReqVO reqVO) {
        validateParent(reqVO.getParentId(), null);
        validateNameUnique(reqVO.getParentId(), reqVO.getName(), null);
        PartyFileCategoryDO category = BeanUtils.toBean(reqVO, PartyFileCategoryDO.class);
        categoryMapper.insert(category);
        return category.getId();
    }

    @Override
    public void updateCategory(PartyFileCategorySaveReqVO reqVO) {
        validateExists(reqVO.getId());
        validateParent(reqVO.getParentId(), reqVO.getId());
        validateNameUnique(reqVO.getParentId(), reqVO.getName(), reqVO.getId());
        categoryMapper.updateById(BeanUtils.toBean(reqVO, PartyFileCategoryDO.class));
    }

    @Override
    public void deleteCategory(Long id) {
        validateExists(id);
        List<PartyFileCategoryDO> children = categoryMapper.selectListByParentId(Collections.singleton(id));
        if (!children.isEmpty()) {
            throw exception(PARTY_FILE_CATEGORY_HAS_CHILDREN);
        }
        categoryMapper.deleteById(id);
    }

    @Override
    public List<PartyFileCategoryDO> getCategoryList(Integer status) {
        return categoryMapper.selectListByStatus(status);
    }

    @Override
    public PartyFileCategoryDO getCategory(Long id) {
        return categoryMapper.selectById(id);
    }

    private void validateExists(Long id) {
        if (categoryMapper.selectById(id) == null) {
            throw exception(PARTY_FILE_CATEGORY_NOT_FOUND);
        }
    }

    private void validateParent(Long parentId, Long id) {
        if (parentId == null || ROOT_PARENT_ID.equals(parentId)) {
            return;
        }
        if (Objects.equals(parentId, id)) {
            throw exception(PARTY_FILE_CATEGORY_PARENT_ERROR);
        }
        PartyFileCategoryDO parent = categoryMapper.selectById(parentId);
        if (parent == null) {
            throw exception(PARTY_FILE_CATEGORY_PARENT_NOT_FOUND);
        }
        if (!Objects.equals(parent.getStatus(), CommonStatusEnum.ENABLE.getStatus())) {
            throw exception(PARTY_FILE_CATEGORY_PARENT_DISABLED);
        }
        Long currentParentId = parent.getParentId();
        while (currentParentId != null && !ROOT_PARENT_ID.equals(currentParentId)) {
            if (Objects.equals(currentParentId, id)) {
                throw exception(PARTY_FILE_CATEGORY_PARENT_ERROR);
            }
            PartyFileCategoryDO currentParent = categoryMapper.selectById(currentParentId);
            if (currentParent == null) {
                break;
            }
            currentParentId = currentParent.getParentId();
        }
    }

    private void validateNameUnique(Long parentId, String name, Long id) {
        PartyFileCategoryDO exists = categoryMapper.selectByParentIdAndName(parentId, name);
        if (exists == null) {
            return;
        }
        if (id == null || !Objects.equals(exists.getId(), id)) {
            throw exception(PARTY_FILE_CATEGORY_NAME_DUPLICATE);
        }
    }
}
