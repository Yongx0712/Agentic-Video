# Copyright (C) 2025 AIDC-AI
#
# Licensed under the Apache License, Version 2.0 (the "License");
# you may not use this file except in compliance with the License.

"""Retry RunningHub create_task when API reports queue full."""

import asyncio

from loguru import logger

_applied = False


def apply_runninghub_queue_retry() -> None:
    global _applied
    if _applied:
        return

    from comfykit.comfyui.runninghub_client import RunningHubClient

    _orig = RunningHubClient.create_task

    async def create_task_with_queue_retry(self, workflow_id, node_info_list=None):
        max_attempts = 24
        base_delay = 5.0
        for attempt in range(max_attempts):
            try:
                return await _orig(self, workflow_id, node_info_list)
            except Exception as e:
                err = str(e)
                if ("TASK_QUEUE_MAXED" in err or "QUEUE_MAX" in err) and attempt < max_attempts - 1:
                    delay = min(base_delay * (1.4**attempt), 90.0)
                    logger.warning(
                        "RunningHub queue busy (TASK_QUEUE_MAXED), waiting {:.0f}s — retry {}/{}",
                        delay,
                        attempt + 2,
                        max_attempts,
                    )
                    await asyncio.sleep(delay)
                    continue
                raise

    RunningHubClient.create_task = create_task_with_queue_retry
    _applied = True
