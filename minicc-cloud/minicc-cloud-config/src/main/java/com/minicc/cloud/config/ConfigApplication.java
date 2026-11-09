package com.minicc.cloud.config;

import org.springframework.boot.SpringApplication;
import org.springframework.boot.autoconfigure.SpringBootApplication;
import org.springframework.cloud.config.server.EnableConfigServer;

/**
 * Config server for the minicc cloud services.
 *
 * <p>The repository it serves is the {@code config-repo} directory shipped on
 * the classpath (and, when mounted, {@code file:./config-repo/} first so a
 * deployment can override a value without rebuilding the jar).  The native
 * profile is deliberate: these services run next to the Python tool they
 * describe, and a git-backed config server would add a second source of truth
 * for files this repository already tracks.
 */
@EnableConfigServer
@SpringBootApplication
public class ConfigApplication {

    public static void main(String[] args) {
        SpringApplication.run(ConfigApplication.class, args);
    }
}
