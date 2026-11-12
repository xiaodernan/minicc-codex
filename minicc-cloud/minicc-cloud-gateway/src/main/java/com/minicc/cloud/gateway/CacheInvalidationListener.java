package com.minicc.cloud.gateway;

import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.Cache;
import org.springframework.cache.CacheManager;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

/**
 * Consumes cache invalidation requests from RabbitMQ and clears the
 * corresponding Redis cache entries.
 *
 * <p>Downstream services (inspector, insights) publish their own service name to
 * the cache-invalidate queue when their data changes. The gateway evicts the
 * relevant entry so the next CLI poll reads fresh data instead of a stale hit.
 *
 * <p>M8-T826 fixes a silent-failure defect: the listener used to call
 * {@code cache.evict(route)} with the raw header, while the controller stored
 * under {@code @Cacheable(key = "inspector:status")}. A publisher sending
 * {@code "inspector"} (the natural payload) evicted key {@code "inspector"},
 * which was never stored — the cache stayed warm for its full TTL and no test
 * could see it. Now the payload/header is resolved through the one home
 * {@link CacheKeys#forService(String)}, so write and evict cannot drift; an
 * unknown service evicts nothing (a typo must not clear another service).
 */
@Component
public class CacheInvalidationListener {

    /** Sentinel meaning "clear the whole cache" — no service targeted. */
    public static final String EVICT_ALL = "*";

    private final CacheManager cacheManager;

    @Autowired
    public CacheInvalidationListener(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    /**
     * Pure decision, no I/O — the subject of {@code ShippedCacheKeysAgreeTest}.
     * A service name or canonical key resolves to that key; {@code null}/{@code *}
     * means evict everything; an unknown name resolves to {@code null} and must
     * not be passed to evict.
     */
    public static String resolveEvictKey(String serviceName, String routeHeader) {
        // The header is the more specific hint when present; otherwise the
        // payload carries the publishing service's name.
        String candidate = routeHeader != null && !routeHeader.isBlank()
                ? routeHeader
                : serviceName;
        if (candidate == null) {
            return EVICT_ALL;
        }
        String trimmed = candidate.trim();
        if (trimmed.isEmpty() || EVICT_ALL.equals(trimmed)) {
            return EVICT_ALL;
        }
        return CacheKeys.forService(trimmed); // null == unknown: caller evicts nothing
    }

    @RabbitListener(queues = RabbitMqConfig.CACHE_INVALIDATE_QUEUE)
    public void handleCacheInvalidate(
            @Payload String serviceName,
            @Header(name = "route", required = false) String route) {
        Cache cache = cacheManager.getCache(CacheKeys.CACHE_NAME);
        if (cache == null) {
            return;
        }
        String key = resolveEvictKey(serviceName, route);
        if (key == null) {
            // Unknown service: never evict an arbitrary key (a typo here would
            // silently clear a different service's warm entry).
            return;
        }
        if (EVICT_ALL.equals(key)) {
            cache.clear();
        } else {
            cache.evict(key);
        }
    }
}
