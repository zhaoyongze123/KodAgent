package cn.iocoder.yudao.module.system.enums.partyfile;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public enum PartyFileTargetTypeEnum {

    ALL(1, "全员"),
    USER(2, "用户"),
    DEPT(3, "部门"),
    ROLE(4, "角色");

    private final Integer type;
    private final String name;
}
