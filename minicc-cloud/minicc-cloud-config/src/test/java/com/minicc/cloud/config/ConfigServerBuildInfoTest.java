package com.minicc.cloud.config;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.InputStream;
import java.util.Properties;
import org.junit.jupiter.api.Test;

/**
 * The shipped jar carries a build manifest, so `/actuator/info` answers
 * artifact/group/version/time without SSH. Same shape as the gateway's.
 */
class ConfigServerBuildInfoTest {

    @Test
    void buildInfoCarriesArtifactGroupAndVersion() throws IOException {
        try (InputStream in = ConfigServerBuildInfoTest.class.getClassLoader()
                .getResourceAsStream("META-INF/build-info.properties")) {
            assertThat(in).as("build-info.properties should be on the classpath").isNotNull();
            Properties props = new Properties();
            props.load(in);
            assertThat(props.getProperty("build.artifact")).isEqualTo("minicc-cloud-config");
            assertThat(props.getProperty("build.group")).isEqualTo("com.minicc.cloud");
            assertThat(props.getProperty("build.version")).isEqualTo("0.1.0");
        }
    }
}
