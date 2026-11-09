package com.minicc.cloud.inspector;

import com.fasterxml.jackson.databind.JsonNode;
import com.minicc.cloud.bridge.CapabilitiesClient;
import org.springframework.stereotype.Service;

@Service
public class CapabilityService {

    private final CapabilitiesClient client;

    public CapabilityService(CapabilitiesClient client) {
        this.client = client;
    }

    /**
     * Deliberately not on the inspection circuit breaker: the catalogue is a
     * read of the shipped registry, not of a workspace. Putting it on that
     * breaker would let a capability read refuse change inspection (and the
     * reverse), which is the same kind of cross-talk the guard test forbids
     * one layer down. A failure still leaves as a BridgeUnavailableException
     * and therefore as the advice's 503.
     */
    public JsonNode capabilities() {
        return client.capabilities();
    }
}
