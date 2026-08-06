package cn.iocoder.yudao.module.system.service.auth;

import cn.iocoder.yudao.framework.common.util.http.HttpUtils;
import cn.iocoder.yudao.framework.test.core.ut.BaseDbUnitTest;
import cn.iocoder.yudao.module.system.controller.admin.auth.vo.AuthLoginRespVO;
import cn.iocoder.yudao.module.system.controller.admin.dept.vo.dept.DeptSaveReqVO;
import cn.iocoder.yudao.module.system.controller.admin.user.vo.user.UserSaveReqVO;
import cn.iocoder.yudao.module.system.dal.dataobject.auth.KodSsoUserBindDO;
import cn.iocoder.yudao.module.system.dal.dataobject.dept.DeptDO;
import cn.iocoder.yudao.module.system.dal.dataobject.user.AdminUserDO;
import cn.iocoder.yudao.module.system.dal.mysql.auth.KodSsoUserBindMapper;
import cn.iocoder.yudao.module.system.dal.mysql.dept.DeptMapper;
import cn.iocoder.yudao.module.system.framework.kodsso.config.KodSsoConfiguration;
import cn.iocoder.yudao.module.system.framework.kodsso.config.KodSsoProperties;
import cn.iocoder.yudao.module.system.service.dept.DeptService;
import cn.iocoder.yudao.module.system.service.permission.PermissionService;
import cn.iocoder.yudao.module.system.service.user.AdminUserService;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.mockito.MockedStatic;
import org.springframework.boot.test.mock.mockito.MockBean;
import org.springframework.context.annotation.Import;
import org.springframework.mock.web.MockHttpServletRequest;
import org.springframework.security.authentication.UsernamePasswordAuthenticationToken;
import org.springframework.security.core.context.SecurityContextHolder;

import javax.annotation.Resource;
import java.net.URLDecoder;
import java.nio.charset.StandardCharsets;
import java.util.Collections;
import java.util.HashMap;
import java.util.HashSet;
import java.util.Objects;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

import static cn.iocoder.yudao.framework.test.core.util.AssertUtils.assertPojoEquals;
import static cn.iocoder.yudao.framework.test.core.util.RandomUtils.randomPojo;
import static cn.iocoder.yudao.framework.web.core.util.WebFrameworkUtils.setLoginUserId;
import static cn.iocoder.yudao.framework.web.core.util.WebFrameworkUtils.setLoginUserType;
import static org.junit.jupiter.api.Assertions.assertThrows;
import static org.junit.jupiter.api.Assertions.assertTrue;
import static org.junit.jupiter.api.Assertions.assertFalse;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.*;

@Import({KodSsoServiceImpl.class, KodSsoConfiguration.class})
public class KodSsoServiceImplTest extends BaseDbUnitTest {

    @Resource
    private KodSsoServiceImpl kodSsoService;
    @Resource
    private KodSsoProperties kodSsoProperties;

    @MockBean
    private KodSsoUserBindMapper kodSsoUserBindMapper;
    @MockBean
    private DeptMapper deptMapper;
    @MockBean
    private AdminUserService adminUserService;
    @MockBean
    private AdminAuthService adminAuthService;
    @MockBean
    private PermissionService permissionService;
    @MockBean
    private DeptService deptService;

    @BeforeEach
    public void setUp() {
        kodSsoProperties.setEnabled(true);
        kodSsoProperties.setBaseUrl("https://kod.example.com/");
        kodSsoProperties.setAppName("oa-lite");
        kodSsoProperties.setAutoCreateUser(true);
        kodSsoProperties.setUsernamePrefix("kod");
        kodSsoProperties.setDefaultRoleIds(Collections.emptySet());
        // apiCheckToken only returns the KodBox user profile.  Local roles are
        // assigned from an explicit OA-side mapping, never from roleID/isRoot
        // fields that are absent from the real response contract.
        kodSsoProperties.setUserRoleMappings(new HashMap<>());
        kodSsoProperties.setRedirectUri(null);
        kodSsoProperties.setKodCommonRoleId(1L);
        kodSsoProperties.setKodDeptAdminRoleId(2L);
        kodSsoProperties.setKodSuperAdminRoleId(3L);
        kodSsoProperties.setLocalCommonRoleId(2L);
        kodSsoProperties.setLocalDeptAdminRoleId(3L);
        kodSsoProperties.setLocalSuperAdminRoleId(1L);
        when(deptService.getDept(eq(2L))).thenReturn(new DeptDO().setId(2L).setStatus(0));
        when(deptService.getDept(eq(3L))).thenReturn(new DeptDO().setId(3L).setStatus(0));
        SecurityContextHolder.clearContext();
    }

    @Test
    public void testBuildClientRedirectUrl_andExchange_success() {
        when(kodSsoUserBindMapper.selectByKodUsername(eq("koduser"))).thenReturn(new KodSsoUserBindDO()
                .setId(11L).setUserId(11L).setKodUserId("old-u-1").setKodUsername("koduser"));
        when(adminUserService.getUser(eq(11L))).thenReturn(new AdminUserDO()
                .setId(11L).setUsername("koduser").setNickname("可道云用户"));

        AuthLoginRespVO loginRespVO = randomPojo(AuthLoginRespVO.class, o -> o.setUserId(11L));
        when(adminAuthService.createLoginToken(eq(11L), eq("koduser"), any())).thenReturn(loginRespVO);

        try (MockedStatic<HttpUtils> mockedHttpUtils = mockStatic(HttpUtils.class, CALLS_REAL_METHODS)) {
            mockedHttpUtils.when(() -> HttpUtils.get(eq("https://kod.example.com/?user/sso/apiCheckToken&accessToken=kod-token&appName=oa-lite"),
                    eq(Collections.emptyMap())))
                    .thenReturn("{\"userID\":\"u-1\",\"name\":\"koduser\",\"nickName\":\"可道云用户\"}");

            String redirectUrl = kodSsoService.buildClientRedirectUrl("kod-token", "http://127.0.0.1:3000/callback");
            assertTrue(redirectUrl.contains("kodSsoCode="));
            String exchangeCode = redirectUrl.substring(redirectUrl.indexOf("kodSsoCode=") + "kodSsoCode=".length());

            AuthLoginRespVO result = kodSsoService.exchangeCode(exchangeCode);
            assertPojoEquals(loginRespVO, result);
        }

        verify(adminUserService, never()).updateUserProfile(anyLong(), any());
    }

    @Test
    public void testBuildClientRedirectUrl_hashRoute_keepExchangeCodeInFragment() {
        when(kodSsoUserBindMapper.selectByKodUsername(eq("koduser"))).thenReturn(new KodSsoUserBindDO()
                .setId(11L).setUserId(11L).setKodUserId("old-u-1").setKodUsername("koduser"));
        when(adminUserService.getUser(eq(11L))).thenReturn(new AdminUserDO()
                .setId(11L).setUsername("koduser").setNickname("可道云用户"));

        try (MockedStatic<HttpUtils> mockedHttpUtils = mockStatic(HttpUtils.class, CALLS_REAL_METHODS)) {
            mockedHttpUtils.when(() -> HttpUtils.get(eq("https://kod.example.com/?user/sso/apiCheckToken&accessToken=kod-token-hash&appName=oa-lite"),
                    eq(Collections.emptyMap())))
                    .thenReturn("{\"userID\":\"u-1\",\"name\":\"koduser\",\"nickName\":\"可道云用户\"}");

            String redirectUrl = kodSsoService.buildClientRedirectUrl("kod-token-hash",
                    "http://192.168.1.100:5666/#/auth/kod-sso-login?tenantId=1&entry=party-file");

            assertTrue(redirectUrl.startsWith("http://192.168.1.100:5666/#/auth/kod-sso-login?tenantId=1&entry=party-file"));
            assertTrue(redirectUrl.contains("#/auth/kod-sso-login?tenantId=1&entry=party-file&kodSsoCode="));
            assertFalse(Pattern.compile("\\?kodSsoCode=[^#]*#").matcher(redirectUrl).find());
            Matcher matcher = Pattern.compile("kodSsoCode=([^&]+)$").matcher(redirectUrl);
            assertTrue(matcher.find());
            assertFalse(matcher.group(1).isEmpty());
        }
    }

    @Test
    public void testExchangeCode_withCurrentLoginContext_stillUseTargetUser() {
        when(kodSsoUserBindMapper.selectByKodUsername(eq("zhanghua"))).thenReturn(new KodSsoUserBindDO()
                .setId(11L).setUserId(219L).setKodUserId("old-u-4").setKodUsername("zhanghua"));
        when(adminUserService.getUser(eq(219L))).thenReturn(new AdminUserDO()
                .setId(219L).setUsername("zhanghua").setNickname("张华"));

        AuthLoginRespVO loginRespVO = randomPojo(AuthLoginRespVO.class, o -> o.setUserId(219L));
        when(adminAuthService.createLoginToken(eq(219L), eq("zhanghua"), any())).thenReturn(loginRespVO);

        MockHttpServletRequest request = new MockHttpServletRequest();
        request.setRequestURI("/admin-api/system/auth/kod-sso/callback");
        setLoginUserId(request, 227L);
        setLoginUserType(request, 2);
        SecurityContextHolder.getContext().setAuthentication(
                new UsernamePasswordAuthenticationToken("old-user", null, Collections.emptyList()));

        try (MockedStatic<HttpUtils> mockedHttpUtils = mockStatic(HttpUtils.class, CALLS_REAL_METHODS);
             MockedStatic<cn.iocoder.yudao.framework.common.util.servlet.ServletUtils> mockedServletUtils =
                     mockStatic(cn.iocoder.yudao.framework.common.util.servlet.ServletUtils.class, CALLS_REAL_METHODS)) {
            mockedServletUtils.when(cn.iocoder.yudao.framework.common.util.servlet.ServletUtils::getRequest)
                    .thenReturn(request);
            mockedHttpUtils.when(() -> HttpUtils.get(eq("https://kod.example.com/?user/sso/apiCheckToken&accessToken=kod-token-context&appName=oa-lite"),
                    eq(Collections.emptyMap())))
                    .thenReturn("{\"userID\":\"u-4\",\"name\":\"zhanghua\",\"nickName\":\"张华\"}");

            String redirectUrl = kodSsoService.buildClientRedirectUrl("kod-token-context", "http://127.0.0.1:3000/callback");
            String exchangeCode = redirectUrl.substring(redirectUrl.indexOf("kodSsoCode=") + "kodSsoCode=".length());
            AuthLoginRespVO result = kodSsoService.exchangeCode(exchangeCode);
            assertPojoEquals(loginRespVO, result);
        }

        verify(adminAuthService, times(1)).createLoginToken(eq(219L), eq("zhanghua"), any());
    }

    @Test
    public void testBuildAuthorizeRedirectUrl_useConfiguredCallbackBaseUrl() {
        kodSsoProperties.setCallbackBaseUrl("http://192.168.1.100:48080/");
        MockHttpServletRequest request = new MockHttpServletRequest("GET",
                "/admin-api/system/auth/kod-sso/start");
        request.setScheme("http");
        request.setServerName("127.0.0.1");
        request.setServerPort(48080);
        request.setRequestURI("/admin-api/system/auth/kod-sso/start");

        String redirectUrl = kodSsoService.buildAuthorizeRedirectUrl(request,
                "http://192.168.1.100:5666/auth/kod-sso-login?tenantId=1&entry=approval");

        String encodedCallbackUrl = redirectUrl.substring(redirectUrl.indexOf("callbackUrl=") + "callbackUrl=".length());
        String callbackUrl = URLDecoder.decode(encodedCallbackUrl, StandardCharsets.UTF_8);

        assertTrue(callbackUrl.startsWith("http://192.168.1.100:48080/admin-api/system/auth/kod-sso/callback?redirectUri="));
        assertTrue(callbackUrl.contains("redirectUri=http://192.168.1.100:5666/auth/kod-sso-login"));
        assertFalse(redirectUrl.contains("127.0.0.1%3A48080"));
    }

    @Test
    public void testLoginByKodToken_matchExistingUserAndCreateBind() {
        kodSsoProperties.getUserRoleMappings().put("u-2", 2L);
        when(kodSsoUserBindMapper.selectByKodUsername(eq("alice"))).thenReturn(null);
        when(adminUserService.getUserByUsername(eq("alice"))).thenReturn(new AdminUserDO()
                .setId(22L).setUsername("alice").setNickname("旧 Alice").setEmail("old@example.com"));
        when(kodSsoUserBindMapper.selectByUserId(eq(22L))).thenReturn(null);
        when(deptMapper.selectByParentIdAndName(eq(0L), eq("销售部")))
                .thenReturn(new DeptDO().setId(2L).setParentId(0L).setName("销售部").setStatus(0));

        AuthLoginRespVO loginRespVO = randomPojo(AuthLoginRespVO.class, o -> o.setUserId(22L));
        when(adminAuthService.createLoginToken(eq(22L), eq("alice"), any())).thenReturn(loginRespVO);

        try (MockedStatic<HttpUtils> mockedHttpUtils = mockStatic(HttpUtils.class, CALLS_REAL_METHODS)) {
            mockedHttpUtils.when(() -> HttpUtils.get(eq("https://kod.example.com/?user/sso/apiCheckToken&accessToken=kod-token-2&appName=oa-lite"),
                    eq(Collections.emptyMap())))
                    .thenReturn("{\"userID\":\"u-2\",\"name\":\"alice\",\"nickName\":\"Alice\",\"email\":\"alice@example.com\","
                            + "\"groupInfo\":[{\"groupID\":\"2\",\"groupName\":\"销售部\"}]}");

            AuthLoginRespVO result = kodSsoService.loginByKodToken("kod-token-2");
            assertPojoEquals(loginRespVO, result);
        }

        verify(kodSsoUserBindMapper).insert(argThat((KodSsoUserBindDO bind) ->
                bind.getUserId().equals(22L)
                        && "u-2".equals(bind.getKodUserId())
                        && "alice".equals(bind.getKodUsername())));
        verify(adminUserService).updateUserProfile(argThat(userId -> userId.equals(22L)), argThat(reqVO ->
                "Alice".equals(reqVO.getNickname())
                        && "alice@example.com".equals(reqVO.getEmail())));
        verify(adminUserService).updateUserDept(22L, 2L);
        verify(permissionService).assignUserRole(eq(22L), eq(Collections.singleton(2L)));
        verify(adminUserService, never()).createUser(any());
    }

    @Test
    public void testLoginByKodToken_matchBindByKodUsernameAndRefreshBind() {
        KodSsoUserBindDO bind = new KodSsoUserBindDO();
        bind.setId(33L);
        bind.setUserId(33L);
        bind.setKodUserId("old-u-3");
        bind.setKodUsername("old-bob");
        bind.setKodNickname("旧 Bob");
        when(kodSsoUserBindMapper.selectByKodUsername(eq("bob"))).thenReturn(bind);
        when(adminUserService.getUser(eq(33L))).thenReturn(new AdminUserDO()
                .setId(33L).setUsername("kodbob").setDeptId(2L).setNickname("Bob"));
        when(deptMapper.selectByParentIdAndName(eq(0L), eq("总公司")))
                .thenReturn(new DeptDO().setId(1L).setParentId(0L).setName("总公司").setStatus(0));
        when(deptMapper.selectByParentIdAndName(eq(1L), eq("项目部")))
                .thenReturn(new DeptDO().setId(3L).setParentId(1L).setName("项目部").setStatus(0));
        when(permissionService.getUserRoleIdListByUserId(33L)).thenReturn(new HashSet<>(Collections.singleton(3L)));

        AuthLoginRespVO loginRespVO = randomPojo(AuthLoginRespVO.class, o -> o.setUserId(33L));
        when(adminAuthService.createLoginToken(eq(33L), eq("kodbob"), any())).thenReturn(loginRespVO);

        try (MockedStatic<HttpUtils> mockedHttpUtils = mockStatic(HttpUtils.class, CALLS_REAL_METHODS)) {
            mockedHttpUtils.when(() -> HttpUtils.get(eq("https://kod.example.com/?user/sso/apiCheckToken&accessToken=kod-token-3&appName=oa-lite"),
                    eq(Collections.emptyMap())))
                    .thenReturn("{\"userID\":\"u-3\",\"name\":\"bob\",\"nickName\":\"Bob\","
                            + "\"groupInfo\":[{\"groupID\":\"1\",\"groupName\":\"总公司\"},{\"groupID\":\"3\",\"groupName\":\"项目部\"}]}");

            AuthLoginRespVO result = kodSsoService.loginByKodToken("kod-token-3");
            assertPojoEquals(loginRespVO, result);
        }

        verify(kodSsoUserBindMapper).updateById(argThat((KodSsoUserBindDO updatedBind) ->
                updatedBind.getId().equals(33L)
                        && updatedBind.getUserId().equals(33L)
                        && "u-3".equals(updatedBind.getKodUserId())
                        && "bob".equals(updatedBind.getKodUsername())));
        verify(adminUserService, never()).updateUserProfile(anyLong(), any());
        verify(permissionService, never()).assignUserRole(anyLong(), anySet());
        verify(adminUserService).updateUserDept(33L, 3L);
    }

    @Test
    public void testLoginByKodToken_noBindAndNoMatchedUser_autoCreateUserAndDept() {
        kodSsoProperties.getUserRoleMappings().put("u-4", 1L);
        when(kodSsoUserBindMapper.selectByKodUsername(eq("root"))).thenReturn(null);
        when(adminUserService.getUserByUsername(eq("root"))).thenReturn(null);
        when(kodSsoUserBindMapper.selectByKodUserId(eq("u-4"))).thenReturn(null);
        when(deptMapper.selectByParentIdAndName(eq(0L), eq("总公司"))).thenReturn(null);
        when(deptMapper.selectByParentIdAndName(eq(88L), eq("项目部"))).thenReturn(null);
        when(deptService.createDept(any(DeptSaveReqVO.class))).thenAnswer(invocation -> {
            DeptSaveReqVO reqVO = invocation.getArgument(0);
            if (Objects.equals(reqVO.getParentId(), 0L) && Objects.equals(reqVO.getName(), "总公司")) {
                return 88L;
            }
            if (Objects.equals(reqVO.getParentId(), 88L) && Objects.equals(reqVO.getName(), "项目部")) {
                return 99L;
            }
            return null;
        });
        when(deptService.getDept(eq(88L))).thenReturn(new DeptDO().setId(88L).setParentId(0L).setName("总公司").setStatus(0));
        when(deptService.getDept(eq(99L))).thenReturn(new DeptDO().setId(99L).setParentId(88L).setName("项目部").setStatus(0));
        when(adminUserService.createUser(any(UserSaveReqVO.class))).thenReturn(44L);
        when(adminUserService.getUser(eq(44L))).thenReturn(new AdminUserDO().setId(44L).setUsername("root"));
        when(permissionService.getUserRoleIdListByUserId(44L)).thenReturn(Collections.emptySet());

        AuthLoginRespVO loginRespVO = randomPojo(AuthLoginRespVO.class, o -> o.setUserId(44L));
        when(adminAuthService.createLoginToken(eq(44L), eq("root"), any())).thenReturn(loginRespVO);

        try (MockedStatic<HttpUtils> mockedHttpUtils = mockStatic(HttpUtils.class, CALLS_REAL_METHODS)) {
            mockedHttpUtils.when(() -> HttpUtils.get(eq("https://kod.example.com/?user/sso/apiCheckToken&accessToken=kod-token-4&appName=oa-lite"),
                    eq(Collections.emptyMap())))
                    .thenReturn("{\"userID\":\"u-4\",\"name\":\"root\",\"nickName\":\"Root\","
                            + "\"groupInfo\":[{\"groupID\":\"1\",\"groupName\":\"总公司\"},{\"groupID\":\"3\",\"groupName\":\"项目部\"}]}");

            AuthLoginRespVO result = kodSsoService.loginByKodToken("kod-token-4");
            assertPojoEquals(loginRespVO, result);
        }

        verify(adminUserService).createUser(argThat((UserSaveReqVO reqVO) ->
                "root".equals(reqVO.getUsername())
                        && "Root".equals(reqVO.getNickname())
                        && "admin123".equals(reqVO.getPassword())
                        && Objects.equals(reqVO.getDeptId(), 99L)));
        verify(permissionService).assignUserRole(eq(44L), eq(Collections.singleton(1L)));
        verify(kodSsoUserBindMapper).insert(argThat((KodSsoUserBindDO bind) ->
                bind.getUserId().equals(44L)
                        && "u-4".equals(bind.getKodUserId())
                        && "root".equals(bind.getKodUsername())));
    }

    @Test
    public void testLoginByKodToken_rebindOldKodUserIdToUsernameMatchedUser() {
        KodSsoUserBindDO oldBind = new KodSsoUserBindDO()
                .setId(66L)
                .setUserId(151L)
                .setKodUserId("2")
                .setKodUsername("old-user")
                .setKodNickname("旧用户");
        when(kodSsoUserBindMapper.selectByKodUsername(eq("shenzhihua"))).thenReturn(null);
        when(adminUserService.getUserByUsername(eq("shenzhihua"))).thenReturn(
                new AdminUserDO().setId(301L).setUsername("shenzhihua").setNickname("沈志华").setEmail("old-shen@example.com")
        );
        when(kodSsoUserBindMapper.selectByUserId(eq(301L))).thenReturn(null);
        when(kodSsoUserBindMapper.selectByKodUserId(eq("2"))).thenReturn(oldBind);
        when(permissionService.getUserRoleIdListByUserId(301L)).thenReturn(Collections.emptySet());

        AuthLoginRespVO loginRespVO = randomPojo(AuthLoginRespVO.class, o -> o.setUserId(301L));
        when(adminAuthService.createLoginToken(eq(301L), eq("shenzhihua"), any())).thenReturn(loginRespVO);

        try (MockedStatic<HttpUtils> mockedHttpUtils = mockStatic(HttpUtils.class, CALLS_REAL_METHODS)) {
            mockedHttpUtils.when(() -> HttpUtils.get(eq("https://kod.example.com/?user/sso/apiCheckToken&accessToken=kod-token-7&appName=oa-lite"),
                    eq(Collections.emptyMap())))
                    .thenReturn("{\"userID\":\"2\",\"name\":\"shenzhihua\",\"nickName\":\"沈志华\",\"email\":\"shen@example.com\"}");

            AuthLoginRespVO result = kodSsoService.loginByKodToken("kod-token-7");
            assertPojoEquals(loginRespVO, result);
        }

        verify(kodSsoUserBindMapper).updateById(argThat((KodSsoUserBindDO bind) ->
                bind.getId().equals(66L)
                        && bind.getUserId().equals(301L)
                        && "2".equals(bind.getKodUserId())
                        && "shenzhihua".equals(bind.getKodUsername())
                        && "沈志华".equals(bind.getKodNickname())));
    }

}
