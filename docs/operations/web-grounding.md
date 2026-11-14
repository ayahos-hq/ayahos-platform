# Public web grounding

The public chat route treats Tavily output as untrusted retrieval data.

- Search results are accepted only when they have an `http` or `https` URL and
  non-empty content.
- IDs, titles, URLs, and content are bounded and sanitized before use.
- Raw retrieval content is never placed in a privileged system message. The
  model receives a static safety instruction plus a separately tagged
  `<untrusted-retrieval-context>` user message.
- The accepted sources travel to the model only inside the tagged
  `<untrusted-retrieval-context>` message; the site keeps the structured
  source list for citation rendering. The public response emits citations
  only from the sources accepted from the current Tavily response;
  provider-generated or invented source IDs are not copied into the response.
- Retrieval content cannot authorize tools, change runtime policy, disclose
  secrets, or override the user's actual request.

The route tests cover conflicting instructions, unsafe URLs, source ID
preservation, bounded source fields, and citation integrity.

## Shared Spine Truth Gateway

When the latest question asks about this request's runtime identity, the public
proxy replaces untrusted model prose with a deterministic disclosure notice.
It does **not** send provider names, model IDs, request IDs, policy versions,
preflight decisions or reason codes to the anonymous chat.

The Python deterministic Undermind still records its preflight decision in the
Shared Spine. `truth_gateway.py` verifies the event's source and projects its
version, decision and bounded reason codes; the authenticated cognition SSE API
includes those fields for trusted operator use. The public proxy strips these
fields along with raw resilience traces before returning the user-facing SSE.
The reviewer-protected operator trace/Inspector is the designated evidence
surface, not public chat or localStorage.

Ordinary chat continues to stream from the API through a citation validator.
Markers of the form `[source_id=...]` must match accepted Tavily result URLs
or authenticated RAG citations with HTTP(S) URLs; invented markers are replaced.
This proves source attribution only, not the correctness of a source, answer,
or any unrecognized citation syntax.

Absent evidence cannot be filled with model guesses. Outcome reason codes
report recorded policy deviations, **not** an exhaustive per-rule audit.
The report concerns the current inference; older messages need a separately
authorized trace lookup. This feature does not guarantee that arbitrary
general-purpose model statements are factually correct.

No local or deployment behavior is claimed verified without a run tied to
a commit. Browser text buffering, retry/edit flows, deterministic Undermind
authority and reviewer access control are unchanged.
