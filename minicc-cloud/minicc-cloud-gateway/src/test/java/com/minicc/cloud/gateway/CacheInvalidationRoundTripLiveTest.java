package com.minicc.cloud.gateway;

import static org.assertj.core.api.Assertions.assertThat;
import static org.junit.jupiter.api.Assumptions.assumeTrue;

import java.nio.charset.StandardCharsets;
import java.util.UUID;
import org.junit.jupiter.api.Test;
import org.springframework.amqp.core.Binding;
import org.springframework.amqp.core.BindingBuilder;
import org.springframework.amqp.core.FanoutExchange;
import org.springframework.amqp.core.Queue;
import org.springframework.amqp.rabbit.connection.CachingConnectionFactory;
import org.springframework.amqp.rabbit.core.RabbitAdmin;
import org.springframework.amqp.rabbit.core.RabbitTemplate;
import org.springframework.amqp.core.Message;

/**
 * Opt-in live AMQP round trip for the invalidation path (skipped unless
 * {@code MINICC_TEST_RABBIT_URI} is set, e.g. {@code amqp://guest:guest@127.0.0.1:5672/}).
 *
 * <p>The mocked tests pin the key agreement and the evict decision; what they cannot
 * see is whether the exchange declaration, fanout binding, and header propagation
 * survive contact with a real broker. This test binds its own throwaway auto-delete
 * queue to the same fanout exchange the listener consumes from and receives one
 * message, so a serialization or header mismatch fails here before an operator
 * notices stale cache entries.
 */
class CacheInvalidationRoundTripLiveTest {

    @Test
    void invalidationMessageCrossesTheFanoutExchange() {
        String uri = System.getenv("MINICC_TEST_RABBIT_URI");
        assumeTrue(uri != null && !uri.isBlank(), "MINICC_TEST_RABBIT_URI not set; skipping live AMQP round trip");

        CachingConnectionFactory factory = new CachingConnectionFactory();
        factory.setUri(uri.trim());
        try {
            RabbitAdmin admin = new RabbitAdmin(factory);
            FanoutExchange exchange =
                    new FanoutExchange(RabbitMqConfig.ROUTE_REFRESH_EXCHANGE, true, false);
            admin.declareExchange(exchange);

            String queueName = "minicc.gateway.cache.invalidate.test." + UUID.randomUUID();
            Queue queue = new Queue(queueName, false, false, true);
            admin.declareQueue(queue);
            Binding binding = BindingBuilder.bind(queue).to(exchange);
            admin.declareBinding(binding);

            RabbitTemplate template = new RabbitTemplate(factory);
            CacheInvalidationPublisher publisher = new CacheInvalidationPublisher(template);

            String canonical = publisher.invalidate("inspector");
            assertThat(canonical).isEqualTo(CacheKeys.INSPECTOR_STATUS);

            Message message = template.receive(queueName, 5_000L);
            assertThat(message).as("the invalidation message arrived at the throwaway queue").isNotNull();
            assertThat(new String(message.getBody(), StandardCharsets.UTF_8)).isEqualTo("inspector");
            assertThat(message.getMessageProperties().getHeaders())
                    .containsEntry(CacheInvalidationPublisher.ROUTE_HEADER, CacheKeys.INSPECTOR_STATUS);

            admin.deleteQueue(queueName);
        } finally {
            factory.destroy();
        }
    }
}
