# Copyright (C) 2025 AIDC-AI

"""成片增强：字幕字体、字号（与 pixelle_video.postprocess.digital_human_post 对接）."""

import streamlit as st

from web.i18n import tr

_FONT_ROWS: list[tuple[str, str]] = [
    ("Microsoft YaHei", "subtitle.font.microsoft_yahei"),
    ("SimHei", "subtitle.font.simhei"),
    ("SimSun", "subtitle.font.simsun"),
    ("KaiTi", "subtitle.font.kaiti"),
    ("FangSong", "subtitle.font.fangsong"),
    ("DengXian", "subtitle.font.dengxian"),
    ("Arial", "subtitle.font.arial"),
    ("Segoe UI", "subtitle.font.segoe_ui"),
]


def render_subtitle_post_controls(key_ns: str) -> dict:
    """返回 post_subtitle_font（ASS 字体名）、post_subtitle_font_size（0=自动）。"""
    indices = list(range(len(_FONT_ROWS)))
    ix = st.selectbox(
        tr("subtitle.pick_font"),
        indices,
        format_func=lambda i: tr(_FONT_ROWS[i][1]),
        key=f"{key_ns}_subtitle_font_ix",
    )
    fs = st.number_input(
        tr("subtitle.font_size"),
        min_value=0,
        max_value=96,
        value=0,
        step=1,
        help=tr("subtitle.font_size_help"),
        key=f"{key_ns}_subtitle_fs",
    )
    col = st.color_picker(
        tr("subtitle.color"),
        value="#FFFFFF",
        key=f"{key_ns}_subtitle_color",
    )
    return {
        "post_subtitle_font": _FONT_ROWS[int(ix)][0],
        "post_subtitle_font_size": None if fs <= 0 else int(fs),
        "post_subtitle_color_hex": col,
    }
