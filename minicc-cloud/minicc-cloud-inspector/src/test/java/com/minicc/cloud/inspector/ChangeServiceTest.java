package com.minicc.cloud.inspector;

import static org.assertj.core.api.Assertions.assertThat;
import static org.assertj.core.api.Assertions.assertThatThrownBy;
import static org.mockito.ArgumentMatchers.any;
import static org.mockito.Mockito.mock;
import static org.mockito.Mockito.never;
import static org.mockito.Mockito.verify;
import static org.mockito.Mockito.when;

import com.minicc.cloud.bridge.BridgeUnavailableException;
import com.minicc.cloud.bridge.ChangeInspectorClient;
import com.minicc.cloud.bridge.ChangeSummary;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import io.github.resilience4j.circuitbreaker.CircuitBreakerConfig;
import java.io.IOException;
import java.nio.file.Files;
import java.nio.file.Path;
import java.time.Duration;
import java.util.List;
import org.junit.jupiter.api.BeforeEach;
import org.junit.jupiter.api.Test;
import org.junit.jupiter.api.io.TempDir;
import org.springframework.web.server.ResponseStatusException;

/**
 * The service is where a refusal and a read failure must not be confused.
 *
 * <p>A workspace the guard rejects was never inspected, so it must not count
 * against the breaker: a client hammering an illegal path would otherwise open
 * the circuit for every legitimate caller. And a summary that arrives with a
 * failed read inside it must leave still labelled partial.
 */
class ChangeServiceTest {

    @TempDir Path temp;

    private ChangeInspectorClient client;
    private CircuitBreaker breaker;
    private ChangeService service;
    private Path workspace;

    private static ChangeSummary summary(
            Integer totalFiles, Integer additions, Integer deletions, String statusReadError) {
        return new ChangeSummary(
                List.of(), totalFiles, additions, deletions, 0, false, 0, false, 0, 0,
                statusReadError, null, 0, 0, 0, 0);
    }

    @BeforeEach
    void setUp() throws IOException {
        workspace = Files.createDirectory(temp.resolve("project"));
        client = mock(ChangeInspectorClient.class);
        breaker = CircuitBreaker.of("minicc-python",
                CircuitBreakerConfig.custom()
                        .slidingWindowSize(2)
                        .minimumNumberOfCalls(2)
                        .failureRateThreshold(50f)
                        .waitDurationInOpenState(Duration.ofMinutes(1))
                        .build());
        WorkspaceGuard guard = new WorkspaceGuard(
                new MiniccProperties("python", temp.toString(), Duration.ofSeconds(5), List.of()));
        service = new ChangeService(client, guard, breaker);
    }

    @Test
    void aCompleteReadIsNotLabelledPartial() {
        when(client.summary(any())).thenReturn(summary(0, 0, 0, null));

        ChangeReport report = service.summary(workspace.toString());

        assertThat(report.partial()).isFalse();
        assertThat(report.reasons()).isEmpty();
        assertThat(report.summary().totalFiles()).isEqualTo(0);
    }

    /** Zero files beside a failed read is still a failed read. */
    @Test
    void aZeroThatArrivedBesideAReadErrorKeepsItsPartialLabel() {
        when(client.summary(any())).thenReturn(summary(0, 0, 0, "git status exited 128"));

        ChangeReport report = service.summary(workspace.toString());

        assertThat(report.summary().totalFiles()).isEqualTo(0);
        assertThat(report.partial()).isTrue();
        assertThat(report.reasons()).anyMatch(reason -> reason.contains("git status exited 128"));
    }

    @Test
    void anUnknownLineTotalIsAReasonAndNotAZero() {
        when(client.summary(any())).thenReturn(summary(3, null, null, null));

        ChangeReport report = service.summary(workspace.toString());

        assertThat(report.partial()).isTrue();
        assertThat(report.summary().additions()).isNull();
        assertThat(report.reasons()).anyMatch(reason -> reason.contains("unknown"));
    }

    @Test
    void aRefusedWorkspaceNeverReachesThePythonChild() {
        assertThatThrownBy(() -> service.summary(temp.resolve("absent").toString()))
                .isInstanceOf(ResponseStatusException.class);

        verify(client, never()).summary(any());
    }

    /** The cell that keeps one caller's illegal path from silencing everyone. */
    @Test
    void aRefusedWorkspaceDoesNotCountAgainstTheCircuitBreaker() {
        for (int attempt = 0; attempt < 5; attempt++) {
            assertThatThrownBy(() -> service.summary(temp.resolve("absent").toString()))
                    .isInstanceOf(ResponseStatusException.class);
        }

        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.CLOSED);
        assertThat(breaker.getMetrics().getNumberOfFailedCalls()).isZero();
        verify(client, never()).summary(any());
    }

    @Test
    void aBridgeFailureLeavesAsItselfSoTheAdviceCanNameIt() {
        when(client.summary(any())).thenThrow(new BridgeUnavailableException("python could not be read"));

        assertThatThrownBy(() -> service.summary(workspace.toString()))
                .isInstanceOf(BridgeUnavailableException.class)
                .hasMessage("python could not be read");
    }

    @Test
    void repeatedReadFailuresOpenTheCircuitAndThenRefuseWithoutTrying() {
        when(client.summary(any())).thenThrow(new BridgeUnavailableException("read failed"));

        for (int attempt = 0; attempt < 2; attempt++) {
            assertThatThrownBy(() -> service.summary(workspace.toString()))
                    .isInstanceOf(BridgeUnavailableException.class);
        }
        assertThat(breaker.getState()).isEqualTo(CircuitBreaker.State.OPEN);

        assertThatThrownBy(() -> service.summary(workspace.toString()))
                .isInstanceOf(CallNotPermittedException.class);
        verify(client, org.mockito.Mockito.times(2)).summary(any());
    }
}