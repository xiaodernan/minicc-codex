package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.io.IOException;
import java.io.UncheckedIOException;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;

/**
 * M8-T882 — the opt-in token bucket exists and stays wired end to end.
 *
 * <p>Three links in one chain, scanned as plain text so a drifted file fails
 * loudly instead of silently shipping an unenforced limit:</p>
 * <ol>
 *   <li>{@code application-ratelimit.yml} declares the RequestRateLimiter
 *       default filter with Redis replenish/burst and points at the
 *       {@code ipKeyResolver} bean;</li>
 *   <li>the profile file and the {@link IpKeyResolver} bean agree on the
 *       bean name (the SpEL reference must resolve);</li>
 *   <li>compose activates the profile for the gateway (SPRING_PROFILES_ACTIVE) —
 *       a profile nobody activates is decoration, not a limiter.</li>
 * </ol>
 */
class RateLimitProfileTest {

    private static final Path PROFILE_YML =
            Path.of("src", "main", "resources", "application-ratelimit.yml");
    private static final Path RESOLVER_JAVA =
            Path.of("src", "main", "java", "com", "minicc", "cloud", "gateway", "IpKeyResolver.java");
    private static final Path COMPOSE = Path.of("..", "docker-compose.yml");

    @Test
    void theProfileDeclaresTheRedisTokenBucket() {
        String yaml = read(PROFILE_YML);
        assertThat(yaml)
                .contains("RequestRateLimiter")
                .contains("redis-rate-limiter.replenishRate")
                .contains("redis-rate-limiter.burstCapacity")
                .contains("redis-rate-limiter.requestedTokens")
                .contains("default-filters");
    }

    @Test
    void theFilterPointsAtTheResolverBeanThatExists() {
        String yaml = read(PROFILE_YML);
        String resolver = read(RESOLVER_JAVA);
        assertThat(yaml).contains("#{@ipKeyResolver}");
        assertThat(resolver).contains("@Component(\"ipKeyResolver\")");
    }

    @Test
    void composeActivatesTheProfileForTheGateway() {
        org.junit.jupiter.api.Assumptions.assumeTrue(Files.isRegularFile(COMPOSE),
                "compose file not present in this checkout");
        String compose = read(COMPOSE);
        assertThat(compose)
                .contains("SPRING_PROFILES_ACTIVE")
                .contains("ratelimit");
    }

    private static String read(Path path) {
        try {
            return Files.readString(path, StandardCharsets.UTF_8);
        } catch (IOException exc) {
            throw new UncheckedIOException(exc);
        }
    }
}
