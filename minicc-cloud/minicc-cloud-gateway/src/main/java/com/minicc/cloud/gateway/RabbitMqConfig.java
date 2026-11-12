package com.minicc.cloud.gateway;

import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.FanoutExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;

/**
 * RabbitMQ topology for gateway cache invalidation (M8-T826).
 *
 * <p>Invalidations go to a <em>fanout exchange</em>, not straight to a queue
 * name. A gateway in production has more than one replica, each with its own
 * Redis-backed cache view for the shared cache; publishing to one queue name
 * would invalidate only whichever replica happened to bind it, leaving the
 * others serving stale data. Fanout delivers the event to every bound replica's
 * queue, so a change invalidates all of them. This is why
 * {@link CacheInvalidationPublisher} sends to {@link #ROUTE_REFRESH_EXCHANGE}
 * and the listener binds a queue to it.
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
    public FanoutExchange routeRefreshExchange() {
        return new FanoutExchange(ROUTE_REFRESH_EXCHANGE, true, false);
    }

    @Bean
    public Binding routeRefreshBinding(Queue cacheInvalidateQueue, FanoutExchange routeRefreshExchange) {
        return BindingBuilder.bind(cacheInvalidateQueue).to(routeRefreshExchange);
    }

    @Bean
    public AmqpTemplate amqpTemplate(RabbitTemplate rabbitTemplate) {
        return rabbitTemplate;
    }
}
