"""api/services/security — Chat security and prompt-injection containment.

Central security boundary for all LLM-facing surfaces. Provides:
- Input validation and canonicalization
- Untrusted envelope encoding
- Strict tool registry and gate
- Output sanitization and leak detection
- Security audit logging
- Rate limiting and resource caps
- Write proposal/confirmation flow
"""