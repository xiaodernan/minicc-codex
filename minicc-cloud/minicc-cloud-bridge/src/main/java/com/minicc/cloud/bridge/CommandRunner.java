package com.minicc.cloud.bridge;

import java.util.List;

/**
 * The one seam between a client and the process boundary.
 *
 * <p>Clients ask a question and receive what the boundary answered; they do not
 * decide how many children may exist or whether two identical questions can
 * share one answer. Those are boundary policies, and keeping them behind this
 * interface is what lets them be tested without an HTTP context.
 */
@FunctionalInterface
public interface CommandRunner {

    /** Run one minicc command and report what came back. Never returns null. */
    BridgeResponse run(List<String> args);
}
