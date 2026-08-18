package cn.iocoder.yudao.module.system.enums.partyfile;

import lombok.AllArgsConstructor;
import lombok.Getter;

import java.util.Arrays;

@Getter
@AllArgsConstructor
public enum PartyFileReadSourceEnum {

    DETAIL(1, "详情"),
    DOWNLOAD(2, "下载"),
    PREVIEW(3, "预览");

    private final Integer source;
    private final String name;

    public static PartyFileReadSourceEnum fromAction(String action) {
        if ("preview".equalsIgnoreCase(action)) {
            return PREVIEW;
        }
        return DOWNLOAD;
    }

    public static String getNameBySource(Integer source) {
        return Arrays.stream(values())
                .filter(item -> item.getSource().equals(source))
                .map(PartyFileReadSourceEnum::getName)
                .findFirst()
                .orElse("详情");
    }
}
