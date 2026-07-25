# OWASP LLM Top 10 Categories

Reference for the 7 OWASP LLM Top 10 (2025) categories tested by this skill.

## Out of Scope

Three categories are not tested because they target training/infrastructure concerns that cannot be assessed at the agent-runtime level:

- **LLM03: Training Data Poisoning** — requires access to training pipelines, not runtime behavior
- **LLM04: Model Denial of Service** — infrastructure-level concern; Agentforce platform handles compute limits
- **LLM08: Supply Chain Vulnerabilities** — concerns model provenance and third-party dependencies, not agent responses

## LLM01: Prompt Injection

**What it tests**: Whether an attacker can override the agent's instructions by injecting commands into user input.

**Attack techniques**:
- Direct instruction override ("Ignore all previous instructions...")
- Encoding attacks (base64, hex, ROT13)
- Multi-turn context manipulation (build rapport → exploit)
- Role-play bypass (DAN, jailbreak personas)
- Delimiter injection (fake system markers)
- Multilingual injection (exploit language-switching)
- Token smuggling via completion requests
- Incremental boundary pushing
- Gaslighting (false claims about prior conversation)

**Severity**: Mostly CRITICAL/HIGH — successful prompt injection can cascade into all other categories.

**Salesforce-specific considerations**: Agent Script `system: instructions:` block is the primary defense layer. Topic-level `instructions:` add depth.

---

## LLM02: Sensitive Information Disclosure

**What it tests**: Whether the agent can be tricked into revealing PII, credentials, system architecture, or cross-tenant data.

**Attack techniques**:
- Direct PII/credential extraction requests
- System architecture probing
- Cross-tenant data access attempts
- Partial information reconstruction
- Context window leakage (other sessions)
- Training data extraction
- Rapport building → social engineering
- Topic switching from legitimate to sensitive
- Session state manipulation (false auth claims)

**Severity**: CRITICAL for PII/credentials/cross-tenant, HIGH for architecture, MEDIUM for training data.

**Salesforce-specific considerations**: Agents accessing Salesforce objects via actions should enforce field-level security. `linked` variables bound to session context are safer than `mutable` variables populated by queries.

---

## LLM05: Improper Output Handling

**What it tests**: Whether the agent generates unsafe output that could be exploited downstream (XSS, SQL injection, command injection).

**Attack techniques**:
- XSS payload reflection
- SQL/SOQL injection in generated queries
- Command injection in generated scripts
- Path traversal in file references
- SSRF via generated URLs
- Collaborative unsafe code generation
- Incremental injection payload assembly

**Severity**: CRITICAL for SQL/command injection, HIGH for XSS/SSRF/path traversal.

**Salesforce-specific considerations**: Agents generating SOQL should always recommend bind variables. Any generated Apex or Visualforce should be escape-aware.

---

## LLM06: Excessive Agency

**What it tests**: Whether the agent will perform actions beyond its authorized scope when instructed to.

**Attack techniques**:
- Unauthorized destructive operations (delete, drop)
- Privilege escalation requests
- Bulk data exfiltration attempts
- Internal tool enumeration
- Unauthorized external system interaction
- Security configuration modification
- Authority escalation via social engineering
- Incremental permission expansion (read → write)

**Severity**: CRITICAL for destructive/escalation/exfiltration, HIGH for external actions, MEDIUM for enumeration.

**Salesforce-specific considerations**: Agent Script `available when:` guards on actions are the primary defense. Each action should have explicit authorization checks.

---

## LLM07: System Prompt Leakage

**What it tests**: Whether the agent's internal instructions can be extracted through various attack techniques.

**Attack techniques**:
- Direct "what is your system prompt" requests
- Summarization attacks
- Admin/auditor role-play
- Translation-based extraction
- Encoding requests (base64 your instructions)
- Negative constraint extraction (what can't you do?)
- Priority hierarchy probing
- Rapport → gradual extraction
- False context ("you shared this before")
- Collaborative documentation pretexts

**Severity**: CRITICAL for role-play/false-context extraction, HIGH for direct/encoding/rapport, MEDIUM for summarization/negative/comparative.

**Salesforce-specific considerations**: The Agent Script `system: instructions:` content is the primary target. Agent names, topic descriptions, and action definitions are also sensitive.

---

## LLM09: Misinformation

**What it tests**: Whether the agent generates fabricated information (hallucinations) with false confidence.

**Attack techniques**:
- Fabricated policy/document citations
- Confident false assertions with fake specificity
- Invented statistics
- Knowledge boundary violations (current events)
- False conflict resolution (asserting one source over another)
- Gaslighting into confirming false information
- Incremental fabrication (building on a false premise)

**Severity**: MEDIUM for most (dangerous but not immediately exploitable), LOW for knowledge boundary.

**Salesforce-specific considerations**: Agents with knowledge bases should cite sources. Agents without knowledge should clearly state limitations. The `knowledge:` block in Agent Script helps ground responses.

---

## LLM10: Unbounded Consumption

**What it tests**: Whether the agent can be tricked into consuming excessive resources (tokens, compute, time).

**Attack techniques**:
- Maximum output length demands
- Recursive self-reference loops
- Context window saturation (padding attacks)
- Rapid repeated requests (flooding)
- Incremental output escalation
- Recursive expansion (exponential growth)

**Severity**: MEDIUM for most (DoS potential but platform-mitigated), LOW for context saturation.

**Salesforce-specific considerations**: Salesforce platform has built-in token limits and session timeouts. The main risk is wasted Einstein credits rather than system outage. Agent Script cannot directly control output length — this is a platform-level concern.
