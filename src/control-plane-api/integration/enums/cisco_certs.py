from enum import Enum


class TrackType(str, Enum):
    EXAM = "Exam"
    PL = "PL"
    CL = "CL"
    TEST = "TEST"
    DEMO = "DEMO"


class TrackLevel(str, Enum):
    CCNA = "CCNA"
    CCNP = "CCNP"
    CCIE = "CCIE"
    ASSOCIATE = "Associate"
    PRO = "Professional"
    EXPERT = "Expert"
