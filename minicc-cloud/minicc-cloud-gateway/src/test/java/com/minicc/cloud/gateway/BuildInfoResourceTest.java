package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.nio.charset.StandardCharsets;
import java.time.OffsetDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Properties;
import org.junit.jupiter.api.Test;

/**
 * The actuator surface exposes /actuator/info via the {@code build} key, from
 * META-INF/build-info.properties, so operators can answer "what is running here,
 * built when" without SSH. This pins the file that build emits: artifact, group,
 * version and an ISO-8601 timestamp — if the plugin stops running, this goes red.
 */
class BuildInfoResourceTest {

    @Test
    void buildInfoCarriesArtifactGroupVersionAndIsoTimestamp() throws IOException {
        try (InputStream in = BuildInfoResourceTest.class.getClassLoader()
                .getResourceAsStream("META-INF/build-info.properties")) {
            assertThat(in).as("build-info.properties is on the classpath at test time").isNotNull();
            Properties props = new Properties();
            props.load(in);

            assertThat(props.getProperty("build.artifact")).isEqualTo("minicc-cloud-gateway");
            assertThat(props.getProperty("build.group")).isEqualTo("com.minicc.cloud");
            assertThat(props.getProperty("build.name")).isEqualTo("minicc-cloud-gateway");
            assertThat(props.getProperty("build.version")).isEqualTo("0.1.0");

            // build.time is java.util.Properties-escaped ISO-8601, e.g. 2026-11-13T04\:48\:01.085Z
            String stamp = props.getProperty("build.time").replace("\\:", ":");
            assertThat(OffsetDateTime.parse(stamp, DateTimeFormatter.ISO_OFFSET_DATE_TIME).getYear())
                    .isGreaterThanOrEqualTo(2026);
        }
    }

    @Test
    void theFileContainsExactlyTheKeysActuatorSurfaces() throws IOException {
        try (InputStream in = BuildInfoResourceTest.class.getClassLoader()
                .getResourceAsStream("META-INF/build-info.properties")) {
            Properties props = new Properties();
            props.load(in);

            // These are the keys Actuator's BuildInfo version uses for /actuator/info.
            assertThat(props).containsKeys("build.artifact", "build.group", "build.version", "build.time", "build.name");
        }
    }
}
