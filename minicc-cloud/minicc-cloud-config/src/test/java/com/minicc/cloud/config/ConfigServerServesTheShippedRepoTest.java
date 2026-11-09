package com.minicc.cloud.config;

import static org.assertj.core.api.Assertions.assertThat;

import org.junit.jupiter.api.Test;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.boot.test.context.SpringBootTest;
import org.springframework.boot.test.web.client.TestRestTemplate;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;

/**
 * The config server's promise is narrow and testable: a service that asks for
 * its own name gets its own file *and* the shared one, and the JSON names the
 * source it came from.  A server that only echoed one file would still answer
 * 200 — which is exactly why this test asks for a key from each.
 */
@SpringBootTest(webEnvironment = SpringBootTest.WebEnvironment.RANDOM_PORT)
class ConfigServerServesTheShippedRepoTest {

    @Autowired
    private TestRestTemplate rest;

    @Test
    void aServiceSeesItsOwnFileAndTheSharedFile() {
        ResponseEntity<String> response =
                rest.getForEntity("/minicc-cloud-gateway/default", String.class);

        assertThat(response.getStatusCode()).isEqualTo(HttpStatus.OK);
        String body = response.getBody();
        assertThat(body).isNotNull();
        // Own file.
        assertThat(body).contains("minicc.cloud.gateway.response-timeout-seconds");
        // Shared file: the cross-service budget lives in application.yml only.
        assertThat(body).contains("minicc.cloud.inspector.timeout-seconds");
        assertThat(body).contains("minicc-cloud-gateway.yml");
    }

    @Test
    void anUnknownNameGetsNoInventedProperties() {
        ResponseEntity<String> response =
                rest.getForEntity("/not-a-minicc-service/default", String.class);

        // Config server answers 200 with the shared file only; what must not
        // happen is a property from another service's file appearing here.
        assertThat(response.getBody()).doesNotContain("response-timeout-seconds");
    }
}
