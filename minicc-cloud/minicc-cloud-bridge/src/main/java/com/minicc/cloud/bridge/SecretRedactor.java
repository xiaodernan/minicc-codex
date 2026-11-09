package com.minicc.cloud.bridge;

import java.util.List;
import java.util.regex.Matcher;
import java.util.regex.Pattern;

/**
 * Scrubs credential-shaped text from diagnostics that crossed the process boundary.
 *
 * <p>The child inherits the host environment, so anything it prints - a
 * traceback, a library's request log, an explicit echo - can carry a key the
 * bridge never intended to publish. Redacting here, in the one type every run
 * outcome passes through, means a caller cannot forget to do it and cannot do it
 * differently. Only the secret value is replaced; the surrounding words stay
 * verbatim so an operator can still read why the child failed.
 */
final class SecretRedactor {

    static final String MASK = "[redacted]";

    /** Ordered so that a bearer value is masked before the generic key/value rule. */
    private static final List<Pattern> PATTERNS = List.of(
            Pattern.compile("(?i)\\bBearer\\s+\\S+"),
            // The lookbehind keeps the key scan anchored to line starts and
            // whitespace. Without it the engine would try [\w-]* at every
            // offset of a long diagnostic and backtrack quadratically over it.
            Pattern.compile("(?im)(?:^|(?<=[\\s,;(\\[{]))"
                    + "([\\w-]*(?:api[_-]?key|token|secret|password))"
                    + "\\s*([=:])\\s*(\"[^\"]*\"|'[^']*'|[^\\s,;]+)"),
            Pattern.compile("\\bsk-[A-Za-z0-9_-]{8,}"));

    private SecretRedactor() {
    }

    static String redact(String text) {
        if (text == null || text.isEmpty()) {
            return text;
        }
        String redacted = PATTERNS.get(0).matcher(text).replaceAll("Bearer " + MASK);
        Matcher keyValue = PATTERNS.get(1).matcher(redacted);
        redacted = keyValue.replaceAll("$1$2" + Matcher.quoteReplacement(MASK));
        return PATTERNS.get(2).matcher(redacted)
                .replaceAll(Matcher.quoteReplacement(MASK));
    }
}
