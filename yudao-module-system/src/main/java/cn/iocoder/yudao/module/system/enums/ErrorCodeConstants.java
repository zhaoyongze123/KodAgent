package cn.iocoder.yudao.module.system.enums;

import cn.iocoder.yudao.framework.common.exception.ErrorCode;

/**
 * System 错误码枚举类
 *
 * system 系统，使用 1-002-000-000 段
 */
public interface ErrorCodeConstants {

    // ========== AUTH 模块 1-002-000-000 ==========
    ErrorCode AUTH_LOGIN_BAD_CREDENTIALS = new ErrorCode(1_002_000_000, "登录失败，账号密码不正确");
    ErrorCode AUTH_LOGIN_USER_DISABLED = new ErrorCode(1_002_000_001, "登录失败，账号被禁用");
    ErrorCode AUTH_LOGIN_CAPTCHA_CODE_ERROR = new ErrorCode(1_002_000_004, "验证码不正确，原因：{}");
    ErrorCode AUTH_THIRD_LOGIN_NOT_BIND = new ErrorCode(1_002_000_005, "未绑定账号，需要进行绑定");
    ErrorCode AUTH_MOBILE_NOT_EXISTS = new ErrorCode(1_002_000_007, "手机号不存在");
    ErrorCode AUTH_REGISTER_CAPTCHA_CODE_ERROR = new ErrorCode(1_002_000_008, "验证码不正确，原因：{}");
    ErrorCode AUTH_KOD_SSO_DISABLED = new ErrorCode(1_002_000_009, "可道云单点登录未启用");
    ErrorCode AUTH_KOD_SSO_BAD_REQUEST = new ErrorCode(1_002_000_010, "可道云单点登录配置不完整或参数不合法，原因：{}");
    ErrorCode AUTH_KOD_SSO_TOKEN_INVALID = new ErrorCode(1_002_000_011, "可道云单点登录失败，原因：{}");
    ErrorCode AUTH_KOD_SSO_EXCHANGE_CODE_NOT_FOUND = new ErrorCode(1_002_000_012, "可道云登录换票码不存在或已过期");
    ErrorCode AUTH_KOD_SSO_AUTO_CREATE_DISABLED = new ErrorCode(1_002_000_013, "当前可道云账号未绑定本地用户，且未开启自动创建");
    ErrorCode AUTH_KOD_SSO_REDIRECT_URI_INVALID = new ErrorCode(1_002_000_014, "可道云回跳地址不合法");

    // ========== 菜单模块 1-002-001-000 ==========
    ErrorCode MENU_NAME_DUPLICATE = new ErrorCode(1_002_001_000, "已经存在该名字的菜单");
    ErrorCode MENU_PARENT_NOT_EXISTS = new ErrorCode(1_002_001_001, "父菜单不存在");
    ErrorCode MENU_PARENT_ERROR = new ErrorCode(1_002_001_002, "不能设置自己为父菜单");
    ErrorCode MENU_NOT_EXISTS = new ErrorCode(1_002_001_003, "菜单不存在");
    ErrorCode MENU_EXISTS_CHILDREN = new ErrorCode(1_002_001_004, "存在子菜单，无法删除");
    ErrorCode MENU_PARENT_NOT_DIR_OR_MENU = new ErrorCode(1_002_001_005, "父菜单的类型必须是目录或者菜单");
    ErrorCode MENU_COMPONENT_NAME_DUPLICATE = new ErrorCode(1_002_001_006, "已经存在该组件名的菜单");

    // ========== 角色模块 1-002-002-000 ==========
    ErrorCode ROLE_NOT_EXISTS = new ErrorCode(1_002_002_000, "角色不存在");
    ErrorCode ROLE_NAME_DUPLICATE = new ErrorCode(1_002_002_001, "已经存在名为【{}】的角色");
    ErrorCode ROLE_CODE_DUPLICATE = new ErrorCode(1_002_002_002, "已经存在标识为【{}】的角色");
    ErrorCode ROLE_CAN_NOT_UPDATE_SYSTEM_TYPE_ROLE = new ErrorCode(1_002_002_003, "不能操作类型为系统内置的角色");
    ErrorCode ROLE_IS_DISABLE = new ErrorCode(1_002_002_004, "名字为【{}】的角色已被禁用");
    ErrorCode ROLE_ADMIN_CODE_ERROR = new ErrorCode(1_002_002_005, "标识【{}】不能使用");

    // ========== 用户模块 1-002-003-000 ==========
    ErrorCode USER_USERNAME_EXISTS = new ErrorCode(1_002_003_000, "用户账号已经存在");
    ErrorCode USER_MOBILE_EXISTS = new ErrorCode(1_002_003_001, "手机号已经存在");
    ErrorCode USER_EMAIL_EXISTS = new ErrorCode(1_002_003_002, "邮箱已经存在");
    ErrorCode USER_NOT_EXISTS = new ErrorCode(1_002_003_003, "用户不存在");
    ErrorCode USER_IMPORT_LIST_IS_EMPTY = new ErrorCode(1_002_003_004, "导入用户数据不能为空！");
    ErrorCode USER_PASSWORD_FAILED = new ErrorCode(1_002_003_005, "用户密码校验失败");
    ErrorCode USER_IS_DISABLE = new ErrorCode(1_002_003_006, "名字为【{}】的用户已被禁用");
    ErrorCode USER_COUNT_MAX = new ErrorCode(1_002_003_008, "创建用户失败，原因：超过租户最大租户配额({})！");
    ErrorCode USER_IMPORT_INIT_PASSWORD = new ErrorCode(1_002_003_009, "初始密码不能为空");
    ErrorCode USER_MOBILE_NOT_EXISTS = new ErrorCode(1_002_003_010, "该手机号尚未注册");
    ErrorCode USER_REGISTER_DISABLED = new ErrorCode(1_002_003_011, "注册功能已关闭");

    // ========== 部门模块 1-002-004-000 ==========
    ErrorCode DEPT_NAME_DUPLICATE = new ErrorCode(1_002_004_000, "已经存在该名字的部门");
    ErrorCode DEPT_PARENT_NOT_EXITS = new ErrorCode(1_002_004_001,"父级部门不存在");
    ErrorCode DEPT_NOT_FOUND = new ErrorCode(1_002_004_002, "当前部门不存在");
    ErrorCode DEPT_EXITS_CHILDREN = new ErrorCode(1_002_004_003, "存在子部门，无法删除");
    ErrorCode DEPT_PARENT_ERROR = new ErrorCode(1_002_004_004, "不能设置自己为父部门");
    ErrorCode DEPT_NOT_ENABLE = new ErrorCode(1_002_004_006, "部门({})不处于开启状态，不允许选择");
    ErrorCode DEPT_PARENT_IS_CHILD = new ErrorCode(1_002_004_007, "不能设置自己的子部门为父部门");

    // ========== 岗位模块 1-002-005-000 ==========
    ErrorCode POST_NOT_FOUND = new ErrorCode(1_002_005_000, "当前岗位不存在");
    ErrorCode POST_NOT_ENABLE = new ErrorCode(1_002_005_001, "岗位({}) 不处于开启状态，不允许选择");
    ErrorCode POST_NAME_DUPLICATE = new ErrorCode(1_002_005_002, "已经存在该名字的岗位");
    ErrorCode POST_CODE_DUPLICATE = new ErrorCode(1_002_005_003, "已经存在该标识的岗位");

    // ========== 字典类型 1-002-006-000 ==========
    ErrorCode DICT_TYPE_NOT_EXISTS = new ErrorCode(1_002_006_001, "当前字典类型不存在");
    ErrorCode DICT_TYPE_NOT_ENABLE = new ErrorCode(1_002_006_002, "字典类型不处于开启状态，不允许选择");
    ErrorCode DICT_TYPE_NAME_DUPLICATE = new ErrorCode(1_002_006_003, "已经存在该名字的字典类型");
    ErrorCode DICT_TYPE_TYPE_DUPLICATE = new ErrorCode(1_002_006_004, "已经存在该类型的字典类型");
    ErrorCode DICT_TYPE_HAS_CHILDREN = new ErrorCode(1_002_006_005, "无法删除，该字典类型还有字典数据");

    // ========== 字典数据 1-002-007-000 ==========
    ErrorCode DICT_DATA_NOT_EXISTS = new ErrorCode(1_002_007_001, "当前字典数据不存在");
    ErrorCode DICT_DATA_NOT_ENABLE = new ErrorCode(1_002_007_002, "字典数据({})不处于开启状态，不允许选择");
    ErrorCode DICT_DATA_VALUE_DUPLICATE = new ErrorCode(1_002_007_003, "已经存在该值的字典数据");

    // ========== 通知公告 1-002-008-000 ==========
    ErrorCode NOTICE_NOT_FOUND = new ErrorCode(1_002_008_001, "当前通知公告不存在");
    ErrorCode NOTICE_TARGET_ID_REQUIRED = new ErrorCode(1_002_008_002, "公告发布对象编号不能为空");
    ErrorCode NOTICE_TARGET_TYPE_INVALID = new ErrorCode(1_002_008_003, "公告发布对象类型不合法");
    ErrorCode NOTICE_TARGET_ALL_CONFLICT = new ErrorCode(1_002_008_004, "选择全员发布时不能再追加其他发布对象");

    // ========== 党务文件 1-002-009-000 ==========
    ErrorCode PARTY_FILE_CATEGORY_NOT_FOUND = new ErrorCode(1_002_009_001, "党务文件分类不存在");
    ErrorCode PARTY_FILE_CATEGORY_NAME_DUPLICATE = new ErrorCode(1_002_009_002, "同级已存在同名党务文件分类");
    ErrorCode PARTY_FILE_CATEGORY_PARENT_NOT_FOUND = new ErrorCode(1_002_009_003, "父级党务文件分类不存在");
    ErrorCode PARTY_FILE_CATEGORY_PARENT_ERROR = new ErrorCode(1_002_009_004, "父级党务文件分类不能是自己或自己的子级");
    ErrorCode PARTY_FILE_CATEGORY_PARENT_DISABLED = new ErrorCode(1_002_009_005, "父级党务文件分类已被禁用");
    ErrorCode PARTY_FILE_CATEGORY_HAS_CHILDREN = new ErrorCode(1_002_009_006, "当前分类下还有子分类，无法删除");
    ErrorCode PARTY_FILE_NOT_FOUND = new ErrorCode(1_002_009_007, "党务文件不存在");
    ErrorCode PARTY_FILE_NOT_AUTHORIZED = new ErrorCode(1_002_009_008, "你无权查看该党务文件");
    ErrorCode PARTY_FILE_TARGET_ID_REQUIRED = new ErrorCode(1_002_009_009, "分发对象编号不能为空");
    ErrorCode PARTY_FILE_TARGET_TYPE_INVALID = new ErrorCode(1_002_009_010, "分发对象类型不合法");
    ErrorCode PARTY_FILE_TARGET_ALL_CONFLICT = new ErrorCode(1_002_009_011, "选择全员分发时不能再追加其他分发对象");
    ErrorCode PARTY_FILE_ATTACHMENT_NOT_FOUND = new ErrorCode(1_002_009_012, "党务文件附件不存在");
    ErrorCode PARTY_FILE_KOD_SOURCE_NOT_FOUND = new ErrorCode(1_002_009_013, "党务文件可道云目录来源不存在");
    ErrorCode PARTY_FILE_KOD_SOURCE_NAME_DUPLICATE = new ErrorCode(1_002_009_014, "已存在同名的可道云目录来源");
    ErrorCode PARTY_FILE_KOD_SOURCE_IN_USE = new ErrorCode(1_002_009_015, "当前可道云目录来源已被党务文件使用，无法删除");
    ErrorCode PARTY_FILE_STORAGE_CONFIG_INVALID = new ErrorCode(1_002_009_016, "党务文件存储配置不完整，请检查存储方式、可道云目录来源、服务账号和目标目录");
    ErrorCode PARTY_FILE_KOD_REQUEST_FAILED = new ErrorCode(1_002_009_017, "可道云请求失败，原因：{}");
    ErrorCode PARTY_FILE_KOD_FOLDER_PATH_INVALID = new ErrorCode(1_002_009_018, "可道云目录路径不合法");

    // ========== 会议室 1-002-009-000 ==========
    ErrorCode MEETING_ROOM_NOT_EXISTS = new ErrorCode(1_002_009_000, "会议室不存在");
    ErrorCode MEETING_ROOM_NAME_DUPLICATE = new ErrorCode(1_002_009_001, "已经存在名为【{}】的会议室");
    ErrorCode MEETING_ROOM_DISABLED = new ErrorCode(1_002_009_002, "会议室【{}】已停用，无法预定");

    // ========== 会议室预定 1-002-010-000 ==========
    ErrorCode MEETING_BOOKING_NOT_EXISTS = new ErrorCode(1_002_010_000, "会议室预定不存在");
    ErrorCode MEETING_BOOKING_TIME_INVALID = new ErrorCode(1_002_010_001, "会议时间不合法");
    ErrorCode MEETING_BOOKING_TIME_SLOT_INVALID = new ErrorCode(1_002_010_002, "会议时长必须为 15 分钟至 8 小时，且按 15 分钟递增");
    ErrorCode MEETING_BOOKING_CONFLICT_EXISTS = new ErrorCode(1_002_010_003, "当前时段存在冲突预定，请确认后重试");
    ErrorCode MEETING_BOOKING_NOT_OWNER = new ErrorCode(1_002_010_004, "只能操作自己的会议室预定");
    ErrorCode MEETING_BOOKING_STARTED_CANNOT_OPERATE = new ErrorCode(1_002_010_005, "会议已开始，无法继续修改或取消");
    ErrorCode MEETING_BOOKING_CROSS_DAY_NOT_SUPPORTED = new ErrorCode(1_002_010_006, "暂不支持跨天预定");
    ErrorCode MEETING_BOOKING_ALREADY_CANCELLED = new ErrorCode(1_002_010_007, "会议室预定已取消，无法再次修改或取消");

    // ========== 个人日程 1-002-017-000 ==========
    ErrorCode PERSONAL_SCHEDULE_NOT_EXISTS = new ErrorCode(1_002_017_000, "个人日程不存在");
    ErrorCode PERSONAL_SCHEDULE_TIME_INVALID = new ErrorCode(1_002_017_001, "日程时间不合法");
    ErrorCode PERSONAL_SCHEDULE_NOT_OWNER = new ErrorCode(1_002_017_002, "只能操作自己的个人日程");

    // ========== 短信渠道 1-002-011-000 ==========
    ErrorCode SMS_CHANNEL_NOT_EXISTS = new ErrorCode(1_002_011_000, "短信渠道不存在");
    ErrorCode SMS_CHANNEL_DISABLE = new ErrorCode(1_002_011_001, "短信渠道不处于开启状态，不允许选择");
    ErrorCode SMS_CHANNEL_HAS_CHILDREN = new ErrorCode(1_002_011_002, "无法删除，该短信渠道还有短信模板");

    // ========== 短信模板 1-002-012-000 ==========
    ErrorCode SMS_TEMPLATE_NOT_EXISTS = new ErrorCode(1_002_012_000, "短信模板不存在");
    ErrorCode SMS_TEMPLATE_CODE_DUPLICATE = new ErrorCode(1_002_012_001, "已经存在编码为【{}】的短信模板");
    ErrorCode SMS_TEMPLATE_API_ERROR = new ErrorCode(1_002_012_002, "短信 API 模板调用失败，原因是：{}");
    ErrorCode SMS_TEMPLATE_API_AUDIT_CHECKING = new ErrorCode(1_002_012_003, "短信 API 模版无法使用，原因：审批中");
    ErrorCode SMS_TEMPLATE_API_AUDIT_FAIL = new ErrorCode(1_002_012_004, "短信 API 模版无法使用，原因：审批不通过，{}");
    ErrorCode SMS_TEMPLATE_API_NOT_FOUND = new ErrorCode(1_002_012_005, "短信 API 模版无法使用，原因：模版不存在");

    // ========== 短信发送 1-002-013-000 ==========
    ErrorCode SMS_SEND_MOBILE_NOT_EXISTS = new ErrorCode(1_002_013_000, "手机号不存在");
    ErrorCode SMS_SEND_MOBILE_TEMPLATE_PARAM_MISS = new ErrorCode(1_002_013_001, "模板参数({})缺失");
    ErrorCode SMS_SEND_TEMPLATE_NOT_EXISTS = new ErrorCode(1_002_013_002, "短信模板不存在");

    // ========== 短信验证码 1-002-014-000 ==========
    ErrorCode SMS_CODE_NOT_FOUND = new ErrorCode(1_002_014_000, "验证码不存在");
    ErrorCode SMS_CODE_EXPIRED = new ErrorCode(1_002_014_001, "验证码已过期");
    ErrorCode SMS_CODE_USED = new ErrorCode(1_002_014_002, "验证码已使用");
    ErrorCode SMS_CODE_EXCEED_SEND_MAXIMUM_QUANTITY_PER_DAY = new ErrorCode(1_002_014_004, "超过每日短信发送数量");
    ErrorCode SMS_CODE_SEND_TOO_FAST = new ErrorCode(1_002_014_005, "短信发送过于频繁");

    // ========== 租户信息 1-002-015-000 ==========
    ErrorCode TENANT_NOT_EXISTS = new ErrorCode(1_002_015_000, "租户不存在");
    ErrorCode TENANT_DISABLE = new ErrorCode(1_002_015_001, "名字为【{}】的租户已被禁用");
    ErrorCode TENANT_EXPIRE = new ErrorCode(1_002_015_002, "名字为【{}】的租户已过期");
    ErrorCode TENANT_CAN_NOT_UPDATE_SYSTEM = new ErrorCode(1_002_015_003, "系统租户不能进行修改、删除等操作！");
    ErrorCode TENANT_NAME_DUPLICATE = new ErrorCode(1_002_015_004, "名字为【{}】的租户已存在");
    ErrorCode TENANT_WEBSITE_DUPLICATE = new ErrorCode(1_002_015_005, "域名为【{}】的租户已存在");

    // ========== 租户套餐 1-002-016-000 ==========
    ErrorCode TENANT_PACKAGE_NOT_EXISTS = new ErrorCode(1_002_016_000, "租户套餐不存在");
    ErrorCode TENANT_PACKAGE_USED = new ErrorCode(1_002_016_001, "租户正在使用该套餐，请给租户重新设置套餐后再尝试删除");
    ErrorCode TENANT_PACKAGE_DISABLE = new ErrorCode(1_002_016_002, "名字为【{}】的租户套餐已被禁用");
    ErrorCode TENANT_PACKAGE_NAME_DUPLICATE = new ErrorCode(1_002_016_003, "已经存在该名字的租户套餐");

    // ========== 社交用户 1-002-018-000 ==========
    ErrorCode SOCIAL_USER_AUTH_FAILURE = new ErrorCode(1_002_018_000, "社交授权失败，原因是：{}");
    ErrorCode SOCIAL_USER_NOT_FOUND = new ErrorCode(1_002_018_001, "社交授权失败，找不到对应的用户");

    ErrorCode SOCIAL_CLIENT_WEIXIN_MINI_APP_PHONE_CODE_ERROR = new ErrorCode(1_002_018_200, "获得手机号失败");
    ErrorCode SOCIAL_CLIENT_WEIXIN_MINI_APP_QRCODE_ERROR = new ErrorCode(1_002_018_201, "获得小程序码失败");
    ErrorCode SOCIAL_CLIENT_WEIXIN_MINI_APP_SUBSCRIBE_TEMPLATE_ERROR = new ErrorCode(1_002_018_202, "获得小程序订阅消息模版失败");
    ErrorCode SOCIAL_CLIENT_WEIXIN_MINI_APP_SUBSCRIBE_MESSAGE_ERROR = new ErrorCode(1_002_018_203, "发送小程序订阅消息失败");
    ErrorCode SOCIAL_CLIENT_WEIXIN_MINI_APP_ORDER_UPLOAD_SHIPPING_INFO_ERROR = new ErrorCode(1_002_018_204, "上传微信小程序发货信息失败");
    ErrorCode SOCIAL_CLIENT_WEIXIN_MINI_APP_ORDER_NOTIFY_CONFIRM_RECEIVE_ERROR = new ErrorCode(1_002_018_205, "上传微信小程序订单收货信息失败");
    ErrorCode SOCIAL_CLIENT_NOT_EXISTS = new ErrorCode(1_002_018_210, "社交客户端不存在");
    ErrorCode SOCIAL_CLIENT_UNIQUE = new ErrorCode(1_002_018_211, "社交客户端已存在配置");

    // ========== OAuth2 客户端 1-002-020-000 =========
    ErrorCode OAUTH2_CLIENT_NOT_EXISTS = new ErrorCode(1_002_020_000, "OAuth2 客户端不存在");
    ErrorCode OAUTH2_CLIENT_EXISTS = new ErrorCode(1_002_020_001, "OAuth2 客户端编号已存在");
    ErrorCode OAUTH2_CLIENT_DISABLE = new ErrorCode(1_002_020_002, "OAuth2 客户端已禁用");
    ErrorCode OAUTH2_CLIENT_AUTHORIZED_GRANT_TYPE_NOT_EXISTS = new ErrorCode(1_002_020_003, "不支持该授权类型");
    ErrorCode OAUTH2_CLIENT_SCOPE_OVER = new ErrorCode(1_002_020_004, "授权范围过大");
    ErrorCode OAUTH2_CLIENT_REDIRECT_URI_NOT_MATCH = new ErrorCode(1_002_020_005, "无效 redirect_uri: {}");
    ErrorCode OAUTH2_CLIENT_CLIENT_SECRET_ERROR = new ErrorCode(1_002_020_006, "无效 client_secret: {}");

    // ========== OAuth2 授权 1-002-021-000 =========
    ErrorCode OAUTH2_GRANT_CLIENT_ID_MISMATCH = new ErrorCode(1_002_021_000, "client_id 不匹配");
    ErrorCode OAUTH2_GRANT_REDIRECT_URI_MISMATCH = new ErrorCode(1_002_021_001, "redirect_uri 不匹配");
    ErrorCode OAUTH2_GRANT_STATE_MISMATCH = new ErrorCode(1_002_021_002, "state 不匹配");

    // ========== OAuth2 授权 1-002-022-000 =========
    ErrorCode OAUTH2_CODE_NOT_EXISTS = new ErrorCode(1_002_022_000, "code 不存在");
    ErrorCode OAUTH2_CODE_EXPIRE = new ErrorCode(1_002_022_001, "code 已过期");

    // ========== 邮箱账号 1-002-023-000 ==========
    ErrorCode MAIL_ACCOUNT_NOT_EXISTS = new ErrorCode(1_002_023_000, "邮箱账号不存在");
    ErrorCode MAIL_ACCOUNT_RELATE_TEMPLATE_EXISTS = new ErrorCode(1_002_023_001, "无法删除，该邮箱账号还有邮件模板");

    // ========== 邮件模版 1-002-024-000 ==========
    ErrorCode MAIL_TEMPLATE_NOT_EXISTS = new ErrorCode(1_002_024_000, "邮件模版不存在");
    ErrorCode MAIL_TEMPLATE_CODE_EXISTS = new ErrorCode(1_002_024_001, "邮件模版 code({}) 已存在");

    // ========== 邮件发送 1-002-025-000 ==========
    ErrorCode MAIL_SEND_TEMPLATE_PARAM_MISS = new ErrorCode(1_002_025_000, "模板参数({})缺失");
    ErrorCode MAIL_SEND_MAIL_NOT_EXISTS = new ErrorCode(1_002_025_001, "邮箱不存在");

    // ========== 站内信模版 1-002-026-000 ==========
    ErrorCode NOTIFY_TEMPLATE_NOT_EXISTS = new ErrorCode(1_002_026_000, "站内信模版不存在");
    ErrorCode NOTIFY_TEMPLATE_CODE_DUPLICATE = new ErrorCode(1_002_026_001, "已经存在编码为【{}】的站内信模板");

    // ========== 站内信模版 1-002-027-000 ==========

    // ========== 站内信发送 1-002-028-000 ==========
    ErrorCode NOTIFY_SEND_TEMPLATE_PARAM_MISS = new ErrorCode(1_002_028_000, "模板参数({})缺失");

}
