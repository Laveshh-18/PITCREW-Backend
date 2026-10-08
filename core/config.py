"""Tuning weights (Lavesh tunes these without a contract change)."""
TEXT_BASE = 0.20
KEYWORDS = [  # (reason, weight, [patterns]) patterns matched as lowercase substrings
    ("crater", 0.50, ["crater", "क्रेटर"]),
    ("injured", 0.50, ["injur", "ghayal", "घायल", "चोट"]),
    ("accident", 0.40, ["accident", "durghatna", "दुर्घटना", "हादसा"]),
    ("deep", 0.35, ["deep", "gehra", "gahra", "गहरा", "गहरे"]),
    ("bike skidded", 0.30, ["skid", "fell", "fall", "gir gaya", "gir gayi", "गिर"]),
    ("large", 0.25, ["large", "huge", "big", "bada", "badi", "बड़ा", "बड़ी"]),
    ("tyre damage", 0.25, ["tyre", "tire", "burst", "पंचर"]),
    ("dangerous", 0.25, ["dangerous", "khatarnak", "खतरनाक"]),
    ("waterlogged", 0.20, ["waterlog", "water", "paani", "pani", "पानी"]),
    ("poor visibility", 0.10, ["night", "dark", "raat", "andhera", "रात", "अंधेरा"]),
    ("minor", -0.10, ["crack", "minor", "small", "chota", "chhota", "छोटा"]),
]
BLEND_WEIGHTS = {"text": 0.4, "photo": 0.3, "sensor": 0.3}
PHOTO_DARK_DIVISOR = 0.35
PHOTO_DARK_THRESHOLD = 60
SENSOR_Z_DIVISOR = 10.0
