package cn.iocoder.yudao.server.service.agent;

import cn.hutool.crypto.SecureUtil;
import cn.iocoder.yudao.framework.test.core.ut.BaseMockitoUnitTest;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.ArgumentMatchers;
import org.springframework.http.HttpHeaders;
import org.springframework.http.HttpMethod;
import org.springframework.http.MediaType;
import org.springframework.http.client.ClientHttpRequest;
import org.springframework.http.client.ClientHttpResponse;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.mock.web.MockHttpServletResponse;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.web.client.RestTemplate;

import java.io.ByteArrayInputStream;
import java.io.ByteArrayOutputStream;
import java.io.IOException;
import java.io.OutputStream;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.Map;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AgentModelGatewayContractTest extends BaseMockitoUnitTest {

    private static final String ENCRYPTION_KEY = "0123456789abcdef0123456789abcdef";
    private static final String PROVIDER_KEY = "provider-secret-never-leaves-java";

    private AgentModelService service;
    private JdbcTemplate jdbcTemplate;
    private RestTemplate restTemplate;

    @BeforeEach
    void setUp() {
        service = new AgentModelService();
        jdbcTemplate = mock(JdbcTemplate.class);
        restTemplate = mock(RestTemplate.class);
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplate);
        ReflectionTestUtils.setField(service, "restTemplate", restTemplate);
        ReflectionTestUtils.setField(service, "encryptionKey", ENCRYPTION_KEY);
    }

    @Test
    void resolveDoesNotReturnProviderCredential() {
        Map<String, Object> row = modelRow();
        when(jdbcTemplate.queryForMap(anyString(), eq(240L), eq(1L))).thenReturn(row);

        Map<String, Object> resolved = service.resolve(1L, 1L, 240L);

        assertFalse(resolved.containsKey("apiKey"));
        assertFalse(resolved.containsKey("api_key_ciphertext"));
        assertTrue(resolved.containsKey("model_id"));
    }

    @Test
    @SuppressWarnings({"unchecked", "rawtypes"})
    void gatewayInjectsCredentialOnlyIntoUpstreamRequest() throws Exception {
        Map<String, Object> row = modelRow();
        when(jdbcTemplate.queryForMap(anyString(), eq(240L), eq(1L))).thenReturn(row);

        final HttpHeaders upstreamHeaders = new HttpHeaders();
        final ByteArrayOutputStream upstreamBody = new ByteArrayOutputStream();
        ClientHttpRequest upstreamRequest = mock(ClientHttpRequest.class);
        when(upstreamRequest.getHeaders()).thenReturn(upstreamHeaders);
        when(upstreamRequest.getBody()).thenReturn(upstreamBody);

        ClientHttpResponse upstreamResponse = mock(ClientHttpResponse.class);
        HttpHeaders responseHeaders = new HttpHeaders();
        responseHeaders.setContentType(MediaType.APPLICATION_JSON);
        when(upstreamResponse.getRawStatusCode()).thenReturn(200);
        when(upstreamResponse.getHeaders()).thenReturn(responseHeaders);
        when(upstreamResponse.getBody()).thenReturn(new ByteArrayInputStream(
                "{\"id\":\"completion-1\",\"choices\":[]}".getBytes(StandardCharsets.UTF_8)));

        when(restTemplate.execute(anyString(), eq(HttpMethod.POST), any(), any()))
                .thenAnswer(invocation -> {
                    org.springframework.web.client.RequestCallback callback = invocation.getArgument(2);
                    org.springframework.web.client.ResponseExtractor extractor = invocation.getArgument(3);
                    callback.doWithRequest(upstreamRequest);
                    return extractor.extractData(upstreamResponse);
                });

        MockHttpServletResponse response = new MockHttpServletResponse();
        service.proxyChatCompletion(1L, 240L,
                "{\"model\":\"attacker-model\",\"messages\":[],\"stream\":false}"
                        .getBytes(StandardCharsets.UTF_8), response);

        assertTrue(upstreamHeaders.getFirst(HttpHeaders.AUTHORIZATION).endsWith(PROVIDER_KEY));
        String body = new String(upstreamBody.toByteArray(), StandardCharsets.UTF_8);
        assertTrue(body.contains("\"model\":\"gpt-5.6-luna\""));
        assertFalse(new String(response.getContentAsByteArray(), StandardCharsets.UTF_8).contains(PROVIDER_KEY));
    }

    private Map<String, Object> modelRow() {
        Map<String, Object> row = new HashMap<>();
        row.put("model_id", 240L);
        row.put("model_name", "gpt-5.6-luna");
        row.put("provider_name", "claude.aiapis.help");
        row.put("base_url", "https://claude.aiapis.help/v1");
        row.put("capabilities", "{\"streaming\":true,\"tools\":true}");
        row.put("api_key_ciphertext", SecureUtil.aes(ENCRYPTION_KEY.getBytes(StandardCharsets.UTF_8))
                .encryptBase64(PROVIDER_KEY));
        return row;
    }
}
