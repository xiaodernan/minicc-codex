package com.minicc.cloud.gateway;

import java.util.Map;
import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.annotation.RabbitListener;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.beans.factory.annotation.Value;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.messaging.handler.annotation.Headers;
import org.springframework.messaging.handler.annotation.Payload;

/**
 * RabbitMQ message configuration and event listeners for the gateway.
 *
 * <p>Publishes route-invalidation events when cached data becomes stale, and
 * consumes cache-clear requests from downstream services.  Decouples the
 * gateway from direct cache invalidation calls, allowing services to request
 * cache refreshes asynchronously.
 */
@Configuration
public class RabbitMqConfig {

    public static final String CACHE_INVALIDATE_QUEUE = "minicc.gateway.cache.invalidate";
    public static final String ROUTE_REFRESH_EXCHANGE = "minicc.gateway.route.refresh";

    @Bean
    public Queue cacheInvalidateQueue() {
        return new Queue(CACHE_INVALIDATE_QUEUE, true);
    }

    @Bean
    public AmqpTemplate amqpTemplate(RabbitTemplate rabbitTemplate) {
        return rabbitTemplate;
    }
}
