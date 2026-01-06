#!/usr/bin/env python3
"""
Extract audio from MP4 video and name the MP3 file based on the first person's name.
"""

import os
import sys
import re
import subprocess
import logging
from pathlib import Path
from datetime import datetime

def check_ffmpeg():
    """Check if ffmpeg is installed."""
    try:
        subprocess.run(['ffmpeg', '-version'], 
                      capture_output=True, check=True)
        return True
    except (subprocess.CalledProcessError, FileNotFoundError):
        return False

def extract_audio_ffmpeg(video_path, output_path):
    """Extract audio from video using ffmpeg."""
    cmd = [
        'ffmpeg',
        '-i', video_path,
        '-vn',  # No video
        '-acodec', 'libmp3lame',  # MP3 codec
        '-ab', '128k',  # Audio bitrate (reduced for smaller file size)
        '-ar', '44100',  # Sample rate
        '-y',  # Overwrite output file
        output_path
    ]
    subprocess.run(cmd, check=True, capture_output=True)

def extract_audio_imageio_ffmpeg(video_path, output_path):
    """Extract audio from video using ffmpeg from imageio_ffmpeg."""
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    except ImportError:
        print("Error: imageio_ffmpeg not found. Installing...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'imageio-ffmpeg'], check=True)
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
    
    # Use ffmpeg to extract audio
    cmd = [
        ffmpeg_path,
        '-i', str(video_path),
        '-vn',  # No video
        '-acodec', 'libmp3lame',  # MP3 codec
        '-ab', '128k',  # Audio bitrate (reduced for smaller file size)
        '-ar', '44100',  # Sample rate
        '-y',  # Overwrite output file
        str(output_path)
    ]
    subprocess.run(cmd, check=True, capture_output=True)

def transcribe_audio(audio_path, model_dir=None):
    """Transcribe audio using whisper."""
    # Set up ffmpeg for whisper if available
    temp_ffmpeg_dir = None
    try:
        import imageio_ffmpeg
        ffmpeg_path = imageio_ffmpeg.get_ffmpeg_exe()
        # Create a temporary directory and symlink ffmpeg there
        import tempfile
        temp_ffmpeg_dir = tempfile.mkdtemp()
        # On Windows, preserve .exe extension; on Unix, use 'ffmpeg'
        if sys.platform == 'win32':
            ffmpeg_link = os.path.join(temp_ffmpeg_dir, 'ffmpeg.exe')
            import shutil
            shutil.copy(ffmpeg_path, ffmpeg_link)
        else:
            ffmpeg_link = os.path.join(temp_ffmpeg_dir, 'ffmpeg')
            os.symlink(ffmpeg_path, ffmpeg_link)
        # Add to PATH
        os.environ['PATH'] = temp_ffmpeg_dir + os.pathsep + os.environ.get('PATH', '')
    except Exception as e:
        print(f"Warning: Could not set up ffmpeg for whisper: {e}")
    
    try:
        import whisper
        # Use local model directory if provided
        if model_dir:
            model_dir.mkdir(exist_ok=True)
            model = whisper.load_model("base", download_root=str(model_dir))
        else:
            model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        # Clean up temp directory
        if temp_ffmpeg_dir and os.path.exists(temp_ffmpeg_dir):
            import shutil
            shutil.rmtree(temp_ffmpeg_dir)
        return result["text"]
    except ImportError:
        print("Error: whisper library not found. Installing...")
        subprocess.run([sys.executable, '-m', 'pip', 'install', 'openai-whisper'], check=True)
        import whisper
        # Use local model directory if provided
        if model_dir:
            model_dir.mkdir(exist_ok=True)
            model = whisper.load_model("base", download_root=str(model_dir))
        else:
            model = whisper.load_model("base")
        result = model.transcribe(audio_path)
        # Clean up temp directory
        if temp_ffmpeg_dir and os.path.exists(temp_ffmpeg_dir):
            import shutil
            shutil.rmtree(temp_ffmpeg_dir)
        return result["text"]
    except Exception as e:
        # Clean up temp directory on error
        if temp_ffmpeg_dir and os.path.exists(temp_ffmpeg_dir):
            import shutil
            shutil.rmtree(temp_ffmpeg_dir)
        raise

def find_first_name(text):
    """Find the first name mentioned in an introduction pattern."""
    # Focus on first 500 characters where introductions typically occur
    intro_text = text[:500] if len(text) > 500 else text
    
    # Common words to skip (expanded list)
    skip_words = {
        'The', 'This', 'That', 'There', 'Here', 'Hello', 'Hi', 'Hey', 'My', 'my', 'I', 'We', 'You',
        'Everybody', 'Everyone', 'Anyone', 'Someone', 'Something', 'Somewhere', 'Today',
        'Tomorrow', 'Yesterday', 'Now', 'Then', 'When', 'Where', 'What', 'Who', 'Why', 'How',
        'Video', 'Intro', 'Introduction', 'About', 'Me', 'Just', 'just', 'And', 'Or', 'But',
        'Senior', 'Junior', 'Sophomore', 'Freshman', 'Undergrad', 'Grad', 'Team', 'Year',
        'Been', 'Have', 'Has', 'Had', 'Was', 'Were', 'Is', 'Are', 'Am', 'Be', 'Being',
        'In', 'On', 'At', 'To', 'For', 'From', 'With', 'By', 'Of', 'As', 'An', 'A',
        'First', 'Last', 'Next', 'Previous', 'Current', 'New', 'Old', 'Good', 'Bad',
        'Little', 'Big', 'Many', 'Much', 'Some', 'Any', 'All', 'Each', 'Every', 'Both',
        'College', 'University', 'School', 'Semester', 'Class', 'Course', 'Shop', 'Two',
        'Raised', 'Born', 'From', 'Living', 'Working', 'Doing', 'Going', 'Getting'
    }
    
    # Create case-insensitive skip words set (once)
    skip_words_lower = {w.lower() for w in skip_words}
    
    # Priority patterns - these are most likely to contain a name
    # Search in intro_text only and return FIRST valid match
    priority_patterns = [
        (r"([A-Z][a-z]+)\s+here\b", 0),  # "[Name] here" pattern (most specific)
        (r"my\s+name\s+is\s+([A-Z][a-z]+)", 1),  # "my name is [Name]"
        (r"i\s+am\s+([A-Z][a-z]+)", 1),  # "I am [Name]"
        (r"i'm\s+([A-Z][a-z]+)", 1),  # "I'm [Name]"
        (r"this\s+is\s+([A-Z][a-z]+)", 1),  # "this is [Name]"
    ]
    
    # Try priority patterns first - return the FIRST valid match
    for pattern, group_idx in priority_patterns:
        match = re.search(pattern, intro_text, re.IGNORECASE)
        if match:
            name_part = match.group(group_idx) if match.groups() else match.group(0)
            if name_part:
                # Extract the first name (first word)
                name = name_part.split()[0]
                # Clean the name
                name = re.sub(r'[^\w]', '', name)
                # Check against skip_words (case-insensitive)
                if name and len(name) > 2 and name.lower() not in skip_words_lower:
                    # Additional validation: name should start with capital letter
                    if name[0].isupper():
                        return name
    
    # Last resort: look for capitalized words followed by another capitalized word in first 200 chars
    words = intro_text[:200].split()
    for i, word in enumerate(words[:15]):  # Check first 15 words only
        clean_word = re.sub(r'[^\w]', '', word)
        if clean_word and clean_word[0].isupper() and len(clean_word) > 2:
            if clean_word.lower() not in skip_words_lower:
                # Only return if followed by another capitalized word (likely a last name)
                if i + 1 < len(words):
                    next_word = re.sub(r'[^\w]', '', words[i + 1])
                    if next_word and next_word[0].isupper() and len(next_word) > 2:
                        if next_word.lower() not in skip_words_lower:
                            # This looks like a full name, return first name
                            return clean_word
    
    return None

def process_video(video_path, logger, model_dir=None):
    """Process a single video file and extract audio with name-based naming."""
    logger.info(f"Processing: {video_path.name}")
    print(f"\n{'='*60}")
    print(f"Processing: {video_path.name}")
    print(f"{'='*60}")
    
    # Create temporary MP3 file (unique per video)
    temp_mp3 = video_path.parent / f"temp_audio_{video_path.stem}.mp3"
    
    print("Extracting audio from video...")
    logger.info(f"Extracting audio from {video_path.name}")
    try:
        if check_ffmpeg():
            extract_audio_ffmpeg(str(video_path), str(temp_mp3))
        else:
            print("ffmpeg not found, using imageio_ffmpeg instead...")
            logger.info("Using imageio_ffmpeg for audio extraction")
            extract_audio_imageio_ffmpeg(str(video_path), str(temp_mp3))
        print(f"Audio extracted to: {temp_mp3}")
        logger.info(f"Audio extracted successfully to {temp_mp3.name}")
    except Exception as e:
        error_msg = f"Error extracting audio: {e}"
        print(error_msg)
        logger.error(f"{video_path.name}: {error_msg}")
        if temp_mp3.exists():
            temp_mp3.unlink()
        return False
    
    # Transcribe audio
    print("Transcribing audio to find name...")
    logger.info(f"Transcribing audio for {video_path.name}")
    try:
        transcription = transcribe_audio(str(temp_mp3), model_dir=model_dir)
        print(f"\nTranscription (first 500 chars):\n{transcription[:500]}...\n")
        logger.debug(f"Transcription preview: {transcription[:500]}")
    except Exception as e:
        error_msg = f"Error transcribing audio: {e}"
        print(error_msg)
        logger.error(f"{video_path.name}: {error_msg}")
        # Clean up temp file
        if temp_mp3.exists():
            temp_mp3.unlink()
        return False
    
    # Find name (only first name)
    name = find_first_name(transcription)
    
    if name:
        # Ensure we only use the first name (split and take first word)
        name = name.split()[0] if name else name
        # Clean name for filename (remove invalid characters)
        safe_name = re.sub(r'[^\w\s-]', '', name).strip()
        safe_name = re.sub(r'[-\s]+', '-', safe_name)
        final_mp3 = video_path.parent / f"{safe_name}.mp3"
        
        # Check if MP3 already exists
        if final_mp3.exists():
            msg = f"Skipping: {final_mp3.name} already exists"
            print(f"[SKIP] {msg}")
            logger.info(f"{video_path.name}: {msg}")
            # Clean up temp file
            if temp_mp3.exists():
                temp_mp3.unlink()
            return True
        
        # Rename temp file
        temp_mp3.rename(final_mp3)
        success_msg = f"Success! Created: {final_mp3.name} (Name found: {name})"
        print(f"[OK] {success_msg}")
        logger.info(f"{video_path.name}: {success_msg}")
    else:
        # Use default name if no name found
        final_mp3 = video_path.parent / "audio.mp3"
        
        # Check if MP3 already exists
        if final_mp3.exists():
            msg = f"Skipping: {final_mp3.name} already exists"
            print(f"[SKIP] {msg}")
            logger.info(f"{video_path.name}: {msg}")
            # Clean up temp file
            if temp_mp3.exists():
                temp_mp3.unlink()
            return True
        
        temp_mp3.rename(final_mp3)
        warning_msg = f"Could not find a name in the transcription. Created: {final_mp3.name}"
        print(f"[WARN] {warning_msg}")
        logger.warning(f"{video_path.name}: {warning_msg}")
    
    return True

def setup_logging(log_dir):
    """Set up logging to both file and console."""
    log_file = log_dir / f"extract_audio_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
    
    # Create logger
    logger = logging.getLogger('extract_audio')
    logger.setLevel(logging.DEBUG)
    
    # Remove existing handlers
    logger.handlers = []
    
    # File handler (detailed)
    file_handler = logging.FileHandler(log_file)
    file_handler.setLevel(logging.DEBUG)
    file_formatter = logging.Formatter('%(asctime)s - %(levelname)s - %(message)s')
    file_handler.setFormatter(file_formatter)
    logger.addHandler(file_handler)
    
    # Console handler (info and above)
    console_handler = logging.StreamHandler()
    console_handler.setLevel(logging.INFO)
    console_formatter = logging.Formatter('%(levelname)s - %(message)s')
    console_handler.setFormatter(console_formatter)
    logger.addHandler(console_handler)
    
    return logger, log_file

def main():
    # Get the directory of this script
    script_dir = Path(__file__).parent
    
    # Create models directory for local Whisper model storage
    models_dir = script_dir / "models"
    models_dir.mkdir(exist_ok=True)
    
    # Set up logging
    logger, log_file = setup_logging(script_dir)
    logger.info("="*60)
    logger.info("Audio Extraction Script Started")
    logger.info(f"Working directory: {script_dir}")
    logger.info(f"Model directory: {models_dir}")
    logger.info(f"Log file: {log_file.name}")
    logger.info("="*60)
    
    # Find all MP4 video files in the directory
    video_files = list(script_dir.glob("*.mp4"))
    
    if not video_files:
        msg = "No MP4 video files found in the directory."
        print(msg)
        logger.warning(msg)
        sys.exit(1)
    
    print(f"Found {len(video_files)} video file(s) to process.\n")
    logger.info(f"Found {len(video_files)} video file(s) to process")
    
    # Process each video file
    successful = 0
    skipped = 0
    failed = 0
    
    for video_path in sorted(video_files):
        try:
            result = process_video(video_path, logger, model_dir=models_dir)
            if result:
                successful += 1
            else:
                failed += 1
        except Exception as e:
            error_msg = f"Error processing {video_path.name}: {e}"
            print(error_msg)
            logger.error(error_msg, exc_info=True)
            failed += 1
    
    # Summary
    summary = f"Processing complete! Successful: {successful}, Failed: {failed}"
    print(f"\n{'='*60}")
    print(summary)
    print(f"{'='*60}")
    logger.info("="*60)
    logger.info(summary)
    logger.info(f"Log file saved to: {log_file}")
    logger.info("="*60)

if __name__ == "__main__":
    main()

