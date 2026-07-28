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

import java.time.LocalDateTime;

@TableName("bpm_oa_leave_cancel")
@KeySequence("bpm_oa_leave_cancel_seq")
@Data
@Builder
@NoArgsConstructor
@AllArgsConstructor
public class BpmOALeaveCancelDO extends BaseDO {

    @TableId(type = IdType.AUTO)
    private Long id;

    private Long userId;

    private Integer type;

    private String reason;

    private LocalDateTime startTime;

    private LocalDateTime endTime;

    private Long day;

    private Integer status;

    private String processInstanceId;

}
