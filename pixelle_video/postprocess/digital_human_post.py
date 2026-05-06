# Copyright (C) 2025 AIDC-AI
#
# Digital-human post chain: synced subtitles (Whisper), ASS styling + keyword
# highlight, optional PiP, preset SFX — implemented locally with FFmpeg.

from __future__ import annotations

import json
import os
import re
from typing import Any
import shutil
import subprocess
import time
from pathlib import Path

from loguru import logger


def _configure_hf_for_download() -> None:
    """Hub 下载易超时：加长超时；默认走 hf-mirror（可用 PIXELLE_HF_OFFICIAL=1 改回官方）。"""
    os.environ.setdefault("HF_HUB_DOWNLOAD_TIMEOUT", "600")
    os.environ.setdefault("HF_HUB_ETAG_TIMEOUT", "120")
    if os.environ.get("HF_ENDPOINT"):
        return
    if os.environ.get("PIXELLE_HF_OFFICIAL", "").strip().lower() in ("1", "true", "yes"):
        return
    custom = (os.environ.get("PIXELLE_HF_ENDPOINT") or "").strip()
    if custom:
        os.environ["HF_ENDPOINT"] = custom.rstrip("/")
    else:
        os.environ["HF_ENDPOINT"] = "https://hf-mirror.com"


def _post_encode_video_args() -> list[str]:
    """Local post only: faster encode defaults (override with PIXELLE_POST_X264_PRESET / PIXELLE_POST_X264_CRF)."""
    preset = os.environ.get("PIXELLE_POST_X264_PRESET", "ultrafast")
    crf = os.environ.get("PIXELLE_POST_X264_CRF", "23")
    return ["-preset", preset, "-crf", crf]


def _subtitle_metrics(width: int, height: int) -> dict[str, Any]:
    """默认大字样式（与原项目一致）；字号可被界面覆盖。"""
    margin_v = max(90, int(height * 0.12))
    base_fs = max(28, min(56, int(48 * height / 1920)))
    outline = max(2, int(3 * height / 1920))
    shadow = max(1, int(2 * height / 1920))
    return {
        "base_fs": base_fs,
        "margin_v": margin_v,
        "outline": outline,
        "shadow": shadow,
        "fontname": "Microsoft YaHei",
        "primary_colour": "&H00FFFFFF",
        "outline_colour": "&H00000000",
    }


def _hex_rgb_to_ass_primary(hex_rgb: str | None) -> str | None:
    if not hex_rgb or not str(hex_rgb).strip():
        return None
    h = str(hex_rgb).strip().lstrip("#")
    if len(h) != 6 or not re.fullmatch(r"[0-9A-Fa-f]{6}", h):
        return None
    r, g, b = int(h[0:2], 16), int(h[2:4], 16), int(h[4:6], 16)
    return f"&H00{b:02X}{g:02X}{r:02X}"


def _outline_colour_for_primary_ass(primary_ass: str) -> str:
    m = re.search(r"&H([0-9A-Fa-f]{8})", primary_ass, re.I)
    if not m:
        return "&H00000000"
    hx = m.group(1)
    body = hx[-6:]
    bb, gg, rr = int(body[0:2], 16), int(body[2:4], 16), int(body[4:6], 16)
    lum = 0.299 * rr + 0.587 * gg + 0.114 * bb
    return "&H00000000" if lum >= 118 else "&H00FFFFFF"


def _max_chars_per_line(video_width: int, font_size: int) -> int:
    fs = max(14, int(font_size))
    return max(8, min(36, int(video_width / (fs * 0.52))))


def _split_two_lines_raw(text: str, limit: int) -> tuple[str, str]:
    t = text.strip()
    if len(t) <= limit:
        return t, ""
    cut = limit
    lo = max(4, limit - 14)
    hi = min(len(t) - 1, limit + 14)
    for pos in range(hi, lo - 1, -1):
        if t[pos - 1] in "，、；：,.!?！？… ":
            cut = pos
            break
    a, b = t[:cut].strip(), t[cut:].strip()
    if not b:
        mid = len(t) // 2
        a, b = t[:mid].strip(), t[mid:].strip()
    max2 = limit * 2 + 4
    if len(b) > max2:
        b = b[: max2 - 1] + "…"
    return a, b


def _subtitle_body_wrapped(
    text: str,
    keywords: list[str],
    base_fs: int,
    video_width: int,
) -> str:
    raw = (text or "").strip()
    if not raw:
        return ""
    lim = _max_chars_per_line(video_width, base_fs)
    if len(raw) <= lim:
        return _highlight_keywords_ass(raw, keywords, base_fs)
    line1, line2 = _split_two_lines_raw(raw, lim)
    if not line2:
        return _highlight_keywords_ass(line1, keywords, base_fs)
    return (
        _highlight_keywords_ass(line1, keywords, base_fs)
        + r"\N"
        + _highlight_keywords_ass(line2, keywords, base_fs)
    )


def _run(cmd: list[str], *, cwd: str | None = None) -> None:
    p = subprocess.run(cmd, capture_output=True, text=True, cwd=cwd)
    if p.returncode != 0:
        logger.error("Command failed: {}", " ".join(cmd))
        logger.error("stderr: {}", p.stderr)
        raise RuntimeError(p.stderr or "ffmpeg/ffprobe failed")


def _ffprobe(path: str) -> dict:
    r = subprocess.run(
        [
            "ffprobe",
            "-v",
            "quiet",
            "-print_format",
            "json",
            "-show_format",
            "-show_streams",
            path,
        ],
        capture_output=True,
        text=True,
        check=True,
    )
    return json.loads(r.stdout)


def _video_audio_meta(path: str) -> tuple[int, int, float, float | None]:
    data = _ffprobe(path)
    dur = float(data.get("format", {}).get("duration", 0) or 0)
    w, h = 1080, 1920
    fps = 30.0
    for s in data.get("streams", []):
        if s.get("codec_type") == "video":
            w = int(s.get("width", w))
            h = int(s.get("height", h))
            afr = s.get("avg_frame_rate") or s.get("r_frame_rate")
            if afr and isinstance(afr, str) and "/" in afr:
                num, den = afr.split("/")
                try:
                    fps = float(num) / float(den)
                except (ValueError, ZeroDivisionError):
                    pass
            break
    return w, h, dur, fps


def _has_audio(path: str) -> bool:
    data = _ffprobe(path)
    return any(s.get("codec_type") == "audio" for s in data.get("streams", []))


def _extract_audio_wav(video: str, wav_out: str) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video,
            "-vn",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            wav_out,
        ]
    )


def _ensure_ding_wav(out_path: str) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-f",
            "lavfi",
            "-i",
            "sine=frequency=880:duration=0.09",
            "-af",
            "afade=t=in:st=0:d=0.02,afade=t=out:st=0.05:d=0.04",
            "-acodec",
            "pcm_s16le",
            "-ar",
            "48000",
            "-ac",
            "2",
            out_path,
        ]
    )


def _extract_keywords(script: str, max_kw: int = 14) -> list[str]:
    if not script or not script.strip():
        return []
    text = script.strip()
    quoted = re.findall(r"[「『](.+?)[」』]", text)
    quoted += re.findall(r'"([^"]{2,})"', text)
    quoted += re.findall(r"'([^']{2,})'", text)
    parts = re.split(r"[\s，。、；：,.!?！？\n\r\t]+", text)
    cand: list[str] = []
    for q in quoted:
        q = q.strip()
        if len(q) >= 2:
            cand.append(q)
    for p in parts:
        p = p.strip()
        if len(p) >= 2 and re.search(r"[\u4e00-\u9fffA-Za-z0-9]", p):
            cand.append(p)
    cand.sort(key=len, reverse=True)
    seen: set[str] = set()
    out: list[str] = []
    for c in cand:
        key = c.lower()
        if key in seen:
            continue
        seen.add(key)
        out.append(c)
        if len(out) >= max_kw:
            break
    return out


def _escape_ass_literal(ch: str) -> str:
    if ch in "{}\\":
        return "\\" + ch
    return ch


def _ass_escape_text(s: str) -> str:
    return "".join(_escape_ass_literal(c) for c in s.replace("\r", "").replace("\n", "\\N"))


def _highlight_keywords_ass(text: str, keywords: list[str], base_fs: int) -> str:
    if not text:
        return ""
    hi_fs = min(base_fs + max(2, base_fs // 5), base_fs + 9)
    keys = [k for k in keywords if k and k in text]
    if not keys:
        return _ass_escape_text(text)
    keys.sort(key=len, reverse=True)
    pattern = "|".join(re.escape(k) for k in keys)
    parts = re.split(f"({pattern})", text)
    chunks: list[str] = []
    for p in parts:
        if not p:
            continue
        if p in keys:
            chunks.append(
                f"{{\\c&H0000FFFF&\\fs{hi_fs}\\b1}}"
                f"{_ass_escape_text(p)}"
                f"{{\\r}}"
            )
        else:
            chunks.append(_ass_escape_text(p))
    return "".join(chunks)


def _format_ass_time(seconds: float) -> str:
    if seconds < 0:
        seconds = 0
    h = int(seconds // 3600)
    m = int((seconds % 3600) // 60)
    s = seconds - h * 3600 - m * 60
    sec_i = int(s)
    cs = int(round((s - sec_i) * 100))
    if cs >= 100:
        sec_i += 1
        cs = 0
        if sec_i >= 60:
            sec_i = 0
            m += 1
            if m >= 60:
                m = 0
                h += 1
    return f"{h:d}:{m:02d}:{sec_i:02d}.{cs:02d}"


def _write_ass(
    path: str,
    width: int,
    height: int,
    events: list[tuple[float, float, str]],
    style: dict[str, Any] | None = None,
) -> None:
    sm = style if style is not None else _subtitle_metrics(width, height)
    base_fs = int(sm["base_fs"])
    margin_v = int(sm["margin_v"])
    outline = int(sm["outline"])
    shadow = int(sm["shadow"])
    font = str(sm.get("fontname") or "Microsoft YaHei")
    primary_c = str(sm.get("primary_colour") or "&H00FFFFFF")
    outline_c = str(sm.get("outline_colour") or "&H00000000")

    header = f"""[Script Info]
ScriptType: v4.00+
PlayResX: {width}
PlayResY: {height}
ScaledBorderAndShadow: yes

[V4+ Styles]
Format: Name, Fontname, Fontsize, PrimaryColour, SecondaryColour, OutlineColour, BackColour, Bold, Italic, Underline, StrikeOut, ScaleX, ScaleY, Spacing, Angle, BorderStyle, Outline, Shadow, Alignment, MarginL, MarginR, MarginV, Encoding
Style: Default,{font},{base_fs},{primary_c},&H000000FF,{outline_c},&H80000000,-1,0,0,0,100,100,0,0,1,{outline},{shadow},2,24,24,{margin_v},1

[Events]
Format: Layer, Start, End, Style, Name, MarginL, MarginR, MarginV, Effect, Text
"""
    lines = [header]
    for start, end, body in events:
        lines.append(
            f"Dialogue: 0,{_format_ass_time(start)},{_format_ass_time(end)},Default,,0,0,0,,{body}\n"
        )
    Path(path).write_text("".join(lines), encoding="utf-8")


def _transcribe_segments(wav_path: str, model_name: str) -> list[tuple[float, float, str]]:
    try:
        from faster_whisper import WhisperModel
    except ImportError as e:
        raise RuntimeError("需要 faster-whisper 依赖，请使用 uv sync / pip install。") from e

    _configure_hf_for_download()
    device = "cuda" if os.environ.get("PIXELLE_WHISPER_DEVICE") == "cuda" else "cpu"
    compute_type = os.environ.get("PIXELLE_WHISPER_COMPUTE", "int8")
    download_root = (os.environ.get("PIXELLE_WHISPER_DOWNLOAD_ROOT") or "").strip() or None
    local_only = os.environ.get("PIXELLE_WHISPER_LOCAL_ONLY", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )

    model = None
    last_err: Exception | None = None
    for attempt in range(5):
        try:
            logger.info(
                "Whisper loading model={} device={} attempt={}/5",
                model_name,
                device,
                attempt + 1,
            )
            model = WhisperModel(
                model_name,
                device=device,
                compute_type=compute_type,
                download_root=download_root,
                local_files_only=local_only,
            )
            break
        except Exception as e:
            last_err = e
            logger.warning("Whisper 模型加载失败 ({}/5): {}", attempt + 1, e)
            if attempt < 4:
                time.sleep(12 + attempt * 8)

    if model is None:
        assert last_err is not None
        raise last_err
    beam = max(1, int(os.environ.get("PIXELLE_WHISPER_BEAM_SIZE", "1")))
    best = max(1, int(os.environ.get("PIXELLE_WHISPER_BEST_OF", "1")))
    cond_prev = os.environ.get("PIXELLE_WHISPER_CONDITION_PREV", "").strip().lower() in (
        "1",
        "true",
        "yes",
    )
    segments, _info = model.transcribe(
        wav_path,
        language=os.environ.get("PIXELLE_WHISPER_LANG") or None,
        word_timestamps=True,
        vad_filter=True,
        beam_size=beam,
        best_of=best,
        condition_on_previous_text=cond_prev,
    )
    return _whisper_time_chunks(list(segments))


def _whisper_time_chunks(segments: list) -> list[tuple[float, float, str]]:
    """用词级时间轴切成多行字幕，跟随语速切换。"""
    out: list[tuple[float, float, str]] = []
    for seg in segments:
        text = (seg.text or "").strip()
        if not text:
            continue
        words = getattr(seg, "words", None)
        if not words:
            out.append((float(seg.start), float(seg.end), text))
            continue
        buf: list[str] = []
        t_start = float(words[0].start)
        t_end = float(words[0].end)
        char_run = 0
        for idx, wd in enumerate(words):
            piece = wd.word or ""
            wtxt = piece.strip()
            if not wtxt:
                continue
            if not buf:
                t_start = float(wd.start)
            buf.append(piece)
            t_end = float(wd.end)
            char_run += len(wtxt)
            gap = 999.0
            if idx + 1 < len(words):
                gap = float(words[idx + 1].start) - float(wd.end)
            if char_run >= 14 or gap > 0.32 or idx == len(words) - 1:
                merged = "".join(buf).strip()
                if merged:
                    out.append((t_start, t_end, merged))
                buf = []
                char_run = 0
    if not out:
        for seg in segments:
            t = (seg.text or "").strip()
            if t:
                out.append((float(seg.start), float(seg.end), t))
    return out


def _merge_adjacent_intervals(iv: list[tuple[float, float]]) -> list[tuple[float, float]]:
    if not iv:
        return []
    iv = sorted(iv)
    out = [iv[0]]
    for s, e in iv[1:]:
        ps, pe = out[-1]
        if s <= pe + 0.08:
            out[-1] = (ps, max(pe, e))
        else:
            out.append((s, e))
    return out


def _speech_intervals_from_wav(wav_path: str, duration: float) -> list[tuple[float, float]] | None:
    """不用 Whisper：从音量静音段反推「有人在说话」的时间段，用来对齐字幕切换。"""
    try:
        p = subprocess.run(
            [
                "ffmpeg",
                "-nostats",
                "-i",
                wav_path,
                "-af",
                "silencedetect=noise=-34dB:d=0.22",
                "-f",
                "null",
                "-",
            ],
            capture_output=True,
            text=True,
            timeout=max(90.0, duration + 45.0),
        )
    except Exception as e:
        logger.warning("silencedetect 调用失败: {}", e)
        return None
    err = (p.stderr or "") + (p.stdout or "")
    silence: list[tuple[float, float]] = []
    cur: float | None = None
    for line in err.splitlines():
        m1 = re.search(r"silence_start:\s*([\d.]+)", line)
        if m1:
            cur = float(m1.group(1))
        m2 = re.search(r"silence_end:\s*([\d.]+)", line)
        if m2 and cur is not None:
            silence.append((cur, float(m2.group(1))))
            cur = None
    if not silence:
        return None
    silence.sort()
    speech: list[tuple[float, float]] = []
    t = 0.0
    for a, b in silence:
        if a > t + 0.04:
            speech.append((t, min(a, duration)))
        t = max(t, b)
    if t < duration - 0.04:
        speech.append((t, duration))
    speech = [(s, e) for s, e in speech if e - s > 0.1]
    return speech or None


def _split_script_into_lines(script: str) -> list[str]:
    s = (script or "").strip()
    if not s:
        return []
    parts = re.split(r"(?<=[。！？!?…])\s+|(?<=[；;])\s+|\n+", s)
    parts = [p.strip() for p in parts if p.strip()]
    if len(parts) <= 1 and len(s) > 18:
        sub = re.split(r"[，,、]+\s*", s)
        sub = [x.strip() for x in sub if x.strip()]
        parts = sub if len(sub) > 1 else []
        if not parts:
            parts = [s[i : i + 16].strip() for i in range(0, len(s), 16)]
            parts = [x for x in parts if x]
    return parts if parts else [s]


def _balance_parts_and_intervals(
    parts: list[str],
    intervals: list[tuple[float, float]],
    duration: float,
) -> tuple[list[str], list[tuple[float, float]]]:
    iv = [(max(0.0, s), min(duration, e)) for s, e in intervals if e - s > 0.06]
    iv = _merge_adjacent_intervals(iv)
    if not iv:
        return parts, []
    while len(iv) > len(parts) and len(iv) > 1:
        best = min(
            range(len(iv) - 1),
            key=lambda i: (iv[i + 1][1] - iv[i][0]),
        )
        iv = iv[:best] + [(iv[best][0], iv[best + 1][1])] + iv[best + 2 :]
    ps = parts[:]
    while len(ps) > len(iv) and len(ps) > 1:
        best = min(range(len(ps) - 1), key=lambda i: len(ps[i]) + len(ps[i + 1]))
        ps = ps[:best] + [ps[best] + ps[best + 1]] + ps[best + 2 :]
    m = min(len(ps), len(iv))
    return ps[:m], iv[:m]


def _proportional_timed_lines(
    duration: float,
    parts: list[str],
    keywords: list[str],
    base_fs: int,
    video_width: int,
) -> list[tuple[float, float, str]]:
    usable = max(0.25, duration - 0.12)
    weights = [max(1, len(p)) for p in parts]
    tw = sum(weights)
    events: list[tuple[float, float, str]] = []
    t = 0.04
    for i, line in enumerate(parts):
        seg = max(0.26, usable * (weights[i] / tw))
        end = min(duration - 0.02, t + seg)
        if i == len(parts) - 1:
            end = max(end, min(duration - 0.02, duration))
        events.append((t, end, _subtitle_body_wrapped(line, keywords, base_fs, video_width)))
        t = min(duration - 0.05, end + 0.015)
    return events


def _fallback_segmented_subtitles(
    duration: float,
    script: str,
    keywords: list[str],
    base_fs: int,
    wav_path: str | None,
    video_width: int,
) -> list[tuple[float, float, str]]:
    parts = _split_script_into_lines(script)
    if not parts:
        return _fallback_single_subtitle(duration, script, keywords, base_fs, video_width)

    intervals = None
    if wav_path and os.path.isfile(wav_path) and duration > 0.25:
        intervals = _speech_intervals_from_wav(wav_path, duration)

    if intervals:
        parts_m, iv_m = _balance_parts_and_intervals(parts, intervals, duration)
        if iv_m and parts_m:
            events = []
            for (s, e), line in zip(iv_m, parts_m):
                s = max(0.0, min(s, duration - 0.08))
                e = max(s + 0.18, min(e, duration))
                events.append(
                    (s, e, _subtitle_body_wrapped(line, keywords, base_fs, video_width))
                )
            return events

    return _proportional_timed_lines(duration, parts, keywords, base_fs, video_width)


def _fallback_single_subtitle(
    duration: float,
    script: str,
    keywords: list[str],
    base_fs: int,
    video_width: int,
) -> list[tuple[float, float, str]]:
    raw = (script or "").strip()
    display = raw if raw else "（口播配乐）"
    body = _subtitle_body_wrapped(display, keywords, base_fs, video_width)
    end = max(0.5, duration - 0.05)
    return [(0.05, end, body)]


def _overlay_pip(main_video: str, pip_video: str, out_path: str) -> None:
    w, h, _dur, mfps = _video_audio_meta(main_video)
    fps_v = max(15, min(60, int(round(mfps or 30))))
    pip_w = max(2, int(w * 0.22) // 2 * 2)
    x = max(8, w - pip_w - 20)
    y = 20
    flt = (
        f"[1:v]scale={pip_w}:-2,setsar=1,fps={fps_v}[pip];"
        f"[0:v][pip]overlay={x}:{y}:shortest=1[outv]"
    )
    cmd = [
        "ffmpeg",
        "-y",
        "-i",
        main_video,
        "-stream_loop",
        "-1",
        "-i",
        pip_video,
        "-filter_complex",
        flt,
        "-map",
        "[outv]",
        "-map",
        "0:a?",
        "-c:v",
        "libx264",
        *_post_encode_video_args(),
        "-c:a",
        "copy",
        out_path,
    ]
    _run(cmd)


def _mix_sfx(main_wav: str, ding_wav: str, times: list[float], out_wav: str) -> None:
    if not times:
        shutil.copy2(main_wav, out_wav)
        return
    dur_probe = _ffprobe(main_wav)
    main_dur = float(dur_probe.get("format", {}).get("duration", 0) or 0)
    inputs = [["-i", main_wav]]
    for _ in times:
        inputs.append(["-i", ding_wav])
    flat: list[str] = ["ffmpeg", "-y"]
    for part in inputs:
        flat.extend(part)
    n = len(times) + 1
    chains: list[str] = []
    mix_refs = ["[0:a]"]
    for i, t in enumerate(times):
        idx = i + 1
        delay = max(0, int(t * 1000))
        tag = f"d{i}"
        chains.append(f"[{idx}:a]adelay={delay}|{delay}[{tag}]")
        mix_refs.append(f"[{tag}]")
    mix = "".join(mix_refs) + f"amix=inputs={n}:duration=first:dropout_transition=0[aout]"
    chains.append(mix)
    fc = ";".join(chains)
    flat.extend(["-filter_complex", fc, "-map", "[aout]", "-acodec", "pcm_s16le", out_wav])
    _run(flat)


def _mux_video_audio(video: str, audio_wav: str, out_mp4: str) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            video,
            "-i",
            audio_wav,
            "-map",
            "0:v:0",
            "-map",
            "1:a:0",
            "-c:v",
            "copy",
            "-c:a",
            "aac",
            "-b:a",
            "192k",
            "-shortest",
            out_mp4,
        ]
    )


def _burn_ass(video: str, ass_path: str, out_mp4: str) -> None:
    """Burn ASS into video. FFmpeg 8+ libass: must use ass=filename=... — bare ass=subs.ass misparses «subs» as an option."""
    ass_abs = Path(ass_path).resolve()
    work_dir = str(ass_abs.parent)
    sub_name = ass_abs.name
    video_abs = str(Path(video).resolve())
    out_abs = str(Path(out_mp4).resolve())

    def _cmd_ass(vf: str) -> list[str]:
        return [
            "ffmpeg",
            "-y",
            "-i",
            video_abs,
            "-vf",
            vf,
            "-c:v",
            "libx264",
            *_post_encode_video_args(),
            "-c:a",
            "copy",
            out_abs,
        ]

    # Primary: explicit filename + cwd next to ASS (avoids Windows «F:» in filter string).
    vf_primary = f"ass=filename={sub_name}"
    try:
        _run(_cmd_ass(vf_primary), cwd=work_dir)
        return
    except RuntimeError as e_first:
        logger.warning("ass=filename=… failed, trying subtitles filter: {}", e_first)

    # Fallback: subtitles filter with escaped absolute path (handles some FFmpeg builds).
    p = ass_abs.as_posix()
    if len(p) >= 2 and p[1] == ":":
        p = p[0] + "\\:" + p[2:]
    p = p.replace("'", r"\'")
    vf_fallback = f"subtitles='{p}'"
    _run(_cmd_ass(vf_fallback), cwd=None)


def enhance_digital_human_video(
    input_video: str,
    task_dir: str,
    script_text: str,
    pip_video_path: str | None = None,
    *,
    whisper_model: str | None = None,
    subtitle_font: str | None = None,
    subtitle_font_size: int | None = None,
    subtitle_color_hex: str | None = None,
) -> str:
    """
    Run local post-enhance on the final digital-human MP4.
    Returns path to enhanced video (or original path on failure if caller handles — currently raises).
    """
    if not shutil.which("ffmpeg") or not shutil.which("ffprobe"):
        raise RuntimeError("未检测到 FFmpeg，请先安装并加入 PATH。")

    task_dir = str(Path(task_dir).resolve())
    os.makedirs(task_dir, exist_ok=True)
    work_base = Path(task_dir) / "_post_work"
    work_base.mkdir(parents=True, exist_ok=True)

    model = whisper_model or os.environ.get("PIXELLE_WHISPER_MODEL", "tiny")
    w, h, duration, _ = _video_audio_meta(input_video)
    style: dict[str, Any] = dict(_subtitle_metrics(w, h))
    if subtitle_font and str(subtitle_font).strip():
        style["fontname"] = str(subtitle_font).strip()
    if subtitle_font_size is not None and int(subtitle_font_size) > 0:
        fs = max(16, min(80, int(subtitle_font_size)))
        style["base_fs"] = fs
        style["outline"] = max(2, min(5, fs // 9))
        style["shadow"] = max(1, min(3, int(style["outline"]) - 1))
    pc = _hex_rgb_to_ass_primary(subtitle_color_hex)
    if pc:
        style["primary_colour"] = pc
        style["outline_colour"] = _outline_colour_for_primary_ass(pc)
    base_fs = int(style["base_fs"])
    keywords = _extract_keywords(script_text)

    wav = str(work_base / "speech.wav")
    if _has_audio(input_video):
        _extract_audio_wav(input_video, wav)
        try:
            raw_segs = _transcribe_segments(wav, model)
        except Exception as e:
            logger.warning("Whisper 失败，改用口播分段 + 音量对齐: {}", e)
            raw_segs = []
    else:
        raw_segs = []

    events: list[tuple[float, float, str]] = []
    if raw_segs:
        for a, b, txt in raw_segs:
            body = _subtitle_body_wrapped(txt, keywords, base_fs, w)
            events.append((a, b, body))
    elif script_text.strip():
        wav_use = wav if _has_audio(input_video) and os.path.isfile(wav) else None
        events = _fallback_segmented_subtitles(
            duration, script_text, keywords, base_fs, wav_use, w
        )
    else:
        events = _fallback_single_subtitle(duration, script_text, keywords, base_fs, w)

    ass_file = str(work_base / "subs.ass")
    _write_ass(ass_file, w, h, events, style=style)

    video_after_pip = str(work_base / "after_pip.mp4")
    if pip_video_path and os.path.isfile(pip_video_path):
        logger.info("画中画: {}", pip_video_path)
        _overlay_pip(input_video, pip_video_path, video_after_pip)
        base_v = video_after_pip
    else:
        base_v = input_video

    sfx_times: list[float] = [0.08]
    if duration > 2.5:
        sfx_times.append(round(duration * 0.5, 2))
    max_extra = 5
    for a, _b, txt in (raw_segs or []):
        if len(sfx_times) >= max_extra:
            break
        if keywords and any(k in txt for k in keywords[:6]):
            if a > 0.2 and a not in sfx_times:
                sfx_times.append(round(a, 2))

    ding = str(work_base / "ding.wav")
    _ensure_ding_wav(ding)
    mixed = str(work_base / "mixed.wav")
    if _has_audio(base_v):
        _extract_audio_wav(base_v, wav)
        _mix_sfx(wav, ding, sfx_times, mixed)
        pre_ass = str(work_base / "pre_ass.mp4")
        _mux_video_audio(base_v, mixed, pre_ass)
    else:
        pre_ass = base_v

    out_final = str(Path(task_dir) / "final_enhanced.mp4")
    _burn_ass(pre_ass, ass_file, out_final)
    logger.info("增强成片: {}", out_final)
    return out_final


def enhance_digital_human_video_safe(
    input_video: str,
    task_dir: str,
    script_text: str,
    pip_video_path: str | None = None,
    *,
    whisper_model: str | None = None,
    subtitle_font: str | None = None,
    subtitle_font_size: int | None = None,
    subtitle_color_hex: str | None = None,
) -> str:
    """Same as enhance_digital_human_video but returns original file if anything fails."""
    try:
        return enhance_digital_human_video(
            input_video,
            task_dir,
            script_text,
            pip_video_path,
            whisper_model=whisper_model,
            subtitle_font=subtitle_font,
            subtitle_font_size=subtitle_font_size,
            subtitle_color_hex=subtitle_color_hex,
        )
    except Exception as e:
        logger.exception("成片增强失败，使用原始视频: {}", e)
        return input_video
