package cn.iocoder.yudao.server.service.agent;

import org.springframework.core.env.Environment;
import org.springframework.core.env.Profiles;
import org.springframework.stereotype.Component;

import javax.annotation.Resource;
import java.nio.file.Files;
import java.nio.file.Path;
import java.nio.file.Paths;

/**
 * Explicit local-only fault injection for the real batch approval acceptance.
 *
 * <p>The hook is inert unless the application runs with the {@code local}
 * profile and the operator sets {@code OA_AGENT_BATCH_TEST_FAILPOINT}. It is
 * intentionally placed at the controller's transaction boundary so the
 * acceptance can prove rollback after a real Flowable mutation, rather than
 * testing a fake repository.</p>
 */
@Component
public class AgentApprovalBatchTestHook {

    private static final String FAILPOINT = "OA_AGENT_BATCH_TEST_FAILPOINT";
    private static final String GATE = "OA_AGENT_BATCH_TEST_GATE";

    @Resource
    private Environment environment;

    /**
     * Called after the first real task mutation in a batch.
     *
     * <p>{@code THROW} aborts the request immediately. {@code BLOCK} waits
     * until the operator creates the configured gate file; this gives the
     * acceptance harness a deterministic window to terminate the Java
     * process and verify connection-loss rollback.</p>
     */
    public void afterFirstMutation() {
        if (!environment.acceptsProfiles(Profiles.of("local"))) {
            return;
        }
        String mode = configured("yudao.agent.batch-test.failpoint", FAILPOINT);
        if ("THROW".equalsIgnoreCase(mode)) {
            throw new IllegalStateException("OA_AGENT_BATCH_TEST_FAILPOINT=THROW");
        }
        if (!"BLOCK".equalsIgnoreCase(mode)) {
            return;
        }
        String gate = configured("yudao.agent.batch-test.gate", GATE);
        if (gate.isEmpty()) {
            throw new IllegalStateException("OA_AGENT_BATCH_TEST_GATE is required for BLOCK");
        }
        Path gatePath = Paths.get(gate).toAbsolutePath().normalize();
        try {
            while (!Files.exists(gatePath)) {
                Thread.sleep(100L);
            }
        } catch (InterruptedException interrupted) {
            Thread.currentThread().interrupt();
            throw new IllegalStateException("Batch approval test failpoint interrupted", interrupted);
        }
    }

    private String value(String name) {
        String value = environment.getProperty(name);
        return value == null ? "" : value.trim();
    }

    private String configured(String propertyName, String environmentName) {
        String configured = value(propertyName);
        return configured.isEmpty() ? value(environmentName) : configured;
    }
}
