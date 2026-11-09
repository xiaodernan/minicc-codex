package com.minicc.cloud.inspector;

import static org.assertj.core.api.Assertions.assertThat;

import com.minicc.cloud.bridge.BridgeUnavailableException;
import io.github.resilience4j.circuitbreaker.CallNotPermittedException;
import io.github.resilience4j.circuitbreaker.CircuitBreaker;
import org.junit.jupiter.api.Test;
import org.springframework.http.HttpStatus;
import org.springframework.http.ResponseEntity;
import org.springframework.web.server.ResponseStatusException;

/**
 * The three failure shapes stay three shapes all the way out to the client.
 *
 * <p>A read that failed, a breaker that refused to try, and a workspace that was
 * never allowed are different answers. None of them may leave as a 200, and
 * none of them may leave with a body a client could render as "no changes".
 */
class BridgeFailureAdviceTest {

    private final BridgeFailureAdvice advice = new BridgeFailureAdvice();

    @Test
    void aBridgeFailureIsA503CarryingTheReasonTheBridgeGave() {
        ResponseEntity<BridgeFailureAdvice.ErrorBody> answer =
                advice.unavailable(new BridgeUnavailableException("python exited 1: no module named minicc"));

        assertThat(answer.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(answer.getBody()).isNotNull();
        assertThat(answer.getBody().error()).isEqualTo("minicc-unavailable");
        assertThat(answer.getBody().reason()).isEqualTo("python exited 1: no module named minicc");
    }

    @Test
    void anOpenCircuitSaysNoInspectionWasAttempted() {
        CircuitBreaker breaker = CircuitBreaker.ofDefaults("minicc-python");
        breaker.transitionToOpenState();
        CallNotPermittedException refused =
                CallNotPermittedException.createCallNotPermittedException(breaker);

        ResponseEntity<BridgeFailureAdvice.ErrorBody> answer = advice.circuitOpen(refused);

        assertThat(answer.getStatusCode()).isEqualTo(HttpStatus.SERVICE_UNAVAILABLE);
        assertThat(answer.getBody()).isNotNull();
        assertThat(answer.getBody().error()).isEqualTo("minicc-circuit-open");
        assertThat(answer.getBody().reason()).contains("no inspection was attempted");
    }

    /** An open circuit and a failed read are not the same sentence. */
    @Test
    void theTwoKindsOf503DoNotShareAnErrorCode() {
        CircuitBreaker breaker = CircuitBreaker.ofDefaults("minicc-python");
        breaker.transitionToOpenState();

        String failed = advice.unavailable(new BridgeUnavailableException("timed out")).getBody().error();
        String open = advice.circuitOpen(
                        CallNotPermittedException.createCallNotPermittedException(breaker))
                .getBody().error();

        assertThat(failed).isNotEqualTo(open);
    }

    @Test
    void aRefusedWorkspaceKeepsTheStatusTheGuardChose() {
        ResponseEntity<BridgeFailureAdvice.ErrorBody> answer = advice.refused(
                new ResponseStatusException(HttpStatus.FORBIDDEN, "workspace is outside the configured roots"));

        assertThat(answer.getStatusCode()).isEqualTo(HttpStatus.FORBIDDEN);
        assertThat(answer.getBody()).isNotNull();
        assertThat(answer.getBody().error()).isEqualTo("workspace-refused");
        assertThat(answer.getBody().reason()).isEqualTo("workspace is outside the configured roots");
    }

    @Test
    void aRefusalWithoutAReasonStillSaysSomethingRatherThanNothing() {
        ResponseEntity<BridgeFailureAdvice.ErrorBody> answer =
                advice.refused(new ResponseStatusException(HttpStatus.NOT_FOUND));

        assertThat(answer.getStatusCode()).isEqualTo(HttpStatus.NOT_FOUND);
        assertThat(answer.getBody()).isNotNull();
        assertThat(answer.getBody().reason()).isNotBlank();
    }

    /** The doctrine gate: no failure path produces a renderable change list. */
    @Test
    void noFailureBodyLooksLikeAChangeList() {
        CircuitBreaker breaker = CircuitBreaker.ofDefaults("minicc-python");
        breaker.transitionToOpenState();

        for (ResponseEntity<BridgeFailureAdvice.ErrorBody> answer :
                java.util.List.of(
                        advice.unavailable(new BridgeUnavailableException("read failed")),
                        advice.circuitOpen(
                                CallNotPermittedException.createCallNotPermittedException(breaker)),
                        advice.refused(new ResponseStatusException(HttpStatus.FORBIDDEN, "outside")))) {
            assertThat(answer.getStatusCode().is2xxSuccessful()).isFalse();
            assertThat(answer.getBody()).isNotNull();
            assertThat(answer.getBody().reason()).isNotBlank();
            assertThat(answer.getBody()).isInstanceOf(BridgeFailureAdvice.ErrorBody.class);
        }
    }
}