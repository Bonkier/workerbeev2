import os
import time
import logging
import threading
import subprocess
import sys

try:
    import shared_vars
except ImportError:
    # v1 sets up a runtime `shared_vars` namespace; the v2 UI does not.
    # Audio only reads `disable_audio` from it (via getattr with a
    # default), so a missing module just means "audio enabled".
    shared_vars = None

logger = logging.getLogger("audio_manager")

AUDIO_AVAILABLE = False
pygame = None

class AudioManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(AudioManager, cls).__new__(cls)
                cls._instance.initialized = False
        return cls._instance

    def initialize(self, base_path):
        if self.initialized:
            return
        
        if getattr(shared_vars, 'disable_audio', False):
            logger.info("Audio is disabled by user setting.")
            self.initialized = False
            return

        global AUDIO_AVAILABLE, pygame
        if not AUDIO_AVAILABLE:
            try:
                os.environ['PYGAME_HIDE_SUPPORT_PROMPT'] = "hide"
                import pygame as pg
                pygame = pg
                pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=2048)
                pygame.init()
                AUDIO_AVAILABLE = True
            except ImportError:
                try:
                    logger.info("Pygame not found. Attempting to install...")
                    subprocess.check_call([sys.executable, "-m", "pip", "install", "pygame"])
                    import pygame as pg
                    pygame = pg
                    pygame.mixer.pre_init(frequency=44100, size=-16, channels=2, buffer=2048)
                    pygame.init()
                    AUDIO_AVAILABLE = True
                    logger.info("Pygame installed and initialized successfully.")
                except Exception as e:
                    AUDIO_AVAILABLE = False
                    logger.warning(f"Failed to install/initialize pygame: {e}")
            except Exception as e:
                AUDIO_AVAILABLE = False
                logger.error(f"Failed to initialize audio: {e}")

        if not AUDIO_AVAILABLE:
            logger.warning("Audio system not available")
            self.initialized = False
            return
        
        self.base_path = base_path
        self.last_play_time = 0
        self.cooldown = 0.5
        self.sounds = {}
        
        audio_dir = os.path.join(self.base_path, "audio")
        if not os.path.exists(audio_dir):
            logger.warning(f"Audio directory not found at {os.path.abspath(audio_dir)}")
            return

        self._load_sound("on", os.path.join(audio_dir, "on.mp3"))
        self._load_sound("off", os.path.join(audio_dir, "off.mp3"))
        
        self.initialized = True
        logger.info(f"Audio initialized. Loaded sounds: {list(self.sounds.keys())}")

    def _load_sound(self, name, path):
        try:
            full_path = os.path.abspath(path)
            if os.path.exists(full_path):
                self.sounds[name] = pygame.mixer.Sound(full_path)
                logger.info(f"Successfully loaded sound '{name}' from {full_path}")
            else:
                logger.warning(f"Sound file not found: {full_path}")
        except Exception as e:
            logger.error(f"Error loading sound {path}: {e}")

    def play_sound(self, name, volume, force=False):
        if getattr(shared_vars, 'disable_audio', False):
            return

        if not AUDIO_AVAILABLE or not self.initialized or not pygame:
            return

        if pygame.mixer.get_init() is None:
            try:
                pygame.mixer.init(frequency=44100, size=-16, channels=2, buffer=2048)
            except Exception as e:
                logger.error(f"Failed to re-initialize mixer: {e}")
                return

        current_time = time.time()
        if not force and (current_time - self.last_play_time < self.cooldown):
            logger.debug(f"Sound {name} skipped due to cooldown")
            return

        if name in self.sounds:
            try:
                vol = float(volume)
                vol = max(0.0, min(1.0, vol))
                self.sounds[name].set_volume(vol)
                self.sounds[name].play()
                self.last_play_time = current_time
                logger.debug(f"Playing sound: {name} at volume {vol}")
            except Exception as e:
                logger.error(f"Error playing sound {name}: {e}")
                return False
        else:
            logger.debug(f"Sound {name} requested but not loaded")
            return False
        return True
