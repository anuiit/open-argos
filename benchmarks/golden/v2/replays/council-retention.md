Voice A prioritizes reliability: additional contributors multiply provider
failure and timeout exposure, so readiness and partial-failure handling must be
visible.

Voice B prioritizes continuity: a persistent conversation can preserve context,
memory, and long-horizon design assumptions that isolated calls repeatedly
reconstruct.

The synthesis must preserve this dissent explicitly. Neither reliability nor
continuity dominates without workload evidence. Run a bounded experiment
across long-term design turns and short operational reviews, then measure
latency, failure rate, context retention, and judged output quality. Choose
defaults by workload while keeping the minority position in the conversation
record.
