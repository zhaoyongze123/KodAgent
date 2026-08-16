"""User-facing result and narration boundary."""

from .narration import NarrationStreamingModel, stream_model_output_enabled
from .message_contract import (
    PRESENTATION_KEY,
    presentation_final_entry_id,
    presentation_kind,
    with_message_presentation,
)

__all__ = [
    "NarrationStreamingModel", "stream_model_output_enabled", "PRESENTATION_KEY",
    "presentation_final_entry_id", "presentation_kind", "with_message_presentation",
]
