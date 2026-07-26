"""Google Calendar tools — list and create events."""

from __future__ import annotations

import logging
from datetime import datetime, timezone
from typing import Any

from jarvis.tools.base import Tool

logger = logging.getLogger("jarvis.tools.calendar")


def _get_calendar_service(token_path: Any, client_id: str, client_secret: str) -> Any:
    """Build a Google Calendar API service from cached credentials."""
    from google.oauth2.credentials import Credentials
    from googleapiclient.discovery import build

    creds = Credentials.from_authorized_user_file(
        str(token_path),
        scopes=[
            "https://www.googleapis.com/auth/calendar.readonly",
            "https://www.googleapis.com/auth/calendar.events",
        ],
    )
    return build("calendar", "v3", credentials=creds)


def build_calendar_tools(
    token_path: Any, client_id: str, client_secret: str
) -> list[Tool]:
    """Return Google Calendar tools bound to the given OAuth credentials."""

    async def _list_today(args: dict[str, Any]) -> str:
        try:
            service = _get_calendar_service(token_path, client_id, client_secret)
            now = datetime.now(timezone.utc)
            start_of_day = now.replace(hour=0, minute=0, second=0, microsecond=0)
            end_of_day = start_of_day.replace(hour=23, minute=59, second=59)

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_of_day.isoformat(),
                    timeMax=end_of_day.isoformat(),
                    maxResults=20,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            if not events:
                return "No events today."

            lines = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                summary = event.get("summary", "(no title)")
                lines.append(f"- {start}: {summary}")
            return "Today's events:\n" + "\n".join(lines)
        except Exception as e:
            logger.exception("calendar list_today failed")
            return f"Error reading calendar: {e}"

    async def _list_week(args: dict[str, Any]) -> str:
        try:
            service = _get_calendar_service(token_path, client_id, client_secret)
            now = datetime.now(timezone.utc)
            start_of_week = now.replace(hour=0, minute=0, second=0, microsecond=0)
            # Go back to Monday
            days_since_monday = start_of_week.weekday()
            start_of_week = start_of_week.replace(day=start_of_week.day - days_since_monday)
            end_of_week = start_of_week.replace(day=start_of_week.day + 7)

            events_result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=start_of_week.isoformat(),
                    timeMax=end_of_week.isoformat(),
                    maxResults=50,
                    singleEvents=True,
                    orderBy="startTime",
                )
                .execute()
            )
            events = events_result.get("items", [])

            if not events:
                return "No events this week."

            lines = []
            for event in events:
                start = event["start"].get("dateTime", event["start"].get("date"))
                summary = event.get("summary", "(no title)")
                lines.append(f"- {start}: {summary}")
            return "This week's events:\n" + "\n".join(lines)
        except Exception as e:
            logger.exception("calendar list_week failed")
            return f"Error reading calendar: {e}"

    async def _create_event(args: dict[str, Any]) -> str:
        try:
            service = _get_calendar_service(token_path, client_id, client_secret)
            summary = args.get("summary", "")
            start_time = args.get("start_time", "")
            end_time = args.get("end_time", "")
            description = args.get("description", "")

            if not summary or not start_time:
                return "Error: summary and start_time are required."

            event_body: dict[str, Any] = {
                "summary": summary,
                "start": {"dateTime": start_time, "timeZone": "Asia/Kolkata"},
                "end": {"dateTime": end_time, "timeZone": "Asia/Kolkata"},
            }
            if description:
                event_body["description"] = description

            created = service.events().insert(
                calendarId="primary", body=event_body
            ).execute()
            return f"Created event: {created.get('summary')} at {start_time}"
        except Exception as e:
            logger.exception("calendar create_event failed")
            return f"Error creating event: {e}"

    return [
        Tool(
            name="list_today_events",
            description="List today's Google Calendar events.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_list_today,
            requires_confirm=False,
        ),
        Tool(
            name="list_week_events",
            description="List this week's Google Calendar events.",
            parameters={"type": "object", "properties": {}, "required": []},
            handler=_list_week,
            requires_confirm=False,
        ),
        Tool(
            name="create_calendar_event",
            description="Create a new Google Calendar event. Requires confirmation before executing.",
            parameters={
                "type": "object",
                "properties": {
                    "summary": {"type": "string", "description": "Event title"},
                    "start_time": {
                        "type": "string",
                        "description": "Start time in ISO 8601 format, e.g. 2026-07-26T14:00:00",
                    },
                    "end_time": {
                        "type": "string",
                        "description": "End time in ISO 8601 format, e.g. 2026-07-26T15:00:00",
                    },
                    "description": {
                        "type": "string",
                        "description": "Optional event description",
                    },
                },
                "required": ["summary", "start_time", "end_time"],
            },
            handler=_create_event,
            requires_confirm=True,
        ),
    ]
