package com.minicc.cloud.inspector;

import com.fasterxml.jackson.databind.JsonNode;
import org.springframework.web.bind.annotation.GetMapping;
import org.springframework.web.bind.annotation.RequestMapping;
import org.springframework.web.bind.annotation.RestController;

@RestController
@RequestMapping("/api/capabilities")
public class CapabilityController {

    private final CapabilityService service;

    public CapabilityController(CapabilityService service) {
        this.service = service;
    }

    /**
     * Returns the parsed payload untouched ({@code count} and {@code tools}).
     * Reshaping it here would give Java a second copy of the catalogue, which
     * is exactly the drift this endpoint exists to prevent.
     */
    @GetMapping
    public JsonNode capabilities() {
        return service.capabilities();
    }
}
