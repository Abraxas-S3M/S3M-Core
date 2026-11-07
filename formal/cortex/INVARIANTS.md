# Cortex formal invariants (reference)

1. Every network or system mutation is preceded by `PolicyGate.evaluate` and executed only through `CortexBroker`.
2. Policy evaluation fails closed on missing configuration, missing evaluator, timeout, or exception.
3. Untrusted text is labeled before model consumption and must not be interpreted as operator instruction.
4. Production mode refuses to start without liboqs, Docker/gVisor isolation, and OPA.
