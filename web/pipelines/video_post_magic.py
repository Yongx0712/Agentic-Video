# Copyright (C) 2025 AIDC-AI

import asyncio
import os
from pathlib import Path
from typing import Any

import streamlit as st

from web.i18n import get_language, tr
from web.pipelines.base import PipelineUI, register_pipeline_ui
from web.utils.async_helpers import run_async
from web.components.subtitle_post_controls import render_subtitle_post_controls
from pixelle_video.utils.os_util import create_task_output_dir


class VideoPostMagicPipelineUI(PipelineUI):
    name = "video_post_magic"
    icon = "✨"

    @property
    def display_name(self):
        return tr("pipeline.video_post_magic.name")

    @property
    def description(self):
        return tr("pipeline.video_post_magic.description")

    def render(self, pixelle_video: Any):
        left, right = st.columns([1, 1])
        with left:
            st.markdown(f"**{tr('video_post_magic.section.input')}**")
            vid = st.file_uploader(
                tr("video_post_magic.upload_video"),
                type=["mp4", "mov", "webm", "mkv"],
                key="vpm_main_video",
            )
            script = st.text_area(
                tr("video_post_magic.script"),
                height=120,
                key="vpm_script",
            )
            pip = st.file_uploader(
                tr("video_post_magic.upload_pip"),
                type=["mp4", "mov", "webm", "mkv"],
                key="vpm_pip",
            )
            sub_style = render_subtitle_post_controls("vpm")
            st.caption(tr("video_post_magic.caption"))

        with right:
            st.markdown(f"**{tr('section.video_generation')}**")
            run_key = "vpm_run_enhance"
            if st.button(tr("video_post_magic.btn_run"), type="primary", use_container_width=True, key=run_key):
                if vid is None:
                    st.warning(tr("video_post_magic.need_video"))
                    return

                task_dir, _tid = create_task_output_dir()
                ext = Path(vid.name).suffix or ".mp4"
                in_path = os.path.join(task_dir, f"upload{ext}")
                with open(in_path, "wb") as f:
                    f.write(vid.getbuffer())

                pip_path = None
                if pip is not None:
                    pext = Path(pip.name).suffix or ".mp4"
                    pip_path = os.path.join(task_dir, f"pip_layer{pext}")
                    with open(pip_path, "wb") as f:
                        f.write(pip.getbuffer())

                from pixelle_video.postprocess.digital_human_post import (
                    enhance_digital_human_video_safe,
                )

                progress = st.progress(0)
                status = st.empty()
                status.text(tr("video_post_magic.running"))
                progress.progress(30)

                async def _job():
                    return await asyncio.to_thread(
                        enhance_digital_human_video_safe,
                        in_path,
                        task_dir,
                        (script or "").strip(),
                        pip_path,
                        subtitle_font=sub_style.get("post_subtitle_font"),
                        subtitle_font_size=sub_style.get("post_subtitle_font_size"),
                        subtitle_color_hex=sub_style.get("post_subtitle_color_hex"),
                    )

                try:
                    out_path = run_async(_job())
                    progress.progress(100)
                    status.empty()
                    st.success(tr("status.video_generated", path=out_path))
                    if os.path.isfile(out_path):
                        st.video(out_path)
                        with open(out_path, "rb") as vf:
                            label = "⬇️ 下载成片" if get_language() == "zh_CN" else "⬇️ Download"
                            st.download_button(
                                label,
                                vf.read(),
                                file_name=os.path.basename(out_path),
                                mime="video/mp4",
                                use_container_width=True,
                                key="vpm_dl",
                            )
                except Exception as e:
                    progress.empty()
                    status.empty()
                    st.error(tr("status.error", error=str(e)))


register_pipeline_ui(VideoPostMagicPipelineUI)
