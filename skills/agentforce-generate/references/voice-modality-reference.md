# Voice Modality Reference

## Overview

Voice agents use the `modality voice:` block to configure text-to-speech (TTS) and speech-to-text (STT) behavior. This block is optional — omit it for text-only agents.

Voice agents also require:
- `agent_template: "Atlas__VoiceAgent"` in the `config` block (or the standard service/employee template if using voice as a secondary channel)
- A `language:` block with the appropriate locale

## Agent Script Syntax

```agentscript
modality voice:
    voice_id: "UgBBYS2sOqTuMpoF3BR0"
    outbound_speed: 1
    outbound_stability: 0.65
    outbound_similarity: 0.75
```

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

### Connection Block for Voice Escalation

Voice agents that escalate to human agents use `connection voice:` (not `connection messaging:`):

```agentscript
connection voice:
    escalation_message: "Let me transfer you to a specialist who can help."
```

This is separate from the `modality voice:` block — `connection` defines the escalation channel, while `modality` defines voice behavior.

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
