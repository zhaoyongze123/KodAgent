package cn.iocoder.yudao.module.system.controller.admin.partyfile.vo.kodsource;

import io.swagger.v3.oas.annotations.media.Schema;
import lombok.Data;

import javax.validation.constraints.NotBlank;
import javax.validation.constraints.NotNull;
import javax.validation.constraints.Size;

@Data
public class PartyFileKodSourceBaseVO {

    @Schema(description = "来源名称", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "来源名称不能为空")
    @Size(max = 100, message = "来源名称不能超过 100 个字符")
    private String name;

    @Schema(description = "可道云地址", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "可道云地址不能为空")
    @Size(max = 255, message = "可道云地址不能超过 255 个字符")
    private String baseUrl;

    @Schema(description = "appName", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "appName 不能为空")
    @Size(max = 100, message = "appName 不能超过 100 个字符")
    private String appName;

    @Schema(description = "访问令牌")
    @Size(max = 1024, message = "访问令牌不能超过 1024 个字符")
    private String accessToken;

    @Schema(description = "服务账号")
    @Size(max = 100, message = "服务账号不能超过 100 个字符")
    private String serviceUsername;

    @Schema(description = "服务密码")
    @Size(max = 255, message = "服务密码不能超过 255 个字符")
    private String servicePassword;

    @Schema(description = "根目录路径", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "根目录路径不能为空")
    @Size(max = 512, message = "根目录路径不能超过 512 个字符")
    private String rootFolderPath;

    @Schema(description = "根目录名称", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotBlank(message = "根目录名称不能为空")
    @Size(max = 255, message = "根目录名称不能超过 255 个字符")
    private String rootFolderName;

    @Schema(description = "状态", requiredMode = Schema.RequiredMode.REQUIRED)
    @NotNull(message = "状态不能为空")
    private Integer status;

    @Schema(description = "是否默认")
    private Boolean isDefault;
}
