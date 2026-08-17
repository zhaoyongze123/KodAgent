package cn.iocoder.yudao.server.service.agent;

import cn.iocoder.yudao.framework.test.core.ut.BaseMockitoUnitTest;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.BeforeEach;
import org.springframework.jdbc.core.JdbcTemplate;
import org.springframework.test.util.ReflectionTestUtils;
import org.springframework.transaction.annotation.Transactional;

import java.util.Arrays;
import java.util.Collections;

import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.junit.jupiter.api.Assertions.assertEquals;
import static org.junit.jupiter.api.Assertions.assertNotNull;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.mockito.ArgumentMatchers.anyString;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.when;

class AgentKnowledgeLibraryServiceTest extends BaseMockitoUnitTest {

    private static final Long TENANT_ID = 1L;
    private static final Long LIBRARY_ID = 101L;
    private static final Long USER_IN_CONFIGURED_DEPARTMENT = 11L;
    private static final Long USER_OUTSIDE_ACL = 12L;
    private static final Long CONFIGURED_DEPARTMENT_ID = 201L;

    private AgentKnowledgeLibraryService service;
    private JdbcTemplate jdbcTemplate;
    private AdminUserService adminUserService;

    @BeforeEach
    void setUp() {
        service = new AgentKnowledgeLibraryService();
        jdbcTemplate = mock(JdbcTemplate.class);
        adminUserService = mock(AdminUserService.class);
        ReflectionTestUtils.setField(service, "jdbcTemplate", jdbcTemplate);
        ReflectionTestUtils.setField(service, "adminUserService", adminUserService);
    }

    @Test
    void localUploadAclAllowsOnlyItsConfiguredDepartmentOrUser() {
        AdminUserDO allowedUser = mock(AdminUserDO.class);
        when(allowedUser.getDeptId()).thenReturn(CONFIGURED_DEPARTMENT_ID);
        when(adminUserService.getUser(USER_IN_CONFIGURED_DEPARTMENT)).thenReturn(allowedUser);
        when(jdbcTemplate.queryForObject(anyString(), eq(Boolean.class), eq(TENANT_ID), eq(LIBRARY_ID),
                eq(USER_IN_CONFIGURED_DEPARTMENT), eq(CONFIGURED_DEPARTMENT_ID))).thenReturn(true);

        AdminUserDO deniedUser = mock(AdminUserDO.class);
        when(deniedUser.getDeptId()).thenReturn(202L);
        when(adminUserService.getUser(USER_OUTSIDE_ACL)).thenReturn(deniedUser);
        when(jdbcTemplate.queryForObject(anyString(), eq(Boolean.class), eq(TENANT_ID), eq(LIBRARY_ID),
                eq(USER_OUTSIDE_ACL), eq(202L))).thenReturn(false);

        assertTrue(service.canReadLocalLibrary(TENANT_ID, USER_IN_CONFIGURED_DEPARTMENT, LIBRARY_ID));
        assertFalse(service.canReadLocalLibrary(TENANT_ID, USER_OUTSIDE_ACL, LIBRARY_ID));
    }

    @Test
    void localUploadAclDoesNotTrustIndirectDepartmentMembership() {
        AdminUserDO user = mock(AdminUserDO.class);
        when(user.getDeptId()).thenReturn(202L);
        when(adminUserService.getUser(USER_OUTSIDE_ACL)).thenReturn(user);
        when(jdbcTemplate.queryForObject(anyString(), eq(Boolean.class), eq(TENANT_ID), eq(LIBRARY_ID),
                eq(USER_OUTSIDE_ACL), eq(202L))).thenReturn(false);

        assertFalse(service.canReadLocalLibrary(TENANT_ID, USER_OUTSIDE_ACL, LIBRARY_ID));
    }

    @Test
    void localUploadPersistsLibraryBinaryAndAclInTheAgentTransaction() throws Exception {
        Transactional transactional = AgentKnowledgeLibraryService.class.getMethod("createLocalUpload",
                Long.class, Long.class, String.class, String.class, String.class, byte[].class,
                String.class, java.util.List.class).getAnnotation(Transactional.class);

        assertNotNull(transactional);
        assertEquals("agentEventTransactionManager", transactional.transactionManager());
        assertTrue(Arrays.asList(transactional.rollbackFor()).contains(Exception.class));
    }

    @Test
    void allAccessLocalUploadDoesNotNeedAnAclRow() {
        assertTrue(AgentKnowledgeLibraryService.allowsLocalRead("ALL", 11L, 101L,
                Collections.<AgentKnowledgeLibraryService.AclSubject>emptyList()));
    }

    @Test
    void customLocalUploadAllowsAnExplicitUserButNotOtherUsers() {
        assertTrue(AgentKnowledgeLibraryService.allowsLocalRead("CUSTOM", 11L, 101L,
                Arrays.asList(new AgentKnowledgeLibraryService.AclSubject("USER", 11L))));
        assertFalse(AgentKnowledgeLibraryService.allowsLocalRead("CUSTOM", 12L, 101L,
                Arrays.asList(new AgentKnowledgeLibraryService.AclSubject("USER", 11L))));
    }

    @Test
    void customLocalUploadAllowsTheUsersDepartment() {
        assertTrue(AgentKnowledgeLibraryService.allowsLocalRead("CUSTOM", 11L, 101L,
                Arrays.asList(new AgentKnowledgeLibraryService.AclSubject("DEPARTMENT", 101L))));
        assertFalse(AgentKnowledgeLibraryService.allowsLocalRead("CUSTOM", 11L, 102L,
                Arrays.asList(new AgentKnowledgeLibraryService.AclSubject("DEPARTMENT", 101L))));
    }

    @Test
    void folderSourcesCannotUseLocalAclModes() {
        assertFalse(AgentKnowledgeLibraryService.validAccessMode("KOD_FOLDER", "ALL"));
        assertTrue(AgentKnowledgeLibraryService.validAccessMode("KOD_FOLDER", "FOLDER"));
        assertTrue(AgentKnowledgeLibraryService.validAccessMode("LOCAL_UPLOAD", "CUSTOM"));
    }
}
