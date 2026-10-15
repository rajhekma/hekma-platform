package com.hekma.ctms;

import com.hekma.ctms.security.client.IdentityServiceClient;
import org.junit.jupiter.api.Test;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.test.context.bean.override.mockito.MockitoBean;

@SpringBootTest
class HekmaCtmsServiceApplicationTests {

    @MockitoBean
    private IdentityServiceClient identityServiceClient;

    @Test
    void contextLoads() {
    }

}
