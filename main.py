

import pygame
import sys
import math
import random
import os
import json
import array
import base64

pygame.init()
try:
    # Настройка микшера на 22050 Гц для совместимости и стабильного воспроизведения
    pygame.mixer.init(frequency=22050, size=-16, channels=2)
    pygame.mixer.set_num_channels(16)
    pygame.mixer.set_reserved(8)
    MIXER_AVAILABLE = True
except pygame.error:
    MIXER_AVAILABLE = False

# =====================================================================
# 1. КОНСТАНТЫ И НАСТРОЙКИ
# =====================================================================
WIDTH, HEIGHT = 1024, 600
FPS = 60

# Физика
GRAVITY = 0.45          # Гравитация
TERMINAL_VEL = 16.0     # Лимит скорости падения
PLAYER_SPEED = 4.7      # Скорость бега
JUMP_FORCE = -13.0      # Сила прыжка
BOUNCE_FORCE = -20.0    # Сила отскока от батута
COYOTE_FRAMES = 8       # Койот-тайм (кадры)
JUMP_BUFFER = 8         # Буфер ввода прыжка (кадры)

# Дефолтный звук
DEFAULT_MUSIC_VOL = 0.25 
DEFAULT_SFX_VOL = 0.35   

# Дефолтное управление
DEFAULT_CONTROLS = {
    "LEFT": pygame.K_a,
    "RIGHT": pygame.K_d,
    "JUMP": pygame.K_SPACE,
    "SHIFT": pygame.K_LSHIFT
}

# Базовые цвета
WHITE = (255, 255, 255)
BLACK = (0, 0, 0)
GRAY = (110, 110, 130)
LIGHT_GRAY = (200, 200, 210) 
DARK_GRAY = (45, 45, 65)

# Цвета интерфейса настроек
SLIDER_BG = (35, 35, 50)          
SLIDER_ACTIVE_MUS = (0, 255, 255) 
SLIDER_ACTIVE_SFX = (255, 0, 128) 
REBIND_HIGHLIGHT = (255, 200, 0)  # Подсветка кнопки при переназначении

# Палитра Мира А (CYBER)
DARK_BG = (12, 12, 28)      
CYAN = (0, 255, 255)        
NEON_PINK = (255, 0, 128)   
PURPLE = (160, 0, 220)      
GOLD = (255, 200, 0)        

# Палитра Мира B (FANTASY)
LIGHT_BG = (120, 190, 230)  
GREEN = (55, 175, 55)       
LIGHT_GREEN = (140, 235, 140) 
BROWN = (130, 85, 40)       
YELLOW = (255, 220, 50)     
ORANGE = (255, 150, 0)      
RED = (220, 50, 50)

# =====================================================================
# 2. МЕНЕДЖЕРЫ (Данные и Звук)
# =====================================================================
class SoundManager:
    """Менеджер звука и музыки (синтез аудио в реальном времени)."""
    _instance = None
    
    def __new__(cls):
        if not cls._instance:
            cls._instance = super(SoundManager, cls).__new__(cls)
            cls._instance.sounds = {}
            cls._instance.vol_cyber = 0.25
            cls._instance.vol_fantasy = 0.0
            cls._instance.enabled = MIXER_AVAILABLE
            
            # Загрузка сохраненного конфига
            try:
                music_vol, sfx_vol, _ = SaveManager.load_settings()
                cls._instance.music_volume = music_vol
                cls._instance.sfx_volume = sfx_vol
            except Exception:
                cls._instance.music_volume = DEFAULT_MUSIC_VOL
                cls._instance.sfx_volume = DEFAULT_SFX_VOL
                
            cls._instance.muted = False
            
            if cls._instance.enabled:
                try:
                    cls._instance.chan_cyber = pygame.mixer.Channel(5)
                    cls._instance.chan_fantasy = pygame.mixer.Channel(6)
                except (pygame.error, AttributeError, Exception):
                    cls._instance.chan_cyber = None
                    cls._instance.chan_fantasy = None
                    cls._instance.enabled = False
                    
            if cls._instance.enabled:
                cls._instance._load_all()
        return cls._instance

    def _gen_synth_sound(self, s_type):
        """Генерация звуковых эффектов (SFX) на лету."""
        if not self.enabled:
            return None
            
        mixer_init = pygame.mixer.get_init()
        sample_rate = mixer_init[0] if mixer_init else 22050
        channels = max(1, abs(mixer_init[2])) if mixer_init else 2
        
        duration = 0.15 if s_type in ('jump', 'shift') else (0.22 if s_type == 'coin' else 0.28)
        num_samples = int(sample_rate * duration)
        
        buf = array.array('h', [0] * (num_samples * channels))
        
        # 5мс плавной атаки для устранения кликов на старте фазы
        attack_time = 0.005
        attack_samples = int(sample_rate * attack_time)
        
        for i in range(num_samples):
            t = i / sample_rate
            if s_type == 'jump':
                freq = 150 + (t / duration) * 480
                val = math.sin(2 * math.pi * freq * t)
            elif s_type == 'coin':
                freq = 987 if t < 0.07 else 1318
                val = math.sin(2 * math.pi * freq * t)
            elif s_type == 'hit':
                freq = max(30, 240 - (t / duration) * 200)
                noise = random.uniform(-0.6, 0.6)
                val = math.sin(2 * math.pi * freq * t) * 0.7 + noise * 0.3
            elif s_type == 'shift':
                freq = 280 + math.sin(t * 70) * 140
                val = math.sin(2 * math.pi * freq * t)
            else:
                val = 0
                
            # Огибающая громкости (линейное затухание + сглаживание атаки)
            fade = 1.0 - (i / num_samples)
            if i < attack_samples:
                fade *= (i / attack_samples)
                
            v = int(val * fade * 16000)
            for c in range(channels):
                buf[i * channels + c] = v
            
        try:
            return pygame.mixer.Sound(buffer=buf.tobytes())
        except (pygame.error, Exception):
            return None

    def _gen_synth_bgm(self, bgm_type):
        """Синтез бесконечных фоновых треков (BGM) с эффектом псевдостерео."""
        if not self.enabled:
            return None
            
        mixer_init = pygame.mixer.get_init()
        sample_rate = mixer_init[0] if mixer_init else 22050
        channels = max(1, abs(mixer_init[2])) if mixer_init else 2
        
        duration = 4.0
        num_samples = int(sample_rate * duration)
        buf = array.array('h', [0] * (num_samples * channels))
        
        if bgm_type == 'cyber':
            bass_seq = [110, 110, 130, 110, 146, 110, 164, 130, 110, 110, 130, 110, 146, 164, 196, 164]
            mel_seq = [220, 330, 440, 330, 261, 392, 523, 392, 293, 440, 587, 440, 329, 493, 659, 493,
                       220, 330, 440, 330, 261, 392, 523, 392, 293, 440, 587, 440, 392, 587, 783, 587]
            
            for i in range(num_samples):
                t = i / sample_rate
                
                step_b = int(t / 0.25) % 16
                fb = bass_seq[step_b]
                bass_val = 1.0 if (t * fb) % 1.0 < 0.5 else -1.0
                b_fade = math.exp(-5.0 * (t % 0.25))
                
                step_m = int(t / 0.125) % 32
                fm = mel_seq[step_m]
                mel_val = 2.0 * ((t * fm) % 1.0) - 1.0
                m_fade = math.exp(-7.0 * (t % 0.125))
                
                # Низкочастотное панорамирование (LFO) мелодии по каналам
                pan_left = 0.5 + 0.3 * math.sin(2 * math.pi * 0.5 * t)
                pan_right = 1.0 - pan_left
                
                # Микширование каналов (бас по центру, мелодия распределена по панораме)
                val_l = 0.38 * bass_val * b_fade + 0.22 * mel_val * m_fade * pan_left
                val_r = 0.38 * bass_val * b_fade + 0.22 * mel_val * m_fade * pan_right
                
                if channels == 2:
                    buf[i * 2] = int(val_l * 16000)
                    buf[i * 2 + 1] = int(val_r * 16000)
                else:
                    buf[i] = int(((val_l + val_r) * 0.5) * 16000)
                    
        else:
            bass_seq = [146, 146, 164, 164, 196, 196, 220, 220]
            mel_seq = [587, 659, 783, 880, 987, 880, 783, 659, 587, 783, 880, 1174, 987, 880, 783, 587]
            
            for i in range(num_samples):
                t = i / sample_rate
                
                step_b = int(t / 0.5) % 8
                fb = bass_seq[step_b]
                bass_val = math.sin(2 * math.pi * fb * t)
                b_fade = math.exp(-2.5 * (t % 0.5))
                
                step_m = int(t / 0.25) % 16
                fm = mel_seq[step_m]
                mel_val = math.sin(2 * math.pi * fm * t) * 0.7 + math.sin(2 * math.pi * (fm * 2.0) * t) * 0.3
                m_fade = math.exp(-4.5 * (t % 0.25))
                
                # LFO-панорама для колокольчиков фэнтези мира
                pan_left = 0.5 + 0.3 * math.sin(2 * math.pi * 0.5 * t)
                pan_right = 1.0 - pan_left
                
                val_l = 0.42 * bass_val * b_fade + 0.20 * mel_val * m_fade * pan_left
                val_r = 0.42 * bass_val * b_fade + 0.20 * mel_val * m_fade * pan_right
                
                if channels == 2:
                    buf[i * 2] = int(val_l * 16000)
                    buf[i * 2 + 1] = int(val_r * 16000)
                else:
                    buf[i] = int(((val_l + val_r) * 0.5) * 16000)
                    
        try:
            return pygame.mixer.Sound(buffer=buf.tobytes())
        except (pygame.error, Exception):
            return None

    def _load_all(self):
        """Синтез аудиоэффектов и музыки напрямую в ОЗУ."""
        if not self.enabled:
            return
            
        # Генерация эффектов
        for name in ['jump', 'coin', 'hit', 'shift']:
            synth = self._gen_synth_sound(name)
            if synth:
                self.sounds[name] = synth

        # Генерация фоновой музыки
        for bgm_type in ['cyber', 'fantasy']:
            synth_bgm = self._gen_synth_bgm(bgm_type)
            if synth_bgm:
                self.sounds[f'bgm_{bgm_type}'] = synth_bgm

        try:
            if self.chan_cyber and self.chan_fantasy:
                if 'bgm_cyber' in self.sounds:
                    self.chan_cyber.play(self.sounds['bgm_cyber'], loops=-1)
                if 'bgm_fantasy' in self.sounds:
                    self.chan_fantasy.play(self.sounds['bgm_fantasy'], loops=-1)
                
                self.chan_cyber.set_volume(self.vol_cyber * self.music_volume)
                self.chan_fantasy.set_volume(self.vol_fantasy * self.music_volume)
        except (pygame.error, Exception):
            pass

    def update_music(self, dimension):
        """Плавный кроссфейд между фоновыми треками измерений."""
        if not self.enabled:
            return
            
        if self.muted:
            if self.chan_cyber: self.chan_cyber.set_volume(0)
            if self.chan_fantasy: self.chan_fantasy.set_volume(0)
            return
            
        target_cyber = 0.22 if dimension == "A" else 0.0
        target_fantasy = 0.22 if dimension == "B" else 0.0
        
        self.vol_cyber += (target_cyber - self.vol_cyber) * 0.04
        self.vol_fantasy += (target_fantasy - self.vol_fantasy) * 0.04
        
        if 'bgm_cyber' in self.sounds and self.chan_cyber:
            self.chan_cyber.set_volume(self.vol_cyber * self.music_volume)
        if 'bgm_fantasy' in self.sounds and self.chan_fantasy:
            self.chan_fantasy.set_volume(self.vol_fantasy * self.music_volume)

    def play(self, name):
        """Воспроизведение SFX."""
        if self.enabled and not self.muted and self.sounds.get(name):
            try:
                sound = self.sounds[name]
                sound.set_volume(self.sfx_volume)
                sound.play()
            except pygame.error:
                pass

    def set_music_volume(self, volume):
        """Установка громкости фоновой музыки."""
        self.music_volume = max(0.0, min(1.0, volume))
        if self.enabled and not self.muted:
            if self.chan_cyber:
                self.chan_cyber.set_volume(self.vol_cyber * self.music_volume)
            if self.chan_fantasy:
                self.chan_fantasy.set_volume(self.vol_fantasy * self.music_volume)

    def set_sfx_volume(self, volume):
        """Установка громкости аудиоэффектов."""
        self.sfx_volume = max(0.0, min(1.0, volume))

    def toggle_mute(self):
        """Включение/выключение звука."""
        self.muted = not self.muted
        if self.enabled:
            if self.muted:
                if self.chan_cyber: self.chan_cyber.set_volume(0)
                if self.chan_fantasy: self.chan_fantasy.set_volume(0)
            else:
                if self.chan_cyber:
                    self.chan_cyber.set_volume(self.vol_cyber * self.music_volume)
                if self.chan_fantasy:
                    self.chan_fantasy.set_volume(self.vol_fantasy * self.music_volume)


class SaveManager:
    """Класс для работы с файлами сохранений, настроек и резервных копий."""
    FILE = "highscore.json"
    BACKUP_FILE = "highscore.bak" # Бэкап
    
    @staticmethod
    def _read_file(filepath):
        """Чтение и декодирование файла сохранений."""
        if not os.path.exists(filepath):
            return None
        try:
            with open(filepath, "r") as f:
                encoded_data = f.read()
                decoded_bytes = base64.b64decode(encoded_data.encode('utf-8'))
                parsed_data = json.loads(decoded_bytes.decode('utf-8'))
                
                if isinstance(parsed_data, dict):
                    if "high_scores" not in parsed_data:
                        parsed_data["high_scores"] = {}
                    if "settings" not in parsed_data:
                        parsed_data["settings"] = {}
                    return parsed_data
        except Exception:
            pass
        return None

    @staticmethod
    def load():
        """Загрузка сохранений. При ошибке восстанавливает данные из бэкапа."""
        data = SaveManager._read_file(SaveManager.FILE)
        if data is not None:
            return data
            
        # Восстановление из резервной копии при повреждении основного файла
        data = SaveManager._read_file(SaveManager.BACKUP_FILE)
        if data is not None:
            SaveManager._write_data_to_file(data, SaveManager.FILE)
            return data
            
        return {"high_scores": {}, "settings": {}}

    @staticmethod
    def _write_data_to_file(data, filepath):
        """Запись сериализованных данных в файл."""
        json_str = json.dumps(data)
        encoded_data = base64.b64encode(json_str.encode('utf-8')).decode('utf-8')
        
        temp_file = filepath + ".tmp"
        try:
            with open(temp_file, "w") as f:
                f.write(encoded_data)
            os.replace(temp_file, filepath)
        except Exception:
            if os.path.exists(temp_file):
                os.remove(temp_file)

    @staticmethod
    def _write_data(data):
        """Дублирование записи в основной файл и в бэкап."""
        SaveManager._write_data_to_file(data, SaveManager.FILE)
        SaveManager._write_data_to_file(data, SaveManager.BACKUP_FILE)

    @staticmethod
    def save(level, time_left, coins):
        """Сохранение рекорда для конкретного уровня."""
        data = SaveManager.load()
        
        if not isinstance(data, dict) or "high_scores" not in data:
            data = {"high_scores": {}, "settings": {}}
            
        lvl_str = str(level)
        if lvl_str not in data["high_scores"] or not isinstance(data["high_scores"][lvl_str], dict):
            data["high_scores"][lvl_str] = {"time": 0, "coins": 0}
        
        old = data["high_scores"][lvl_str]
        old_time = old.get("time", 0) if isinstance(old, dict) else 0
        old_coins = old.get("coins", 0) if isinstance(old, dict) else 0
        
        data["high_scores"][lvl_str] = {
            "time": max(old_time, time_left),
            "coins": max(old_coins, coins)
        }
        
        SaveManager._write_data(data)

    @staticmethod
    def load_settings():
        """Загрузка настроек звука и раскладки клавиатуры."""
        data = SaveManager.load()
        settings = data.get("settings", {})
        
        music_vol = settings.get("music_volume", DEFAULT_MUSIC_VOL)
        sfx_vol = settings.get("sfx_volume", DEFAULT_SFX_VOL)
        
        saved_controls = settings.get("controls", {})
        controls = {}
        for action, default_key in DEFAULT_CONTROLS.items():
            controls[action] = saved_controls.get(action, default_key)
            
        return music_vol, sfx_vol, controls

    @staticmethod
    def save_settings(music_vol, sfx_vol, controls):
        """Сохранение настроек звука и раскладки."""
        data = SaveManager.load()
        
        data["settings"] = {
            "music_volume": music_vol,
            "sfx_volume": sfx_vol,
            "controls": controls
        }
        
        SaveManager._write_data(data)

sfx = SoundManager()
# =====================================================================
# 3. УТИЛИТЫ И ВИЗУАЛ (Эффекты, Камера, Пост-обработка и Частицы)
# =====================================================================
_FONT_CACHE = {}  # Кэш системных шрифтов
_GLOW_CACHE = {}  # Кэш текстур свечения

def draw_text(surf, text, size, x, y, color=WHITE, center=False, alpha=255):
    """Вывод текста с тенью."""
    if size not in _FONT_CACHE:
        _FONT_CACHE[size] = pygame.font.SysFont(["consolas", "arial", "freesans", "dejavusans", "liberationsans"], size, bold=True)
    font = _FONT_CACHE[size]
    
    shadow_color = (10, 10, 24)
    shadow_rendered = font.render(str(text), True, shadow_color)
    if alpha < 255:
        shadow_rendered.set_alpha(int(alpha * 0.65))
    else:
        shadow_rendered.set_alpha(170)
        
    rendered = font.render(str(text), True, color)
    if alpha < 255:
        rendered.set_alpha(alpha)
        
    rect = rendered.get_rect()
    if center:
        rect.center = (int(x), int(y))
    else:
        rect.topleft = (int(x), int(y))
        
    surf.blit(shadow_rendered, (rect.x + 2, rect.y + 2))
    surf.blit(rendered, rect)
    return rect


def get_glow_surf(radius, color):
    """Генерация радиального размытия для эффекта свечения (кэшируемая)."""
    optimized_radius = max(2, (int(radius) // 2) * 2)
    key = (optimized_radius, color[:3])
    
    if key not in _GLOW_CACHE:
        size = int(optimized_radius * 4)
        surf = pygame.Surface((size, size), pygame.SRCALPHA).convert_alpha()
        
        for r in range(size // 2, 0, -1):
            ratio = r / (size // 2)
            alpha = int(((1.0 - ratio) ** 2.2) * 255)
            alpha = max(0, min(255, alpha))
            pygame.draw.circle(surf, (*color[:3], alpha), (size // 2, size // 2), r)
            
        _GLOW_CACHE[key] = surf
    return _GLOW_CACHE[key]


def make_platform_surf(w, h, dim, bounce=False):
    """Отрисовка текстур платформ в зависимости от активного измерения."""
    surf = pygame.Surface((w, h), pygame.SRCALPHA).convert_alpha()
    
    if bounce:
        if dim == "A":
            surf.fill((25, 25, 35))
            for i in range(-20, w, 20):
                pygame.draw.polygon(surf, (240, 200, 10), [
                    (i + 5, h), (i + 12, 4), (i + 17, 4), (i + 10, h)
                ])
            pygame.draw.rect(surf, (0, 255, 240), (0, 0, w, 4))
            pygame.draw.rect(surf, WHITE, (0, 0, w, 1))
        else:
            surf.fill((110, 65, 30))
            for y in range(h):
                ratio = y / h
                c = (int(240 - ratio * 40), int(120 - ratio * 60), int(20 - ratio * 15))
                pygame.draw.line(surf, c, (0, y), (w, y))
            for x in range(6, w, 16):
                pygame.draw.circle(surf, (255, 220, 150), (x, 7), 3)
            pygame.draw.rect(surf, (255, 255, 255), (0, 0, w, 3))
            
    elif dim == "A":
        for y in range(h):
            ratio = y / h
            c_val = int(20 + ratio * 18)
            pygame.draw.line(surf, (c_val, c_val + 5, c_val + 18), (0, y), (w, y))
        for y in range(3, h, 3):
            pygame.draw.line(surf, (10, 10, 20), (0, y), (w, y), 1)
        for x in range(0, w, 16):
            pygame.draw.line(surf, (35, 35, 65), (x, 0), (x, h), 1)
        pygame.draw.rect(surf, (0, 255, 240), (0, 0, w, 3))
        pygame.draw.rect(surf, WHITE, (0, 0, w, 1))
        if w >= 48:
            pygame.draw.line(surf, (180, 0, 255), (20, h // 2), (w - 20, h // 2), 1)
            pygame.draw.circle(surf, (0, 255, 240), (24, h // 2), 2)
            pygame.draw.circle(surf, (180, 0, 255), (w - 24, h // 2), 2)
        pygame.draw.rect(surf, (40, 50, 90), (0, 0, w, h), 1)

    elif dim == "B":
        for y in range(h):
            ratio = y / h
            c_val = int(95 - ratio * 35)
            pygame.draw.line(surf, (c_val, c_val - 12, c_val - 22), (0, y), (w, y))
        for x in range(0, w, 28):
            pygame.draw.line(surf, (30, 20, 15), (x, 0), (x, h), 1)
            pygame.draw.line(surf, (135, 115, 105), (x + 1, 0), (x + 1, h - 2), 1)
        pygame.draw.line(surf, (30, 20, 15), (0, h // 2), (w, h // 2), 1)
        pygame.draw.line(surf, (135, 115, 105), (0, h // 2 + 1), (w, h // 2 + 1), 1)
        pygame.draw.rect(surf, (40, 175, 45), (0, 0, w, 4))
        for x in range(2, w, 6):
            blade_h = random.randint(3, 8)
            pygame.draw.polygon(surf, (28, 130, 32), [
                (x - 2, 4), (x + 2, 4), (x + random.randint(-1, 1), 4 + blade_h)
            ])
        pygame.draw.rect(surf, (130, 230, 80), (0, 0, w, 1))
        
    else:
        for y in range(h):
            ratio = y / h
            c_val = int(55 - ratio * 15)
            pygame.draw.line(surf, (c_val, c_val, c_val + 5), (0, y), (w, y))
        if w >= 32:
            for x_p in (6, w - 8):
                pygame.draw.circle(surf, (90, 90, 105), (x_p, h // 2), 2)
                pygame.draw.circle(surf, (25, 25, 35), (x_p, h // 2), 1)
        pygame.draw.rect(surf, (70, 70, 85), (0, 0, w, h), 1)
        
    return surf


class Camera:
    """Следящая за игроком камера с поддержкой тряски (shake)."""
    def __init__(self, lw):
        self.x = 0.0
        self.lw = lw
        self.target_x = 0.0
        self.shake = 0
        self.shake_time = 0.0

    def update(self, px):
        self.target_x = px - WIDTH // 3
        self.x += (self.target_x - self.x) * 0.09
        self.x = max(0.0, min(self.x, self.lw - WIDTH))
        if self.shake > 0:
            self.shake -= 1
            self.shake_time += 1.4
        else:
            self.shake_time = 0.0

    def offset(self):
        if self.shake > 0:
            decay = self.shake / 14.0
            amplitude = decay * 8.5
            sx = int(math.sin(self.shake_time) * amplitude)
            return int(self.x) + sx
        return int(self.x)


class Shockwave:
    """Радиальная волна искажения при переключении измерений."""
    __slots__ = ['x', 'y', 'color', 'radius', 'max_radius', 'thickness']
    _scratch_surf = None
    
    def __init__(self, x, y, color):
        self.x = x
        self.y = y
        self.color = color
        self.radius = 8.0
        self.max_radius = 135.0
        self.thickness = 3

    def update(self):
        self.radius += 5.5
        self.thickness = max(1, int(3 * (1.0 - (self.radius / self.max_radius))))
        return self.radius < self.max_radius

    def draw(self, surf, cam_x):
        ratio = self.radius / self.max_radius
        alpha = int((1.0 - ratio) * 35)
        
        if Shockwave._scratch_surf is None:
            Shockwave._scratch_surf = pygame.Surface((300, 300), pygame.SRCALPHA)
        
        Shockwave._scratch_surf.fill((0, 0, 0, 0))
        center = 150
        pygame.draw.circle(Shockwave._scratch_surf, (*self.color[:3], alpha), (center, center), int(self.radius), int(self.thickness))
        surf.blit(Shockwave._scratch_surf, (int(self.x - cam_x - center), int(self.y - center)), special_flags=pygame.BLEND_RGBA_ADD)


class ParticleSystem:
    """Система частиц для отрисовки искр, взрывов и глитч-эффектов."""
    
    class Particle:
        __slots__ = ['x', 'y', 'vx', 'vy', 'life', 'max_life', 'color', 'size', 'style', 'gravity', 'friction']
        
        def __init__(self, x, y, color, vx=None, vy=None):
            self.x = x
            self.y = y
            self.vx = vx if vx is not None else random.uniform(-2.5, 2.5)
            self.vy = vy if vy is not None else random.uniform(-4.5, -1.0)
            self.life = random.randint(16, 34)
            self.max_life = self.life
            self.color = color
            self.size = random.uniform(2.5, 5.5)
            self.gravity = 0.16
            self.friction = 0.985

            r, g, b = color[:3]
            if (r == 0 and g == 255 and b == 255) or (r == 255 and g == 0 and b == 128):
                self.style = 'neon_pixel'
            elif r == 255 and g == 200 and b == 0:
                self.style = 'glow'
            elif r == 220 and g == 50 and b == 50:
                self.style = 'streak'
            else:
                self.style = 'glow'

        def update(self):
            self.vx *= self.friction
            self.vy += self.gravity
            self.x += self.vx
            self.y += self.vy
            self.life -= 1

        def draw(self, surf, cam_x):
            if self.life <= 0: return
            t = self.life / self.max_life
            dx = int(self.x - cam_x)
            dy = int(self.y)
            r, g, b = self.color[:3]

            if self.style == 'glow':
                glow_r = max(2, int(self.size * 2.5 * t))
                g_surf = get_glow_surf(glow_r, (r, g, b))
                surf.blit(g_surf, (dx - g_surf.get_width() // 2, dy - g_surf.get_height() // 2), special_flags=pygame.BLEND_RGBA_ADD)
            elif self.style == 'neon_pixel':
                sz = max(1, int(self.size * t))
                faded_col = (int(r * t), int(g * t), int(b * t))
                pygame.draw.rect(surf, faded_col, (dx - sz // 2, dy - sz // 2, sz, sz))
            else:
                speed = math.hypot(self.vx, self.vy)
                length = max(2.0, speed * 2.5 * t)
                angle = math.atan2(self.vy, self.vx)
                ex = dx + int(math.cos(angle) * length)
                ey = dy + int(math.sin(angle) * length)
                pygame.draw.line(surf, (r, g, b), (dx, dy), (ex, ey), max(1, int(self.size * 0.4)))

    def __init__(self):
        self.particles = []
        self.shockwaves = []
        self.glitch_timer = 0
        self.flash_timer = 0
        self.flash_color = (255, 255, 255)
        self.flash_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        
        self._glitch_cyan = pygame.Surface((WIDTH, 36), pygame.SRCALPHA)
        self._glitch_cyan.fill((0, 255, 255, 90))
        self._glitch_pink = pygame.Surface((WIDTH, 36), pygame.SRCALPHA)
        self._glitch_pink.fill((255, 0, 128, 90))

    def emit(self, x, y, color, count=8, vx=None, vy=None):
        for _ in range(count):
            self.particles.append(self.Particle(x, y, color, vx, vy))
            
        if count >= 20: 
            self.shockwaves.append(Shockwave(x, y, color))
            
            r, g, b = color[:3]
            if r == 220 and g == 50 and b == 50:
                self.glitch_timer = 12
                self.flash_timer = 14
                self.flash_color = (180, 0, 0)
            elif (r == 0 and g == 255 and b == 255) or (r == 55 and g == 175 and b == 55):
                self.flash_timer = 8
                self.flash_color = color

    def update(self):
        self.particles = [p for p in self.particles if p.life > 0]
        for p in self.particles:
            p.update()
            
        self.shockwaves = [sw for sw in self.shockwaves if sw.update()]

    def draw(self, surf, cam_x):
        for sw in self.shockwaves:
            sw.draw(surf, cam_x)
            
        for p in self.particles:
            p.draw(surf, cam_x)
            
        if self.glitch_timer > 0:
            self.glitch_timer -= 1
            for _ in range(4):
                gy = random.randint(0, HEIGHT)
                gh = random.randint(6, 36)
                offset = random.randint(-20, 20)
                
                surf.blit(self._glitch_cyan, (offset, gy), area=(0, 0, WIDTH, gh))
                surf.blit(self._glitch_pink, (-offset, gy + 3), area=(0, 0, WIDTH, gh))

        if self.flash_timer > 0:
            self.flash_timer -= 1
            alpha = int((self.flash_timer / 8.0) * 15)
            self.flash_surf.fill((*self.flash_color[:3], alpha))
            surf.blit(self.flash_surf, (0, 0))
# =====================================================================
# 4. ИГРОВЫЕ ОБЪЕКТЫ (Платформы, Двери, Препятствия)
# =====================================================================
class Platform(pygame.sprite.Sprite):
    """Базовый класс платформы. Поддерживает рендер в активном и фантомном состояниях."""
    def __init__(self, x, y, w, h, dim, bounce=False):
        super().__init__()
        self.rect = pygame.Rect(x, y, w, h)
        self.dimension = dim
        self.bounce = bounce
        
        # Кэшируем текстуры при создании объекта, чтобы не грузить рендер в игровом цикле
        self._surf_visible = make_platform_surf(w, h, dim, bounce)
        self._surf_ghost = self._surf_visible.copy()
        self._surf_ghost.set_alpha(45) # Фантомный вид для платформ из неактивного мира
        self.surf = self._surf_visible

    def update(self): 
        pass

    def draw(self, screen, cam_x, current_dim):
        # Отсекаем отрисовку платформ за пределами экрана (камера-куллинг)
        if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
            return
            
        # Платформа материальна, если она общая (ALL) или принадлежит текущему измерению
        is_active = (self.dimension == "ALL" or self.dimension == current_dim)
        self.surf = self._surf_visible if is_active else self._surf_ghost
        screen.blit(self.surf, (self.rect.x - cam_x, self.rect.y))


class MovingPlatform(Platform):
    """Платформа, перемещающаяся по горизонтали в заданном диапазоне."""
    def __init__(self, x, y, w, h, dim, move_range, speed):
        super().__init__(x, y, w, h, dim, bounce=False)
        self.start_x = x
        self.move_range = move_range
        self.speed_x = speed
        self.fx = float(x) # Движение считаем во float для плавности при субпиксельных скоростях

    def update(self):
        # Обновляем вещественную координату, затем округляем до целых пикселей для хитбокса
        self.fx += self.speed_x
        self.rect.x = int(self.fx)
        
        # Разворачиваем платформу на краях зоны патрулирования
        if (self.rect.x > self.start_x + self.move_range and self.speed_x > 0) or (self.rect.x < self.start_x and self.speed_x < 0):
            self.speed_x *= -1


class CrumblingPlatform(Platform):
    """Платформа, которая начинает трястись и падает через секунду после того, как на нее наступили."""
    def __init__(self, x, y, w, h, dim):
        super().__init__(x, y, w, h, dim, bounce=False)
        self.state = "IDLE" # Возможные состояния: IDLE (целая), CRUMBLING (трясется), BROKEN (исчезла)
        self.timer = 0
        
        # Генерируем красную предупреждающую текстуру методом аддитивного наложения цвета
        self._surf_warning = self._surf_visible.copy()
        self._surf_warning.fill((150, 0, 0), special_flags=pygame.BLEND_RGB_ADD)

    def touch(self):
        """Запуск процесса обрушения при контакте с ногами игрока."""
        if self.state == "IDLE":
            self.state = "CRUMBLING"
            self.timer = int(FPS * 1.2) # Даем игроку 1.2 секунды, чтобы спрыгнуть

    def update(self):
        if self.state == "CRUMBLING":
            self.timer -= 1
            if self.timer <= 0:
                self.state = "BROKEN"
                self.timer = FPS * 3 # Платформа исчезает ровно на 3 секунды перед восстановлением
        elif self.state == "BROKEN":
            self.timer -= 1
            if self.timer <= 0:
                self.state = "IDLE"

    def draw(self, screen, cam_x, current_dim):
        if self.state == "BROKEN": 
            return # Скрытые платформы не отрисовываем вообще
            
        is_active = (self.dimension == "ALL" or self.dimension == current_dim)
        
        # Если платформа трясется, смещаем текстуру на рандомный пиксель влево-вправо
        shake_offset_x = random.randint(-1, 1) if self.state == "CRUMBLING" else 0
        dx = int(self.rect.x - cam_x + shake_offset_x)
        
        if is_active:
            # Перед падением заставляем платформу быстро мигать красным цветом (каждые 4 кадра)
            if self.state == "CRUMBLING" and (self.timer // 4) % 2 == 0:
                surf = self._surf_warning
            else:
                surf = self._surf_visible
        else:
            surf = self._surf_ghost
        screen.blit(surf, (dx, self.rect.y))


class Door(pygame.sprite.Sprite):
    """Запертая дверь. Открывается, если у игрока есть хотя бы один ключ."""
    def __init__(self, x, y, w, h, dim):
        super().__init__()
        self.rect = pygame.Rect(x, y, w, h)
        self.dimension = dim
        self.is_open = False
        self.bounce = False
        self.dissolve_progress = 0.0 # Коэффициент растворения двери от 0.0 до 1.0
        self.tick = random.randint(0, 100)
        
        self._surf_visible = pygame.Surface((w, h), pygame.SRCALPHA)
        self._build_door_texture(self._surf_visible, dim, w, h)
        
        self._surf_ghost = pygame.Surface((w, h), pygame.SRCALPHA)
        self._surf_ghost.fill((50, 50, 80, 35))
        pygame.draw.rect(self._surf_ghost, (100, 100, 130), (0, 0, w, h), 1)

    def _build_door_texture(self, surf, dim, dw, dh):
        """Отрисовка текстуры двери: неоновый шлюз для Кибера (A) и деревянные врата для Фэнтези (B)."""
        if dim == "A":
            surf.fill((35, 30, 45))
            for sy in range(4, dh, 8):
                pygame.draw.line(surf, (15, 10, 20), (1, sy), (dw - 2, sy), 1)
            pygame.draw.rect(surf, CYAN, (0, 0, dw, dh), 2, border_radius=2)
            
            lock_y = dh // 2
            pygame.draw.circle(surf, (15, 10, 20), (dw // 2, lock_y), 6)
            pygame.draw.circle(surf, CYAN, (dw // 2, lock_y), 4)
            pygame.draw.circle(surf, WHITE, (dw // 2, lock_y), 2)
        else:
            surf.fill((90, 60, 40))
            pygame.draw.rect(surf, (160, 110, 50), (0, 6, dw, 5))
            pygame.draw.rect(surf, (160, 110, 50), (0, dh - 11, dw, 5))
            for sx in range(6, dw, 6):
                pygame.draw.line(surf, (40, 25, 15), (sx, 0), (sx, dh), 1)
            pygame.draw.rect(surf, (120, 210, 100), (0, 0, dw, dh), 2, border_radius=2)
            
            rune_y = dh // 2
            pygame.draw.circle(surf, GOLD, (dw // 2, rune_y), 6, 2)
            pygame.draw.line(surf, GOLD, (dw // 2, rune_y + 6), (dw // 2, rune_y + 11), 2)

    def update(self): 
        pass

    def draw(self, screen, cam_x, current_dim):
        self.tick += 1
        
        if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
            return

        # Если дверь открыта — инкрементируем таймер растворения. При 1.0 полностью удаляем
        if self.is_open:
            self.dissolve_progress = min(1.0, self.dissolve_progress + 0.04)
            if self.dissolve_progress >= 1.0:
                return 

        is_active = (self.dimension == "ALL" or self.dimension == current_dim)
        dx = int(self.rect.x - cam_x)
        dy = int(self.rect.y)
        dw = int(self.rect.w)
        dh = int(self.rect.h)
        
        # Эффект открытия: обрезаем высоту рендеринга текстуры снизу вверх через параметр area у blit
        draw_h = int(dh * (1.0 - self.dissolve_progress))
        if draw_h <= 0: 
            return

        if is_active:
            screen.blit(self._surf_visible, (dx, dy), area=(0, 0, dw, draw_h))
            # Спавним мелкие искры под срезом исчезающей двери для красоты
            if self.is_open:
                col = CYAN if self.dimension == "A" else GOLD
                for _ in range(3):
                    sx = dx + random.randint(0, dw)
                    sy = dy + draw_h + random.randint(-3, 3)
                    pygame.draw.circle(screen, col, (sx, sy), 2)
        else:
            screen.blit(self._surf_ghost, (dx, dy), area=(0, 0, dw, draw_h))


class Laser(pygame.sprite.Sprite):
    """Препятствие-лазер. Циклично переходит из выключенного состояния в предупреждение, затем в смертоносный луч."""
    def __init__(self, x, y, h, dim, interval=120, offset=0):
        super().__init__()
        self.rect = pygame.Rect(x, y, 16, h)
        self.dimension = dim
        self.interval = interval
        self.tick = offset
        self.active = False
        self.warning = False
        self.glow_surf = pygame.Surface((32, h), pygame.SRCALPHA).convert_alpha()

    def update(self):
        self.tick += 1
        # Рассчитываем фазу лазера внутри цикла размером (interval * 2) кадра
        phase = self.tick % (self.interval * 2)
        if phase < self.interval - 30:
            # Первая половина цикла: лазер полностью выключен
            self.active = False
            self.warning = False
        elif phase < self.interval:
            # За 30 кадров до включения: активируем режим предупреждения (мигающий пунктир)
            self.active = False
            self.warning = True
        else:
            # Вторая половина цикла: лазер включен и смертельно опасен
            self.active = True
            self.warning = False

    def draw(self, screen, cam_x, current_dim):
        if self.dimension not in ("ALL", current_dim): 
            return
        if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
            return
            
        dx = int(self.rect.x - cam_x)
        dy = int(self.rect.y)
        dh = int(self.rect.h)
        
        # Рисуем статичные металлические эмиттеры сверху и снизу
        pygame.draw.rect(screen, DARK_GRAY, (dx - 4, dy - 10, 24, 10), border_radius=2)
        pygame.draw.rect(screen, DARK_GRAY, (dx - 4, dy + dh, 24, 10), border_radius=2)
        
        if self.active:
            # Ширина луча постоянно колеблется по синусоиде (эффект нестабильной энергии)
            beam_w = int(6 + math.sin(self.tick * 0.45) * 2)
            
            # Рендерим мягкое аддитивное свечение вокруг лазера
            self.glow_surf.fill((0, 0, 0, 0)) 
            pygame.draw.rect(self.glow_surf, (220, 50, 50, 55), (16 - beam_w, 0, beam_w * 2, dh))
            screen.blit(self.glow_surf, (dx - 8, dy), special_flags=pygame.BLEND_RGBA_ADD)
            
            # Рисуем плотное красное ядро луча и тонкий белый центр для эффекта сверхвысокой температуры
            pygame.draw.rect(screen, RED, (dx + 8 - beam_w // 2, dy, beam_w, dh))
            pygame.draw.rect(screen, WHITE, (dx + 8 - max(1, beam_w // 4), dy, max(1, beam_w // 2), dh))
            
            # Искры у верхнего и нижнего эмиттеров для сочности картинки
            for _ in range(3):
                bx = dx + 8 + random.randint(-5, 5)
                by = dy + dh + random.randint(-4, 0)
                pygame.draw.circle(screen, WHITE, (bx, by), 2)
                pygame.draw.circle(screen, RED, (bx, by), 3, 1)
                tx = dx + 8 + random.randint(-5, 5)
                ty = dy + random.randint(0, 4)
                pygame.draw.circle(screen, WHITE, (tx, ty), 2)
                pygame.draw.circle(screen, RED, (tx, ty), 3, 1)
                
        elif self.warning:
            # В фазе предупреждения рисуем пунктирный лазерный целеуказатель, мигающий каждые 5 кадров
            if (self.tick // 5) % 2 == 0:
                for wy in range(dy, dy + dh, 16):
                    pygame.draw.line(screen, RED, (dx + 8, wy), (dx + 8, wy + 8), 1)
                    pygame.draw.circle(screen, RED, (dx + 8, wy), 2)
# =====================================================================
# 5. ИНТЕРАКТИВНЫЕ ОБЪЕКТЫ (Монеты, Ключи, Чекпоинты, Финиш)
# =====================================================================
class Coin(pygame.sprite.Sprite):
    """Собираемая монета с анимацией вращения в 3D и синусоидальным покачиванием."""
    def __init__(self, x, y, dim):
        super().__init__()
        self.rect = pygame.Rect(x, y, 16, 16)
        self.dimension = dim
        self.collected = False
        # Рандомизируем стартовый кадр, чтобы монеты на сцене не крутились синхронно
        self.tick = random.randint(0, 60)

    def update(self):
        self.tick += 1

    def draw(self, screen, cam_x, current_dim):
        if self.collected or self.dimension not in ("ALL", current_dim): 
            return
        if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
            return
        
        # Синусоидальное покачивание (парение в воздухе) по вертикали
        bob = int(math.sin(self.tick * 0.1) * 3)
        cx = int(self.rect.x - cam_x + 8)
        cy = int(self.rect.y + 8 + bob)
        
        # Симуляция 3D вращения: сжимаем ширину эллипса по модулю синуса
        spin_width = max(2, abs(int(16 * math.sin(self.tick * 0.08))))
        
        # Пульсирующий внешний ореол подсветки
        glow_r = int(11 + math.sin(self.tick * 0.12) * 2)
        pygame.draw.circle(screen, (220, 160, 10), (cx, cy), glow_r, 1)
        
        # Отрисовка тела монеты (два эллипса разного оттенка для объема)
        pygame.draw.ellipse(screen, GOLD, (cx - spin_width // 2, cy - 8, spin_width, 16))
        pygame.draw.ellipse(screen, YELLOW, (cx - int(spin_width * 0.65) // 2, cy - 5, int(spin_width * 0.65), 10))
        
        # Блик, бегущий по поверхности вращающейся монеты
        sheen_x = cx - spin_width // 2 + int(((self.tick * 0.35) % spin_width))
        if cx - spin_width // 2 < sheen_x < cx + spin_width // 2:
            pygame.draw.line(screen, WHITE, (sheen_x, cy - 6), (sheen_x, cy + 6), 1)


class Key(pygame.sprite.Sprite):
    """Ключ для открытия дверей. Анимирован покачиванием и вращением механической головки."""
    def __init__(self, x, y, dim):
        super().__init__()
        self.rect = pygame.Rect(x, y, 20, 20)
        self.dimension = dim
        self.collected = False
        self.tick = random.randint(0, 60)

    def update(self): 
        self.tick += 1

    def draw(self, screen, cam_x, current_dim):
        if self.collected or self.dimension not in ("ALL", current_dim): 
            return
        if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
            return
        
        # Синусоидальное покачивание по высоте
        bob = int(math.sin(self.tick * 0.08) * 4)
        dx = int(self.rect.x - cam_x)
        dy = int(self.rect.y + bob)
        
        # Расчет 4 вращающихся вершин для квадратной головки ключа
        angle = self.tick * 0.05
        head_pts = []
        for i in range(4):
            a = angle + i * (math.pi / 2)
            px = dx + 10 + int(math.cos(a) * 7)
            py = dy + 7 + int(math.sin(a) * 7)
            head_pts.append((px, py))
            
        # Отрисовка головки ключа
        pygame.draw.circle(screen, (240, 190, 40), (dx + 10, dy + 10), 12, 1)
        pygame.draw.polygon(screen, GOLD, head_pts)
        pygame.draw.polygon(screen, YELLOW, head_pts, 2)
        pygame.draw.circle(screen, (12, 12, 28), (dx + 10, dy + 7), 2)
        
        # Отрисовка стержня и зубцов ключа ниже головки
        pygame.draw.line(screen, GOLD, (dx + 10, dy + 14), (dx + 10, dy + 22), 3)
        pygame.draw.line(screen, GOLD, (dx + 10, dy + 20), (dx + 15, dy + 20), 2)
        pygame.draw.line(screen, GOLD, (dx + 10, dy + 22), (dx + 15, dy + 22), 2)


class Checkpoint(pygame.sprite.Sprite):
    """Точка сохранения. При активации пускает расширяющуюся световую волну."""
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(x, y, 32, 64)
        self.active = False
        self.prev_active = False # Флаг детектора первого кадра активации
        self.tick = random.randint(0, 60)
        self.ring_r = 0.0 # Радиус расходящейся волны сохранения

    def update(self): 
        self.tick += 1
        if self.active:
            # Запускаем триггер расширения кольца при первом касании
            if not self.prev_active:
                self.ring_r = 1.0
                self.prev_active = True
            # Наращиваем радиус кольца, пока оно не выйдет за пределы хитбокса
            if self.ring_r > 0:
                self.ring_r += 4.5
                if self.ring_r > 130:
                    self.ring_r = 0.0 # Гасим волну

        def draw(self, screen, cam_x, current_dim):
            if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
                return
                
            dx = int(self.rect.x - cam_x)
            dy = int(self.rect.y)
            
            # Флагшток и подставка чекпоинта
            pygame.draw.rect(screen, GRAY, (dx + 14, dy, 4, 64))
            pygame.draw.rect(screen, DARK_GRAY, (dx + 9, dy + 56, 14, 8), border_radius=2)
            
            if current_dim == "A":
                # Мир Кибера: голографический векторный ромб
                col = CYAN if self.active else GRAY
                pygame.draw.circle(screen, col, (dx + 16, dy + 10), 6)
                if self.active:
                    pulse_r = int(9 + math.sin(self.tick * 0.15) * 3)
                    pygame.draw.circle(screen, CYAN, (dx + 16, dy + 10), pulse_r, 1)
                    ang = self.tick * 0.06
                    pts = []
                    for i in range(4):
                        a = ang + i * (math.pi / 2)
                        pts.append((dx + 16 + int(math.cos(a) * 11), dy - 15 + int(math.sin(a) * 8)))
                    pygame.draw.polygon(screen, CYAN, pts, 1)
            else:
                # Мир Фэнтези: магический флаг с поднимающимися спорами-частицами
                col = GREEN if self.active else GRAY
                pygame.draw.polygon(screen, col, [(dx + 16, dy), (dx + 25, dy + 15), (dx + 16, dy + 30), (dx + 7, dy + 15)])
                if self.active:
                    for i in range(3):
                        sy = dy + 15 - ((self.tick + i * 20) % 40)
                        sx = dx + 16 + int(math.sin(self.tick * 0.06 + i) * 6)
                        pygame.draw.circle(screen, (140, 235, 140), (sx, sy), 2)
                        
            # Отрисовка радиального кольца расширяющейся волны через альфа-канал
            if self.ring_r > 0:
                ratio = self.ring_r / 120.0
                alpha = int((1.0 - ratio) * 200)
                alpha = max(0, min(255, alpha))
                
                r_size = int(self.ring_r * 2 + 12)
                ring_surf = pygame.Surface((r_size, r_size), pygame.SRCALPHA).convert_alpha()
                ring_surf.fill((0, 0, 0, 0)) 
                center = r_size // 2
                thickness = max(1, int(4 * (1.0 - ratio)))
                pygame.draw.circle(ring_surf, (0, 255, 240, alpha), (center, center), int(self.ring_r), thickness)
                screen.blit(ring_surf, (dx + 16 - center, dy + 10 - center))


class Goal(pygame.sprite.Sprite):
    """Портал финиша уровня. Состоит из вложенных крутящихся полигонов и засасываемых внутрь искр."""
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(x, y, 44, 64)
        self.tick = 0
        self.portal_particles = [] # Массив искр, спиралевидно затягивающихся в центр портала
        for _ in range(12):
            self.portal_particles.append({
                'angle': random.uniform(0, math.pi * 2),
                'radius': random.uniform(25, 75),
                'speed': random.uniform(0.7, 1.4)
            })

    def update(self): 
        self.tick += 1
        # Уменьшаем радиус орбит частиц, симулируя падение в сингулярность
        for p in self.portal_particles:
            p['radius'] -= p['speed'] * 0.4
            p['angle'] += 0.065
            # При достижении горизонта событий пересоздаем искру на внешней границе
            if p['radius'] < 5:
                p['radius'] = random.uniform(55, 75)
                p['angle'] = random.uniform(0, math.pi * 2)

    def draw(self, screen, cam_x, current_dim):
        if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
            return
            
        dx = int(self.rect.x - cam_x + 22)
        dy = int(self.rect.y + 32)
        
        # Вихрь рендерим на отдельном прозрачном холсте для аддитивного смешивания
        vortex_surf = pygame.Surface((160, 160), pygame.SRCALPHA).convert_alpha()
        vortex_surf.fill((0, 0, 0, 0))
        cx, cy = 80, 80 
        
        r = 26 + int(math.sin(self.tick * 0.07) * 4)
        
        # Рисуем три вращающихся пятиугольника с разным направлением вращения для объема
        for i in range(3):
            alpha = 75 - i * 20
            size = r - i * 5
            rot_dir = 1 if i % 2 == 0 else -1
            angle = self.tick * 0.02 * rot_dir
            
            pts = []
            for k in range(5):
                a = angle + k * (math.pi * 2 / 5)
                pts.append((cx + int(math.cos(a) * size), cy + int(math.sin(a) * size)))
            pygame.draw.polygon(vortex_surf, (*PURPLE[:3], alpha), pts)
            
        # Отрисовка ядра сингулярности портала
        pygame.draw.circle(vortex_surf, PURPLE, (cx, cy), r - 12)
        pygame.draw.circle(vortex_surf, WHITE, (cx, cy), r - 20)
        
        # Отрисовка летящих искр со световыми шлейфами
        for p in self.portal_particles:
            ratio = p['radius'] / 75.0
            alpha = int((1.0 - ratio) * 220)
            alpha = max(0, min(255, alpha))
            
            px = cx + int(math.cos(p['angle']) * p['radius'])
            py = cy + int(math.sin(p['angle']) * p['radius'])
            
            pygame.draw.circle(vortex_surf, (0, 255, 255, alpha), (px, py), 1)
            tx = px - int(math.cos(p['angle']) * 5)
            ty = py - int(math.sin(p['angle']) * 5)
            pygame.draw.line(vortex_surf, (150, 0, 220, int(alpha * 0.45)), (px, py), (tx, ty), 1)
            
        screen.blit(vortex_surf, (dx - 80, dy - 80), special_flags=pygame.BLEND_RGBA_ADD)
        draw_text(screen, "FINISH", 12, dx, dy - r - 14, GOLD, center=True)
# =====================================================================
# 6. ВРАГИ — АНИМИРОВАННЫЕ И ТЕМАТИЧЕСКИЕ СУЩЕСТВА
# =====================================================================
class Enemy(pygame.sprite.Sprite):
    """Наземный патрулирующий враг. Имеет упругую деформацию при ходьбе."""
    def __init__(self, x, y, pl, pr, dim, speed):
        super().__init__()
        self.rect = pygame.Rect(x, y, 40, 40)
        self.dimension = dim
        self.speed = speed
        self.direction = 1 # 1 - движение вправо, -1 - влево
        self.alive = True
        self.fx = float(x) # Накопитель вещественных координат для плавности хода
        self.pl = pl # Левая граница патрулирования (patrol left)
        self.pr = pr # Правая граница патрулирования (patrol right)
        self.tick = random.randint(0, 100)

    def update(self):
        if not self.alive: 
            return
        self.tick += 1
        
        # Сдвигаем координату и обновляем целый хитбокс
        self.fx += self.speed * self.direction
        self.rect.x = int(self.fx)
        
        # Разворот на левой границе
        if self.rect.x <= self.pl and self.direction == -1:
            self.direction = 1
        # Разворот на правой границе
        elif self.rect.right >= self.pr and self.direction == 1:
            self.direction = -1

    def draw(self, screen, cam_x, current_dim):
        if not self.alive or self.dimension != current_dim: 
            return
        if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
            return
            
        dx = int(self.rect.x - cam_x)
        
        # Рассчитываем деформацию сквиша (Squash & Stretch) по синусоиде во время ходьбы
        bounce = math.sin(self.tick * 0.18)
        squish_y = 1.0 + bounce * 0.06 # Враг сжимается и вытягивается
        squish_x = 1.0 - bounce * 0.06 # Поперечное сжатие обратно пропорционально вертикальному
        
        dw = int(40 * squish_x)
        dh = int(40 * squish_y)
        
        # Корректируем смещение отрисовки, чтобы точка опоры оставалась стабильно по центру снизу
        dx_offset = dx + (40 - dw) // 2
        dy_offset = int(self.rect.y) + (40 - dh)

        if self.dimension == "A":
            # Мир Кибера: Кибер-слайм со встроенными горизонтальными сканерами-полосами
            pygame.draw.rect(screen, (20, 15, 35), (dx_offset, dy_offset, dw, dh), border_radius=6)
            pygame.draw.rect(screen, NEON_PINK, (dx_offset, dy_offset, dw, dh), 2, border_radius=6)
            
            # Рендер внутренних горизонтальных полос развертки
            for sy in range(4, dh - 4, 4):
                pygame.draw.line(screen, (80, 0, 40), (dx_offset + 3, dy_offset + sy), (dx_offset + dw - 3, dy_offset + sy), 1)
                
            # Сдвиг глаз в сторону вектора движения
            ex_center = dx_offset + (int(dw * 0.72) if self.direction == 1 else int(dw * 0.28))
            ey = dy_offset + int(dh * 0.35)
            pygame.draw.circle(screen, CYAN, (ex_center - 5, ey), 4)
            pygame.draw.circle(screen, CYAN, (ex_center + 5, ey), 4)
            pygame.draw.circle(screen, WHITE, (ex_center - 5, ey), 1.5)
            pygame.draw.circle(screen, WHITE, (ex_center + 5, ey), 1.5)
        else:
            # Мир Фэнтези: Каменный голем с полоской лесного мха сверху
            pygame.draw.rect(screen, (90, 80, 75), (dx_offset, dy_offset, dw, dh), border_radius=4)
            pygame.draw.rect(screen, (55, 45, 40), (dx_offset, dy_offset, dw, dh), 2, border_radius=4)
            pygame.draw.rect(screen, (35, 120, 40), (dx_offset + 2, dy_offset + 2, dw - 4, int(dh * 0.2)), border_radius=2) # Мох
            
            # Глаза голема, смещающиеся по направлению хода
            ex_center = dx_offset + (int(dw * 0.72) if self.direction == 1 else int(dw * 0.28))
            ey = dy_offset + int(dh * 0.35)
            pygame.draw.circle(screen, YELLOW, (ex_center - 5, ey), 4)
            pygame.draw.circle(screen, YELLOW, (ex_center + 5, ey), 4)
            pygame.draw.circle(screen, WHITE, (ex_center - 5, ey), 1)
            pygame.draw.circle(screen, WHITE, (ex_center + 5, ey), 1)


class FlyingEnemy(pygame.sprite.Sprite):
    """Летающий враг. Парит по вертикальной синусоиде и анимировано машет крыльями."""
    def __init__(self, x, y, dim, range_y=50, speed=0.05):
        super().__init__()
        self.rect = pygame.Rect(x, y, 30, 30)
        self.dimension = dim
        self.start_y = y
        self.range_y = range_y
        self.speed = speed # Шаг изменения фазы за кадр
        self.tick = random.randint(0, 100)
        self.alive = True

    def update(self):
        if not self.alive: 
            return
        self.tick += 1
        # Вертикальное синусоидальное парение вокруг стартовой высоты
        self.rect.y = int(self.start_y + math.sin(self.tick * self.speed) * self.range_y)

    def draw(self, screen, cam_x, current_dim):
        if not self.alive or self.dimension != current_dim: 
            return
        if self.rect.right - cam_x < 0 or self.rect.left - cam_x > WIDTH:
            return
            
        dx = int(self.rect.x - cam_x)
        dy = int(self.rect.y)
        
        # Расчет высоты взмаха крыльев на основе быстрой синусоиды
        wing_y = int(math.sin(self.tick * 0.22) * 8)
        
        if self.dimension == "A":
            # Мир Кибера: Дрон-перехватчик с неоновыми векторизованными крыльями
            pygame.draw.polygon(screen, CYAN, [(dx, dy + 15), (dx - 12, dy + 4 + wing_y), (dx - 3, dy + 19)])
            pygame.draw.polygon(screen, CYAN, [(dx + 30, dy + 15), (dx + 42, dy + 4 + wing_y), (dx + 33, dy + 19)])
            
            # Корпус в форме ромба
            pygame.draw.polygon(screen, (30, 30, 50), [(dx + 15, dy), (dx + 30, dy + 15), (dx + 15, dy + 30), (dx, dy + 15)])
            pygame.draw.polygon(screen, PURPLE, [(dx + 15, dy), (dx + 30, dy + 15), (dx + 15, dy + 30), (dx, dy + 15)], 2)
            
            # Пульсирующий реакторный объектив по центру дрона
            pulse_r = int(5 + math.sin(self.tick * 0.15) * 1.5)
            pygame.draw.circle(screen, RED, (dx + 15, dy + 15), pulse_r)
            pygame.draw.circle(screen, WHITE, (dx + 13, dy + 13), 2) 
        else:
            # Мир Фэнтези: Лесная гаргулья с деревянным ядром и золотыми крыльями
            pygame.draw.polygon(screen, GOLD, [(dx, dy + 15), (dx - 11, dy + 12 + wing_y), (dx - 2, dy + 18)])
            pygame.draw.polygon(screen, GOLD, [(dx + 30, dy + 15), (dx + 42, dy + 12 + wing_y), (dx + 32, dy + 18)])
            
            # Корпус
            pygame.draw.polygon(screen, (110, 55, 20), [(dx + 15, dy), (dx + 30, dy + 15), (dx + 15, dy + 30), (dx, dy + 15)])
            pygame.draw.polygon(screen, ORANGE, [(dx + 15, dy), (dx + 30, dy + 15), (dx + 15, dy + 30), (dx, dy + 15)], 2)
            
            # Магическая руна голема, пульсирующая золотым сиянием
            pulse_r = int(6 + math.sin(self.tick * 0.12) * 2)
            pygame.draw.circle(screen, (255, 180, 50), (dx + 15, dy + 15), pulse_r + 4, 1) 
            pygame.draw.circle(screen, YELLOW, (dx + 15, dy + 15), pulse_r)
            pygame.draw.circle(screen, WHITE, (dx + 15, dy + 15), int(pulse_r * 0.5))

# =====================================================================
# 7. ИГРОК
# =====================================================================
class Player(pygame.sprite.Sprite):
    """Игрок с продвинутой физикой прыжка (койот-тайм, буферизация ввода), 
    инерцией платформ и визуальными деформациями Squash & Stretch."""
    def __init__(self, x, y):
        super().__init__()
        self.rect = pygame.Rect(x, y, 34, 46)
        # Храним координаты во float, чтобы медленная скорость не терялась из-за округления
        self.fx, self.fy = float(x), float(y)
        self.vx, self.vy, self.platform_vx = 0.0, 0.0, 0.0
        self.on_ground = False
        self.dimension = "A"
        self.is_dead = False
        self.facing = 1          # Направление: 1 - вправо, -1 - влево
        self.tick = 0
        self.coyote = 0          # Таймер возможности прыжка после падения с уступа (в кадрах)
        self.jump_buffer = 0     # Буферизация ввода прыжка перед приземлением (в кадрах)
        self.invincible = 0      # Фреймы неуязвимости при уроне
        self.keys = 0            
        self.trail = []          # Массив координат предыдущих шагов для отрисовки шлейфа
        
        # Переменные Squash & Stretch деформации
        self.squish_x = 1.0
        self.squish_y = 1.0
        self.prev_vy = 0.0       # Скорость на предыдущем кадре для расчета силы удара об землю
        self.land_timer = 0      # Временная заторможенность движения при жестком приземлении

        # Преаллокация поверхностей шлейфа (защита от частых аллокаций памяти и фризов GC)
        self._trail_surf_cyber = pygame.Surface((34, 46), pygame.SRCALPHA)
        pygame.draw.rect(self._trail_surf_cyber, (0, 255, 255), (0, 0, 34, 46), border_radius=4)
        
        self._trail_surf_fantasy = pygame.Surface((34, 46), pygame.SRCALPHA)
        pygame.draw.rect(self._trail_surf_fantasy, (140, 235, 140), (0, 0, 34, 46), border_radius=4)

    def handle_input(self, controls):
        """Опрос клавиатуры с поддержкой переназначенных клавиш и дублирующих стрелок."""
        # Если игрок жестко приземлился, его скорость временно урезается на 60%
        speed_multiplier = 0.4 if self.land_timer > 0 else 1.0
        keys = pygame.key.get_pressed()
        
        # Получаем назначенные бинды или дефолты
        left_key = controls.get("LEFT", pygame.K_a)
        right_key = controls.get("RIGHT", pygame.K_d)
        jump_key = controls.get("JUMP", pygame.K_SPACE)
        
        # Дублируем управление на стрелки по умолчанию
        move_left = keys[left_key] or (left_key == pygame.K_a and keys[pygame.K_LEFT])
        move_right = keys[right_key] or (right_key == pygame.K_d and keys[pygame.K_RIGHT])
        
        # Рассчитываем итоговую горизонтальную скорость
        self.vx = (move_right * PLAYER_SPEED - move_left * PLAYER_SPEED) * speed_multiplier
        
        if self.vx > 0: 
            self.facing = 1
        elif self.vx < 0: 
            self.facing = -1
        
        # Запись прыжка в буфер ввода (дублируется на W и стрелку Вверх)
        is_jumping = keys[jump_key] or (jump_key == pygame.K_SPACE and (keys[pygame.K_w] or keys[pygame.K_UP]))
        if is_jumping:
            self.jump_buffer = JUMP_BUFFER

    def try_jump(self, ps: ParticleSystem):
        """Проверка условий и инициализация прыжка."""
        if self.jump_buffer > 0 and (self.on_ground or self.coyote > 0):
            if self.vy < JUMP_FORCE:
                return False
            self.vy = JUMP_FORCE
            sfx.play('jump')
            
            # Деформируем модельку (вытягиваем вверх при толчке)
            self.squish_y = 1.28
            self.squish_x = 0.72
            
            # Эффект пыли под ногами при прыжке
            col = CYAN if self.dimension == "A" else LIGHT_GREEN
            ps.emit(self.rect.centerx, self.rect.bottom, col, count=8)
            
            self.on_ground = False
            self.coyote, self.jump_buffer = 0, 0 # Сбрасываем триггеры
            return True
        return False

    def switch_dimension(self, future_plats, future_hazards):
        """Проверяет безопасность смены измерения (защита от застревания в объектах)."""
        for p in future_plats:
            if self.rect.colliderect(p.rect):
                return False
        for h in future_hazards:
            if self.rect.colliderect(h.rect):
                return False
        self.dimension = "B" if self.dimension == "A" else "A"
        return True

    def update(self, active_plats, ps: ParticleSystem, controls):
        """Обновление физического состояния, обработка столкновений и таймеров."""
        self.handle_input(controls)
        self.tick += 1
        
        # Декрементируем служебные таймеры
        if self.invincible > 0: self.invincible -= 1
        if self.jump_buffer > 0: self.jump_buffer -= 1
        if self.land_timer > 0: self.land_timer -= 1

        # Запись текущей позиции в историю шлейфа, если игрок двигается
        if abs(self.vx) > 0.2 or abs(self.vy) > 0.2:
            self.trail.append((self.fx + 17, self.fy + 23, self.tick))
        if len(self.trail) > 8: 
            self.trail.pop(0)

        # Сохраняем скорость предыдущего кадра перед обновлением физики
        self.prev_vy = self.vy

        # 1. Горизонтальное перемещение и коллизии
        self.fx += self.vx + self.platform_vx
        self.rect.x = int(self.fx)
        
        # Используем урезанный по высоте хитбокс для проверки стен (исключает цепляние за край пола)
        temp_rect = self.rect.inflate(0, -4) 
        for p in active_plats:
            if temp_rect.colliderect(p.rect):
                if self.vx + self.platform_vx > 0:
                    self.rect.right = p.rect.left
                else:
                    self.rect.left = p.rect.right
                self.fx = float(self.rect.x)
                temp_rect.x = self.rect.x

        # 2. Вертикальное перемещение и коллизии
        prev_on = self.on_ground
        
        # Смещаем хитбокс на 1 пиксель вниз, чтобы проверить, стоим ли мы на опоре
        test_rect = self.rect.copy()
        test_rect.y += 1
        on_solid_ground = False
        for p in active_plats:
            if test_rect.colliderect(p.rect):
                on_solid_ground = True
                break
                
        # Если под ногами есть опора — обнуляем скорость падения
        if on_solid_ground and self.vy >= 0:
            self.vy = 0.0
            self.on_ground = True
        else:
            # Свободное падение с ограничением терминальной скорости
            self.vy = min(self.vy + GRAVITY, TERMINAL_VEL)
            self.on_ground = False
            
        self.fy += self.vy
        self.rect.y = int(self.fy)
        
        standing_on_moving = False
        for p in active_plats:
            if self.rect.colliderect(p.rect):
                if self.vy >= 0: 
                    # Приземление на платформу сверху
                    self.rect.bottom = p.rect.top
                    self.on_ground = True
                    if p.bounce:
                        self.vy = BOUNCE_FORCE # Пружинный батут
                        self.on_ground = False
                    elif isinstance(p, MovingPlatform):
                        self.platform_vx = p.speed_x # Передаем инерцию подвижной платформы
                        standing_on_moving = True
                    else:
                        self.vy, self.platform_vx = 0, 0.0
                else: 
                    # Удар головой снизу. Проверяем перекрытие ребер
                    overlap_left = self.rect.right - p.rect.left
                    overlap_right = p.rect.right - self.rect.left
                    
                    # Плавное «соскальзывание» с углов блоков, если зацепились самым краем
                    if overlap_left < 10: 
                        self.fx -= overlap_left
                        self.rect.x = int(self.fx)
                    elif overlap_right < 10: 
                        self.fx += overlap_right
                        self.rect.x = int(self.fx)
                    else:
                        self.rect.top = p.rect.bottom
                        self.vy = 1
                self.fy = float(self.rect.y)

        # Обработка силы приземления (Squash-сплющивание модели и спавн пыли)
        if self.on_ground and not prev_on:
            impact = abs(self.prev_vy)
            if impact > 2.0:
                self.squish_y = max(0.52, 1.0 - impact * 0.055)
                self.squish_x = min(1.48, 1.0 + impact * 0.055)
                
                col = (0, 220, 220) if self.dimension == "A" else (120, 210, 80)
                ps.emit(self.rect.centerx, self.rect.bottom, col, count=int(impact * 1.5))
                
                if impact > 9.0:
                    self.land_timer = 8 # Жесткое падение оглушает игрока

        # Плавное угасание унаследованной горизонтальной скорости платформы в воздухе
        if not standing_on_moving:
            if self.on_ground:
                self.platform_vx = 0.0
            else:
                self.platform_vx *= 0.95
                if abs(self.platform_vx) < 0.05: 
                    self.platform_vx = 0.0

        # Управление койоти-таймом
        if prev_on and not self.on_ground and self.vy >= 0: 
            self.coyote = COYOTE_FRAMES
        elif self.on_ground: 
            self.coyote = 0
        elif self.coyote > 0: 
            self.coyote -= 1

        # Отрисовка искр под ногами во время активного окна койоти-тайма
        if self.coyote > 0 and self.tick % 3 == 0:
            spark_col = (0, 255, 255) if self.dimension == "A" else GOLD
            ps.emit(self.rect.centerx, self.rect.bottom, spark_col, count=1, vx=random.uniform(-1, 1), vy=random.uniform(-0.5, 0.5))

        self.try_jump(ps)

        # Плавный возврат пропорций модельки к дефолтным (lerp к 1.0)
        self.squish_x += (1.0 - self.squish_x) * 0.16
        self.squish_y += (1.0 - self.squish_y) * 0.16

        # Падение в пропасть
        if self.rect.top > HEIGHT + 80:
            self.is_dead = True

    def draw(self, screen, cam_x, ps):
        # Моргание спрайта во время кадров фрейм-неуязвимости при получении урона
        if self.invincible > 0 and (self.tick // 4) % 2 == 0:
            return

        # Рендерим затухающие шлейфы из кэшированных альфа-поверхностей
        for tx, ty, t_tick in self.trail:
            age = self.tick - t_tick
            if age < 8:
                alpha = int((1.0 - age / 8.0) * 100)
                trail_surf = self._trail_surf_cyber if self.dimension == "A" else self._trail_surf_fantasy
                trail_surf.set_alpha(alpha)
                screen.blit(trail_surf, (int(tx - 17 - cam_x), int(ty - 23)))

        # Вычисляем деформированные габариты для отрисовки
        w = int(34 * self.squish_x)
        h = int(46 * self.squish_y)
        dx = int(self.fx - cam_x) + (34 - w) // 2
        dy = int(self.fy) + (46 - h)

        if self.dimension == "A":  # Кибер-робот
            pygame.draw.rect(screen, (15, 15, 35), (dx, dy, w, h), border_radius=6)
            pygame.draw.rect(screen, CYAN, (dx, dy, w, h), 2, border_radius=6)
            
            # Отрисовка глаза, направленного по вектору взгляда
            eye_x = dx + (int(w * 0.7) if self.facing == 1 else int(w * 0.2))
            eye_y = dy + int(h * 0.25)
            pygame.draw.circle(screen, NEON_PINK, (eye_x, eye_y), 4)
            pygame.draw.circle(screen, WHITE, (eye_x, eye_y), 1.5)
            pygame.draw.line(screen, CYAN, (dx + 4, dy + h - 8), (dx + w - 4, dy + h - 8), 2)
        else:  # Лесной дух
            pygame.draw.rect(screen, (80, 50, 30), (dx, dy, w, h), border_radius=4)
            pygame.draw.rect(screen, LIGHT_GREEN, (dx, dy, w, h), 2, border_radius=4)
            
            # Травяная накидка-треугольник
            pygame.draw.polygon(screen, GREEN, [
                (dx, dy + int(h * 0.3)),
                (dx + w // 2, dy + h),
                (dx + w, dy + int(h * 0.3))
            ])
            
            # Магический золотой глаз
            eye_x = dx + (int(w * 0.7) if self.facing == 1 else int(w * 0.2))
            eye_y = dy + int(h * 0.25)
            pygame.draw.circle(screen, GOLD, (eye_x, eye_y), 3)
            pygame.draw.circle(screen, WHITE, (eye_x, eye_y), 1)

# =====================================================================
# 8. УРОВНИ И ГЕНЕРАЦИЯ — ИГРОВОЙ МИР
# =====================================================================
class Level:
    # Описание структуры каждого из 10 уровней с помощью блочных чанков (кусочков сцены)
    BLUEPRINTS = {
        1: ["lvl1_start", "lvl1_rift_tutorial", "lvl1_inspection_safe", "lvl1_ceiling_lock", "finish_safe"],
        2: ["lvl2_start", "lvl2_alternating_bridge", "lvl2_vertical_climb", "lvl2_chase_run", "finish_safe"],
        3: ["lvl3_start", "lvl3_trampoline_bounce", "lvl3_crumbling_cliffs", "lvl3_climax_leap", "finish_safe"],
        4: ["lvl4_start", "lvl4_laser_corridor", "lvl4_moving_shield_ride", "lvl4_sky_gauntlet", "finish_safe"],
        5: ["lvl5_start", "lvl5_non_linear_puzzle", "lvl5_collapsing_column", "lvl5_final_sprint", "finish_safe"],
        6: ["lvl6_start", "lvl6_crossfire", "lvl6_inspection", "lvl6_climb", "finish_safe"],
        7: ["lvl7_start", "lvl7_labyrinth", "finish_safe"],
        8: ["lvl8_start", "lvl8_ballet_gauntlet", "finish_safe"],
        9: ["lvl9_start", "lvl9_unstable_glitch", "finish_safe"],
        10: ["lvl10_start", "lvl10_sector1_glitch_run", "lvl10_sector2_vertical_abyss", "lvl10_sector3_final_sprint", "finish_safe"]
    }

    def __init__(self, level_num, difficulty):
        self.platforms = []
        self.enemies = []
        self.flying_enemies = []
        self.lasers = []
        self.coins = []
        self.keys = []
        self.doors = []
        self.checkpoints = []
        self.goal = None
        self.start_dimension = "A"
        
        # Корректировка параметров генерации на основе выбранной сложности
        self.pw = 120 if difficulty == "EASY" else (100 if difficulty == "MEDIUM" else 80) # Ширина платформ
        self.gap = 80 if difficulty == "EASY" else (110 if difficulty == "MEDIUM" else 130) # Пропасти
        self.baseline = 420 # Высота основного уровня земли
        self.cursor_x = 0   # Горизонтальный курсор сборки сцены
        
        # Сложностные модификаторы врагов и лазеров
        self.enemy_speed_mod = 0.8 if difficulty == "EASY" else (1.0 if difficulty == "MEDIUM" else 1.3)
        self.laser_interval_mod = 1.3 if difficulty == "EASY" else (1.0 if difficulty == "MEDIUM" else 0.7)
        
        # Фиксируем сид под каждый уровень, чтобы звездное небо генерировалось одинаково
        random.seed(777 + level_num)
        self.stars = []
        for _ in range(35):
            self.stars.append({
                'x': random.randint(0, WIDTH),
                'y': random.randint(0, HEIGHT - 120),
                'size': random.choice([1, 2]),
                'is_cyan': random.random() > 0.5
            })
            
        # Подготовка вспомогательного холста для эффекта дождя и сканирующей CRT-линии (Мир Кибера)
        self.trail_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.scan_line = pygame.Surface((WIDTH, 5), pygame.SRCALPHA)
        pygame.draw.rect(self.scan_line, (0, 255, 255, 18), (0, 2, WIDTH, 1))
        pygame.draw.rect(self.scan_line, (0, 255, 255, 8), (0, 0, WIDTH, 5))
        
        self._build(level_num)

    # --- Вспомогательные хелперы для быстрой сборки чанков ---
    def _plat(self, x, y, w, dim, bounce=False, h=20):
        p = Platform(x, y, w, h, dim, bounce)
        self.platforms.append(p)
        return p

    def _moving_plat(self, x, y, w, dim, move_range, speed, h=20):
        p = MovingPlatform(x, y, w, h, dim, move_range, speed)
        self.platforms.append(p)
        return p

    def _crumbling(self, x, y, w, dim, h=20):
        p = CrumblingPlatform(x, y, w, h, dim)
        self.platforms.append(p)
        return p

    def _coin_row(self, x, y, count, dim):
        for i in range(count):
            self.coins.append(Coin(x + i * 28, y - 20, dim))

    # --- МОДУЛЬНЫЕ ЧАНКИ СЦЕНЫ (Сшиваются горизонтально друг за другом) ---
    def _chunk_lvl1_start(self):
        self._plat(0, self.baseline, 350, "B", h=30)
        self._coin_row(60, self.baseline, 3, "B")
        self.start_dimension = "B"
        self.cursor_x = 350

    def _chunk_lvl1_rift_tutorial(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, self.pw, "B")
        self._plat(x + self.pw + self.gap, self.baseline - 40, self.pw, "A")
        self._coin_row(x + self.pw + self.gap + 10, self.baseline - 40, 2, "A")
        self._plat(x + 2 * (self.pw + self.gap), self.baseline, self.pw, "B")
        self.cursor_x = x + 2 * (self.pw + self.gap) + self.pw

    def _chunk_lvl1_inspection_safe(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 160, "ALL")
        self.checkpoints.append(Checkpoint(x + 40, self.baseline - 64))
        self.cursor_x = x + 160

    def _chunk_lvl1_ceiling_lock(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 300, "ALL")
        self._plat(x + 100, 0, 100, "ALL", h=self.baseline - 90)
        self.doors.append(Door(x + 130, self.baseline - 60, 20, 60, "ALL"))
        self._plat(x + 30, self.baseline - 160, 80, "B")
        self.keys.append(Key(x + 50, self.baseline - 200, "B"))
        self.cursor_x = x + 300

    def _chunk_lvl2_start(self):
        self._plat(self.cursor_x, self.baseline, 200, "ALL", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 50, self.baseline - 64))
        self.cursor_x += 200

    def _chunk_lvl2_alternating_bridge(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 300, "B")
        self._plat(x + 120, self.baseline - 140, 40, "B", h=140)
        self._plat(x + 80, self.baseline - 150, 120, "B")
        self.enemies.append(Enemy(x + 40, self.baseline - 40, x, x + 300, "A", 2.0 * self.enemy_speed_mod))
        self.cursor_x = x + 300

    def _chunk_lvl2_vertical_climb(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "B")
        self._plat(x + 100, self.baseline - 80, 60, "A")
        self._plat(x + 180, self.baseline - 160, 60, "B")
        self._plat(x + 260, self.baseline - 240, 60, "A")
        self._coin_row(x + 270, self.baseline - 240, 2, "A")
        self._plat(x + 360, self.baseline, 120, "ALL")
        self.cursor_x = x + 360 + 120

    def _chunk_lvl2_chase_run(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "ALL")
        self._moving_plat(x + 100, self.baseline, 100, "A", 200, 2.0)
        self._plat(x + 100, self.baseline, 200, "B")
        self.enemies.append(Enemy(x + 120, self.baseline - 40, x + 100, x + 300, "B", 1.8 * self.enemy_speed_mod))
        self._plat(x + 340, self.baseline, 100, "ALL")
        self.cursor_x = x + 340 + 100

    def _chunk_lvl3_start(self):
        self._plat(self.cursor_x, self.baseline, 160, "ALL", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 30, self.baseline - 64))
        self.cursor_x += 160

    def _chunk_lvl3_trampoline_bounce(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "B", bounce=True)
        self._plat(x + 120, self.baseline - 240, 100, "A")
        self._coin_row(x + 130, self.baseline - 240, 2, "A")
        self._plat(x + 280, self.baseline, 100, "ALL")
        self.cursor_x = x + 280 + 100

    def _chunk_lvl3_crumbling_cliffs(self):
        x = self.cursor_x + self.gap
        self._crumbling(x, self.baseline - 30, 80, "B")
        self._crumbling(x + 110, self.baseline - 90, 80, "A")
        self._crumbling(x + 220, self.baseline - 40, 80, "B")
        self._plat(x + 330, self.baseline, 120, "ALL")
        self.cursor_x = x + 330 + 120

    def _chunk_lvl3_climax_leap(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "ALL")
        self._plat(x + 100, self.baseline - 70, 60, "A")
        self._plat(x + 180, self.baseline - 140, 60, "B")
        self._plat(x + 260, self.baseline - 210, 60, "A")
        self._plat(x + 360, self.baseline, 150, "ALL")
        self.cursor_x = x + 360 + 150

    def _chunk_lvl4_start(self):
        self._plat(self.cursor_x, self.baseline, 180, "ALL", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 40, self.baseline - 64))
        self.cursor_x += 180

    def _chunk_lvl4_laser_corridor(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 120, "ALL")
        self._plat(x, self.baseline - 140, 120, "ALL")
        self._plat(x + 140, self.baseline, 280, "ALL")
        self.lasers.append(Laser(x + 200, self.baseline - 120, 120, "A", interval=int(60 * self.laser_interval_mod), offset=0))
        self.lasers.append(Laser(x + 280, self.baseline - 120, 120, "B", interval=int(60 * self.laser_interval_mod), offset=30))
        self.cursor_x = x + 420

    def _chunk_lvl4_moving_shield_ride(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "ALL")
        self.lasers.append(Laser(x + 200, self.baseline - 140, 140, "A", interval=int(50 * self.laser_interval_mod), offset=0))
        self._moving_plat(x + 90, self.baseline, 90, "A", 220, 2.3)
        self._plat(x + 420, self.baseline, 100, "ALL")
        self.cursor_x = x + 420 + 100

    def _chunk_lvl4_sky_gauntlet(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "ALL")
        self.flying_enemies.append(FlyingEnemy(x + 120, self.baseline - 130, "A", range_y=60, speed=0.07 * self.enemy_speed_mod))
        self._plat(x + 100, self.baseline, 120, "B")
        self._coin_row(x + 120, self.baseline, 2, "B")
        self._plat(x + 260, self.baseline, 100, "ALL")
        self.cursor_x = x + 260 + 100

    def _chunk_lvl5_start(self):
        self._plat(self.cursor_x, self.baseline, 150, "ALL", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 30, self.baseline - 64))
        self.cursor_x += 150

    def _chunk_lvl5_non_linear_puzzle(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 100, "B")
        self._plat(x + 120, self.baseline + 100, 100, "B", bounce=True)
        self._plat(x + 120, self.baseline + 100, 100, "A")
        self.keys.append(Key(x + 160, self.baseline + 60, "A"))
        self._plat(x + 260, self.baseline, 200, "ALL")
        self._plat(x + 320, 0, 100, "ALL", h=self.baseline - 90)
        self.doors.append(Door(x + 350, self.baseline - 60, 20, 60, "ALL"))
        self.cursor_x = x + 460

    def _chunk_lvl5_collapsing_column(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "ALL")
        self.flying_enemies.append(FlyingEnemy(x + 150, self.baseline - 150, "A", range_y=40, speed=0.08 * self.enemy_speed_mod))
        self._crumbling(x + 100, self.baseline - 40, 60, "B")
        self._crumbling(x + 190, self.baseline - 80, 60, "B")
        self._plat(x + 280, self.baseline, 120, "ALL")
        self.cursor_x = x + 280 + 120

    def _chunk_lvl5_final_sprint(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "ALL")
        self._plat(x + 100, self.baseline, 60, "B", bounce=True)
        self.lasers.append(Laser(x + 180, self.baseline - 120, 120, "ALL", interval=int(50 * self.laser_interval_mod), offset=0))
        self._plat(x + 220, self.baseline, 60, "A", bounce=True)
        self._plat(x + 320, self.baseline, 120, "ALL")
        self.cursor_x = x + 320 + 120

    def _chunk_lvl6_start(self):
        self._plat(self.cursor_x, self.baseline, 200, "B", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 50, self.baseline - 64))
        self.start_dimension = "B"
        self.cursor_x += 200

    def _chunk_lvl6_crossfire(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "ALL")
        self._moving_plat(x + 100, self.baseline, 90, "A", 220, 2.0)
        self.lasers.append(Laser(x + 210, self.baseline - 140, 140, "B", interval=int(60 * self.laser_interval_mod), offset=0))
        self._plat(x + 440, self.baseline, 100, "ALL")
        self.cursor_x = x + 440 + 100

    def _chunk_lvl6_inspection(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 120, "ALL")
        self._plat(x + 30, self.baseline - 100, 60, "ALL")
        self.cursor_x = x + 120

    def _chunk_lvl6_climb(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "B")
        self._moving_plat(x + 90, self.baseline - 60, 80, "A", 120, 1.8)
        self._moving_plat(x + 220, self.baseline - 140, 80, "B", 120, -1.8)
        self._plat(x + 440, self.baseline, 120, "ALL")
        self.cursor_x = x + 440 + 120

    def _chunk_lvl7_start(self):
        self._plat(self.cursor_x, self.baseline, 180, "ALL", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 40, self.baseline - 64))
        self.cursor_x += 180

    def _chunk_lvl7_labyrinth(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 150, "ALL")
        self._plat(x + 180, self.baseline + 100, 100, "B")
        self.keys.append(Key(x + 220, self.baseline + 60, "B"))
        self._plat(x + 180, self.baseline + 100, 100, "A", bounce=True)
        self._plat(x + 50, self.baseline - 80, 80, "A")
        self._plat(x + 120, self.baseline - 160, 100, "B")
        self.keys.append(Key(x + 160, self.baseline - 200, "A"))
        self._plat(x + 300, self.baseline, 150, "ALL")
        self._plat(x + 300, 0, 150, "ALL", h=self.baseline - 90)
        self.doors.append(Door(x + 320, self.baseline - 60, 20, 60, "ALL"))
        self.doors.append(Door(x + 350, self.baseline - 60, 20, 60, "ALL"))
        self.cursor_x = x + 450

    def _chunk_lvl8_start(self):
        self._plat(self.cursor_x, self.baseline, 150, "ALL", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 30, self.baseline - 64))
        self.cursor_x += 150

    def _chunk_lvl8_ballet_gauntlet(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 80, "B", bounce=True)
        self.flying_enemies.append(FlyingEnemy(x + 120, self.baseline - 220, "A", range_y=60, speed=0.08 * self.enemy_speed_mod))
        self.lasers.append(Laser(x + 200, self.baseline - 260, 160, "B", interval=int(50 * self.laser_interval_mod), offset=0))
        self.lasers.append(Laser(x + 320, self.baseline - 260, 160, "A", interval=int(50 * self.laser_interval_mod), offset=25))
        self._plat(x + 360, self.baseline, 150, "ALL")
        self.cursor_x = x + 360 + 150

    def _chunk_lvl9_start(self):
        self._plat(self.cursor_x, self.baseline, 150, "ALL", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 30, self.baseline - 64))
        self.cursor_x += 150

    def _chunk_lvl9_unstable_glitch(self):
        x = self.cursor_x + self.gap
        self._crumbling(x, self.baseline, 80, "B")
        self._moving_plat(x + 100, self.baseline - 60, 80, "A", 140, 2.2)
        self._crumbling(x + 320, self.baseline, 80, "B")
        self._plat(x + 420, self.baseline, 120, "ALL")
        self.cursor_x = x + 420 + 120

    def _chunk_lvl10_start(self):
        self._plat(self.cursor_x, self.baseline, 150, "ALL", h=30)
        self.checkpoints.append(Checkpoint(self.cursor_x + 30, self.baseline - 64))
        self.cursor_x += 150

    def _chunk_lvl10_sector1_glitch_run(self):
        x = self.cursor_x + self.gap
        for i in range(3):
            self._crumbling(x + i * 110, self.baseline, 80, "B")
        self.lasers.append(Laser(x + 90, self.baseline - 120, 120, "A", interval=int(50 * self.laser_interval_mod), offset=0))
        self.lasers.append(Laser(x + 200, self.baseline - 120, 120, "A", interval=int(50 * self.laser_interval_mod), offset=25))
        self._plat(x + 330, self.baseline, 120, "ALL")
        self.checkpoints.append(Checkpoint(x + 350, self.baseline - 64))
        self.cursor_x = x + 330 + 120

    def _chunk_lvl10_sector2_vertical_abyss(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 100, "ALL")
        self._plat(x + 30, self.baseline - 80, 60, "A")
        self._plat(x + 100, self.baseline - 160, 60, "B")
        self.keys.append(Key(x + 120, self.baseline - 200, "A"))
        self._plat(x + 220, self.baseline + 100, 80, "B", bounce=True)
        self._plat(x + 220, self.baseline + 100, 80, "A")
        self.keys.append(Key(x + 250, self.baseline + 60, "A"))
        self._plat(x + 360, self.baseline, 180, "ALL")
        self._plat(x + 360, 0, 180, "ALL", h=self.baseline - 90)
        self.doors.append(Door(x + 400, self.baseline - 60, 20, 60, "ALL"))
        self.doors.append(Door(x + 430, self.baseline - 60, 20, 60, "ALL"))
        self.cursor_x = x + 360 + 180

    def _chunk_lvl10_sector3_final_sprint(self):
        x = self.cursor_x + self.gap
        self._plat(x, self.baseline, 400, "ALL")
        self.lasers.append(Laser(x + 100, self.baseline - 120, 120, "A", interval=int(40 * self.laser_interval_mod), offset=0))
        self.lasers.append(Laser(x + 180, self.baseline - 120, 120, "B", interval=int(40 * self.laser_interval_mod), offset=15))
        self.lasers.append(Laser(x + 260, self.baseline - 120, 120, "A", interval=int(40 * self.laser_interval_mod), offset=30))
        self.cursor_x = x + 400

    def _chunk_finish_safe(self):
        x = self.cursor_x + self.gap * 2
        self._plat(x, self.baseline, 350, "ALL", h=25)
        self._coin_row(x + 50, self.baseline, 4, "ALL")
        self.goal = Goal(x + 270, self.baseline - 64)
        self.level_width = x + 380

    def _build(self, level_num):
        """Парсинг схемы и склеивание чанков горизонтально друг за другом."""
        blueprint = self.BLUEPRINTS.get(level_num, self.BLUEPRINTS[1])
        dispatch = {
            "lvl1_start": self._chunk_lvl1_start,
            "lvl1_rift_tutorial": self._chunk_lvl1_rift_tutorial,
            "lvl1_inspection_safe": self._chunk_lvl1_inspection_safe,
            "lvl1_ceiling_lock": self._chunk_lvl1_ceiling_lock,
            "finish_safe": self._chunk_finish_safe,
            "lvl2_start": self._chunk_lvl2_start,
            "lvl2_alternating_bridge": self._chunk_lvl2_alternating_bridge,
            "lvl2_vertical_climb": self._chunk_lvl2_vertical_climb,
            "lvl2_chase_run": self._chunk_lvl2_chase_run,
            "lvl3_start": self._chunk_lvl3_start,
            "lvl3_trampoline_bounce": self._chunk_lvl3_trampoline_bounce,
            "lvl3_crumbling_cliffs": self._chunk_lvl3_crumbling_cliffs,
            "lvl3_climax_leap": self._chunk_lvl3_climax_leap,
            "lvl4_start": self._chunk_lvl4_start,
            "lvl4_laser_corridor": self._chunk_lvl4_laser_corridor,
            "lvl4_moving_shield_ride": self._chunk_lvl4_moving_shield_ride,
            "lvl4_sky_gauntlet": self._chunk_lvl4_sky_gauntlet,
            "lvl5_start": self._chunk_lvl5_start,
            "lvl5_non_linear_puzzle": self._chunk_lvl5_non_linear_puzzle,
            "lvl5_collapsing_column": self._chunk_lvl5_collapsing_column,
            "lvl5_final_sprint": self._chunk_lvl5_final_sprint,
            "lvl6_start": self._chunk_lvl6_start,
            "lvl6_crossfire": self._chunk_lvl6_crossfire,
            "lvl6_inspection": self._chunk_lvl6_inspection,
            "lvl6_climb": self._chunk_lvl6_climb,
            "lvl7_start": self._chunk_lvl7_start,
            "lvl7_labyrinth": self._chunk_lvl7_labyrinth,
            "lvl8_start": self._chunk_lvl8_start,
            "lvl8_ballet_gauntlet": self._chunk_lvl8_ballet_gauntlet,
            "lvl9_start": self._chunk_lvl9_start,
            "lvl9_unstable_glitch": self._chunk_lvl9_unstable_glitch,
            "lvl10_start": self._chunk_lvl10_start,
            "lvl10_sector1_glitch_run": self._chunk_lvl10_sector1_glitch_run,
            "lvl10_sector2_vertical_abyss": self._chunk_lvl10_sector2_vertical_abyss,
            "lvl10_sector3_final_sprint": self._chunk_lvl10_sector3_final_sprint,
        }
        for chunk_name in blueprint:
            if chunk_name in dispatch:
                dispatch[chunk_name]()

    def draw_bg(self, screen, dim, cam_x):
        """Отрисовка многослойного параллаксного фона в зависимости от текущего мира."""
        if not hasattr(self, '_bg_tick'):
            self._bg_tick = 0
        self._bg_tick += 1

        # Кэшируем тяжелые фоновые поверхности, чтобы не нагружать процессор графическим перерендером
        if not hasattr(self, '_parallax_cache'):
            self._parallax_cache = {}

        if dim == "A":
            if "cyber" not in self._parallax_cache:
                # 1. Заливка градиентного неба (Кибермир)
                sky = pygame.Surface((WIDTH, HEIGHT))
                for y in range(HEIGHT):
                    ratio = y / HEIGHT
                    glow_ratio = math.pow(ratio, 2.0)
                    r = int(10 + glow_ratio * 170)
                    g = int(8 + glow_ratio * 12)
                    b = int(24 + glow_ratio * 96)
                    pygame.draw.line(sky, (r, g, b), (0, y), (WIDTH, y))
                
                # 2. Мягкое неоновое солнце (эффект Bloom)
                sun_glow = pygame.Surface((350, 350), pygame.SRCALPHA)
                for r in range(175, 0, -2):
                    ratio = r / 175
                    alpha = int((1.0 - ratio) ** 2.2 * 110)
                    pygame.draw.circle(sun_glow, (255, 20, 140, alpha), (175, 175), r)
                sky.blit(sun_glow, (WIDTH // 2 - 175, 165))

                sun = pygame.Surface((200, 200), pygame.SRCALPHA)
                for sy in range(200):
                    sun_ratio = sy / 200.0
                    r = int(255 - sun_ratio * 35)
                    g = int(230 - sun_ratio * 195)
                    b = int(60 + sun_ratio * 75)
                    
                    dy = sy - 100
                    half_width = int(math.sqrt(max(0, 10000 - dy*dy)))
                    if half_width > 0:
                        pygame.draw.line(sun, (r, g, b, 255), (100 - half_width, sy), (100 + half_width, sy))
                sky.blit(sun, (WIDTH // 2 - 100, 240))
                
                # 3. Дальний слой: черные силуэты небоскребов со светящимися окнами
                far_towers = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                random.seed(101)
                cx = 0
                while cx < WIDTH:
                    w = random.randint(45, 85)
                    h = random.randint(180, 310)
                    pygame.draw.rect(far_towers, (14, 10, 26), (cx, HEIGHT - h, w, h))
                    for wy in range(HEIGHT - h + 15, HEIGHT - 15, 28):
                        for wx in range(cx + 8, cx + w - 8, 18):
                            if random.random() > 0.65:
                                pygame.draw.rect(far_towers, (255, 220, 90, 150), (wx, wy, 2, 4))
                    cx += w + random.randint(-5, 15)

                # 4. Средний слой: темные контуры зданий с розовой неоновой окантовкой
                mid = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                random.seed(202)
                cx = 0
                while cx < WIDTH:
                    w = random.randint(55, 95)
                    h = random.randint(110, 220)
                    rect = (cx, HEIGHT - h, w, h)
                    pygame.draw.rect(mid, (22, 14, 38), rect)
                    pygame.draw.rect(mid, (255, 0, 128), rect, 1)
                    cx += w + random.randint(10, 35)

                # 5. Ближний слой: передний план построек с яркой голубой окантовкой
                near = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                random.seed(303)
                cx = 0
                while cx < WIDTH:
                    w = random.randint(70, 130)
                    h = random.randint(60, 140)
                    rect = (cx, HEIGHT - h, w, h)
                    pygame.draw.rect(near, (28, 18, 44), rect)
                    pygame.draw.rect(near, (0, 255, 240), rect, 2)
                    cx += w + random.randint(20, 60)

                self._parallax_cache["cyber"] = (sky, far_towers, mid, near)

            sky, far_towers, mid, near = self._parallax_cache["cyber"]
            screen.blit(sky, (0, 0))
            
            # Рендерим мерцающие звезды
            for star in self.stars:
                pulse = int(math.sin(self._bg_tick * 0.02 + star['x']) * 60) + 190
                pulse = max(100, min(255, pulse))
                col = (0, 255, 255, pulse) if star['is_cyan'] else (255, 0, 128, pulse)
                pygame.draw.circle(screen, col, (star['x'], star['y']), star['size'])
            
            # Тилинг (зацикливание) текстур по горизонтали через сдвиг на остаток от деления
            far_t_offset = -(cam_x // 12) % WIDTH
            screen.blit(far_towers, (far_t_offset - WIDTH, 0))
            screen.blit(far_towers, (far_t_offset, 0))
            
            mid_offset = -(cam_x // 6) % WIDTH
            screen.blit(mid, (mid_offset - WIDTH, 0))
            screen.blit(mid, (mid_offset, 0))
            
            near_offset = -(cam_x // 3) % WIDTH
            screen.blit(near, (near_offset - WIDTH, 0))
            screen.blit(near, (near_offset, 0))

            # Трехмерная неоновая сетка на горизонте с перспективным искажением (нелинейный шаг по экспоненте)
            horizon_y = HEIGHT - 180
            grid_surf = pygame.Surface((WIDTH, HEIGHT - horizon_y), pygame.SRCALPHA)
            grid_surf.fill((0, 0, 0, 0))
            for i in range(5):
                ly = int(((i + (self._bg_tick * 0.015) % 1.0) / 5.0) ** 2.2 * (HEIGHT - horizon_y))
                alpha = int((ly / (HEIGHT - horizon_y)) * 20)
                pygame.draw.line(grid_surf, (150, 0, 220, alpha), (0, ly), (WIDTH, ly), 1)
            for x in range(-150, WIDTH + 150, 65):
                dx = x - WIDTH // 2
                start_x = WIDTH // 2 + dx * 0.15
                pygame.draw.line(grid_surf, (80, 0, 120, 15), (start_x, 0), (x, HEIGHT - horizon_y), 1)
            screen.blit(grid_surf, (0, horizon_y))

            # Эффект вертикального неонового дождя (расчет движения векторов)
            self.trail_surf.fill((0, 0, 0, 0))
            for i in range(14):
                speed_y = 1.6 + (i % 3) * 0.4
                speed_x = speed_y * 0.22 
                
                rx = int((i * 157 + self._bg_tick * speed_x) % (WIDTH + 100)) - 50
                ry = int((i * 211 + self._bg_tick * speed_y) % HEIGHT)
                
                p_ratio = ry / HEIGHT
                trail_len_y = int(p_ratio * 30)
                trail_len_x = int(trail_len_y * 0.22)
                
                if trail_len_y > 1:
                    pygame.draw.line(self.trail_surf, (0, 230, 230, int(p_ratio * 70)), 
                                     (rx - trail_len_x, ry - trail_len_y), (rx, ry), 1)
                    
                if 0 <= rx < WIDTH and 0 <= ry < HEIGHT:
                    pygame.draw.circle(self.trail_surf, (220, 255, 255), (rx, ry), 1)
                    
            screen.blit(self.trail_surf, (0, 0))

            # Пролетающие на заднем плане метеоры
            for i in range(4):
                spd = 2.2 + i * 0.7
                mx = int((i * 280 + self._bg_tick * spd) % (WIDTH + 100)) - 50
                my = 110 + i * 45
                pygame.draw.circle(screen, (0, 255, 240), (mx, my), 2)
                pygame.draw.line(screen, (0, 130, 130), (mx - 15, my), (mx, my), 1)

            # Бегущие горизонтальные CRT помехи на экране
            scan_y = (self._bg_tick * 1.4) % HEIGHT
            screen.blit(self.scan_line, (0, scan_y))
        else:
            if "fantasy" not in self._parallax_cache:
                # 1. Заливка фэнтезийного сумеречного неба
                sky = pygame.Surface((WIDTH, HEIGHT))
                for y in range(HEIGHT):
                    ratio = y / HEIGHT
                    c = (int(90 + ratio*60), int(45 + ratio*95), int(120 + ratio * 40))
                    pygame.draw.line(sky, c, (0, y), (WIDTH, y))
                
                # 2. Огромная луна с мягким свечением
                moon = pygame.Surface((160, 160), pygame.SRCALPHA)
                for r in range(65, 0, -1):
                    alpha = int((1.0 - (r/65)) * 140)
                    pygame.draw.circle(moon, (255, 200, 250, alpha), (80, 80), r + 15)
                pygame.draw.circle(moon, (255, 255, 240), (80, 80), 50)
                sky.blit(moon, (WIDTH - 240, 50))

                # 3. Дальний слой холмов
                far = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                random.seed(101)
                pts = [(0, HEIGHT)]
                for x in range(0, WIDTH + 120, 120):
                    y = HEIGHT - 210 - int(math.sin(x * 0.004) * 55) - random.randint(-20, 20)
                    pts.append((x, y))
                pts.append((WIDTH, HEIGHT))
                pygame.draw.polygon(far, (100, 75, 120), pts)

                # 4. Средний слой холмов
                mid = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                random.seed(202)
                pts = [(0, HEIGHT)]
                for x in range(0, WIDTH + 90, 90):
                    y = HEIGHT - 150 - int(math.sin(x * 0.008) * 45) - random.randint(-15, 15)
                    pts.append((x, y))
                pts.append((WIDTH, HEIGHT))
                pygame.draw.polygon(mid, (65, 80, 105), pts)

                # 5. Ближний слой: скалы и силуэты сосен на вершинах холмов
                near = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
                random.seed(303)
                pts = [(0, HEIGHT)]
                for x in range(0, WIDTH + 65, 65):
                    y = HEIGHT - 90 - int(math.cos(x * 0.012) * 35) - random.randint(-10, 10)
                    pts.append((x, y))
                pts.append((WIDTH, HEIGHT))
                pygame.draw.polygon(near, (42, 68, 85), pts) 
                
                # Рендер силуэтов деревьев на ближних холмах скал
                for px, py in pts[1:-1]:
                    if py < HEIGHT:
                        pygame.draw.circle(near, (32, 55, 72), (px, py + 2), 12)
                        pygame.draw.circle(near, (32, 55, 72), (px - 7, py + 5), 8)
                        pygame.draw.circle(near, (32, 55, 72), (px + 7, py + 5), 8)
                        pygame.draw.circle(near, (42, 75, 95), (px - 2, py - 1), 4)

                self._parallax_cache["fantasy"] = (sky, far, mid, near)

            sky, far, mid, near = self._parallax_cache["fantasy"]
            screen.blit(sky, (0, 0))
            
            # Тилинг слоев фэнтези горизонта
            far_offset = -(cam_x // 12) % WIDTH
            screen.blit(far, (far_offset - WIDTH, 0))
            screen.blit(far, (far_offset, 0))
            
            mid_offset = -(cam_x // 6) % WIDTH
            screen.blit(mid, (mid_offset - WIDTH, 0))
            screen.blit(mid, (mid_offset, 0))
            
            near_offset = -(cam_x // 3) % WIDTH
            screen.blit(near, (near_offset - WIDTH, 0))
            screen.blit(near, (near_offset, 0))

            # Лепестки сакуры, плывущие по ветру (парящая синусоида)
            for i in range(12):
                mx = int((i * 140 - self._bg_tick * 0.95) % (WIDTH + 60)) - 30
                my = int((40 + i * 42 + math.sin(self._bg_tick * 0.025 + i) * 22) % (HEIGHT - 90))
                pygame.draw.ellipse(screen, (255, 150, 185), (mx, my, 6, 4))

            # Поднимающиеся в небо светлячки (световые споры леса)
            for i in range(6):
                mx = int((i * 190 + math.sin(self._bg_tick * 0.03 + i) * 25) % WIDTH)
                my = int((HEIGHT - 40 - self._bg_tick * 0.6 - i * 85) % HEIGHT)
                pygame.draw.circle(screen, (255, 215, 80), (mx, my), 2)
# =====================================================================
# 9. ИНТЕРФЕЙС И МЕНЮ
# =====================================================================
class HUD:
    """Игровой интерфейс (HUD). Отображает уровень, измерение, очки, монеты, жизни и кулдаун сдвига."""
    def __init__(self):
        # Заранее создаем и кэшируем подложки плашек HUD во избежание тяжелого рендеринга каждый кадр
        self.bar_cyber = pygame.Surface((WIDTH, 52), pygame.SRCALPHA).convert_alpha()
        self.bar_cyber.fill((10, 8, 26, 210))
        pygame.draw.line(self.bar_cyber, CYAN, (0, 50), (WIDTH, 50), 2)
        pygame.draw.line(self.bar_cyber, (0, 45, 45), (0, 1), (WIDTH, 1), 1)
        pygame.draw.rect(self.bar_cyber, CYAN, (8, 12, 6, 28), border_radius=2)
        pygame.draw.rect(self.bar_cyber, NEON_PINK, (WIDTH - 14, 12, 6, 28), border_radius=2)
        
        self.bar_fantasy = pygame.Surface((WIDTH, 52), pygame.SRCALPHA).convert_alpha()
        self.bar_fantasy.fill((10, 8, 26, 210))
        pygame.draw.line(self.bar_fantasy, (45, 125, 45), (0, 50), (WIDTH, 50), 2)
        pygame.draw.line(self.bar_fantasy, (110, 90, 20), (0, 1), (WIDTH, 1), 1)
        pygame.draw.circle(self.bar_fantasy, (120, 220, 80), (12, 26), 5)
        pygame.draw.circle(self.bar_fantasy, (120, 220, 80), (WIDTH - 12, 26), 5)

    def _draw_pixel_heart(self, surf, x, y, size=11, active=True, tick=0):
        """Отрисовка векторного пиксельного сердечка с эффектом пульсации (биением сердца)."""
        cx, cy = x + 10, y + 10
        if not active:
            # Серое разбитое сердечко для потерянной жизни
            col = (90, 90, 105)
            pts = [(cx, cy - size//3), (cx - size//2, cy - size), (cx - size, cy - size//3), (cx, cy + size), (cx + size, cy - size//3), (cx + size//2, cy - size)]
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.polygon(surf, (40, 40, 50), pts, 1)
            pygame.draw.line(surf, (40, 40, 50), (cx, cy - 3), (cx - 3, cy + 3), 1)
            pygame.draw.line(surf, (40, 40, 50), (cx - 3, cy + 3), (cx + 1, cy + 7), 1)
        else:
            # Красное бьющееся сердце (частота и фаза пульса рассчитываются синусоидой с офсетом X)
            pulse = 1.0 + math.sin(tick * 0.12 + x * 0.05) * 0.12
            p_size = int(size * pulse)
            col = (255, 25, 95) 
            
            pts = [
                (cx, cy - p_size//3),
                (cx - p_size//2, cy - p_size),
                (cx - p_size, cy - p_size//3),
                (cx, cy + p_size),
                (cx + p_size, cy - p_size//3),
                (cx + p_size//2, cy - p_size)
            ]
            
            pygame.draw.polygon(surf, col, pts)
            pygame.draw.polygon(surf, (255, 130, 180), pts, 2) 
            pygame.draw.circle(surf, WHITE, (cx - p_size//3 - 1, cy - p_size//3 - 2), 2) # Блик

    def draw(self, screen, player, level_num, score, lives, max_lives, coins_total, coins_collected, dim_cooldown, timer_sec):
        anim_tick = pygame.time.get_ticks() // 16
        
        # Выбираем подложку панели HUD в зависимости от мира
        bar = self.bar_cyber if player.dimension == "A" else self.bar_fantasy
        screen.blit(bar, (0, 0))

        col = CYAN if player.dimension == "A" else GREEN
        dim_label = "◈ CYBER" if player.dimension == "A" else "◈ FANTASY"

        lbl_col = col
        if player.dimension == "A" and (anim_tick // 8) % 15 == 0:
            lbl_col = (0, 120, 120)
            
        # Рендерим тексты статистики
        draw_text(screen, f"Lvl {level_num}/10", 18, 22, 11, WHITE)
        draw_text(screen, dim_label, 18, 22, 28, lbl_col)
        
        draw_text(screen, f"Очки: {score}", 18, 175, 11, GOLD)
        draw_text(screen, f"Монеты: {coins_collected}/{coins_total}", 18, 175, 28, YELLOW)

        # Рисуем крутящиеся золотые маркеры-звезды около очков
        star_angle = anim_tick * 0.05
        sc_x, sc_y = 154, 38
        for a in [0, math.pi / 2]:
            dx = int(math.cos(star_angle + a) * 4)
            dy = int(math.sin(star_angle + a) * 4)
            pygame.draw.line(screen, GOLD, (sc_x - dx, sc_y - dy), (sc_x + dx, sc_y + dy), 2)

        if player.keys > 0:
            draw_text(screen, f"Ключи: {player.keys}", 18, 385, 28, GOLD)

        # Вывод сердечек здоровья игрока
        for i in range(max_lives):
            is_active = i < lives
            self._draw_pixel_heart(screen, WIDTH // 2 - 80 + i * 36, 12, size=11, active=is_active, tick=anim_tick)

        # Секундомер с опасной красной индикацией менее 30 секунд
        tc = YELLOW if timer_sec > 30 else RED
        cx, cy = WIDTH - 150, 18
        pygame.draw.circle(screen, GOLD, (cx, cy), 7, 2)
        pygame.draw.line(screen, GOLD, (cx, cy - 7), (cx, cy - 10), 2)
        pygame.draw.line(screen, tc, (cx, cy), (cx, cy - 4), 2)
        pygame.draw.line(screen, tc, (cx, cy), (cx + 3, cy), 1)
        
        draw_text(screen, f"{timer_sec}s", 18, WIDTH - 134, 11, tc)

        # Полоса индикации перезарядки сдвига измерения (Shift)
        bar_w = 140
        ratio = 1 - dim_cooldown / 20
        bar_col = col
        if ratio >= 1.0:
            pulse_val = int(180 + math.sin(anim_tick * 0.2) * 75)
            bar_col = (0, pulse_val, pulse_val) if player.dimension == "A" else (pulse_val // 2, pulse_val, pulse_val // 2)
            
        pygame.draw.rect(screen, DARK_GRAY, (WIDTH - 165, 28, bar_w, 10), border_radius=4)
        
        if ratio > 0.0:
            r_width = int(bar_w * ratio)
            safe_radius = min(4, r_width // 2)
            pygame.draw.rect(screen, bar_col, (WIDTH - 165, 28, r_width, 10), border_radius=safe_radius)
            
        pygame.draw.rect(screen, col, (WIDTH - 165, 28, bar_w, 10), 1, border_radius=4)
        
        draw_text(screen, "[SHIFT]", 13, WIDTH - 212, 26, col if ratio >= 1.0 else GRAY)


class Menu:
    """Главное меню игры. Отрисовывает анимированные сетки, радары, глитч-заголовок и кнопки."""
    DIFFS = ["EASY", "MEDIUM", "HARD"]
    DIFF_COLORS = [GREEN, YELLOW, RED]

    def __init__(self):
        self.diff_idx = 1
        self.selected = 0
        self.rects = [pygame.Rect(0, 0, 0, 0)] * 4 # Храним области хитбоксов кнопок меню
        self.tick = 0

        # Отдельный независимый сид для звезд в меню
        local_rand = random.Random(999)
        self.stars = []
        for _ in range(25):
            self.stars.append({
                'x': local_rand.randint(0, WIDTH),
                'y': local_rand.randint(0, HEIGHT),
                'size': local_rand.choice([1, 2]),
                'is_cyan': local_rand.random() > 0.5
            })

        self.fx_surf = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA).convert_alpha()
        self.btn_bg = pygame.Surface((320, 46), pygame.SRCALPHA).convert_alpha()
        self.sheen_surf = pygame.Surface((320, 46), pygame.SRCALPHA).convert_alpha()
        self.fade_surf = pygame.Surface((WIDTH, HEIGHT)).convert()
        self.fade_surf.fill(BLACK)

    def get_options(self):
        d = self.DIFFS[self.diff_idx]
        dc = self.DIFF_COLORS[self.diff_idx]
        return [
            ("ИГРАТЬ", WHITE),
            (f"Сложность: {d}", dc),
            ("НАСТРОЙКИ", GOLD),
            ("ВЫХОД", GRAY),
        ]

    def handle(self, event):
        """Интерактивное наведение мыши и клавиатурная навигация по опциям."""
        if event.type == pygame.MOUSEMOTION:
            for i, r in enumerate(self.rects):
                if r.collidepoint(event.pos): self.selected = i
        elif event.type == pygame.MOUSEBUTTONDOWN and event.button == 1:
            for i, r in enumerate(self.rects):
                if r.collidepoint(event.pos): return self._activate(i)
        elif event.type == pygame.KEYDOWN:
            if event.key in (pygame.K_UP, pygame.K_w): self.selected = (self.selected-1)%4
            if event.key in (pygame.K_DOWN, pygame.K_s): self.selected = (self.selected+1)%4
            if event.key in (pygame.K_RETURN, pygame.K_SPACE): return self._activate(self.selected)
        return None

    def _activate(self, i):
        if i == 0: return ("START", self.DIFFS[self.diff_idx])
        if i == 1: self.diff_idx = (self.diff_idx + 1) % 3; return None
        if i == 2: return ("SETTINGS", None) 
        if i == 3: return ("EXIT", None)

    def draw(self, screen):
        self.tick += 1
        screen.fill(DARK_BG)
        
        # Рисуем задний план: фоновую координатную сетку
        for gy in range(0, HEIGHT, 55):
            pygame.draw.line(screen, (8, 25, 45), (0, gy), (WIDTH, gy), 1)
        for gx in range(0, WIDTH, 55):
            pygame.draw.line(screen, (8, 25, 45), (gx, 0), (gx, HEIGHT), 1)

        self.fx_surf.fill((0, 0, 0, 0))
            
        # Рисуем круговой вращающийся вектор радара по центру
        center_x, center_y = WIDTH // 2, HEIGHT // 2 - 40
        radar_angle = self.tick * 0.006
        for i in range(1, 4):
            pygame.draw.circle(self.fx_surf, (0, 80, 120, 20), (center_x, center_y), i * 90, 1)
        lx = center_x + int(math.cos(radar_angle) * 320)
        ly = center_y + int(math.sin(radar_angle) * 320)
        pygame.draw.line(self.fx_surf, (0, 255, 255, 14), (center_x, center_y), (lx, ly), 2)

        # Отрисовка звезд фона
        for star in self.stars:
            pulse = int(math.sin(self.tick * 0.02 + star['x']) * 80) + 150
            pulse = max(0, min(255, pulse))
            col = (0, 255, 255, pulse) if star['is_cyan'] else (255, 0, 128, pulse)
            pygame.draw.circle(self.fx_surf, col, (star['x'], star['y']), star['size'])

        # Двойной хроматический сдвиг (глитч-эффект) в заголовке
        t = int(math.sin(self.tick * 0.04) * 4)
        title_x, title_y = WIDTH // 2, 90 + t
        draw_text(screen, "DIMENSION SHIFT", 58, title_x - 3, title_y - 1, NEON_PINK, center=True)
        draw_text(screen, "DIMENSION SHIFT", 58, title_x + 3, title_y + 1, CYAN, center=True)
        draw_text(screen, "DIMENSION SHIFT", 58, title_x, title_y, WHITE, center=True)
        
        draw_text(screen, "Переключай измерения — побеждай!", 18, WIDTH//2, 148, LIGHT_GRAY, center=True)

        controls = "A/D — движение  |  SPACE — прыжок  |  SHIFT — сменить мир"
        draw_text(screen, controls, 16, WIDTH//2, 178, (120, 240, 240), center=True)

        # Рендер кнопок меню
        for i, (label, col) in enumerate(self.get_options()):
            by = 240 + i * 58
            is_sel = (i == self.selected)
            
            bg_alpha = 220 if is_sel else 140
            self.btn_bg.fill((0, 0, 0, 0))
            self.btn_bg.fill((20, 22, 50, bg_alpha) if is_sel else (10, 12, 30, bg_alpha))
            screen.blit(self.btn_bg, (WIDTH//2 - 160, by))
            
            border = col if is_sel else DARK_GRAY
            pygame.draw.rect(screen, border, (WIDTH//2 - 160, by, 320, 46), 2, border_radius=4)
            
            if is_sel:
                # Бегущая световая полоса (блик) на активной кнопке
                sheen_x = (self.tick * 4) % 640 - 160
                self.sheen_surf.fill((0, 0, 0, 0))
                pygame.draw.polygon(self.sheen_surf, (255, 255, 255, 20), [
                    (sheen_x, 0), (sheen_x + 30, 0), (sheen_x - 20, 46), (sheen_x - 50, 46)
                ])
                screen.blit(self.sheen_surf, (WIDTH//2 - 160, by), special_flags=pygame.BLEND_RGBA_ADD)
                
                # Подсветка по углам выбранной кнопки (угловые скобки-прицелы)
                bx, by_b, bw, bh = WIDTH//2 - 160, by, 320, 46
                br_alpha = int(170 + math.sin(self.tick * 0.15) * 85)
                b_col = (*col[:3], br_alpha)
                pygame.draw.line(self.fx_surf, b_col, (bx - 6, by_b - 6), (bx + 14, by_b - 6), 2)
                pygame.draw.line(self.fx_surf, b_col, (bx - 6, by_b - 6), (bx - 6, by_b + 14), 2)
                pygame.draw.line(self.fx_surf, b_col, (bx + bw + 6, by_b - 6), (bx + bw - 14, by_b - 6), 2)
                pygame.draw.line(self.fx_surf, b_col, (bx + bw + 6, by_b - 6), (bx + bw + 6, by_b + 14), 2)
                pygame.draw.line(self.fx_surf, b_col, (bx - 6, by_b + bh + 6), (bx + 14, by_b + bh + 6), 2)
                pygame.draw.line(self.fx_surf, b_col, (bx - 6, by_b + bh + 6), (bx - 6, by_b + bh - 14), 2)
                pygame.draw.line(self.fx_surf, b_col, (bx + bw + 6, by_b + bh + 6), (bx + bw - 14, by_b + bh + 6), 2)
                pygame.draw.line(self.fx_surf, b_col, (bx + bw + 6, by_b + bh + 6), (bx + bw + 6, by_b + bh - 14), 2)
            
            prefix = ">> " if is_sel else "   "
            draw_text(screen, f"{prefix}{label}", 24, WIDTH//2, by + 23, col, center=True)
            self.rects[i] = pygame.Rect(WIDTH//2 - 160, by, 320, 46)

        screen.blit(self.fx_surf, (0, 0))

        # Плавный фейд появления меню из темноты при старте игры
        if self.tick < 30:
            self.fade_surf.set_alpha(int((1.0 - self.tick / 30.0) * 255))
            screen.blit(self.fade_surf, (0, 0))

        draw_text(screen, "↑↓ / мышь — выбор   ENTER — подтвердить", 15, WIDTH//2, HEIGHT - 35, LIGHT_GRAY, center=True)


class SettingsUI:
    """Экран настроек. Позволяет регулировать громкости и переназначать бинды клавиш."""
    def __init__(self):
        self.slider_mus_rect = pygame.Rect(0, 0, 0, 0)
        self.slider_sfx_rect = pygame.Rect(0, 0, 0, 0)
        self.rebind_rects = {}
        self.back_rect = pygame.Rect(0, 0, 0, 0)
        self.dragging_music = False
        self.dragging_sfx = False
        self.active_rebind = None  # Содержит ID действия (LEFT, JUMP...), если ждем ввода клавиши

    def draw(self, surf, music_vol, sfx_vol, controls):
        """Отрисовка ползунков звука и кнопок переназначения клавиш."""
        overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        overlay.fill((10, 10, 24, 225)) 
        surf.blit(overlay, (0, 0))
        
        draw_text(surf, "НАСТРОЙКИ ЗВУКА И КЛАВИШ", 34, WIDTH // 2, 50, GOLD, center=True)
        
        # --- СЕКЦИЯ 1. ГРОМКОСТЬ ---
        slider_y1 = 130
        draw_text(surf, f"ГРОМКОСТЬ МУЗЫКИ: {int(music_vol * 100)}%", 16, WIDTH // 2 - 180, slider_y1, LIGHT_GRAY)
        
        track_w, track_h = 360, 8
        track_x = WIDTH // 2 - 180
        track_y = slider_y1 + 25
        pygame.draw.rect(surf, SLIDER_BG, (track_x, track_y, track_w, track_h), border_radius=4)
        
        # Заливка активной части слайдера музыки (Cyan)
        act_w_mus = int(track_w * music_vol)
        if act_w_mus > 0:
            pygame.draw.rect(surf, SLIDER_ACTIVE_MUS, (track_x, track_y, act_w_mus, track_h), border_radius=4)
        pygame.draw.circle(surf, WHITE, (track_x + act_w_mus, track_y + track_h // 2), 8)
        pygame.draw.circle(surf, CYAN, (track_x + act_w_mus, track_y + track_h // 2), 5)
        self.slider_mus_rect = pygame.Rect(track_x - 10, track_y - 10, track_w + 20, track_h + 20)

        slider_y2 = 200
        draw_text(surf, f"ГРОМКОСТЬ ЭФФЕКТОВ: {int(sfx_vol * 100)}%", 16, WIDTH // 2 - 180, slider_y2, LIGHT_GRAY)
        
        # Заливка активной части слайдера звуков (Розовый)
        track_y2 = slider_y2 + 25
        pygame.draw.rect(surf, SLIDER_BG, (track_x, track_y2, track_w, track_h), border_radius=4)
        
        act_w_sfx = int(track_w * sfx_vol)
        if act_w_sfx > 0:
            pygame.draw.rect(surf, SLIDER_ACTIVE_SFX, (track_x, track_y2, act_w_sfx, track_h), border_radius=4)
        pygame.draw.circle(surf, WHITE, (track_x + act_w_sfx, track_y2 + track_h // 2), 8)
        pygame.draw.circle(surf, NEON_PINK, (track_x + act_w_sfx, track_y2 + track_h // 2), 5)
        self.slider_sfx_rect = pygame.Rect(track_x - 10, track_y2 - 10, track_w + 20, track_h + 20)

        # --- СЕКЦИЯ 2. НАЗНАЧЕНИЕ КЛАВИШ ---
        draw_text(surf, "РАСКЛАДКА КЛАВИАТУРЫ", 18, WIDTH // 2, 285, GOLD, center=True)
        
        start_y = 315
        row_h = 42
        actions = [
            ("LEFT", "ДВИЖЕНИЕ ВЛЕВО"),
            ("RIGHT", "ДВИЖЕНИЕ ВПРАВО"),
            ("JUMP", "ПРЫЖОК / ТОЛЧОК"),
            ("SHIFT", "СМЕНА ИЗМЕРЕНИЯ")
        ]
        
        for i, (act_id, act_name) in enumerate(actions):
            ry = start_y + i * row_h
            draw_text(surf, act_name, 14, WIDTH // 2 - 180, ry + 8, LIGHT_GRAY)
            
            btn_w, btn_h = 160, 28
            btn_x = WIDTH // 2 + 20
            btn_y = ry
            btn_rect = pygame.Rect(btn_x, btn_y, btn_w, btn_h)
            self.rebind_rects[act_id] = btn_rect
            
            if self.active_rebind == act_id:
                # Если кнопка в режиме ожидания ввода, мигаем золотой окантовкой
                pulse = int(127 + 128 * math.sin(pygame.time.get_ticks() * 0.01))
                pulse = max(0, min(255, pulse))
                pygame.draw.rect(surf, REBIND_HIGHLIGHT, btn_rect, 2, border_radius=4)
                draw_text(surf, "[ НАЖМИТЕ... ]", 14, btn_x + btn_w // 2, btn_y + btn_h // 2, (pulse, pulse, 0), center=True)
            else:
                key_code = controls.get(act_id, pygame.K_UNKNOWN)
                key_name = pygame.key.name(key_code).upper() if key_code != pygame.K_UNKNOWN else "NONE"
                
                pygame.draw.rect(surf, DARK_GRAY, btn_rect, border_radius=4)
                pygame.draw.rect(surf, GRAY, btn_rect, 1, border_radius=4)
                draw_text(surf, key_name, 14, btn_x + btn_w // 2, btn_y + btn_h // 2, WHITE, center=True)

        # --- СЕКЦИЯ 3. КНОПКА НАЗАД ---
        back_y = 505
        self.back_rect = pygame.Rect(WIDTH // 2 - 80, back_y, 160, 36)
        pygame.draw.rect(surf, DARK_GRAY, self.back_rect, border_radius=4)
        pygame.draw.rect(surf, GOLD, self.back_rect, 2, border_radius=4)
        draw_text(surf, "НАЗАД [ESC]", 15, WIDTH // 2, back_y + 18, WHITE, center=True)

    def handle_event(self, ev, music_vol, sfx_vol, controls):
        """Интерактивное перетаскивание ползунков и перехват событий переназначения клавиш."""
        changes = {}
        
        if ev.type == pygame.MOUSEBUTTONDOWN and ev.button == 1:
            # Слайдеры
            if self.slider_mus_rect.collidepoint(ev.pos):
                self.dragging_music = True
                changes["music"] = self._get_slider_val(ev.pos[0])
            elif self.slider_sfx_rect.collidepoint(ev.pos):
                self.dragging_sfx = True
                changes["sfx"] = self._get_slider_val(ev.pos[0])
                
            # Переопределение клавиш (ставим бинд в статус "waiting")
            if self.active_rebind is None:
                for act_id, rect in self.rebind_rects.items():
                    if rect.collidepoint(ev.pos):
                        self.active_rebind = act_id
                        changes["rebind"] = act_id
                        sfx.play('shift')
                        break
                        
            # Выход из настроек
            if self.back_rect.collidepoint(ev.pos) and self.active_rebind is None:
                changes["back"] = True
                sfx.play('coin')
                
        elif ev.type == pygame.MOUSEBUTTONUP and ev.button == 1:
            self.dragging_music = False
            self.dragging_sfx = False
            
        elif ev.type == pygame.MOUSEMOTION:
            if self.dragging_music:
                changes["music"] = self._get_slider_val(ev.pos[0])
            elif self.dragging_sfx:
                changes["sfx"] = self._get_slider_val(ev.pos[0])
                
        elif ev.type == pygame.KEYDOWN:
            if self.active_rebind is not None:
                # Перехватываем нажатую кнопку, биндим её к ID действия и выходим из режима ожидания
                target_action = self.active_rebind
                self.active_rebind = None
                changes["key_capture"] = (target_action, ev.key)
                sfx.play('coin')
            elif ev.key == pygame.K_ESCAPE:
                changes["back"] = True
                sfx.play('coin')
                
        return changes

    def _get_slider_val(self, mouse_x):
        """Нормализация абсолютного X-положения мыши в значение громкости [0.0 - 1.0] относительно трека."""
        track_x = WIDTH // 2 - 180
        track_w = 360
        val = (mouse_x - track_x) / track_w
        return max(0.0, min(1.0, val))

# =====================================================================
# 10. ЯДРО ИГРЫ (ОСНОВНОЙ ЦИКЛ И ЛОГИКА)
# =====================================================================
class Game:
    MAX_LEVELS = 10  
    LEVEL_TIME = 120 # Лимит времени на уровень (в секундах)

    def __init__(self):
        # Инициализация физического окна (поддерживает двойную буферизацию)
        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.DOUBLEBUF)
        pygame.display.set_caption("Dimension Shift Ultimate")
        self.clock = pygame.time.Clock()
        
        # Виртуальный холст 1024х600: рендерим игру в фиксированном разрешении,
        # а затем масштабируем его под размер окна с сохранением пропорций (Letterboxing)
        self.virtual_screen = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA)
        self.fullscreen = False
        
        # Расчет масштабирования холста под размер физического окна
        self._update_scaling_dimensions()
        
        # Системные переменные для плавного перехода (Fade-затухания) между экранами
        self.fade_alpha = 0.0
        self.fade_direction = 0  # 1 - затухание в черный, -1 - выход из черного
        self.fade_callback = None # Функция, вызываемая на пике затемнения
        
        self.reset_checkpoint_flag = True # Флаг сброса точек сохранения при старте уровня/игры
        
        self.menu = Menu()
        self.hud = HUD()
        self.settings_ui = SettingsUI()
        self.ps = ParticleSystem()
        
        self.state = "MENU"
        self.difficulty = "MEDIUM"
        self.level_num = 1
        self.score = 0
        self.lives = 3
        self.tick = 0
        self._shift_prev = False  # Флаг для отслеживания удержания клавиши Shift (зашита от автоповтора)
        self.respawn_pos = None
        self.max_lives = 3
        
        self.last_time_bonus = 0
        self.last_coin_bonus = 0
        
        # Сеты собранных монет/ключей/дверей на уровне для корректного респауна без потери прогресса
        self._collected_coin_positions = set()
        self._stored_coin_positions = set()
        self._collected_key_positions = set()
        self._stored_key_positions = set()
        self._open_door_positions = set()
        self._stored_door_positions = set()
        self._stored_dimension = "A"  # Сохраненное измерение при прохождении чекпоинта
        
        self.dim_overlay = pygame.Surface((WIDTH, HEIGHT), pygame.SRCALPHA).convert_alpha()
        self.dim_overlay.fill((0, 0, 0, 175))

        # Загрузка настроек управления и звука из конфигурационного json
        music_vol, sfx_vol, self.controls = SaveManager.load_settings()
        sfx.set_music_volume(music_vol)
        sfx.set_sfx_volume(sfx_vol)

    def _update_scaling_dimensions(self):
        """Расчет пропорций и черных полей (Letterbox) при изменении размеров окна/экрана."""
        win_w, win_h = self.screen.get_size()
        self.scale = min(win_w / WIDTH, win_h / HEIGHT)
        self.new_w = int(WIDTH * self.scale)
        self.new_h = int(HEIGHT * self.scale)
        self.offset_x = (win_w - self.new_w) // 2
        self.offset_y = (win_h - self.new_h) // 2

    def trigger_transition(self, target_state, callback=None):
        """Запуск плавного затухания экрана с переходом в указанный стейт."""
        self.fade_direction = 1
        self.fade_callback = (target_state, callback)

    def _load_level(self):
        """Полная инициализация объектов уровня или откат к состоянию на последнем чекпоинте."""
        if self.reset_checkpoint_flag:
            # Сброс всех накопленных данных при запуске нового уровня
            self.respawn_pos = None
            self._stored_keys = 0
            self._stored_score = self.score
            self._stored_coins = 0  
            self._collected_coin_positions.clear()
            self._stored_coin_positions.clear()
            self._collected_key_positions.clear()
            self._stored_key_positions.clear()
            self._open_door_positions.clear()
            self._stored_door_positions.clear()
            self.coins_collected = 0
            self.reset_checkpoint_flag = False  
        else:
            # Восстанавливаем состояние мира на момент взятия чекпоинта
            self.score = getattr(self, '_stored_score', self.score)
            self.coins_collected = getattr(self, '_stored_coins', self.coins_collected)
            self._collected_coin_positions = set(self._stored_coin_positions)
            self._collected_key_positions = set(self._stored_key_positions)
            self._open_door_positions = set(self._stored_door_positions)

        self.level = Level(self.level_num, self.difficulty)
        
        # Восстанавливаем собранное состояние для монет, ключей и дверей после респауна
        for co in self.level.coins:
            if (co.rect.x, co.rect.y) in self._collected_coin_positions:
                co.collected = True

        for k in self.level.keys:
            if (k.rect.x, k.rect.y) in self._collected_key_positions:
                k.collected = True

        for d in self.level.doors:
            if (d.rect.x, d.rect.y) in self._open_door_positions:
                d.is_open = True

        # Установка игрока на спавн или чекпоинт
        spawn_x = self.respawn_pos[0] if self.respawn_pos else 80
        spawn_y = self.respawn_pos[1] if self.respawn_pos else self.level.baseline - 60
        
        self.player = Player(spawn_x, spawn_y)
        self.player.keys = getattr(self, '_stored_keys', 0)
        
        if self.respawn_pos:
            self.player.dimension = self._stored_dimension
        else:
            self.player.dimension = self.level.start_dimension
            self._stored_dimension = self.level.start_dimension

        self.camera = Camera(self.level.level_width)
        self.dim_cd = 0 # Кулдаун переключения миров
        self.timer = self.LEVEL_TIME * FPS
        self.coins_total = len(self.level.coins)

        # Визуальная активация флага чекпоинта на сцене
        if self.respawn_pos:
            for cp in self.level.checkpoints:
                if cp.rect.x == self.respawn_pos[0]:
                    cp.active = True

    def _hurt_player(self):
        """Нанесение урона игроку с отскоком, тряской экрана и запуском кадров неуязвимости."""
        sfx.play('hit')
        self.lives -= 1
        self.player.invincible = 90 # Полторы секунды неуязвимости при 60 FPS
        self.player.vy = -6.0 # Небольшой отброс вверх
        self.camera.shake = 14
        self.ps.emit(self.player.rect.centerx, self.player.rect.centery, RED, count=20)
        if self.lives <= 0:
            self.state = "GAME_OVER"

    def _events(self):
        """Обработка системных событий Pygame."""
        for ev in pygame.event.get():
            if ev.type == pygame.QUIT:
                pygame.quit()
                sys.exit()

            # Нормализация координат мыши: пересчитываем клики на физическом экране
            # обратно в координаты виртуального холста 1024х600 с учетом полей
            if hasattr(ev, 'pos'):
                v_x = int((ev.pos[0] - self.offset_x) / self.scale)
                v_y = int((ev.pos[1] - self.offset_y) / self.scale)
                ev.pos = (v_x, v_y)

            # Глобальные горячие клавиши: переключение полноэкранного режима на F11/F
            if ev.type == pygame.KEYDOWN:
                if ev.key in (pygame.K_F11, pygame.K_f):
                    self.fullscreen = not self.fullscreen
                    if self.fullscreen:
                        self.screen = pygame.display.set_mode((0, 0), pygame.FULLSCREEN | pygame.DOUBLEBUF)
                    else:
                        self.screen = pygame.display.set_mode((WIDTH, HEIGHT), pygame.DOUBLEBUF)
                    self._update_scaling_dimensions()

            # Если идет плавное затемнение экрана, блокируем ввод во избежание дабл-кликов
            if self.fade_direction != 0:
                continue

            # Обработка событий в зависимости от игрового состояния (стейт-машина)
            if self.state == "MENU":
                action = self.menu.handle(ev)
                if action:
                    cmd, val = action
                    if cmd == "START":
                        self.difficulty = val
                        self.max_lives = 5 if val == "EASY" else (3 if val == "MEDIUM" else 1)
                        self.lives = self.max_lives
                        self.score = 0
                        self.level_num = 1
                        self.reset_checkpoint_flag = True
                        self.trigger_transition("PLAYING", callback=self._load_level)
                    elif cmd == "SETTINGS":
                        self.trigger_transition("SETTINGS_MENU")
                    elif cmd == "EXIT":
                        pygame.quit()
                        sys.exit()

            elif self.state == "SETTINGS_MENU":
                changes = self.settings_ui.handle_event(ev, sfx.music_volume, sfx.sfx_volume, self.controls)
                if "music" in changes:
                    sfx.set_music_volume(changes["music"])
                if "sfx" in changes:
                    sfx.set_sfx_volume(changes["sfx"])
                if "key_capture" in changes:
                    action_id, key_code = changes["key_capture"]
                    self.controls[action_id] = key_code
                if "back" in changes:
                    SaveManager.save_settings(sfx.music_volume, sfx.sfx_volume, self.controls)
                    self.trigger_transition("MENU")

            elif self.state == "PAUSED_SETTINGS":
                changes = self.settings_ui.handle_event(ev, sfx.music_volume, sfx.sfx_volume, self.controls)
                if "music" in changes:
                    sfx.set_music_volume(changes["music"])
                if "sfx" in changes:
                    sfx.set_sfx_volume(changes["sfx"])
                if "key_capture" in changes:
                    action_id, key_code = changes["key_capture"]
                    self.controls[action_id] = key_code
                if "back" in changes:
                    SaveManager.save_settings(sfx.music_volume, sfx.sfx_volume, self.controls)
                    self.state = "PAUSED"

            elif self.state == "PLAYING":
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        self.state = "PAUSED"
                        sfx.play('shift')

            elif self.state == "PAUSED":
                if ev.type == pygame.KEYDOWN:
                    if ev.key == pygame.K_ESCAPE:
                        self.state = "PLAYING"
                        sfx.play('shift')
                    elif ev.key == pygame.K_s:
                        self.state = "PAUSED_SETTINGS"
                        sfx.play('shift')
                    elif ev.key == pygame.K_b:
                        SaveManager.save_settings(sfx.music_volume, sfx.sfx_volume, self.controls)
                        self.trigger_transition("MENU")

            elif self.state in ("DEAD", "LEVEL_WIN", "GAME_WIN", "GAME_OVER"):
                if ev.type == pygame.KEYDOWN:
                    if ev.key in (pygame.K_RETURN, pygame.K_SPACE):
                        self._handle_result_key()
                    elif ev.key == pygame.K_b:
                        self.trigger_transition("MENU")

    def _handle_result_key(self):
        """Обработка подтверждения действия на экранах победы, поражения или смерти."""
        if self.state == "DEAD":
            self.reset_checkpoint_flag = False # Не сбрасываем чекпоинт — респавнимся на нем
            self.trigger_transition("PLAYING", callback=self._load_level)
        elif self.state == "LEVEL_WIN":
            SaveManager.save(self.level_num, max(0, self.timer // FPS), self.coins_collected)
            if self.level_num < self.MAX_LEVELS:
                self.level_num += 1
                self.reset_checkpoint_flag = True # Новый уровень — сбрасываем чекпоинты
                self.trigger_transition("PLAYING", callback=self._load_level)
            else:
                self.trigger_transition("GAME_WIN")
        elif self.state in ("GAME_WIN", "GAME_OVER"):
            self.trigger_transition("MENU")

    def _update(self):
        """Главный такт обновления физического состояния игры (60 тактов в секунду)."""
        # Обработка таймера плавного затухания/проявления экранов (всегда работает)
        if self.fade_direction != 0:
            self.fade_alpha += self.fade_direction * 15.5
            if self.fade_direction == 1 and self.fade_alpha >= 255:
                self.fade_alpha = 255
                self.fade_direction = -1
                target_state, cb = self.fade_callback
                self.state = target_state
                if cb: cb()
            elif self.fade_direction == -1 and self.fade_alpha <= 0:
                self.fade_alpha = 0
                self.fade_direction = 0
                self.fade_callback = None

        if self.state != "PLAYING": 
            return
            
        self.tick += 1
        self.timer -= 1

        sfx.update_music(self.player.dimension)

        p = self.player
        new_dim = "B" if p.dimension == "A" else "A"
        
        # Формируем списки коллизий для ТЕКУЩЕГО и СЛЕДУЮЩЕГО измерений
        active_plats = [
            pl for pl in self.level.platforms 
            if pl.dimension in ("ALL", p.dimension)
            and not (isinstance(pl, CrumblingPlatform) and pl.state == "BROKEN")
        ]
        future_plats = [
            pl for pl in self.level.platforms 
            if pl.dimension in ("ALL", new_dim)
            and not (isinstance(pl, CrumblingPlatform) and pl.state == "BROKEN")
        ]

        # Список опасностей в новом измерении для проверки безопасности телепортации
        future_hazards = []
        for en in self.level.enemies:
            if en.alive and en.dimension == new_dim:
                future_hazards.append(en)
        for fen in self.level.flying_enemies:
            if fen.alive and fen.dimension in ("ALL", new_dim):
                future_hazards.append(fen)
        for ls in self.level.lasers:
            if ls.active and ls.dimension in ("ALL", new_dim):
                future_hazards.append(ls)

        # Считывание нажатия кнопки сдвига измерений с защитой от залипания
        keys = pygame.key.get_pressed()
        shift_key = self.controls.get("SHIFT", pygame.K_LSHIFT)
        shift_now = keys[shift_key] or (shift_key == pygame.K_LSHIFT and keys[pygame.K_RSHIFT])
        
        if shift_now and not self._shift_prev and self.dim_cd == 0:
            if p.switch_dimension(future_plats, future_hazards):
                self.dim_cd = 20 # Перезарядка 1/3 секунды при 60 FPS
                sfx.play('shift')
                col = CYAN if p.dimension == "A" else GREEN
                self.ps.emit(p.rect.centerx, p.rect.centery, col, count=20)
                self.score += 5
        self._shift_prev = shift_now
        
        if self.dim_cd > 0: self.dim_cd -= 1

        p_inflated = p.rect.inflate(4, 4)
        
        # Проверка и открытие запертых дверей
        for d in self.level.doors:
            if not d.is_open and d.dimension in ("ALL", p.dimension):
                if p_inflated.colliderect(d.rect) and p.keys > 0:
                    d.is_open = True
                    self._open_door_positions.add((d.rect.x, d.rect.y)) 
                    p.keys -= 1
                    sfx.play('hit')
                    self.ps.emit(d.rect.centerx, d.rect.centery, CYAN, count=15)
                elif not d.is_open and d not in active_plats:
                    active_plats.append(d)

        # Детекция наступания на разрушающиеся платформы
        for cp in self.level.platforms:
            if isinstance(cp, CrumblingPlatform):
                if cp.state != "BROKEN" and p_inflated.colliderect(cp.rect) and p.dimension in ("ALL", cp.dimension) and p.vy >= 0:
                    cp.touch()

        for pl in self.level.platforms: pl.update()
        
        # Обновление положения игрока с передачей текущего бинда управления
        p.update(active_plats, self.ps, self.controls)
        
        for en in self.level.enemies: en.update()
        for fen in self.level.flying_enemies: fen.update()
        for ls in self.level.lasers: ls.update()
        for co in self.level.coins: co.update()
        for k in self.level.keys: k.update()
        for cp in self.level.checkpoints: cp.update()
        if self.level.goal: self.level.goal.update()
        
        self.camera.update(p.rect.x)
        self.ps.update()

        # Сбор монет
        for co in self.level.coins:
            if not co.collected and co.dimension in ("ALL", p.dimension) and p.rect.colliderect(co.rect):
                co.collected = True
                self._collected_coin_positions.add((co.rect.x, co.rect.y)) 
                sfx.play('coin')
                self.coins_collected += 1
                self.score += 50
                self.ps.emit(co.rect.centerx, co.rect.centery, GOLD, count=12)

        # Сбор ключей
        for k in self.level.keys:
            if not k.collected and k.dimension in ("ALL", p.dimension) and p.rect.colliderect(k.rect):
                k.collected = True
                self._collected_key_positions.add((k.rect.x, k.rect.y)) 
                sfx.play('coin')
                p.keys += 1
                self.ps.emit(k.rect.centerx, k.rect.centery, GOLD, count=15)

        # Активация точки сохранения (запись состояния)
        for cp in self.level.checkpoints:
            if not cp.active and p.rect.colliderect(cp.rect):
                cp.active = True
                sfx.play('coin')
                self.respawn_pos = (cp.rect.x, cp.rect.y - 20)
                self._stored_dimension = p.dimension
                self._stored_keys = p.keys
                self._stored_score = self.score
                self._stored_coins = self.coins_collected
                self._stored_coin_positions = set(self._collected_coin_positions)
                self._stored_key_positions = set(self._collected_key_positions)
                self._stored_door_positions = set(self._open_door_positions)

        # Обработка прыжков на врагов (убийство при наступании сверху) или получение урона
        for en in self.level.enemies:
            if en.alive and en.dimension == p.dimension and p.rect.colliderect(en.rect):
                # Если падаем сверху на голову врагу — убиваем его и получаем отскок
                if p.vy > 0 and p.rect.bottom < en.rect.centery + 12:
                    en.alive = False
                    p.vy = JUMP_FORCE * 0.65
                    self.score += 100
                    sfx.play('hit')
                    self.ps.emit(en.rect.centerx, en.rect.centery, RED, count=16)
                    self.camera.shake = 8
                elif p.invincible == 0:
                    self._hurt_player()
                    if self.state == "GAME_OVER": return

        # Столкновение с летающими врагами
        for fen in self.level.flying_enemies:
            if fen.alive and fen.dimension in ("ALL", p.dimension) and p.rect.colliderect(fen.rect) and p.invincible == 0:
                self._hurt_player()
                if self.state == "GAME_OVER": return

        # Столкновение с лазерными лучами
        for ls in self.level.lasers:
            if ls.active and ls.dimension in ("ALL", p.dimension) and p.rect.colliderect(ls.rect) and p.invincible == 0:
                self._hurt_player()
                if self.state == "GAME_OVER": return

        # Гибель при падении за экран или по таймеру уровня
        if p.is_dead or self.timer <= 0:
            self.lives -= 1
            sfx.play('hit')
            self.ps.emit(p.rect.centerx, p.rect.centery + 40, RED, count=24)
            if self.lives <= 0: 
                self.state = "GAME_OVER"
            else: 
                self.state = "DEAD"
            return

        # Достижение финишного портала
        if self.level.goal and p.rect.colliderect(self.level.goal.rect):
            time_bonus = max(0, self.timer // FPS) * 10
            coin_bonus = self.coins_collected * 20
            self.last_time_bonus = time_bonus
            self.last_coin_bonus = coin_bonus
            self.score += time_bonus + coin_bonus + 500
            self.state = "LEVEL_WIN"

    def _draw(self):
        """Сборка кадра и вывод на физический экран."""
        if self.state == "MENU":
            self.menu.draw(self.virtual_screen)
            self._draw_transition_fade()
            self._render_scaled()
            return
            
        elif self.state == "SETTINGS_MENU":
            self.settings_ui.draw(self.virtual_screen, sfx.music_volume, sfx.sfx_volume, self.controls)
            self._draw_transition_fade()
            self._render_scaled()
            return

        p = self.player
        cam_x = self.camera.offset()
        canvas = self.virtual_screen
        
        # Сначала рисуем бэкграунд уровня
        self.level.draw_bg(canvas, p.dimension, cam_x)

        # Отрисовка всех сущностей с учетом смещения камеры
        for pl in self.level.platforms: pl.draw(canvas, cam_x, p.dimension)
        for d in self.level.doors: d.draw(canvas, cam_x, p.dimension)
        for cp in self.level.checkpoints: cp.draw(canvas, cam_x, p.dimension)
        for k in self.level.keys: k.draw(canvas, cam_x, p.dimension)
        for co in self.level.coins: co.draw(canvas, cam_x, p.dimension)
        for en in self.level.enemies: en.draw(canvas, cam_x, p.dimension)
        for fen in self.level.flying_enemies: fen.draw(canvas, cam_x, p.dimension)
        for ls in self.level.lasers: ls.draw(canvas, cam_x, p.dimension)
        if self.level.goal: self.level.goal.draw(canvas, cam_x, p.dimension)
        
        # Эффекты частиц и спрайт игрока
        self.ps.draw(canvas, cam_x)
        if self.state != "DEAD" and not p.is_dead:
            p.draw(canvas, cam_x, self.ps)

        # Интерфейс поверх игрового кадра
        self.hud.draw(canvas, p, self.level_num, self.score, self.lives, self.max_lives, self.coins_total, self.coins_collected, self.dim_cd, max(0, self.timer // FPS))

        # Отрисовка меню паузы и статусных оверлеев поверх игры
        if self.state == "PAUSED":
            self._overlay("ПАУЗА", "ESC — продолжить  |  S — настройки  |  B — главное меню", WHITE, LIGHT_GRAY)
        elif self.state == "PAUSED_SETTINGS":
            self.settings_ui.draw(canvas, sfx.music_volume, sfx.sfx_volume, self.controls)
        elif self.state == "DEAD":
            self._overlay("— СМЕРТЬ —", "ENTER — рестарт уровня  |  B — меню", RED, WHITE)
        elif self.state == "GAME_OVER":
            self._overlay("ИГРА ОКОНЧЕНА", "ENTER — в главное меню", RED, GOLD)
        elif self.state == "LEVEL_WIN":
            bonus = self.last_time_bonus + self.last_coin_bonus + 500
            self._overlay(f"УРОВЕНЬ {self.level_num} ПРОЙДЕН! +{bonus}", "ENTER — следующий уровень  |  B — меню", GREEN, WHITE)
        elif self.state == "GAME_WIN":
            self._overlay("ВЫ ПРОШЛИ ИГРУ!", f"Итог: {self.score} очков!  ENTER — в меню", GOLD, YELLOW)

        self._draw_transition_fade()
        self._render_scaled()

    def _overlay(self, title, subtitle, tc, sc):
        """Отрисовка затемняющей подложки и текстовых плашек для статусных экранов."""
        self.virtual_screen.blit(self.dim_overlay, (0, 0))
        
        draw_text(self.virtual_screen, title, 44, WIDTH // 2, HEIGHT // 2 - 50, tc, center=True)
        draw_text(self.virtual_screen, subtitle, 20, WIDTH // 2, HEIGHT // 2 + 15, sc, center=True)
        
        # Вывод детальной статистики на экранах результатов
        if self.state == "LEVEL_WIN" and hasattr(self, 'last_time_bonus'):
            draw_text(self.virtual_screen, f"Бонус времени: +{self.last_time_bonus}  |  Бонус монет: +{self.last_coin_bonus}", 15, WIDTH // 2, HEIGHT // 2 + 65, sc, center=True)
            draw_text(self.virtual_screen, f"Общие очки: {self.score}", 16, WIDTH // 2, HEIGHT // 2 + 95, tc, center=True)
        elif self.state == "DEAD":
            draw_text(self.virtual_screen, f"Осталось жизней: {self.lives}", 16, WIDTH // 2, HEIGHT // 2 + 65, tc, center=True)
        elif self.state == "GAME_OVER":
            draw_text(self.virtual_screen, f"Финальный счет: {self.score}", 16, WIDTH // 2, HEIGHT // 2 + 65, tc, center=True)

    def _draw_transition_fade(self):
        """Отрисовка черной альфа-плашки для красивых затуханий при смене стейтов."""
        if self.fade_alpha > 0:
            fade_surf = pygame.Surface((WIDTH, HEIGHT))
            fade_surf.fill(BLACK)
            fade_surf.set_alpha(int(self.fade_alpha))
            self.virtual_screen.blit(fade_surf, (0, 0))

    def _render_scaled(self):
        """Масштабирование виртуального холста 1024х600 до разрешения физического монитора."""
        scaled_surf = pygame.transform.scale(self.virtual_screen, (self.new_w, self.new_h))
        self.screen.fill(BLACK)
        self.screen.blit(scaled_surf, (self.offset_x, self.offset_y))
        pygame.display.flip()

    def run(self):
        """Главный игровой цикл обновления физики и отрисовки с лимитом FPS."""
        while True:
            self._events()
            self._update()
            self._draw()
            self.clock.tick(FPS)

if __name__ == "__main__":
    Game().run()
