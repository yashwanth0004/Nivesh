import os
import sys
import io
import time
import re
from pathlib import Path
import numpy as np
import sounddevice as sd
import sherpa_onnx
from download_models import ensure_speech_model

# Import keyboard hook based on Operating System
if sys.platform == "win32":
    import msvcrt
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
else:
    import select
    import tty
    import termios

def check_quit_key():
    """Checks if the user pressed the 'q' key to stop the program."""
    if sys.platform == "win32":
        if msvcrt.kbhit():
            return msvcrt.getch().decode('utf-8', errors='ignore').lower() == 'q'
    else:
        # Non-blocking check for Linux/macOS terminal
        dr, dw, de = select.select([sys.stdin], [], [], 0)
        if dr:
            return sys.stdin.read(1).lower() == 'q'
    return False

def clean_and_format_text(text):
    """Converts raw token segments into highly readable spaced layouts."""
    if not text:
        return ""
    text = text.replace(" ", " ").replace("▁", " ")
    text = re.sub(r'([a-zA-Z]+)([^a-zA-Z\s])', r'\1 \2', text)
    text = re.sub(r'([^a-zA-Z\s])([a-zA-Z]+)', r'\1 \2', text)
    return " ".join(text.split())

def main():
    language_code = input("Enter language folder name (e.g., te, hi): ").strip().lower()
    
    try:
        model_path, tokens_path = ensure_speech_model(language_code, Path(__file__).resolve().parent)
    except Exception as exc:
        print(f"\n[ERROR] Could not prepare the speech model: {exc}")
        return

    print(f"\n[RAM Footprint ~300MB] Loading [{language_code.upper()}] engine...")
    recognizer = sherpa_onnx.OfflineRecognizer.from_nemo_ctc(
        model=str(model_path),
        tokens=str(tokens_path),
        num_threads=4,
        decoding_method="greedy_search",
        debug=False
    )
    print("Model initialized successfully!")

    # Audio Stream Parameters
    sample_rate = 16000
    block_size = 1600  # 100ms chunks
    
    # VAD Tweak Variables (You can adjust these based on background noise)
    VAD_THRESHOLD = 0.008      # Amplitude below this is considered silence
    SILENCE_DURATION = 1.0     # Time in seconds to wait before transcribing
    
    # State tracking metrics stored entirely in RAM
    audio_buffer = []
    is_speaking = False
    silence_start_time = None
    
    print("\n" + "="*60)
    print(">>> SPEAK NOW (System is listening...)")
    print(">>> Press the 'q' key followed by Enter to STOP completely.")
    print("="*60 + "\n")

    # Setup non-blocking terminal mode for Unix-like systems if applicable
    old_settings = None
    if sys.platform != "win32":
        old_settings = termios.tcgetattr(sys.stdin)
        tty.setcbreak(sys.stdin.fileno())

    try:
        # Open continuous audio input capture layer directly into your system RAM
        with sd.InputStream(samplerate=sample_rate, channels=1, dtype='float32', blocksize=block_size) as input_stream:
            while True:
                # 1. Periodically check if user requested to stop the loop
                if check_quit_key():
                    print("\n'q' pressed. Ending transcription engine.")
                    break
                
                # 2. Read raw micro-buffer from input stream into RAM
                samples, overflowed = input_stream.read(block_size)
                samples = samples.flatten()
                
                # Compute current audio energy (volume level) using Root Mean Square
                rms = np.sqrt(np.mean(samples**2)) if len(samples) > 0 else 0
                
                if rms > VAD_THRESHOLD:
                    # User is actively speaking
                    if not is_speaking:
                        is_speaking = True
                    audio_buffer.extend(samples.tolist())
                    silence_start_time = None  # Reset silence timer
                else:
                    # Silence detected in this slice
                    if is_speaking:
                        audio_buffer.extend(samples.tolist())
                        if silence_start_time == None:
                            silence_start_time = time.time()
                        
                        # Check if silence has lasted longer than our threshold window
                        if time.time() - silence_start_time >= SILENCE_DURATION:
                            # User stopped speaking! Trigger offline core directly from RAM buffer
                            #te
                            # print("\n[Processing speech...]", end="", flush=True)
                            
                            stream = recognizer.create_stream()
                            stream.accept_waveform(16000.0, audio_buffer)
                            recognizer.decode_stream(stream)
                            
                            final_text = clean_and_format_text(stream.result.text)
                            
                            if final_text.strip():
                                print(f" {final_text}")
                            #else:
                            #    print("\r[Silent pause ignored]")
                                
                            # Reset buffers and state variables for next sentence pool
                            audio_buffer = []
                            is_speaking = False
                            silence_start_time = None
                            #te
                            # print(">>> Listening again...\n")
                            
                # Sleep briefly to free up CPU execution cycles
                time.sleep(0.01)

    except Exception as e:
        print(f"\n[Runtime Error]: {e}")
    finally:
        # Clean terminal input state if running on Unix systems
        if old_settings:
            termios.tcsetattr(sys.stdin, termios.TCSADRAIN, old_settings)

if __name__ == "__main__":
    main()
