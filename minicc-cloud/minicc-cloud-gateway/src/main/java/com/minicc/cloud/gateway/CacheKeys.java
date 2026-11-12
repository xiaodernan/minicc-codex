package com.minicc.cloud.gateway;

import java.util.Locale;
import java.util.Map;

/**
 * M8-T826 — the one home for the gateway's cache keys.
 *
 * <p>Before this class the cache key existed in three incompatible spellings:
 * {@code @Cacheable(key = "'inspector:status'")} on the controller, a service
 * name ({@code "inspector"}) in the invalidation message payload, and whatever
 * the {@code route} header happened to carry when the listener called
 * {@code cache.evict(route)}. When those spellings disagreed, evict silently
 * missed — the listener returned normally, the stale entry stayed in Redis for
 * its full 60s TTL, and every CLI poll kept reading pre-change data. There was
 * no test that could see it, and no publisher that ever sent a message at all.
 *
 * <p>The rule now has one home, mirroring the Python side's
 * {@code is_nameless_tool_name}: the controller, the publisher and the listener
 * all ask {@link #forService(String)}. A downstream service publishes its own
 * name; both the write key and the evict key come from this one function, so
 * they cannot drift.
 */
public final class CacheKeys {

    /** Cache name declared in application.yml (cache-names: gateway-routes). */
    public static final String CACHE_NAME = "gateway-routes";

    /** Canonical keys — the exact strings @Cacheable stores under. */
    public static final String INSPECTOR_STATUS = "inspector:status";
    public static final String INSIGHTS_SUMMARY = "insights:summary";

    private static final Map<String, String> BY_SERVICE = Map.of(
            "inspector", INSPECTOR_STATUS,
            "insights", INSIGHTS_SUMMARY);

    private CacheKeys() {
    }

    /**
     * Resolve the canonical cache key for a service name or an already-canonical
     * key. Accepts both so a publisher can send {@code "inspector"} and a future
     * operator can send {@code "inspector:status"} without creating a second
     * spelling. Case and surrounding whitespace are normalised.
     *
     * @return the canonical key, or {@code null} when the service is unknown —
     *         unknown services must not evict an arbitrary key (that is how one
     *         typo could clear another service's entry).
     */
    public static String forService(String serviceOrKey) {
        if (serviceOrKey == null) {
            return null;
        }
        String raw = serviceOrKey.trim().toLowerCase(Locale.ROOT);
        if (raw.isEmpty()) {
            return null;
        }
        String byService = BY_SERVICE.get(raw);
        if (byService != null) {
            return byService;
        }
        // Already canonical (e.g. "inspector:status") — accept only known keys.
        for (String canonical : BY_SERVICE.values()) {
            if (canonical.equals(raw)) {
                return canonical;
            }
        }
        return null;
    }

    /** The services whose cached routes exist (for publishers / introspection). */
    public static java.util.Set<String> services() {
        return BY_SERVICE.keySet();
    }
}
