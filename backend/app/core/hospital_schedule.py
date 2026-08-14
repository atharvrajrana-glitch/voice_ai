from datetime import time


WORKING_DAYS = {
    0,  # Monday
    1,  # Tuesday
    2,  # Wednesday
    3,  # Thursday
    4,  # Friday
}


WORKING_SLOTS = [
    time(9, 0),
    time(9, 30),
    time(10, 0),
    time(10, 30),
    time(11, 0),
    time(11, 30),
    time(14, 0),
    time(14, 30),
    time(15, 0),
    time(15, 30),
    time(16, 0),
]