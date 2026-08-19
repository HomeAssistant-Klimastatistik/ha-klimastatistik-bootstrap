"""Reparaturflüsse.

Home Assistant kennt bis heute keine offizielle "Neustart erforderlich"-API.
Der unterstützte Weg ist ein Reparaturhinweis mit ausführbarem Flow, der den
Neustart über den regulären Dienst `homeassistant.restart` auslöst.
"""

from __future__ import annotations

import voluptuous as vol
from homeassistant.components.repairs import ConfirmRepairFlow, RepairsFlow
from homeassistant.core import HomeAssistant
from homeassistant.data_entry_flow import FlowResult

from .const import ISSUE_RESTART_REQUIRED


class RestartRequiredFlow(RepairsFlow):
    """Bestätigt und führt den erforderlichen Neustart aus."""

    async def async_step_init(self, user_input: dict[str, str] | None = None) -> FlowResult:
        """Einstieg."""
        return await self.async_step_confirm_restart()

    async def async_step_confirm_restart(
        self, user_input: dict[str, str] | None = None
    ) -> FlowResult:
        """Neustart bestätigen lassen."""
        if user_input is not None:
            await self.hass.services.async_call("homeassistant", "restart", blocking=False)
            return self.async_create_entry(data={})
        return self.async_show_form(step_id="confirm_restart", data_schema=vol.Schema({}))


async def async_create_fix_flow(
    hass: HomeAssistant,
    issue_id: str,
    data: dict[str, str | int | float | None] | None,
) -> RepairsFlow:
    """Passenden Reparaturfluss liefern."""
    if issue_id == ISSUE_RESTART_REQUIRED:
        return RestartRequiredFlow()
    return ConfirmRepairFlow()
