# Requirements Document

## Introduction

**Feature Name**: personal-memory-apps

**Description**: Stop hallucinated personal answers by giving JARVIS a local profile + Google Calendar context, then add a tool-calling layer with confirm-before-send for Gmail and Meta/LinkedIn connectors.

**User Value**: Users can ask personal questions ("What's on my calendar?", "Who is my sister?") and get accurate answers from their own data, plus perform actions ("Send an email to mom") with safety confirmation before execution.

---

## Glossary

| Term | Definition |
|------|------------|
| Confirm Gate | A system that stores pending actions requiring user confirmation before execution |
| Pending Action | A tool call that has been prepared but awaits user confirmation before execution |
| Tool Registry | Central registry of available tools with their JSON schemas for Groq function calling |
| AWAITING_CONFIRM | New pipeline state where JARVIS waits for user to confirm or cancel a pending action |
| Memory Context | Profile data and notes injected into the system prompt for personal context |
| Anti-Hallucination Rule | System prompt rule that instructs JARVIS to never invent personal facts |

---

## Requirements

### Requirement 1

**User Story:** 1. As a user, I want JARVIS to load my profile from a local file so that it knows my personal information.

**Acceptance Criteria:**
- Given a valid `profile.yaml` file exists
- When JARVIS starts
- Then the profile data is loaded and included in the system prompt
- And the system prompt contains the user's name, preferences, and people data

**Priority:** P0 (Critical)

---

### Requirement 2

**User Story:** 2. As a user, I want JARVIS to load my notes from local files so that it can reference them in conversations.

**Acceptance Criteria:**
- Given one or more `.md` files exist in `data/notes/`
- When JARVIS starts
- Then all notes are loaded and available for context
- And notes exceeding 500 characters are summarized to 200 characters

**Priority:** P0 (Critical)

---

### Requirement 3

**User Story:** 3. As a user, I want JARVIS to never invent personal facts so that I can trust its answers about me.

**Acceptance Criteria:**
- Given the user asks "What's my favorite color?" and this is not in profile
- When JARVIS responds
- Then JARVIS says it doesn't have that information saved
- And JARVIS offers to help add it to the profile

**Priority:** P0 (Critical)

---

### Requirement 4

**User Story:** 4. As a user, I want to update my profile via voice so that I can add information hands-free.

**Acceptance Criteria:**
- Given the user says "Add my favorite color as blue"
- When JARVIS processes this command
- Then JARVIS asks for confirmation before saving
- And on confirmation, the profile is updated

**Priority:** P1 (High)

---

### Requirement 5

**User Story:** 5. As a user, I want JARVIS to have a registry of tools so that it can interact with external services.

**Acceptance Criteria:**
- Given JARVIS is running
- When the tool registry is initialized
- Then all registered tools have valid JSON Schema definitions
- And each tool has a unique name
- And each tool has a `requires_confirmation` flag

**Priority:** P0 (Critical)

---

### Requirement 6

**User Story:** 6. As a user, I want JARVIS to execute tool calls so that it can perform actions on my behalf.

**Acceptance Criteria:**
- Given the LLM requests a tool call with valid arguments
- When the tool executes
- Then the result is returned to the LLM
- And the LLM incorporates the result into its response

**Priority:** P0 (Critical)

---

### Requirement 7

**User Story:** 7. As a user, I want JARVIS to store pending actions so that it can wait for my confirmation before executing sensitive operations.

**Acceptance Criteria:**
- Given a tool requires confirmation
- When JARVIS executes the tool in preview mode
- Then a pending action is stored with a unique action_id
- And the pending action has a TTL of 5 minutes
- And the pending action can be retrieved by action_id

**Priority:** P0 (Critical)

---

### Requirement 8

**User Story:** 8. As a user, I want to confirm or cancel actions with natural speech so that the interaction feels conversational.

**Acceptance Criteria:**
- Given the user says "yes", "yeah", "send it", "confirm", or "do it"
- When JARVIS evaluates the phrase
- Then it is recognized as CONFIRM
- Given the user says "no", "cancel", "stop", or "don't send"
- When JARVIS evaluates the phrase
- Then it is recognized as CANCEL

**Priority:** P0 (Critical)

---

### Requirement 9

**User Story:** 9. As a user, I want JARVIS to never execute sensitive actions without my confirmation so that I have control over what gets sent.

**Acceptance Criteria:**
- Given a tool is marked `requires_confirmation=true`
- When the LLM requests this tool
- Then JARVIS creates a pending action and enters AWAITING_CONFIRM state
- And the side effect is NOT executed
- And the user must confirm before execution

**Priority:** P0 (Critical)

---

### Requirement 10

**User Story:** 10. As a user, I want JARVIS to check my Google Calendar so that I can ask about my schedule.

**Acceptance Criteria:**
- Given the user asks "What's on my calendar today?"
- When JARVIS executes the list_events tool
- Then events are returned from Google Calendar API
- And events are formatted for spoken delivery
- And no confirmation is required (read-only)

**Priority:** P0 (Critical)

---

### Requirement 11

**User Story:** 11. As a user, I want JARVIS to create calendar events so that I can schedule things hands-free.

**Acceptance Criteria:**
- Given the user says "Schedule a meeting with Alice tomorrow at 2 PM"
- When JARVIS creates a draft event
- Then JARVIS speaks the event details
- And JARVIS enters AWAITING_CONFIRM state
- And on confirmation, the event is created

**Priority:** P1 (High)

---

### Requirement 12

**User Story:** 12. As a user, I want JARVIS to read my emails so that I can check my inbox hands-free.

**Acceptance Criteria:**
- Given the user asks "Do I have any new emails?"
- When JARVIS executes the list_messages tool
- Then recent emails are returned with sender, subject, snippet
- And no confirmation is required (read-only)

**Priority:** P0 (Critical)

---

### Requirement 13

**User Story:** 13. As a user, I want JARVIS to draft and send emails with confirmation so that I can email hands-free safely.

**Acceptance Criteria:**
- Given the user says "Send an email to mom asking about dinner"
- When JARVIS drafts the email
- Then the draft is created in Gmail
- And JARVIS reads the draft aloud
- And JARVIS enters AWAITING_CONFIRM state
- And on confirmation, the email is sent

**Priority:** P0 (Critical)

---

### Requirement 14

**User Story:** 14. As a user, I want JARVIS to send WhatsApp messages so that I can message contacts hands-free.

**Acceptance Criteria:**
- Given the user says "Send a WhatsApp to Alice saying I'll be late"
- When JARVIS drafts the message
- Then JARVIS reads the message aloud
- And JARVIS enters AWAITING_CONFIRM state
- And on confirmation, the message is sent

**Priority:** P1 (High)

---

### Requirement 15

**User Story:** 15. As a user, I want JARVIS to post on Instagram so that I can manage my social media hands-free.

**Acceptance Criteria:**
- Given the user says "Reply to that comment with thanks"
- When JARVIS drafts the reply
- Then JARVIS reads the reply aloud
- And JARVIS enters AWAITING_CONFIRM state
- And on confirmation, the reply is posted

**Priority:** P2 (Medium)

---

### Requirement 16

**User Story:** 16. As a user, I want JARVIS to post on LinkedIn so that I can share professional updates hands-free.

**Acceptance Criteria:**
- Given the user says "Post on LinkedIn about our product launch"
- When JARVIS drafts the post
- Then JARVIS reads the post aloud
- And JARVIS enters AWAITING_CONFIRM state
- And on confirmation, the post is published

**Priority:** P2 (Medium)

---

### Requirement 17

**User Story:** 17. As a user, I want JARVIS to draft LinkedIn messages but explain it cannot send them so that I know the API limitation.

**Acceptance Criteria:**
- Given the user says "Send a LinkedIn message to John"
- When JARVIS processes this request
- Then JARVIS explains that LinkedIn DMs can only be drafted
- And JARVIS creates a draft
- And JARVIS explains the draft must be sent manually via LinkedIn

**Priority:** P2 (Medium)

---

### Requirement 18

**User Story:** 18. As a user, I want OAuth tokens to be stored securely so that my credentials are protected.

**Acceptance Criteria:**
- Given OAuth tokens are saved
- When the file is created
- Then file permissions are 600 (owner read/write only)
- And the file is listed in .gitignore

**Priority:** P0 (Critical)

---

### Requirement 19

**User Story:** 19. As a user, I want tool detection to be fast so that pure chat responses are not delayed.

**Acceptance Criteria:**
- Given the user asks a question not requiring tools
- When JARVIS processes the request
- Then the overhead of checking for tool need is under 100ms
- And streaming to TTS begins within normal latency bounds

**Priority:** P1 (High)

---

## Constraints

### Constraint 1: Platform Requirements

- **Google Calendar/Gmail**: Requires Google Cloud OAuth credentials with appropriate scopes
- **WhatsApp**: Requires Meta Business account and approved phone number
- **Instagram**: Requires Instagram Business/Creator account linked to Facebook Page
- **LinkedIn**: Requires LinkedIn Developer app with appropriate permissions

### Constraint 2: API Limitations

- **LinkedIn DMs**: Official API does not expose personal messaging; draft-only
- **Rate Limits**: All APIs have rate limits that must be respected
- **Webhooks**: WhatsApp and Instagram may require webhook setup for real-time updates (out of scope for Phase 1)

### Constraint 3: Data Location

- All personal data stored locally in `data/` directory
- No cloud sync of profile or notes
- OAuth tokens stored locally only

---

## Out of Scope

- Unofficial WhatsApp Web / Instagram / LinkedIn browser automation
- Full LinkedIn inbox automation (API unavailable)
- Auto-send without confirmation
- Webhook setup for real-time message delivery (Phase 2)
- Media attachments in messages (Phase 2)
- Multi-user support
