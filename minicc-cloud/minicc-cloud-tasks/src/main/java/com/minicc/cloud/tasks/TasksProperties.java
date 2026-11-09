package com.minicc.cloud.tasks;

import org.springframework.boot.context.properties.ConfigurationProperties;

/**
 * Where the task database lives and how much of it one list call may return.
 *
 * @param db       the SQLite file the Python engine writes; opened read-only
 * @param maxLimit the hard ceiling for {@code limit}, served by the config
 *                 server so it is not a literal inside the controller
 */
@ConfigurationProperties(prefix = "minicc.cloud.tasks")
public record TasksProperties(String db, Integer maxLimit) {

    public TasksProperties {
        if (db == null || db.isBlank()) {
            throw new IllegalStateException("minicc.cloud.tasks.db must name the SQLite file to read");
        }
        if (maxLimit == null || maxLimit < 1) {
            throw new IllegalStateException("minicc.cloud.tasks.max-limit must be a positive integer");
        }
    }
}
