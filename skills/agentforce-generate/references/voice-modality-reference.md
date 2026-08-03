# Voice Modality Reference

## Overview

Voice agents use the `modality voice:` block to configure text-to-speech (TTS) and speech-to-text (STT) behavior. This block is optional — omit it for text-only agents.

Voice agents also require:
- The standard `agent_type` (e.g. `AgentforceServiceAgent`) — **do NOT** set `Atlas__VoiceAgent` in the bundle `config` block. `Atlas__VoiceAgent` is a runtime `planner_type` value applied by the platform, not an authored field in the `.agent` file.
- A `VoiceCallId` linked variable bound to `@VoiceCall.Id` (the voice-channel session identifier — the voice analog of `@MessagingSession.Id`).
- A `language:` block with the appropriate locale.
- A voice-capable connection surface — `connection customer_web_client:` (ECv2). `connection messaging:` is **additive**, needed only for human escalation (see "Connection Blocks" below).

### VoiceCallId variable

Add this to the `variables:` block whenever `modality voice:` is present:

```agentscript
    VoiceCallId: linked string
        source: @VoiceCall.Id
        description: "This variable may also be referred to as Voice Call Id"
```

## Agent Script Syntax

```agentscript
modality voice:
    voice_id: "UgBBYS2sOqTuMpoF3BR0"
    outbound_speed: 1
    outbound_stability: 0.65
    outbound_similarity: 0.75
```

## Default Voice — start here

There is **no reliable CLI/API way to enumerate available voice IDs** and their tuning values, so ADLC always authors the platform default voice and lets the user customize afterward in the UI. Do **not** ask the user to supply a `voice_id`.

| Field | Default value |
|-------|---------------|
| `voice_id` | `UgBBYS2sOqTuMpoF3BR0` ("Mark") |
| `outbound_speed` | `1` |
| `outbound_stability` | `0.65` |
| `outbound_similarity` | `0.75` |
| locale | `en_US` |

These match the platform default (`Eleven_Flash_V2_5` model config `outboundVoice` parameter).

**Tell the user how to customize:** after the agent is created, open it in **Agent Builder → Connections → Voice** and click **Continue** to pick a different voice and tune speed/stability/similarity. The picklist of voices (with names, gender, accent, and locale) is only exposed in that UI — not via the CLI.

The `modality voice:` block is a top-level optional block, placed after `language:` and before `start_agent`:

```agentscript
system:
config:
variables:
connection:
knowledge:
language:
modality voice:
start_agent:
subagent:
```

## Properties

### Core Voice Properties

| Property | Type | Range | Description |
|----------|------|-------|-------------|
| `voice_id` | string | — | The ID of the voice model to use for TTS |
| `outbound_speed` | float | 0.5–2.0 | Speech rate (0.5 = slow, 1.0 = normal, 2.0 = fast) |
| `outbound_stability` | float | 0.0–1.0 | Voice consistency (lower = more emotional range, higher = more stable) |
| `outbound_similarity` | float | 0.0–1.0 | How closely the AI replicates the original voice's characteristics |
| `outbound_style_exaggeration` | float | 0.0–1.0 | Emotional intensity (0.0 = neutral, 1.0 = expressive) |

### Inbound (STT) Properties

| Property | Type | Description |
|----------|------|-------------|
| `inbound_filler_words_detection` | boolean | Enable recognition of filler words ("uh", "um") |
| `inbound_keywords` | list | Keywords to improve speech recognition accuracy |

### Advanced Configuration

| Property | Type | Description |
|----------|------|-------------|
| `outbound_filler_sentences` | object | Filler sentences by context (e.g., "waiting") — spoken while processing |
| `pronunciation_dict` | object | Custom pronunciations for domain-specific terms |
| `additional_configs` | object | Advanced voice settings (speak-up, endpointing, beep-boop) |

### Additional Configs Sub-Properties

**speak_up_config** — prompts when user is silent:

| Property | Type | Range | Description |
|----------|------|-------|-------------|
| `speak_up_first_wait_time_ms` | int | 10000–300000 | Wait before first speak-up prompt (10s–5min) |
| `speak_up_follow_up_wait_time_ms` | int | 10000–300000 | Wait for follow-up speak-up prompts |
| `speak_up_message` | string | — | Message to speak when user is silent |

**endpointing_config** — speech boundary detection:

| Property | Type | Range | Description |
|----------|------|-------|-------------|
| `max_wait_time_ms` | int | 500–60000 | Max wait for speech endpoint detection (0.5s–60s) |

**beepboop_config** — beep-boop tone behavior:

| Property | Type | Range | Description |
|----------|------|-------|-------------|
| `max_wait_time_ms` | int | 500–60000 | Max wait for beep-boop behavior (0.5s–60s) |

## Pronunciation Dictionary

For domain-specific terms that TTS may mispronounce:

```agentscript
modality voice:
    voice_id: "UgBBYS2sOqTuMpoF3BR0"
    outbound_speed: 1
    outbound_stability: 0.7
    outbound_similarity: 0.8
    pronunciation_dict:
        pronunciations:
            - grapheme: "Xfinity"
              phoneme: "ɛks.ˈfɪn.ɪ.ti"
              type: "IPA"
            - grapheme: "SkyMiles"
              phoneme: "S K AY M AY L Z"
              type: "CMU"
```

Supported pronunciation types: `IPA` (International Phonetic Alphabet), `CMU` (Carnegie Mellon University Pronouncing Dictionary).

## Voice-Specific Authoring Guidance

### Instructions for Voice Agents

Voice interactions differ from text. When authoring instructions for voice agents:

1. **Keep responses concise.** Users cannot scan/skim voice responses. Aim for 1-2 sentences per turn, not paragraphs. (Long turns also risk tripping the silence/nudge timer — see [voice-latency-heuristics.md](voice-latency-heuristics.md) §5.)
2. **Avoid lists longer than 3 items — and batch long ones.** Users lose track of spoken lists. For a list that can be long, read at most **2 items per turn** and offer to continue (*"Would you like the next two?"*) rather than reading the whole set. **Never speak a raw total count** ("I found forty-seven results") — it's meaningless aloud; summarize or offer to narrow instead.
3. **Use confirmation patterns — and split capture from action.** Repeat back key information (account numbers, dates, amounts) before taking action. For anything that triggers an irreversible action (sending an email/SMS, creating a record), make **capture and send two separate steps**: capture and store the value, read it back, get a yes, and only *then* call the action that acts on it. Don't let a single turn both collect a misheard value and act on it.
4. **Design for barge-in.** Users may interrupt. Instructions should handle partial inputs gracefully. Add: *"If the caller starts talking, stop speaking immediately, listen, and respond to what they said — don't finish your sentence."*
5. **Avoid formatting references.** Do not reference links, bullet points, tables, or visual formatting in instructions — they don't render in voice.
6. **Acknowledge slow actions — prefer the platform's progress indicator over LLM filler.** Any action over ~800ms (SOQL, external HTTP, retrieval) needs a "still working" signal. **Best practice:** set a `progress_indicator_message` on the action itself (*"Just a moment while I look that up"*) so the platform speaks the hold phrase and the agent's own turn begins **with the answer** — don't have the LLM vocalize "one moment" as well, or the caller hears it twice. Reserve LLM-spoken filler (*"Let me pull that up"*) for cases where you can't set a progress message. Mark truly instant actions out of the progress indicator so they don't announce a delay that isn't there. This is the instruction-level fix for the latency patterns in [voice-latency-heuristics.md](voice-latency-heuristics.md).
7. **Render numbers, prices, and IDs in spoken form.** TTS reads `$19.99` and `+14155551212` as garble. Instruct: *"When reading numbers, prices, phone numbers, IDs, or dates, use natural spoken form — never read punctuation, currency symbols, or raw digits."* Spell out numbers under 100 ("twenty-five"); prices as *"nineteen dollars and ninety-nine cents"*; phone numbers digit-by-digit grouped naturally; dates as *"May tenth, twenty twenty-six"*. Author this guidance **once** — do not stack extra rules or tag overrides trying to force phone-number grouping, country-code suppression, or a specific date format. Those are platform-controlled; see "Entity Confirmation & Normalization" below.
8. **Add ASR repair prompts for misheard input.** Speech recognition isn't perfect. Instruct: *"If the caller's response doesn't match an expected value, or you're unsure what you heard, repeat it back and ask them to confirm — e.g. 'I heard four four two, is that right?'"*
9. **Give empty results a caller-friendly fallback.** Any lookup that can return zero results needs a graceful recovery. Instruct: *"If a lookup returns nothing, don't say 'no records found.' Say something like 'I couldn't find that account — could you spell your last name?' or offer a different search."* (Pair with voice-friendly action error shapes — see [actions-reference.md](actions-reference.md) "Voice-Safe Action Authoring".)
10. **Never claim an action happened unless it did.** The most common voice failure mode is the agent saying *"I've sent that to you"* or *"you'll get a text shortly"* when no action actually fired. Instruct explicitly: *"Never state or imply that an email, SMS, or record action has happened, is happening, or will happen unless you actually executed the corresponding action this turn."* Confirm delivery only *after* the action returns success.
11. **Never expose internals to the caller.** Action names, variable names, JSON, tool inputs, and retriever/knowledge-source names must never be spoken aloud. Instruct: *"When invoking an action, say only the configured progress message or the final customer-facing answer — never read out action names, field names, or raw data structures."*

### Entity Confirmation & Normalization — what you CANNOT control from instructions

How spoken entities are **read back and confirmed** (phone numbers, currency, dates, numerals, IDs) is decided by the platform's voice normalization layer, **downstream of your agent instructions**. A few specific behaviors are **not** reliably controllable from the `.agent` file — and trying to control them makes things *worse*, not better:

- **Country code on phone numbers** (e.g. a "plus one" prepended to a US number). Whether it appears is decided by the normalization layer, not your prompt.
- **Digit grouping when reading numbers back** (e.g. `980 23 222 45` vs. an even digit-by-digit read). Grouping is applied at the language level and can vary run-to-run.
- **Dropping the current year from a date** (e.g. reading a same-year date as month and day only).

**Do NOT author custom instructions or tag overrides to fight these.** Adding rules like "always emit the phone tag with an empty country code," "read phone numbers as area-code / prefix / last-four," or "always include the year" **conflicts with the platform's built-in tagging and makes readback *less* consistent, not more.** In practice these overrides produce unreliable, ~50/50 results and can destabilize otherwise-correct normalization.

**What to do instead:**
- Write the spoken-form guidance in item 7 **once**, and stop there. Tag entities correctly (say the value is a phone number, a price, a date) and let the platform normalize it.
- If a customer needs a specific readback format or wants to **suppress an out-of-the-box confirmation**, that is **platform/product configuration, not agent-script authoring**. Per-entity confirmation configurability is active platform work — surface the requirement to the voice product team rather than encoding a workaround in the `.agent` file.
- Set the customer's expectations: these three behaviors may still occur regardless of instructions, and are being addressed at the platform layer.

### Instruction Example — Voice vs Text

**Text agent instruction:**
```agentscript
| Here are your options:
| 1. Check order status
| 2. Return an item
| 3. Speak with a representative
| Please enter the number of your choice.
```

**Voice agent instruction:**
```agentscript
| Ask the customer what they'd like help with. You can check order status, process a return, or connect them with a representative. If unclear, ask one clarifying question.
```

### Connection Blocks — how `modality` and `connection` relate

`connection` blocks are separate from `modality voice:`. **`modality voice:` configures voice *behavior*** (TTS voice, speed, STT tuning); **`connection` blocks declare the *surface/channel*** the agent is wired to. A voice agent needs both: the modality block for how it speaks, and a voice-capable connection surface for where it runs.

There is **no `connection voice:` surface type** — do not invent one. In Agent Script, the voice-capable connection surface is **`connection customer_web_client:`**, which corresponds to **Enhanced Chat v2 (ECv2)** in Agent Builder (see Agent Builder → Connections). This is the surface that makes Agent Builder **Preview** and voice work:

```agentscript
connection customer_web_client:
    adaptive_response_allowed: True
```

**Is `connection messaging:` also required?** No — it is **additive, not required for voice**. Add `connection messaging:` only if the agent escalates to a human (`@utils.escalate`); escalation is routed through it. If the agent has no human-escalation path, `customer_web_client` alone is sufficient. Most service voice agents *do* escalate, so both blocks commonly appear together (this is what the UI shows when both ECv2 and Messaging connections are enabled):

```agentscript
connection messaging:
    escalation_message: "Let me transfer you to a specialist who can help."

connection customer_web_client:
    adaptive_response_allowed: True
```

> **Choosing a surface — ECv2 (`customer_web_client`) vs Telephony.** Both ECv2 and Telephony (Service Cloud Voice) are voice-capable channels. In Agent Builder, adding *either* connection auto-enables Voice Settings. ADLC authors **`customer_web_client` (ECv2)** because it is the surface that is reliably created via the CLI/DSL today and is what Agent Builder Preview requires; Telephony/SCV channel attachment (phone number / SIP) is a UI-only step (see "Known Limitation" below). If your deployment target is Service Cloud Voice telephony, author `customer_web_client` for authoring/preview and complete the telephony channel wiring in the UI.
>
> **Do not** invent `connection voice:`, and do not remove an existing `connection messaging:` block when enabling voice — enabling voice **adds** the `modality voice:` block, the `VoiceCallId` variable, and `connection customer_web_client:`.

> **Note on the `telephony` connection type.** `actions-reference.md` lists `telephony` as an escalation-routing channel. That is a *routing* surface for the `connection` escalation block; for voice *authoring + preview* the DSL surface ADLC emits is `customer_web_client` (ECv2). See known-issues.md Issue 18 for why `CustomerWebClient` must sometimes be patched into the compiled `GenAiPlannerBundle` after publish.

## When to Add a Modality Block

| Scenario | Modality Block? |
|----------|----------------|
| Text-only agent (messaging, web chat) | No |
| Voice-only agent (telephony) | Yes — required |
| Multi-channel agent (text + voice) | Yes — voice channel uses it |
| Employee agent (internal, no customer channel) | No (employee agents are text-only) |

## Validation

The `modality voice:` block is validated during `sf agent validate`. Common issues:

- Invalid `voice_id` — must be a valid voice model ID from the org's voice provider
- Out-of-range floats — `outbound_speed` must be 0.5–2.0, others must be 0.0–1.0
- Timing values out of bounds — speak-up timers: 10s–5min, endpointing/beepboop: 0.5s–60s

## Known Limitation — Voice-Channel Deploy Is UI-Only

You can **author** and **validate** a voice bundle entirely headless (CLI/API): `sf agent validate authoring-bundle` and `sf agent publish authoring-bundle` compile and deploy the agent metadata, including the `modality voice:` block. What the CLI **cannot** do today is wire the published agent to the actual telephony/voice channel — that last-mile connection step is only available in the Agent Builder UI.

After publishing, the user must open the agent in **Agent Builder → Connections → Voice** and click **Continue** to:
1. Attach the agent to a voice channel (phone number / SIP endpoint), and
2. Optionally customize the voice and tuning (see "Default Voice — start here" above).

This is the one break in an otherwise headless flow. It is a tracked Project Codey "Steel Thread 2" gap (deploy-to-voice-channel not supported in CLI) — surface it to the user rather than implying `sf agent publish` fully activates the voice channel. Until CLI support lands, treat the UI step as a required manual handoff and tell the user exactly which screen to open.

## Steel Thread Alignment (Project Codey)

Voice work in ADLC targets **Steel Thread 2 — "Voice-Enabled Agent with Knowledge Grounding"**: build voice agents with subagents, actions, and knowledge integration (ADL / Salesforce Knowledge), then deploy to the voice channel. Two implications for authoring:

- **Pair voice with knowledge grounding.** Voice service agents are almost always FAQ/policy-backed, so `/agentforce-generate` proactively asks the Knowledge Grounding question when it detects a voice agent. The combined template is `assets/agents/voice-knowledge-grounded.agent`.
- **Deploy is the known gap.** See "Known Limitation" above — authoring and validation are headless; channel wiring is UI-only.

## Related References

- [voice-latency-heuristics.md](voice-latency-heuristics.md) — latency anti-patterns (sync writes, bulky retrieval, long turns) for authoring and trace diagnosis.
- [actions-reference.md](actions-reference.md) "Voice-Safe Action Authoring" — voice-safe action descriptions, parameter names, enums, error shapes.
