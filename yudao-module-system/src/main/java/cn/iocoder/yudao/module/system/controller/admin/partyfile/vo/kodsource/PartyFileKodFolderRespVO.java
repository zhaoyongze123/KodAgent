package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import java.util.List;

@Schema(description = "管理后台 - 党务文件可道云目录树节点 Response VO")
@Data
public class PartyFileKodFolderRespVO {

    private String key;

    private String title;

    private String value;

    private String path;

    /**
     * 是否为叶子目录。目录选择器按需展开目录时使用，避免一次性递归加载整棵目录树。
     */
    private Boolean isLeaf;

    private List<PartyFileKodFolderRespVO> children;
}
