# Voice Modality Reference

## Overview

Voice agents use the `modality voice:` block to configure text-to-speech (TTS) and speech-to-text (STT) behavior. This block is optional — omit it for text-only agents.

Voice agents also require:
- The standard `agent_type` (e.g. `AgentforceServiceAgent`) — **do NOT** set `Atlas__VoiceAgent` in the bundle `config` block. `Atlas__VoiceAgent` is a runtime `planner_type` value applied by the platform, not an authored field in the `.agent` file.
- A `VoiceCallId` linked variable bound to `@VoiceCall.Id` (the voice-channel session identifier — the voice analog of `@MessagingSession.Id`).
- A `language:` block with the appropriate locale.
- The existing `connection` blocks — keep `connection messaging:` (used for escalation) and add `connection customer_web_client:` (see "Connection Blocks" below).

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

```
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

1. **Keep responses concise.** Users cannot scan/skim voice responses. Aim for 1-2 sentences per turn, not paragraphs.
2. **Avoid lists longer than 3 items.** Users lose track of spoken lists. Offer to repeat or narrow down.
3. **Use confirmation patterns.** Repeat back key information (account numbers, dates, amounts) before taking action.
4. **Design for barge-in.** Users may interrupt. Instructions should handle partial inputs gracefully.
5. **Avoid formatting references.** Do not reference links, bullet points, tables, or visual formatting in instructions — they don't render in voice.

### Instruction Example — Voice vs Text

**Text agent instruction:**
```
| Here are your options:
| 1. Check order status
| 2. Return an item
| 3. Speak with a representative
| Please enter the number of your choice.
```

**Voice agent instruction:**
```
| Ask the customer what they'd like help with. You can check order status, process a return, or connect them with a representative. If unclear, ask one clarifying question.
```

### Connection Blocks

`connection` blocks are separate from `modality voice:` — they define the surface/channel the agent is wired to, while `modality` defines voice behavior. The only valid connection surface types are **messaging** and **customer_web_client** — there is **no `connection voice:`**.

A voice-enabled service agent keeps its `connection messaging:` block (escalation is still wired through it) and adds a `connection customer_web_client:` block. This matches what the Agent Builder UI emits when voice is turned on:

```agentscript
connection messaging:
    escalation_message: "Let me transfer you to a specialist who can help."

connection customer_web_client:
    adaptive_response_allowed: True
```

> **Do not** replace `connection messaging:` with a voice-specific block, and do not invent `connection voice:`. Enabling voice **adds** the `modality voice:` block, the `VoiceCallId` variable, and `connection customer_web_client:` — it does not remove the existing messaging connection.

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
