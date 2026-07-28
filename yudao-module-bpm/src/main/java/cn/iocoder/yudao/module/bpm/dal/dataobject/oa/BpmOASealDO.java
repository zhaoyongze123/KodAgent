package cn.iocoder.yudao.module.bpm.dal.dataobject.oa;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import cn.iocoder.yudao.module.bpm.enums.task.BpmTaskStatusEnum;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.time.LocalDateTime;

/**
 * OA 用章申请 DO
 *
 * {@link #day} 用章天数，目前先简单做。一般是分成用章上午和下午，可以是 1 整天，可以是 0.5 半天
 *
 * @author jason
 * @author 芋道源码
 */
@TableName("bpm_oa_seal")
@KeySequence("bpm_oa_seal_seq") // 用于 Oracle、PostgreSQL、Kingbase、DB2、H2 数据库的主键自增。如果是 MySQL 等数据库，可不写。
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BpmOASealDO extends BaseDO {

    /**
     * 用章表单主键
     */
    @TableId(type = IdType.AUTO)
    private Long id;
    /**
     * 申请人的用户编号
     *
     * 关联 AdminUserDO 的 id 属性
     */
    private Long userId;
    /**
     * 申请人姓名快照
     */
    private String applicantName;
    /**
     * 部门编号
     */
    private Long deptId;
    /**
     * 部门名称快照
     */
    private String deptName;
    /**
     * 用章类型
     */
    private Integer type;
    /**
     * 文件名称
     */
    private String fileName;
    /**
     * 文件份数
     */
    private Integer fileCount;
    /**
     * 原因
     */
    private String reason;
    /**
     * 开始时间
     */
    private LocalDateTime startTime;
    /**
     * 结束时间
     */
    private LocalDateTime endTime;
    /**
     * 用章天数
     */
    private Long day;
    /**
     * 对方单位
     */
    private String counterpartUnit;
    /**
     * 是否外带
     */
    private Boolean externalCarry;
    /**
     * 经办人
     */
    private String operatorName;
    /**
     * 附件地址，多个使用 JSON 数组字符串存储
     */
    private String attachmentUrls;
    /**
     * 备注
     */
    private String remark;
    /**
     * 审批结果
     *
     * 枚举 {@link BpmTaskStatusEnum}
     * 考虑到简单，所以直接复用了 BpmProcessInstanceStatusEnum 枚举，也可以自己定义一个枚举哈
     */
    private Integer status;

    /**
     * 对应的流程编号
     *
     * 关联 ProcessInstance 的 id 属性
     */
    private String processInstanceId;

}
