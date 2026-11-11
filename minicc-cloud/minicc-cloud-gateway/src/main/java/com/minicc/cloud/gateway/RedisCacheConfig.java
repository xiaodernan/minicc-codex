package com.minicc.cloud.gateway;

import org.springframework.cache.annotation.EnableCaching;
import org.springframework.context.annotation.Bean;
import org.springframework.context.annotation.Configuration;
import org.springframework.data.redis.connection.RedisStandaloneConfiguration;
import org.springframework.data.redis.connection.lettuce.LettuceConnectionFactory;
import org.springframework.data.redis.core.RedisTemplate;
import org.springframework.data.redis.serializer.StringRedisSerializer;

/**
 * Redis cache configuration for the gateway.
 *
 * <p>Caches route responses so repeated calls to the same endpoint do not
 * repeatedly hit downstream services.  The cache is short-lived by design -
 * stale data is preferable to no data when a downstream service is slow or
 * degraded.
 */
@Configuration
@EnableCaching
public class RedisCacheConfig {

    @Bean
    public LettuceConnectionFactory redisConnectionFactory() {
        RedisStandaloneConfiguration config = new RedisStandaloneConfiguration();
        config.setHostName(System.getenv("SPRING_DATA_REDIS_HOST"));
        config.setPort(Integer.parseInt(System.getenv("SPRING_DATA_REDIS_PORT")));
        return new LettuceConnectionFactory(config);
    }

    @Bean
    public RedisTemplate<String, Object> redisTemplate(
            LettuceConnectionFactory connectionFactory) {
        RedisTemplate<String, Object> template = new RedisTemplate<>();
        template.setConnectionFactory(connectionFactory);
        template.setKeySerializer(new StringRedisSerializer());
        template.setValueSerializer(new StringRedisSerializer());
        return template;
    }
}
