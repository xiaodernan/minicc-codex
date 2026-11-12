package com.minicc.cloud.gateway;

import java.util.Map;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.cache.CacheManager;
import org.springframework.messaging.handler.annotation.Header;
import org.springframework.messaging.handler.annotation.Payload;
import org.springframework.stereotype.Component;

/**
 * Consumes cache invalidation requests from RabbitMQ and clears the
 * corresponding Redis cache entries.
 *
 * <p>Downstream services (inspector, tasks, insights) publish messages to
 * the cache-invalidate queue when their data changes.  The gateway listens
 * and evicts the relevant cache entries so subsequent requests get fresh
 * data instead of stale cache hits.
 */
@Component
public class CacheInvalidationListener {

    private final CacheManager cacheManager;

    @Autowired
    public CacheInvalidationListener(CacheManager cacheManager) {
        this.cacheManager = cacheManager;
    }

    @RabbitListener(queues = RabbitMqConfig.CACHE_INVALIDATE_QUEUE)
    public void handleCacheInvalidate(
            @Payload String serviceName,
            @Header(name = "route", required = false) String route) {
        var cache = cacheManager.getCache("gateway-routes");
        if (cache == null) {
            return;
        }
        if (route != null) {
            cache.evict(route);
        } else {
            cache.clear();
        }
    }
}
