"""
Rumble Processor - Download videos and transcribe with Whisper

Uses yt-dlp which has native Rumble support.
Supports both local Whisper and RunPod serverless transcription.
"""

from __future__ import annotations

import asyncio
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import AsyncIterator

import yt_dlp

from app.config import config, TRANSCRIPTS_DIR

logger = logging.getLogger(__name__)


@dataclass
class RumbleVideoInfo:
    """Information about a Rumble video."""
    video_id: str
    title: str
    channel_id: str
    channel_name: str
    channel_url: str
    description: str
    duration: int  # seconds
    upload_date: str
    view_count: int
    thumbnail_url: str | None


@dataclass
class TranscriptResult:
    """Result of video transcription."""
    video_id: str
    title: str
    text: str
    language: str | None
    duration: float
    word_count: int


def is_rumble_url(url: str) -> bool:
    """Check if URL is a Rumble URL."""
    return 'rumble.com' in url.lower()


def extract_rumble_video_id(url: str) -> str | None:
    """
    Extract video ID from Rumble URL.

    Rumble video URLs look like:
    - https://rumble.com/v4abc123-video-title.html
    - https://rumble.com/embed/v4abc123/
    """
    patterns = [
        r'rumble\.com\/v([a-zA-Z0-9]+)',  # Standard video URL
        r'rumble\.com\/embed\/v([a-zA-Z0-9]+)',  # Embed URL
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return f"v{match.group(1)}"
    return None


def extract_rumble_channel_id(url: str) -> str | None:
    """
    Extract channel/user identifier from Rumble URL.

    Rumble channel URLs look like:
    - https://rumble.com/c/ChannelName
    - https://rumble.com/user/Username
    """
    patterns = [
        r'rumble\.com\/c\/([a-zA-Z0-9_-]+)',  # Channel URL
        r'rumble\.com\/user\/([a-zA-Z0-9_-]+)',  # User URL
    ]

    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


def _get_yt_dlp_opts(extract_info_only: bool = True) -> dict:
    """Get yt-dlp options for Rumble."""
    opts = {
        'quiet': True,
        'no_warnings': True,
        'extract_flat': extract_info_only,
        'ignoreerrors': True,
    }

    if not extract_info_only:
        opts.update({
            'format': 'bestaudio/best',
            'postprocessors': [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': 'mp3',
                'preferredquality': '192',
            }],
            'extract_flat': False,
        })

    return opts


async def get_video_info(url: str) -> RumbleVideoInfo | None:
    """Get information about a single Rumble video."""
    video_id = extract_rumble_video_id(url)
    if not video_id:
        # Try to extract info anyway (yt-dlp might handle it)
        pass

    opts = _get_yt_dlp_opts(extract_info_only=True)
    opts['extract_flat'] = False

    def _extract():
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(url, download=False)
                if info:
                    return RumbleVideoInfo(
                        video_id=info.get('id', video_id or 'unknown'),
                        title=info.get('title', 'Unknown'),
                        channel_id=info.get('channel_id', ''),
                        channel_name=info.get('channel', info.get('uploader', 'Unknown')),
                        channel_url=info.get('channel_url', info.get('uploader_url', '')),
                        description=info.get('description', ''),
                        duration=info.get('duration', 0) or 0,
                        upload_date=info.get('upload_date', ''),
                        view_count=info.get('view_count', 0) or 0,
                        thumbnail_url=info.get('thumbnail'),
                    )
            except Exception as e:
                print(f"Error extracting Rumble video info: {e}")
        return None

    return await asyncio.to_thread(_extract)


async def get_channel_info(channel_url: str) -> dict | None:
    """Get information about a Rumble channel."""
    opts = _get_yt_dlp_opts(extract_info_only=True)

    def _extract():
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(channel_url, download=False)
                if info:
                    return {
                        'channel_id': info.get('channel_id') or info.get('id', ''),
                        'channel_name': info.get('channel') or info.get('uploader', 'Unknown'),
                        'channel_url': info.get('channel_url') or info.get('webpage_url') or channel_url,
                        'description': info.get('description', ''),
                        'subscriber_count': info.get('channel_follower_count', 0),
                    }
            except Exception as e:
                print(f"Error extracting Rumble channel info: {e}")
        return None

    return await asyncio.to_thread(_extract)


async def list_channel_videos(
    channel_url: str,
    limit: int | None = None,
    after_video_id: str | None = None,
) -> list[RumbleVideoInfo]:
    """List videos from a Rumble channel."""
    opts = _get_yt_dlp_opts(extract_info_only=True)

    def _extract():
        videos = []
        found_after = after_video_id is None

        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                info = ydl.extract_info(channel_url, download=False)
                if info and 'entries' in info:
                    for entry in info['entries']:
                        if entry is None:
                            continue

                        video_id = entry.get('id', '')

                        # Skip entries without valid video_id
                        if not video_id:
                            continue

                        # Skip until we find the after_video_id
                        if not found_after:
                            if video_id == after_video_id:
                                found_after = True
                            continue

                        videos.append(RumbleVideoInfo(
                            video_id=video_id,
                            title=entry.get('title', 'Unknown'),
                            channel_id=info.get('channel_id', ''),
                            channel_name=info.get('channel', info.get('uploader', 'Unknown')),
                            channel_url=info.get('channel_url', info.get('webpage_url', '')),
                            description=entry.get('description', ''),
                            duration=entry.get('duration', 0) or 0,
                            upload_date=entry.get('upload_date', ''),
                            view_count=entry.get('view_count', 0) or 0,
                            thumbnail_url=entry.get('thumbnail'),
                        ))

                        if limit and len(videos) >= limit:
                            break
            except Exception as e:
                print(f"Error listing Rumble channel videos: {e}")

        return videos

    return await asyncio.to_thread(_extract)


async def download_audio(video_url: str, output_dir: Path | None = None) -> Path | None:
    """Download audio from a Rumble video."""
    if output_dir is None:
        output_dir = TRANSCRIPTS_DIR

    output_dir.mkdir(parents=True, exist_ok=True)

    video_id = extract_rumble_video_id(video_url)
    if not video_id:
        # Generate a unique ID from the URL
        import hashlib
        video_id = hashlib.md5(video_url.encode()).hexdigest()[:12]

    output_template = str(output_dir / f"rumble_{video_id}.%(ext)s")

    opts = _get_yt_dlp_opts(extract_info_only=False)
    opts['outtmpl'] = output_template

    def _download():
        with yt_dlp.YoutubeDL(opts) as ydl:
            try:
                ydl.download([video_url])
                # Find the output file
                for ext in ['mp3', 'wav', 'm4a', 'webm', 'opus']:
                    output_path = output_dir / f"rumble_{video_id}.{ext}"
                    if output_path.exists():
                        return output_path
            except Exception as e:
                print(f"Error downloading Rumble audio: {e}")
        return None

    return await asyncio.to_thread(_download)


async def transcribe_audio(
    audio_path: Path,
    language: str | None = None,
    job_id: int | None = None,
) -> dict | None:
    """
    Transcribe audio file using Whisper or RunPod.

    Args:
        audio_path: Path to the audio file
        language: Language code or None for auto-detect
        job_id: Optional job ID for RunPod URL building

    Returns:
        Dict with text, language, duration, word_count or None on failure
    """
    # Check if RunPod is configured and job_id is provided
    if config.runpod.is_configured and job_id is not None:
        return await _transcribe_with_runpod(audio_path, language, job_id)
    else:
        return await _transcribe_with_local_whisper(audio_path, language)


async def _transcribe_with_runpod(
    audio_path: Path,
    language: str | None,
    job_id: int,
) -> dict | None:
    """Transcribe using RunPod serverless GPU."""
    from app.services.runpod_whisper import (
        transcribe_audio_runpod,
        build_audio_url,
        RunPodWhisperError,
    )

    try:
        # Build the public URL for RunPod to fetch the audio
        filename = audio_path.name
        audio_url = build_audio_url(job_id, filename)

        logger.info(f"Submitting Rumble audio to RunPod: job_id={job_id}, file={filename}")

        # Transcribe using RunPod
        result = await transcribe_audio_runpod(audio_url, language)

        logger.info(f"RunPod transcription completed: {result.word_count} words, {result.duration:.1f}s")

        return {
            'text': result.text,
            'language': result.language,
            'duration': result.duration,
            'word_count': result.word_count,
        }

    except RunPodWhisperError as e:
        logger.error(f"RunPod transcription failed: {e}")
        # Fall back to local Whisper if RunPod fails
        logger.info("Falling back to local Whisper transcription")
        return await _transcribe_with_local_whisper(audio_path, language)
    except Exception as e:
        logger.error(f"Unexpected error in RunPod transcription: {e}")
        return None


async def _transcribe_with_local_whisper(
    audio_path: Path,
    language: str | None,
) -> dict | None:
    """Transcribe using local Whisper model."""
    import whisper

    # Get whisper config
    model_size = config.whisper.model_size
    device = config.whisper.device

    if device == "auto":
        import torch
        device = "cuda" if torch.cuda.is_available() else "cpu"

    def _transcribe():
        try:
            model = whisper.load_model(model_size, device=device)

            result = model.transcribe(
                str(audio_path),
                language=language,
                task="transcribe",
            )

            text = result.get('text', '').strip()
            detected_lang = result.get('language')

            # Calculate word count
            word_count = len(text.split())

            # Get duration from segments
            segments = result.get('segments', [])
            duration = segments[-1]['end'] if segments else 0

            return {
                'text': text,
                'language': detected_lang,
                'duration': duration,
                'word_count': word_count,
            }
        except Exception as e:
            logger.error(f"Local Whisper transcription error: {e}")
            return None

    return await asyncio.to_thread(_transcribe)


async def transcribe_video(
    video_url: str,
    language: str | None = None,
    keep_audio: bool = False,
    job_id: int | None = None,
) -> TranscriptResult | None:
    """
    Download and transcribe a Rumble video.

    Args:
        video_url: Rumble video URL
        language: Language code or None for auto-detect
        keep_audio: If True, keep the audio file after transcription
        job_id: Optional job ID for RunPod URL building

    Returns:
        TranscriptResult or None on failure
    """
    video_info = await get_video_info(video_url)
    if not video_info:
        return None

    # Download audio
    audio_path = await download_audio(video_url)
    if not audio_path:
        return None

    try:
        # Transcribe (will use RunPod if configured and job_id provided)
        result = await transcribe_audio(audio_path, language, job_id)

        if result:
            return TranscriptResult(
                video_id=video_info.video_id,
                title=video_info.title,
                text=result['text'],
                language=result['language'],
                duration=result['duration'],
                word_count=result['word_count'],
            )
    finally:
        # Clean up audio file if not keeping
        if not keep_audio and audio_path.exists():
            audio_path.unlink()

    return None


async def transcribe_channel_videos(
    channel_url: str,
    limit: int | None = None,
    after_video_id: str | None = None,
    language: str | None = None,
) -> AsyncIterator[tuple[RumbleVideoInfo, TranscriptResult | str]]:
    """
    Transcribe videos from a Rumble channel.

    Yields tuples of (RumbleVideoInfo, TranscriptResult) for successful transcriptions,
    or (RumbleVideoInfo, error_message) for failures.
    """
    videos = await list_channel_videos(channel_url, limit, after_video_id)

    for video in videos:
        video_url = get_video_url(video.video_id)

        try:
            result = await transcribe_video(video_url, language)
            if result:
                yield (video, result)
            else:
                yield (video, "Transcription failed")
        except Exception as e:
            yield (video, str(e))


def get_video_url(video_id: str) -> str:
    """Get the full Rumble URL for a video ID."""
    # Rumble video IDs typically start with 'v'
    if not video_id.startswith('v'):
        video_id = f"v{video_id}"
    return f"https://rumble.com/{video_id}"


def get_channel_url(channel_id: str) -> str:
    """Get the full Rumble URL for a channel ID."""
    return f"https://rumble.com/c/{channel_id}"
