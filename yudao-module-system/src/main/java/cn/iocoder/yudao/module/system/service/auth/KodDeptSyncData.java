package cn.iocoder.yudao.module.system.service.auth;

import lombok.Data;

import java.util.ArrayList;
import java.util.List;

/**
 * 可道云组织同步插件的稳定 JSON 契约。
 */
@Data
public class KodDeptSyncData {

    private Boolean success;
    private Integer departmentCount;
    private Integer userCount;
    private Integer createdSourceCount;
    private Integer revokedPermissionCount;
    private String message;
    private List<Group> groups = new ArrayList<>();
    private List<UserGroups> users = new ArrayList<>();

    @Data
    public static class Group {
        private String groupId;
        private String parentGroupId;
        private String name;
        private Integer status;
        private Integer sort;
        private Long sourceId;
    }

    @Data
    public static class UserGroups {
        private String userId;
        private List<String> groupIds = new ArrayList<>();
    }
}
