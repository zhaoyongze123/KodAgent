package cn.iocoder.yudao.module.system.dal.mysql.partyfile;

import cn.iocoder.yudao.framework.mybatis.core.mapper.BaseMapperX;
import cn.iocoder.yudao.framework.mybatis.core.query.LambdaQueryWrapperX;
import cn.iocoder.yudao.module.system.dal.dataobject.partyfile.PartyFileKodAttachmentDO;
import org.apache.ibatis.annotations.Mapper;

@Mapper
public interface PartyFileKodAttachmentMapper extends BaseMapperX<PartyFileKodAttachmentDO> {

    default PartyFileKodAttachmentDO selectByFileId(Long fileId) {
        return selectOne(new LambdaQueryWrapperX<PartyFileKodAttachmentDO>()
                .eq(PartyFileKodAttachmentDO::getFileId, fileId));
    }
}
