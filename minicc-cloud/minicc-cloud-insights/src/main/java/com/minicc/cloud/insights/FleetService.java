package com.minicc.cloud.insights;

import com.netflix.appinfo.InstanceInfo;
import java.util.ArrayList;
import java.util.List;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.netflix.eureka.EurekaServiceInstance;
import org.springframework.stereotype.Service;

/**
 * Read-only fleet topology from the registry — the one question Eureka knows
 * that nothing else answers: "which instances exist right now, and are they UP?"
 *
 * <p>Registration itself is owned by each service; this service never writes,
 * never heartbeats and never forces eviction. Any failure to read the
 * registry surfaces as {@link RegistryUnavailableException} — never as an
 * empty fleet, which would look like "nothing is running" to an operator
 * at the exact moment the lookup is blind.
 */
@Service
public class FleetService {

    private final DiscoveryClient discovery;

    public FleetService(DiscoveryClient discovery) {
        this.discovery = discovery;
    }

    public FleetResponse fleet() {
        final List<String> serviceNames;
        try {
            serviceNames = discovery.getServices();
        } catch (RuntimeException exc) {
            throw new RegistryUnavailableException(
                    "the service registry could not be read: " + exc.getMessage(), exc);
        }

        List<FleetResponse.ServiceEntry> entries = new ArrayList<>();
        int totalInstances = 0;
        if (serviceNames != null) {
            for (String name : serviceNames.stream().filter(s -> s != null && !s.isBlank()).distinct().sorted().toList()) {
                List<FleetResponse.Instance> instances = new ArrayList<>();
                try {
                    for (ServiceInstance instance : discovery.getInstances(name)) {
                        instances.add(new FleetResponse.Instance(
                                safe(instance.getInstanceId()),
                                safe(instance.getHost()),
                                instance.getPort(),
                                instance.getUri() == null ? null : instance.getUri().toString(),
                                statusOf(instance)));
                    }
                } catch (RuntimeException exc) {
                    // A single unreadable application is the registry being
                    // blind, not an empty service - refuse rather than guess.
                    throw new RegistryUnavailableException(
                            "the instances of '" + name + "' could not be read: " + exc.getMessage(), exc);
                }
                entries.add(new FleetResponse.ServiceEntry(name, instances.size(), List.copyOf(instances)));
                totalInstances += instances.size();
            }
        }
        return new FleetResponse(
                "minicc.fleet.v1",
                java.time.Instant.now().toString(),
                entries.size(),
                totalInstances,
                List.copyOf(entries));
    }

    private static String safe(String value) {
        return value == null ? "" : value;
    }

    private static String statusOf(ServiceInstance instance) {
        // The plane is Eureka by construction (docker-compose, gateway lb://).
        // When the backend is Eureka, report its real UP/DOWN; any other
        // backend reports UNKNOWN rather than a fabricated UP.
        if (instance instanceof EurekaServiceInstance eureka) {
            InstanceInfo info = eureka.getInstanceInfo();
            if (info != null && info.getStatus() != null) {
                return info.getStatus().name();
            }
        }
        return "UNKNOWN";
    }
}
