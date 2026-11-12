package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;

import java.util.Map;
import org.junit.jupiter.api.Test;
import org.springframework.data.redis.serializer.JdkSerializationRedisSerializer;

/**
 * The real Redis write path (`spring.cache.type=redis`) serializes values with the
 * JDK serializer. M8-T861 was motivated by the cached routes returning
 * {@code ResponseEntity} — an object the JDK cannot write — which would have made
 * every cache write against a real Redis throw, after weeks of green unit tests that
 * ran with {@code spring.cache.type=none}. This gate pins the actual contract: every
 * payload the @Cacheable service hands to the cache round-trips.
 */
class CachedPayloadRoundTripTest {

    private final JdkSerializationRedisSerializer serializer = new JdkSerializationRedisSerializer();

    @SuppressWarnings("unchecked")
    private static Map<String, Object> roundTrip(JdkSerializationRedisSerializer s, Map<String, Object> payload) {
        return (Map<String, Object>) s.deserialize(s.serialize(payload));
    }

    @Test
    void theStatusPayloadsRoundTripThroughTheRealSerializer() {
        Map<String, Object> inspector = CachedStatusService.statusPayload("inspector", "UP");
        Map<String, Object> insights = CachedStatusService.statusPayload("insights", "DOWN");

        Map<String, Object> restoredInspector = roundTrip(serializer, inspector);
        Map<String, Object> restoredInsights = roundTrip(serializer, insights);

        assertThat(restoredInspector).containsEntry("service", "inspector").containsEntry("upstreamStatus", "UP");
        assertThat(restoredInsights).containsEntry("service", "insights").containsEntry("upstreamStatus", "DOWN");
    }

    @Test
    void theChangesBodyRoundTripsAsAString() {
        String body = "{\"files\":[{\"path\":\"minicc/web.py\",\"additions\":3}]}";
        String restored = (String) serializer.deserialize(serializer.serialize(body));
        assertThat(restored).isEqualTo(body);
    }

    @Test
    void anEmptyStringBodyRoundTrips() {
        String restored = (String) serializer.deserialize(serializer.serialize(""));
        assertThat(restored).isEqualTo("");
    }
}
