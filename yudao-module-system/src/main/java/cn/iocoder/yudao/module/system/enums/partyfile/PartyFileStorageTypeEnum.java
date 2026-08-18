package cn.iocoder.yudao.module.system.enums.partyfile;

import lombok.AllArgsConstructor;
import lombok.Getter;

@Getter
@AllArgsConstructor
public enum PartyFileStorageTypeEnum {

    LOCAL(1, "本地"),
    KOD(2, "可道云");

    private final Integer type;
    private final String name;

    public static boolean isKod(Integer type) {
        return KOD.type.equals(type);
    }
}
