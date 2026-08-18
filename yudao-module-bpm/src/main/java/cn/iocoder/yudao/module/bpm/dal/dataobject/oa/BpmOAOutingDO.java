package cn.iocoder.yudao.module.bpm.dal.dataobject.oa;

import cn.iocoder.yudao.framework.mybatis.core.dataobject.BaseDO;
import com.baomidou.mybatisplus.annotation.KeySequence;
import com.baomidou.mybatisplus.annotation.IdType;
import com.baomidou.mybatisplus.annotation.TableId;
import com.baomidou.mybatisplus.annotation.TableName;
import lombok.AllArgsConstructor;
import lombok.Builder;
import lombok.Data;
import lombok.NoArgsConstructor;

import java.math.BigDecimal;
import java.time.LocalDate;
import java.time.LocalDateTime;

@TableName("bpm_oa_outing")
@KeySequence("bpm_oa_outing_seq")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BpmOAOutingDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private Integer type;

    private LocalDate outingDate;

    private LocalDateTime startTime;

    private LocalDateTime endTime;

    private BigDecimal durationHours;

    private String destination;

    private Boolean outsideOffice;

    private String contactMobile;

    private String companionNames;

    private String reason;

    private String remark;

    private Integer status;

    private String processInstanceId;

}
