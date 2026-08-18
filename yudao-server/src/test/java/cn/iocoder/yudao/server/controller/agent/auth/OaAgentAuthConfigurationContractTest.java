package cn.iocoder.yudao.server.controller.agent.auth;

import org.junit.jupiter.api.Test;

import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

import static org.junit.jupiter.api.Assertions.assertTrue;

class OaAgentAuthConfigurationContractTest {

    private static final String KNOWLEDGE_ADMIN_PATH = "/admin-api/agent/knowledge-libraries/**";

    @Test
    void knowledgeAdministrationUsesTheSameAgentIdentityBoundaryAsOtherAdminApis() throws Exception {
        assertContains("OaAgentAuthConfiguration.java", KNOWLEDGE_ADMIN_PATH);
        assertContains("OaAgentAuthorizeRequestsCustomizer.java", KNOWLEDGE_ADMIN_PATH);
    }

    private static void assertContains(String filename, String value) throws Exception {
        Path path = Paths.get("src", "main", "java", "cn", "iocoder", "yudao", "server",
                "controller", "agent", "auth", filename);
        String source = new String(Files.readAllBytes(path), StandardCharsets.UTF_8);
        assertTrue(source.contains(value), filename + " must include " + value);
    }
}
