package com.minicc.cloud.insights;

import com.fasterxml.jackson.annotation.JsonProperty;
import java.util.List;

/** One JSON answer: the fleet's service topology, names and statuses only. */
public record FleetResponse(
        @JsonProperty("schema_version") String schemaVersion,
        @JsonProperty("generated_at") String generatedAt,
        @JsonProperty("service_count") int serviceCount,
        @JsonProperty("total_instances") int totalInstances,
        @JsonProperty("services") List<ServiceEntry> services) {

    public record ServiceEntry(
            @JsonProperty("name") String name,
            @JsonProperty("instance_count") int instanceCount,
            @JsonProperty("instances") List<Instance> instances) {
    }

    public record Instance(
            @JsonProperty("instance_id") String instanceId,
            @JsonProperty("host") String host,
            @JsonProperty("port") int port,
            @JsonProperty("uri") String uri,
            @JsonProperty("status") String status) {
    }
}
