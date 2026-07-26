# Tasks: Personal Memory + App Integrations

## Phase 1: Memory System

### Task 1.1: Create Profile YAML Schema and Loader
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Create the `data/profile.yaml` schema and implement the ProfileLoader class to parse it.

**Acceptance Criteria**:
- ProfileLoader loads `data/profile.yaml` on initialization
- Validates required fields: `full_name`, `preferred_name`
- Handles missing optional fields gracefully
- Returns Profile dataclass

**Files to Create/Modify**:
- `jarvis/memory/__init__.py`
- `jarvis/memory/profile.py`
- `data/profile.yaml` (example template)

**Dependencies**: None

---

### Task 1.2: Create Notes Loader
**Priority**: P0 | **Estimate**: 1h | **Status**: Pending

**Description**: Implement the NotesLoader class to load markdown files from `data/notes/`.

**Acceptance Criteria**:
- Loads all `.md` files from `data/notes/` directory
- Each note has title (from filename or frontmatter), content, and tags
- Notes longer than 500 chars are summarized to 200 chars for context
- Handles empty notes directory gracefully

**Files to Create/Modify**:
- `jarvis/memory/notes.py`
- `data/notes/.gitkeep`

**Dependencies**: None

---

### Task 1.3: Build Memory Context Block
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Implement the `build_context_block()` function that creates the system prompt context from profile and notes.

**Acceptance Criteria**:
- Context block starts with anti-hallucination rule (CRITICAL RULE section)
- Includes profile data: name, work, people, preferences
- Includes notes (summarized if too long)
- Total context stays under token budget
- Returns formatted string ready for system prompt injection

**Files to Create/Modify**:
- `jarvis/memory/context_builder.py`

**Dependencies**: 1.1, 1.2

---

### Task 1.4: Extend GroqBrain with Memory Context
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Modify GroqBrain to inject memory context into system prompt.

**Acceptance Criteria**:
- Memory context injected at top of system prompt
- Existing streaming path unchanged
- Memory loaded once at initialization, reused for all requests
- Configuration option to disable memory injection

**Files to Create/Modify**:
- `jarvis/llm/groq_client.py`
- `jarvis/config.py` (add memory settings)

**Dependencies**: 1.3

---

### Task 1.5: Add Profile Update Tools
**Priority**: P1 | **Estimate**: 2h | **Status**: Pending

**Description**: Implement tools for updating profile fields and adding notes.

**Acceptance Criteria**:
- `save_note` tool adds a new note file
- `update_profile_field` tool modifies profile.yaml
- Both require confirmation before writing
- Profile updates validate schema before saving

**Files to Create/Modify**:
- `jarvis/tools/memory_tools.py`

**Dependencies**: 1.1, 2.1, 3.1

---

## Phase 2: Tool System

### Task 2.1: Create Tool Registry Base
**Priority**: P0 | **Estimate**: 3h | **Status**: Pending

**Description**: Implement the ToolRegistry class and base Tool interface.

**Acceptance Criteria**:
- Tool dataclass with name, description, parameters schema, execute function
- ToolRegistry registers and looks up tools by name
- `get_tool_schemas()` returns Groq-compatible function definitions
- `requires_confirmation()` checks tool's confirmation flag

**Files to Create/Modify**:
- `jarvis/tools/__init__.py`
- `jarvis/tools/base.py`
- `jarvis/tools/registry.py`

**Dependencies**: None

---

### Task 2.2: Extend GroqBrain for Tool Calling
**Priority**: P0 | **Estimate**: 4h | **Status**: Pending

**Description**: Add `complete_with_tools()` method to GroqBrain for tool-calling mode.

**Acceptance Criteria**:
- Detect when tools are needed vs pure chat
- Make non-streamed API call with tool definitions
- Execute tool calls and append results to messages
- Return AgentResponse with appropriate type
- Preserve existing `stream_reply()` for pure chat

**Files to Create/Modify**:
- `jarvis/llm/groq_client.py`
- `jarvis/llm/types.py` (AgentResponse, ResponseType)

**Dependencies**: 2.1

---

### Task 2.3: Wire Tool System into Pipeline
**Priority**: P0 | **Estimate**: 3h | **Status**: Pending

**Description**: Integrate tool calling into the orchestrator pipeline.

**Acceptance Criteria**:
- Pipeline detects tool responses from GroqBrain
- Tool execution happens during THINKING state
- Tool results fed back to LLM
- Final response streams to TTS as before
- No disruption to streaming latency for pure chat

**Files to Create/Modify**:
- `jarvis/orchestrator/pipeline.py`

**Dependencies**: 2.2, 1.4

---

## Phase 3: Confirm Gate

### Task 3.1: Implement Confirm Gate
**Priority**: P0 | **Estimate**: 3h | **Status**: Pending

**Description**: Implement the ConfirmGate class for managing pending actions.

**Acceptance Criteria**:
- Store pending actions with unique ID and TTL
- Retrieve pending actions by ID
- Check if action is expired
- Confirm or cancel pending actions
- Background cleanup of expired actions

**Files to Create/Modify**:
- `jarvis/tools/confirm.py`

**Dependencies**: None

---

### Task 3.2: Implement Confirmation Phrase Matching
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Implement natural language matching for confirmation phrases.

**Acceptance Criteria**:
- Match confirmation phrases: yes, yeah, send it, confirm, do it, okay, sure
- Match cancellation phrases: no, cancel, stop, don't send, abort
- Case-insensitive matching
- Substring matching for natural variations
- Return CONFIRM, CANCEL, or AMBIGUOUS

**Files to Create/Modify**:
- `jarvis/tools/confirm.py`

**Dependencies**: None

---

### Task 3.3: Add AWAITING_CONFIRM State
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Extend the state machine with AWAITING_CONFIRM state.

**Acceptance Criteria**:
- Add AWAITING_CONFIRM to PipelineState enum
- Add legal transitions: THINKING → AWAITING_CONFIRM
- Add legal transitions: AWAITING_CONFIRM → SPEAKING, IDLE
- Support barge-in during AWAITING_CONFIRM
- Update state machine visualization

**Files to Create/Modify**:
- `jarvis/types.py`
- `jarvis/orchestrator/state.py`

**Dependencies**: None

---

### Task 3.4: Wire Confirm Gate into Pipeline
**Priority**: P0 | **Estimate**: 4h | **Status**: Pending

**Description**: Integrate confirm gate into the orchestrator pipeline.

**Acceptance Criteria**:
- When tool requires confirmation, transition to AWAITING_CONFIRM
- Speak draft/preview content
- Listen for user response
- On confirm: execute pending action, speak result
- On cancel: speak "Cancelled", return to IDLE
- Handle expired pending actions

**Files to Create/Modify**:
- `jarvis/orchestrator/pipeline.py`

**Dependencies**: 3.1, 3.2, 3.3, 2.3

---

## Phase 4: Google Integration

### Task 4.1: Create Google OAuth Setup Script
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Create a one-time OAuth setup script for Google Calendar and Gmail.

**Acceptance Criteria**:
- Script opens browser for user authorization
- Requests Calendar and Gmail scopes
- Saves token to `data/google_token.json`
- Token file has 600 permissions
- Token path added to .gitignore

**Files to Create/Modify**:
- `scripts/google_oauth_setup.py`
- `jarvis/integrations/google_auth.py`

**Dependencies**: None

---

### Task 4.2: Implement Google Calendar Tool
**Priority**: P0 | **Estimate**: 4h | **Status**: Pending

**Description**: Implement Google Calendar API integration.

**Acceptance Criteria**:
- `list_events(date, max_results)` - lists events for given date
- `create_event(summary, start, end, description)` - creates event (requires confirm)
- OAuth token refresh on 401
- Events formatted for spoken delivery
- Timezone handling from profile

**Files to Create/Modify**:
- `jarvis/integrations/__init__.py`
- `jarvis/integrations/google_calendar.py`
- `jarvis/tools/calendar_google.py`

**Dependencies**: 4.1, 2.1

---

### Task 4.3: Implement Gmail Tool
**Priority**: P0 | **Estimate**: 4h | **Status**: Pending

**Description**: Implement Gmail API integration.

**Acceptance Criteria**:
- `list_messages(query, max_results)` - lists emails
- `get_message(message_id)` - gets full email
- `draft_message(to, subject, body)` - creates draft
- `send_message(to, subject, body)` - sends email (requires confirm)
- Emails formatted for spoken delivery

**Files to Create/Modify**:
- `jarvis/integrations/gmail.py`
- `jarvis/tools/gmail.py`

**Dependencies**: 4.1, 2.1

---

## Phase 5: WhatsApp Integration

### Task 5.1: Implement WhatsApp Cloud API Client
**Priority**: P1 | **Estimate**: 4h | **Status**: Pending

**Description**: Implement WhatsApp Cloud API integration via Meta.

**Acceptance Criteria**:
- Configure phone number ID and token from environment
- `list_messages(phone_number, limit)` - lists recent messages
- `send_message(to, body)` - sends message (requires confirm)
- Proper error handling for API failures
- Rate limit awareness

**Files to Create/Modify**:
- `jarvis/integrations/whatsapp.py`
- `jarvis/tools/whatsapp.py`

**Dependencies**: 2.1, 3.4

---

## Phase 6: Instagram Integration

### Task 6.1: Implement Instagram Graph API Client
**Priority**: P2 | **Estimate**: 4h | **Status**: Pending

**Description**: Implement Instagram Graph API integration.

**Acceptance Criteria**:
- Configure page ID and access token from environment
- `get_comments(media_id, limit)` - gets comments on posts
- `reply_to_comment(comment_id, message)` - replies (requires confirm)
- `get_direct_messages(limit)` - gets recent DMs
- `send_direct_message(recipient_id, message)` - sends DM (requires confirm)

**Files to Create/Modify**:
- `jarvis/integrations/instagram.py`
- `jarvis/tools/instagram.py`

**Dependencies**: 2.1, 3.4

---

## Phase 7: LinkedIn Integration

### Task 7.1: Implement LinkedIn API Client
**Priority**: P2 | **Estimate**: 4h | **Status**: Pending

**Description**: Implement LinkedIn API integration.

**Acceptance Criteria**:
- Configure client ID and secret from environment
- `get_profile()` - gets user profile data
- `create_post(commentary, visibility)` - creates post (requires confirm)
- `draft_message(recipient_urn, subject, body)` - drafts message (NO send)
- Clear messaging that LinkedIn DMs are draft-only

**Files to Create/Modify**:
- `jarvis/integrations/linkedin.py`
- `jarvis/tools/linkedin.py`

**Dependencies**: 2.1, 3.4

---

## Phase 8: Configuration and Documentation

### Task 8.1: Update Configuration System
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Add all new configuration options to Settings class.

**Acceptance Criteria**:
- Add memory settings: profile path, notes path
- Add tool settings: require_confirm flag
- Add Google settings: client_id, client_secret
- Add WhatsApp settings: phone_id, token
- Add Instagram settings: page_id, access_token
- Add LinkedIn settings: client_id, client_secret

**Files to Create/Modify**:
- `jarvis/config.py`
- `.env.example`

**Dependencies**: None

---

### Task 8.2: Update README and Documentation
**Priority**: P1 | **Estimate**: 2h | **Status**: Pending

**Description**: Document the new features and setup process.

**Acceptance Criteria**:
- Document profile.yaml schema
- Document notes directory structure
- Document OAuth setup process
- Document available tools and commands
- Document confirm-before-send flow
- Add troubleshooting section

**Files to Create/Modify**:
- `README.md`
- `docs/memory.md`
- `docs/tools.md`

**Dependencies**: All previous tasks

---

## Phase 9: Testing

### Task 9.1: Unit Tests for Memory System
**Priority**: P0 | **Estimate**: 3h | **Status**: Pending

**Description**: Write unit tests for profile loader, notes loader, and context builder.

**Acceptance Criteria**:
- Test profile loading with valid/invalid files
- Test notes loading with empty/populated directory
- Test context block generation
- Test note summarization for long content
- All tests pass

**Files to Create/Modify**:
- `tests/test_memory_profile.py`
- `tests/test_memory_notes.py`
- `tests/test_memory_context.py`

**Dependencies**: 1.1, 1.2, 1.3

---

### Task 9.2: Unit Tests for Confirm Gate
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Write unit tests for confirm gate and phrase matching.

**Acceptance Criteria**:
- Test pending action storage and retrieval
- Test TTL expiration
- Test confirmation phrase matching (positive cases)
- Test cancellation phrase matching (positive cases)
- Test ambiguous phrase handling
- Property-based tests with hypothesis for determinism

**Files to Create/Modify**:
- `tests/test_confirm_gate.py`
- `tests/test_phrase_matching.py`

**Dependencies**: 3.1, 3.2

---

### Task 9.3: Unit Tests for Tool Registry
**Priority**: P0 | **Estimate**: 2h | **Status**: Pending

**Description**: Write unit tests for tool registry and base tool functionality.

**Acceptance Criteria**:
- Test tool registration
- Test schema generation
- Test requires_confirmation flag
- Test tool execution (with mock tools)

**Files to Create/Modify**:
- `tests/test_tool_registry.py`

**Dependencies**: 2.1

---

### Task 9.4: Integration Tests for Pipeline with Tools
**Priority**: P1 | **Estimate**: 4h | **Status**: Pending

**Description**: Write integration tests for the full pipeline with tools.

**Acceptance Criteria**:
- Test pure chat path (no tools)
- Test tool execution without confirmation
- Test tool execution with confirmation flow
- Test cancel flow
- Test expired pending action handling
- Mock Groq API responses

**Files to Create/Modify**:
- `tests/test_pipeline_tools.py`

**Dependencies**: 2.3, 3.4

---

### Task 9.5: Smoke Tests for Integrations
**Priority**: P1 | **Estimate**: 3h | **Status**: Pending

**Description**: Write smoke tests for API integrations (skip if no credentials).

**Acceptance Criteria**:
- Test Google Calendar API (skip if no token)
- Test Gmail API (skip if no token)
- Test WhatsApp API (skip if no token)
- Test Instagram API (skip if no token)
- Test LinkedIn API (skip if no token)
- Document how to run with live credentials

**Files to Create/Modify**:
- `tests/test_google_integration.py`
- `tests/test_whatsapp_integration.py`
- `tests/test_instagram_integration.py`
- `tests/test_linkedin_integration.py`

**Dependencies**: 4.2, 4.3, 5.1, 6.1, 7.1

---

## Build Order Summary

1. **Memory System** (Phase 1): 1.1 → 1.2 → 1.3 → 1.4 → 1.5
2. **Tool System** (Phase 2): 2.1 → 2.2 → 2.3 (parallel with 1.4)
3. **Confirm Gate** (Phase 3): 3.1, 3.2, 3.3 (parallel) → 3.4
4. **Google Integration** (Phase 4): 4.1 → 4.2, 4.3 (parallel)
5. **WhatsApp Integration** (Phase 5): 5.1
6. **Instagram Integration** (Phase 6): 6.1
7. **LinkedIn Integration** (Phase 7): 7.1
8. **Configuration and Documentation** (Phase 8): 8.1 (parallel throughout), 8.2 (at end)
9. **Testing** (Phase 9): Throughout development, final integration tests at end
