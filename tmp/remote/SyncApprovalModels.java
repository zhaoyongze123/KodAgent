import cn.iocoder.yudao.module.bpm.controller.admin.definition.vo.model.simple.BpmSimpleModelNodeVO;
import cn.iocoder.yudao.module.bpm.framework.flowable.core.util.BpmnModelUtils;
import cn.iocoder.yudao.module.bpm.framework.flowable.core.util.SimpleModelUtils;
import cn.iocoder.yudao.framework.common.util.json.JsonUtils;
import org.flowable.bpmn.model.BpmnModel;

import java.nio.charset.StandardCharsets;
import java.sql.Connection;
import java.sql.DriverManager;
import java.sql.PreparedStatement;
import java.sql.ResultSet;

/** 使用系统自身的简易流程转换逻辑，把已保存的审批模型发布到当前流程资源。 */
public class SyncApprovalModels {
    private static final String DB_URL = "jdbc:mysql://127.0.0.1:13307/ruoyi-vue-pro?useSSL=false&serverTimezone=Asia/Shanghai&allowPublicKeyRetrieval=true&characterEncoding=utf8";
    private static final String DB_USER = "root";
    private static final String DB_PASSWORD = "qNnVECf4HfZWefitcqmS7TVd";

    public static void main(String[] args) throws Exception {
        Class.forName("com.mysql.cj.jdbc.Driver");
        try (Connection connection = DriverManager.getConnection(DB_URL, DB_USER, DB_PASSWORD)) {
            String query = "SELECT t.code,t.process_definition_id,m.KEY_,m.NAME_,p.simple_model,pr.DEPLOYMENT_ID_ "
                    + "FROM bpm_approval_template t "
                    + "JOIN bpm_process_definition_info p ON p.process_definition_id=t.process_definition_id "
                    + "JOIN ACT_RE_MODEL m ON m.ID_=p.model_id "
                    + "JOIN ACT_RE_PROCDEF pr ON pr.ID_=t.process_definition_id "
                    + "WHERE t.deleted=0 AND t.code LIKE 'tpl:oa_%' AND t.code <> 'tpl:oa_leave_test' "
                    + "AND pr.SUSPENSION_STATE_=1 ORDER BY t.id";
            String updateBpmn = "UPDATE ACT_GE_BYTEARRAY SET BYTES_=? WHERE DEPLOYMENT_ID_=? AND NAME_ LIKE '%.bpmn'";
            String updateSource = "UPDATE ACT_GE_BYTEARRAY SET BYTES_=? WHERE ID_=?";
            try (PreparedStatement select = connection.prepareStatement(query);
                 PreparedStatement bpmn = connection.prepareStatement(updateBpmn);
                 PreparedStatement source = connection.prepareStatement(updateSource);
                 ResultSet result = select.executeQuery()) {
                int count = 0;
                while (result.next()) {
                    String code = result.getString(1);
                    String definitionId = result.getString(2);
                    String processKey = result.getString(3);
                    String processName = result.getString(4);
                    String simpleJson = result.getString(5);
                    String deploymentId = result.getString(6);
                    BpmSimpleModelNodeVO simpleModel = JsonUtils.parseObject(simpleJson, BpmSimpleModelNodeVO.class);
                    BpmnModel bpmnModel = SimpleModelUtils.buildBpmnModel(processKey, processName, simpleModel);
                    byte[] bpmnXml = BpmnModelUtils.getBpmnXml(bpmnModel).getBytes(StandardCharsets.UTF_8);
                    bpmn.setBytes(1, bpmnXml);
                    bpmn.setString(2, deploymentId);
                    int bpmnRows = bpmn.executeUpdate();

                    String sourceId = findSourceExtraId(connection, result.getString(3));
                    source.setBytes(1, simpleJson.getBytes(StandardCharsets.UTF_8));
                    source.setString(2, sourceId);
                    int sourceRows = source.executeUpdate();
                    System.out.println(code + " definition=" + definitionId + " bpmn=" + bpmnRows + " source=" + sourceRows);
                    count++;
                }
                System.out.println("updated=" + count);
            }
        }
    }

    private static String findSourceExtraId(Connection connection, String key) throws Exception {
        try (PreparedStatement statement = connection.prepareStatement(
                "SELECT EDITOR_SOURCE_EXTRA_VALUE_ID_ FROM ACT_RE_MODEL WHERE KEY_=?")) {
            statement.setString(1, key);
            try (ResultSet result = statement.executeQuery()) {
                if (!result.next()) {
                    throw new IllegalStateException("找不到模型 source-extra：" + key);
                }
                return result.getString(1);
            }
        }
    }
}
