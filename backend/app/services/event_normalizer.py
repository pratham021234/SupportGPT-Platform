"""Provider event adapters and normalization into canonical domain representation."""

from datetime import UTC, datetime
from typing import Any

from app.core.errors import EventNormalizationException
from app.models.enums import AuthorType, MessageDirection, SourceProvider, TicketPriority
from app.models.event_source import EventSource
from app.schemas.canonical_event import CanonicalCustomer, CanonicalEvent


class BaseProviderAdapter:
    """Interface for provider-specific event payload parsing and normalization."""

    def normalize(
        self,
        source: EventSource,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> CanonicalEvent:
        raise NotImplementedError


class StandardWebhookAdapter(BaseProviderAdapter):
    """Normalizes generic/standard SupportGPT JSON webhooks."""

    def normalize(
        self,
        source: EventSource,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> CanonicalEvent:
        headers = headers or {}

        # 1. External Event Identifier
        external_event_id = (
            headers.get("x-supportgpt-event-id") or payload.get("event_id") or payload.get("id")
        )
        if not external_event_id:
            raise EventNormalizationException(
                "Missing required external event identifier ('event_id')."
            )

        # 2. Event Type
        event_type = (
            headers.get("x-supportgpt-event-type")
            or payload.get("event_type")
            or payload.get("type")
        )
        if not event_type:
            raise EventNormalizationException("Missing required event type ('event_type').")

        # 3. Timestamp
        event_timestamp = datetime.now(UTC)
        raw_ts = payload.get("timestamp") or headers.get("x-supportgpt-timestamp")
        if raw_ts:
            try:
                if isinstance(raw_ts, (int, float)) or (
                    isinstance(raw_ts, str) and raw_ts.isdigit()
                ):
                    event_timestamp = datetime.fromtimestamp(float(raw_ts), tz=UTC)
                elif isinstance(raw_ts, str):
                    event_timestamp = datetime.fromisoformat(raw_ts.replace("Z", "+00:00"))
            except Exception:
                pass

        # 4. Customer Extraction
        customer_data = payload.get("customer") or {}
        customer = None
        email = customer_data.get("email") or payload.get("customer_email")
        phone = customer_data.get("phone") or payload.get("customer_phone")
        name = customer_data.get("name") or payload.get("customer_name")
        ext_cust_id = (
            customer_data.get("id")
            or customer_data.get("external_id")
            or payload.get("external_customer_id")
        )

        if email or phone or name or ext_cust_id:
            customer = CanonicalCustomer(
                email=email,
                phone=phone,
                name=name,
                external_id=str(ext_cust_id) if ext_cust_id is not None else None,
            )

        # 5. External Reference Identifiers
        ticket_data = payload.get("ticket") or {}
        external_ticket_id = (
            payload.get("external_ticket_id") or payload.get("ticket_id") or ticket_data.get("id")
        )
        external_conversation_id = payload.get("external_conversation_id") or payload.get(
            "conversation_id"
        )
        external_message_id = (
            payload.get("external_message_id")
            or payload.get("message_id")
            or (payload.get("message") or {}).get("id")
        )

        # 6. Subject & Content
        subject = payload.get("subject") or ticket_data.get("subject")
        message_body = (
            payload.get("message_body")
            or payload.get("message")
            or payload.get("body")
            or payload.get("description")
            or ticket_data.get("description")
        )
        if isinstance(message_body, dict):
            message_body = message_body.get("text") or message_body.get("body")

        # 7. Priority Mapping
        raw_priority = payload.get("priority") or ticket_data.get("priority")
        priority = None
        if raw_priority:
            try:
                priority = TicketPriority(str(raw_priority).lower())
            except ValueError:
                pass

        correlation_id = (
            headers.get("x-correlation-id")
            or headers.get("x-request-id")
            or payload.get("correlation_id")
        )

        return CanonicalEvent(
            schema_version="1.0",
            source_id=source.id,
            provider=source.provider,
            external_event_id=str(external_event_id),
            event_type=str(event_type),
            event_timestamp=event_timestamp,
            external_ticket_id=str(external_ticket_id) if external_ticket_id is not None else None,
            external_conversation_id=str(external_conversation_id)
            if external_conversation_id is not None
            else None,
            external_message_id=str(external_message_id)
            if external_message_id is not None
            else None,
            subject=str(subject) if subject is not None else None,
            message_body=str(message_body) if message_body is not None else None,
            message_direction=MessageDirection.INBOUND,
            author_type=AuthorType.CUSTOMER,
            customer=customer,
            priority=priority,
            metadata=payload.get("metadata") or {},
            correlation_id=str(correlation_id) if correlation_id is not None else None,
        )


class EventNormalizer:
    """Registry and dispatcher for provider-specific event normalization."""

    _adapters: dict[str, BaseProviderAdapter] = {
        SourceProvider.GENERIC_WEBHOOK: StandardWebhookAdapter(),
        SourceProvider.CUSTOM_API: StandardWebhookAdapter(),
        SourceProvider.EMAIL_POSTMARK: StandardWebhookAdapter(),
        SourceProvider.EMAIL_SENDGRID: StandardWebhookAdapter(),
        SourceProvider.ZENDESK: StandardWebhookAdapter(),
    }

    @classmethod
    def get_adapter(cls, provider: str) -> BaseProviderAdapter:
        return cls._adapters.get(provider, StandardWebhookAdapter())

    @classmethod
    def normalize(
        cls,
        source: EventSource,
        payload: dict[str, Any],
        headers: dict[str, str] | None = None,
    ) -> CanonicalEvent:
        adapter = cls.get_adapter(source.provider)
        return adapter.normalize(source, payload, headers)
