package com.minicc.cloud.gateway;

import org.springframework.amqp.core.AmqpTemplate;
import org.springframework.amqp.core.Message;
import org.springframework.amqp.core.MessageBuilder;
import org.springframework.amqp.core.MessageProperties;
import org.springframework.beans.factory.annotation.Autowired;
import org.springframework.stereotype.Component;

/**
 * M8-T826 — the missing publisher half of the cache-invalidation loop.
 *
 * <p>Before this class the gateway had a {@link CacheInvalidationListener} and a
 * queue but no producer anywhere in the repo: the docstring claimed "downstream
 * services publish messages" while grep found zero {@code convertAndSend} calls.
 * A listener nobody can feed is decoration, not an invalidation path.
 *
 * <p>This is the canonical producer. It accepts only known services (the same
 * ones {@link CacheKeys#forService(String)} resolves), and sends the service
 * name as payload plus the canonical key in the {@code route} header, so the
 * consumer's evict key is guaranteed to match the controller's write key.
 * Downstream services can call {@link #invalidate(String)} directly, or publish
 * the same shape over the queue from their own language.
 */
@Component
public class CacheInvalidationPublisher {

    /** Header carrying the canonical cache key; mirrors the listener's reader. */
    public static final String ROUTE_HEADER = "route";

    private final AmqpTemplate amqpTemplate;

    @Autowired
    public CacheInvalidationPublisher(AmqpTemplate amqpTemplate) {
        this.amqpTemplate = amqpTemplate;
    }

    /**
     * Publish an invalidation for one service.
     *
     * @param service a known service name ({@code inspector} / {@code insights});
     *                unknown or null is rejected, never published.
     * @return the canonical key that was put in the header, or {@code null} when
     *         the service was unknown (nothing was sent).
     */
    public String invalidate(String service) {
        String canonical = CacheKeys.forService(service);
        if (canonical == null) {
            return null;
        }
        Message message = MessageBuilder.withBody(service.trim().getBytes(java.nio.charset.StandardCharsets.UTF_8))
                .setContentType(MessageProperties.CONTENT_TYPE_TEXT_PLAIN)
                .setHeader(ROUTE_HEADER, canonical)
                .build();
        // Fanout exchange, not the queue name: every gateway replica bound to
        // the exchange gets the invalidation, not just one lucky consumer.
        amqpTemplate.convertAndSend(RabbitMqConfig.ROUTE_REFRESH_EXCHANGE, "", (Object) message);
        return canonical;
    }
}
