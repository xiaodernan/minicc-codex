package com.minicc.cloud.insights;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.boot.context.properties.ConfigurationPropertiesScan;
import org.springframework.cloud.client.discovery.EnableDiscoveryClient;

@EnableDiscoveryClient
@ConfigurationPropertiesScan
@SpringBootApplication
public class InsightsApplication {

    public static void main(String[] args) {
        SpringApplication.run(InsightsApplication.class, args);
    }
}
