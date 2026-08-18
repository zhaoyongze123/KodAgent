package cn.iocoder.yudao.module.bpm.service.message.dto;

import lombok.Data;

/**
 * BPM 待办分配 WebSocket 消息
 */
@Data
public class BpmTaskAssignedWebSocketMessage {

    /**
     * 流程实例编号
     */
    private String processInstanceId;
    /**
     * 流程实例名称
     */
    private String processInstanceName;
    /**
     * 任务编号
     */
    private String taskId;
    /**
     * 任务名称
     */
    private String taskName;
    /**
     * 发起人编号
     */
    private Long startUserId;
    /**
     * 发起人昵称
     */
    private String startUserNickname;
    /**
     * 审批人编号
     */
    private Long assigneeUserId;

}
