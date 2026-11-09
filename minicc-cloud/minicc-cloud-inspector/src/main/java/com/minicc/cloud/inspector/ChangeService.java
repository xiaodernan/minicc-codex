package com.minicc.cloud.inspector;

import com.minicc.cloud.bridge.ChangeInspectorClient;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import java.nio.file.Path;
import org.springframework.stereotype.Service;

@Service
public class ChangeService {

    private final ChangeInspectorClient client;
    private final WorkspaceGuard guard;
    private final CircuitBreaker breaker;

    public ChangeService(ChangeInspectorClient client, WorkspaceGuard guard, CircuitBreaker breaker) {
        this.client = client;
        this.guard = guard;
        this.breaker = breaker;
    }

    public ChangeReport summary(String workspace) {
        Path resolved = guard.resolve(workspace);
        return ChangeReport.of(breaker.executeSupplier(() -> client.summary(resolved)));
    }

    public DiffReport diff(String workspace, String rawPath) {
        Path resolved = guard.resolve(workspace);
        return DiffReport.of(breaker.executeSupplier(() -> client.diff(resolved, rawPath)));
    }
}