package com.minicc.cloud.insights;

import static org.assertj.core.api.Assertions.assertThat;
import static org.springframework.test.web.servlet.request.MockMvcRequestBuilders.get;
import static org.springframework.test.web.servlet.result.MockMvcResultMatchers.status;

import com.fasterxml.jackson.databind.JsonNode;
import com.fasterxml.jackson.databind.ObjectMapper;
import com.netflix.appinfo.DataCenterInfo;
import com.netflix.appinfo.InstanceInfo;
import com.netflix.appinfo.LeaseInfo;
import com.netflix.appinfo.MyDataCenterInfo;
import java.nio.charset.StandardCharsets;
import java.util.HashMap;
import java.util.List;
import java.util.Map;
import java.util.function.Supplier;
import org.junit.jupiter.api.Test;
import org.springframework.cloud.client.ServiceInstance;
import org.springframework.cloud.client.discovery.DiscoveryClient;
import org.springframework.cloud.netflix.eureka.EurekaServiceInstance;
import org.springframework.test.web.servlet.MockMvc;
import org.springframework.test.web.servlet.MvcResult;
import org.springframework.test.web.servlet.setup.MockMvcBuilders;

/**
 * The fleet view must answer with the registry's truth or nothing at all:
 * names, counts and real UP/DOWN statuses — never a fabricated empty fleet
 * when the registry is blind.
 */
class FleetEndpointTest {

    private static final ObjectMapper JSON = new ObjectMapper();

    @Test
    void fleetReportsServicesInstancesAndStatuses() throws Exception {
        DiscoveryClient registry = stub(
                List.of("minicc-cloud-tasks", "minicc-cloud-insights", "minicc-cloud-gateway"),
                Map.of(
                        "minicc-cloud-insights", List.of(eurekaInstance("insights-1", "127.0.0.1", 8087, InstanceInfo.InstanceStatus.UP)),
                        "minicc-cloud-gateway", List.of(eurekaInstance("gateway-1", "127.0.0.1", 8080, InstanceInfo.InstanceStatus.DOWN)),
                        "minicc-cloud-tasks", List.of()));
        MockMvc mvc = standalone(registry);

        JsonNode body = answer(mvc, 200);

        assertThat(body.get("schema_version").asText()).isEqualTo("minicc.fleet.v1");
        assertThat(body.get("service_count").asInt()).isEqualTo(3);
        assertThat(body.get("total_instances").asInt()).isEqualTo(2);
        // sorted by service name
        assertThat(body.get("services").get(0).get("name").asText()).isEqualTo("minicc-cloud-gateway");
        assertThat(body.get("services").get(2).get("name").asText()).isEqualTo("minicc-cloud-tasks");
        // a service with zero live instances is shown, not dropped
        assertThat(body.get("services").get(2).get("instance_count").asInt()).isZero();
        assertThat(body.get("services").get(2).get("instances")).isEmpty();
        // statuses are Eureka's real words
        assertThat(body.get("services").get(0).get("instances").get(0).get("status").asText()).isEqualTo("DOWN");
        assertThat(body.get("services").get(1).get("instances").get(0).get("status").asText()).isEqualTo("UP");
        assertThat(body.get("services").get(1).get("instances").get(0).get("port").asInt()).isEqualTo(8087);
    }

    @Test
    void nonEurekaBackendsReportUnknownStatuses() throws Exception {
        DiscoveryClient registry = stub(
                List.of("consul-ish"),
                Map.of("consul-ish", List.of(plainInstance("consul-1", "10.0.0.9", 9090))));
        MockMvc mvc = standalone(registry);

        JsonNode body = answer(mvc, 200);

        assertThat(body.get("services").get(0).get("instances").get(0).get("status").asText()).isEqualTo("UNKNOWN");
    }

    @Test
    void aBlindRegistryIsA503NeverAnEmptyFleet() throws Exception {
        DiscoveryClient registry = new FailingDiscoveryClient(new RuntimeException("connection refused"));
        MockMvc mvc = standalone(registry);

        MvcResult result = mvc.perform(get("/api/insights/fleet"))
                .andExpect(status().isServiceUnavailable())
                .andReturn();
        String text = result.getResponse().getContentAsString(StandardCharsets.UTF_8);
        JsonNode body = JSON.readTree(text);

        assertThat(body.get("error").asText()).isEqualTo("registry-unavailable");
        assertThat(text).doesNotContain("service_count");
    }

    @Test
    void anUnreadableApplicationRefusesTheWholeFleet() throws Exception {
        DiscoveryClient registry = new DiscoveryClient() {
            @Override
            public List<String> getServices() {
                return List.of("gateway", "insights");
            }

            @Override
            public List<ServiceInstance> getInstances(String serviceId) {
                if ("gateway".equals(serviceId)) {
                    throw new RuntimeException("instance list fetch failed");
                }
                return List.of();
            }

            @Override
            public String description() {
                return "test registry";
            }
        };
        MockMvc mvc = standalone(registry);

        MvcResult result = mvc.perform(get("/api/insights/fleet"))
                .andExpect(status().isServiceUnavailable())
                .andReturn();
        JsonNode body = JSON.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));

        assertThat(body.get("error").asText()).isEqualTo("registry-unavailable");
    }

    @Test
    void anEmptyRegistryAnswersZeroNotAnError() throws Exception {
        DiscoveryClient registry = stub(List.of(), Map.of());
        MockMvc mvc = standalone(registry);

        JsonNode body = answer(mvc, 200);

        assertThat(body.get("service_count").asInt()).isZero();
        assertThat(body.get("total_instances").asInt()).isZero();
        assertThat(body.get("services")).isEmpty();
    }

    private static MockMvc standalone(DiscoveryClient registry) {
        InsightsService service = new InsightsService(null, null); // /fleet never touches these
        return MockMvcBuilders.standaloneSetup(
                        new InsightsController(service, null, new FleetService(registry)))
                .setControllerAdvice(new InsightsFailureAdvice())
                .build();
    }

    private static JsonNode answer(MockMvc mvc, int expectedStatus) throws Exception {
        MvcResult result = mvc.perform(get("/api/insights/fleet"))
                .andExpect(status().is(expectedStatus))
                .andReturn();
        return JSON.readTree(result.getResponse().getContentAsString(StandardCharsets.UTF_8));
    }

    private static DiscoveryClient stub(List<String> services, Map<String, List<ServiceInstance>> instances) {
        return new DiscoveryClient() {
            @Override
            public List<String> getServices() {
                return services;
            }

            @Override
            public List<ServiceInstance> getInstances(String serviceId) {
                return instances.getOrDefault(serviceId, List.of());
            }

            @Override
            public String description() {
                return "test registry";
            }
        };
    }

    private static ServiceInstance plainInstance(String id, String host, int port) {
        return new ServiceInstance() {
            @Override
            public String getInstanceId() { return id; }

            @Override
            public String getServiceId() { return "consul-ish"; }

            @Override
            public String getHost() { return host; }

            @Override
            public int getPort() { return port; }

            @Override
            public boolean isSecure() { return false; }

            @Override
            public java.net.URI getUri() { return java.net.URI.create("http://" + host + ":" + port); }

            @Override
            public Map<String, String> getMetadata() { return new HashMap<>(); }

            @Override
            public String getScheme() { return "http"; }
        };
    }

    private static ServiceInstance eurekaInstance(String id, String ip, int port, InstanceInfo.InstanceStatus status) {
        InstanceInfo info = InstanceInfo.Builder.newBuilder()
                .setInstanceId(id)
                .setAppName(id.split("-")[0].equals("") ? id : id.split("-")[0])
                .setAppNameForDeser(id)
                .setHostName(ip)
                .setIPAddr(ip)
                .setPort(port)
                .enablePort(InstanceInfo.PortType.UNSECURE, true)
                .setVIPAddress(id)
                .setSecureVIPAddress(id)
                .setDataCenterInfo(new MyDataCenterInfo(DataCenterInfo.Name.MyOwn))
                .setLeaseInfo(LeaseInfo.Builder.newBuilder()
                        .setRenewalIntervalInSecs(30)
                        .setDurationInSecs(90)
                        .build())
                .setStatus(status)
                .build();
        return new EurekaServiceInstance(info);
    }

    private static final class FailingDiscoveryClient implements DiscoveryClient {
        private final RuntimeException failure;

        private FailingDiscoveryClient(RuntimeException failure) {
            this.failure = failure;
        }

        @Override
        public List<String> getServices() {
            throw failure;
        }

        @Override
        public List<ServiceInstance> getInstances(String serviceId) {
            throw failure;
        }

        @Override
        public String description() {
            return "failing test registry";
        }
    }
}
