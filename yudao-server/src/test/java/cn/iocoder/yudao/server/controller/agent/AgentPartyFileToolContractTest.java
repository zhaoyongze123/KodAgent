package cn.iocoder.yudao.server.controller.agent;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;

/**
 * Keeps the Agent attachment endpoint on the employee-scoped authorization
 * path. The service invoked here resolves ALL/USER/DEPT/ROLE visibility and
 * validates that fileId belongs to the requested party file before bytes are
 * returned.
 */
class AgentPartyFileToolContractTest {

    @Test
    void attachmentContentMustUseCurrentUserVisibilityAndOwnershipChecks() throws Exception {
        Path sourcePath = locate("yudao-server/src/main/java/cn/iocoder/yudao/server/controller/agent/AgentPartyFileToolController.java");
        String source = new String(Files.readAllBytes(sourcePath), StandardCharsets.UTF_8);

        assertTrue(source.contains("/party-files/my-attachment/content"));
        assertTrue(source.contains("getMyPartyFileAttachment(id, fileId, getLoginUserId(), getLoginUserNickname()"));
        assertTrue(source.contains("PARTY_FILE_ATTACHMENT_NOT_FOUND"));
        assertTrue(source.contains("PartyFileReadSourceEnum.PREVIEW"));
        assertTrue(source.contains("PartyFileReadSourceEnum.DOWNLOAD"));
        assertTrue(source.contains("action must be preview or download"));
        assertTrue(source.contains("partyFileAttachmentService.getAttachmentContent(fileId)"));
        assertFalse(source.contains("partyFileService.getPartyFileDetail(id)"));
        assertFalse(source.contains("attachment.getUrl()"));
    }

    @Test
    void manageDetailMustUseTheOperationPermissionBoundaryAndSingleFacade() throws Exception {
        Path toolPath = locate("yudao-server/src/main/java/cn/iocoder/yudao/server/controller/agent/AgentPartyFileToolController.java");
        String toolSource = new String(Files.readAllBytes(toolPath), StandardCharsets.UTF_8);
        assertTrue(toolSource.contains("partyFileDraftService.detail(partyFileId, getLoginUserId())"));
        assertFalse(toolSource.contains("partyFileDraftService.detail(partyFileId)"));

        Path servicePath = locate("yudao-server/src/main/java/cn/iocoder/yudao/server/service/agent/AgentPartyFileDraftService.java");
        String serviceSource = new String(Files.readAllBytes(servicePath), StandardCharsets.UTF_8);
        assertTrue(serviceSource.contains("hasAnyPermissions(userId, \"system:party-file:update\", \"system:party-file:delete\")"));

        Path facadePath = locate("yudao-server/src/main/java/cn/iocoder/yudao/server/controller/agent/OaAgentFacadeController.java");
        String facadeSource = new String(Files.readAllBytes(facadePath), StandardCharsets.UTF_8);
        assertFalse(facadeSource.contains("/party-files/"));
        assertFalse(facadeSource.contains("PartyFileService"));
    }

    private static Path locate(String relative) {
        Path direct = Paths.get(System.getProperty("user.dir"), relative);
        return Files.exists(direct) ? direct : Paths.get(System.getProperty("user.dir"), "..", relative);
    }
}
