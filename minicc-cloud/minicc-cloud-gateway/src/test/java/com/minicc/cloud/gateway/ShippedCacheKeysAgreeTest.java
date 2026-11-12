package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.ArgumentMatchers.eq;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;

import java.lang.reflect.Method;
import java.nio.charset.StandardCharsets;
import java.nio.file.Files;
import java.nio.file.Path;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.Message;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;

/**
 * M8-T826 — write key, publish key and evict key are the same string.
 *
 * <p>The defect this pins: the controller stored under {@code "inspector:status"}
 * but the listener evicted the raw message payload (e.g. {@code "inspector"}).
 * The evict missed silently, Redis kept the stale value for its 60s TTL, and
 * nothing in the test suite could see it. A second defect: nobody published at
 * all — the queue had a consumer only.
 *
 * <p>These are plain unit tests (no Spring context, no broker): they read the
 * shipped service source (the {@code @Cacheable} home — M8-T861 moved the
 * annotations out of the controller) for the literals and assert the one home
 * {@link CacheKeys} agrees, then exercise publish → consume with mocks to prove
 * the whole loop resolves to the identical key.
 */
class ShippedCacheKeysAgreeTest {

    private static final Path SERVICE = Path.of(
            "src", "main", "java", "com", "minicc", "cloud", "gateway",
            "CachedStatusService.java");
    private static final Path CONTROLLER = Path.of(
            "src", "main", "java", "com", "minicc", "cloud", "gateway",
            "CachedRouteController.java");

    private String serviceSource() throws Exception {
        return Files.readString(SERVICE, StandardCharsets.UTF_8);
    }

    @Test
    void theCacheableLiteralsComeFromTheOneHome() throws Exception {
        String source = serviceSource();
        // The annotations sit on the service boundary now; it references
        // CacheKeys.INSPECTOR_STATUS / INSIGHTS_SUMMARY and carries no copy.
        assertThat(source).contains("CacheKeys.INSPECTOR_STATUS");
        assertThat(source).contains("CacheKeys.INSIGHTS_SUMMARY");
        assertThat(source).doesNotContain("\"inspector:status\"");
        assertThat(source).doesNotContain("\"insights:summary\"");
        assertThat(CacheKeys.INSPECTOR_STATUS).isEqualTo("inspector:status");
        assertThat(CacheKeys.INSIGHTS_SUMMARY).isEqualTo("insights:summary");

        String controller = Files.readString(CONTROLLER, StandardCharsets.UTF_8);
        // The controller must not re-declare the keys or the annotations.
        assertThat(controller).doesNotContain("@Cacheable");
        assertThat(controller).doesNotContain("\"inspector:status\"");
        assertThat(controller).doesNotContain("\"insights:summary\"");
    }

    @Test
    void everyPublishedServiceResolvesToTheKeyTheControllerWrites() {
        for (String service : CacheKeys.services()) {
            String published = CacheKeys.forService(service);
            assertThat(published).as("service %s must resolve", service).isNotNull();
            // Simulate what the controller stores and what the listener evicts.
            String writeKey = published;
            String evictKey = CacheInvalidationListener.resolveEvictKey(service, published);
            assertThat(evictKey).as("evict key must equal write key for %s", service).isEqualTo(writeKey);
        }
    }

    @Test
    void aServiceNamePayloadAloneEvictsTheCanonicalKey() {
        // The natural case that used to silently miss: publisher sends "inspector",
        // no route header; the listener must still find "inspector:status".
        assertThat(CacheInvalidationListener.resolveEvictKey("inspector", null))
                .isEqualTo(CacheKeys.INSPECTOR_STATUS);
        assertThat(CacheInvalidationListener.resolveEvictKey("INSIGHTS", "  "))
                .isEqualTo(CacheKeys.INSIGHTS_SUMMARY);
        // Canonical key sent directly is accepted unchanged.
        assertThat(CacheInvalidationListener.resolveEvictKey(null, "inspector:status"))
                .isEqualTo(CacheKeys.INSPECTOR_STATUS);
    }

    @Test
    void anUnknownServiceEvictsNothingAndAnEmptyTargetClearsAll() {
        assertThat(CacheInvalidationListener.resolveEvictKey("nope", null)).isNull();
        assertThat(CacheInvalidationListener.resolveEvictKey("", "typo-key")).isNull();
        assertThat(CacheInvalidationListener.resolveEvictKey(null, null))
                .isEqualTo(CacheInvalidationListener.EVICT_ALL);
        assertThat(CacheInvalidationListener.resolveEvictKey("inspector", "*"))
                .isEqualTo(CacheInvalidationListener.EVICT_ALL);
    }

    @Test
    void thePublisherSendsTheServiceWithTheCanonicalRouteHeader() {
        AmqpTemplate template = mock(AmqpTemplate.class);
        CacheInvalidationPublisher publisher = new CacheInvalidationPublisher(template);

        String key = publisher.invalidate("inspector");

        assertThat(key).isEqualTo(CacheKeys.INSPECTOR_STATUS);
        // Fanout exchange (not a queue name) so every gateway replica is invalidated.
        verify(template).convertAndSend(
                eq(RabbitMqConfig.ROUTE_REFRESH_EXCHANGE), eq(""), any(Message.class));
    }

    @Test
    void thePublisherRefusesUnknownServicesWithoutSending() {
        AmqpTemplate template = mock(AmqpTemplate.class);
        CacheInvalidationPublisher publisher = new CacheInvalidationPublisher(template);

        assertThat(publisher.invalidate("nope")).isNull();
        assertThat(publisher.invalidate(null)).isNull();
        verify(template, never()).convertAndSend(any(String.class), any(String.class), any(Object.class));
    }

    @Test
    void invalidationUsesAFanoutExchangeSoEveryReplicaIsReached() {
        RabbitMqConfig config = new RabbitMqConfig();
        org.assertj.core.api.Assertions.assertThat(config.routeRefreshExchange().getType())
                .as("a direct publish to one queue would leave other gateway replicas stale")
                .isEqualTo("fanout");
        Binding binding = config.routeRefreshBinding(
                config.cacheInvalidateQueue(), config.routeRefreshExchange());
        assertThat(binding.getExchange()).isEqualTo(RabbitMqConfig.ROUTE_REFRESH_EXCHANGE);
        assertThat(binding.getDestination()).isEqualTo(RabbitMqConfig.CACHE_INVALIDATE_QUEUE);
    }

    @Test
    void theListenerEvictsExactlyThePublishedKey() {
        // End-to-end over mocks: publisher's header → listener's evict call.
        Cache cache = mock(Cache.class);
        CacheManager manager = mock(CacheManager.class);
        org.mockito.Mockito.when(manager.getCache(CacheKeys.CACHE_NAME)).thenReturn(cache);
        CacheInvalidationListener listener = new CacheInvalidationListener(manager);

        String publishedKey = CacheKeys.forService("insights");
        listener.handleCacheInvalidate("insights", publishedKey);

        verify(cache).evict(CacheKeys.INSIGHTS_SUMMARY);
    }
}
