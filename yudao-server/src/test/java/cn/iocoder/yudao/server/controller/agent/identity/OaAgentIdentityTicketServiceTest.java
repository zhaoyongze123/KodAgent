package cn.iocoder.yudao.server.controller.agent.identity;

import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;

import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertThrows;

class OaAgentIdentityTicketServiceTest {

    private OaAgentIdentityTicketService ticketService;

    @BeforeEach
    void setUp() {
        OaAgentIdentityProperties properties = new OaAgentIdentityProperties();
        properties.setSecret("0123456789abcdef0123456789abcdef");
        properties.setTtlSeconds(300L);
        ticketService = new OaAgentIdentityTicketService(properties);
    }

    @Test
    void shouldIssueAndVerifyTicket() {
        String ticket = ticketService.issue(215L, 1L);

        OaAgentIdentityTicketService.IdentityPayload payload = ticketService.verify(ticket);

        assertEquals(215L, payload.getUserId());
        assertEquals(1L, payload.getTenantId());
    }

    @Test
    void shouldDefaultTicketTtlCoverLongHumanInputFlow() {
        OaAgentIdentityProperties properties = new OaAgentIdentityProperties();

        assertEquals(7200L, properties.getTtlSeconds());
    }

    @Test
    void shouldRejectTamperedTicket() {
        String ticket = ticketService.issue(215L, 1L);
        String tampered = (ticket.charAt(0) == 'a' ? 'b' : 'a') + ticket.substring(1);

        assertThrows(IllegalArgumentException.class, () -> ticketService.verify(tampered));
    }

    @Test
    void shouldRejectExpiredTicket() {
        OaAgentIdentityProperties properties = new OaAgentIdentityProperties();
        properties.setSecret("0123456789abcdef0123456789abcdef");
        properties.setTtlSeconds(-1L);
        OaAgentIdentityTicketService expiredTicketService = new OaAgentIdentityTicketService(properties);

        String ticket = expiredTicketService.issue(215L, 1L);

        assertThrows(IllegalArgumentException.class, () -> expiredTicketService.verify(ticket));
    }
}
