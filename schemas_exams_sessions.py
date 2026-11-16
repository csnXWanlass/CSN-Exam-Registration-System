# INCOMPLETE! DO NOT CALL

import re
from datetime import date, time, datetime
# data validation library
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator, ConfigDict
from typing import Optional, Annotated
from helpers import format_time


UNSIGNED_MAX = 2**32 - 1  # the max value for MySQL's unsigned int.
# Custom data type for validation of MySQL Row IDs
# read: "An integer that is greater than 1 and less than the unsigned maximum value."
UnsignedInt = Annotated[int, Field(ge=1, le=UNSIGNED_MAX)]

## FORMAT RULES ##
EXAM_LEVEL = re.compile(r"[A-Z0-9]{1,4}")  # Exam level must be 1-4 uppercase letters or numbers
BUILDING_NUM = re.compile(r"[A-Z0-9]{1,3}")  # Building number must be alphanumeric and 1-3 chars
ROOM_NUM = re.compile(r"[A-Z0-9]{1,10}")  # Room number must be alphanumeric and 1-10 chars

## CONSTANTS ##
OPEN_TIME = time(8, 0)      #  8:00 AM  in military time
CLOSE_TIME = time(22, 0)    # 10:00 PM  in military time

# Unused until admin role is added. UNFINISHED.
# class ExamCreate(BaseModel):  # pydantic: BaseModel is a class that provides data validation and serialization capabilities
#     exam_name:  str = Field(max_length = 100)  # pydantic: Field function is used to specify constraints on the fields
#     exam_level: str = Field(max_length = 4)
#     @field_validator("exam_level")  # pydantic: any time the exam_level field is set, this function will be called to validate it
#     @classmethod
#     def chk_exam_level(cls, exam_level: str) -> str: # check exam level
#         if not EXAM_LEVEL.fullmatch(exam_level):
#             raise ValueError("must be 1-4 uppercase letters or numbers")
#         return exam_level

# exam_name and campus_name have unique constraints in db, so we can search by them.
class ExamSearch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    exam_name: str = Field(default="", max_length=100)

class RoomSearch(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)  # remove leading/trailing spaces from all fields
    campus:   str = Field(default="", max_length=100)   # part of a campus name
    campus_id: UnsignedInt | None = None  # Value may be an unsigned integer or none; default None
    building: str = ""  # Optional search, so can be None
    room_num: str = ""  # Optional search, so can be None

    @field_validator("building")
    @classmethod
    def chk_building(cls, building: str) -> str:
        if building and not BUILDING_NUM.fullmatch(building):   # empty is allowed: the filter is optional
            raise ValueError("Building must be 1-3 letters or digits")
        return building

    @field_validator("room_num")
    @classmethod
    def chk_room_num(cls, room_num: str) -> str:
        if room_num and not ROOM_NUM.fullmatch(room_num):
            raise ValueError("Room number must be 1-10 letters or digits")
        return room_num


# validate data from session entry, matching constraints to db.
class SessionCreate(BaseModel):  # pydantic: BaseModel is a class that provides data validation and serialization capabilities
    model_config = ConfigDict(extra="forbid")   # reject unknown fields, such as a sneaky proctor_id
    
    room_id:        UnsignedInt  # must be a valid MySQL ID
    exam_id:        UnsignedInt
    session_date:   date  # Format: YYYY-MM-DD
    session_time:   time  # Format: HH:MM or HH:MM:SS

    @field_validator("session_time")
    @classmethod
    def within_hours(cls, value: time) -> time:
        if not (OPEN_TIME <= value <= CLOSE_TIME):
            raise ValueError(
                f"Exams must start between {format_time(OPEN_TIME)} and {format_time(CLOSE_TIME)}"
            )
        return value

    # session must be for a future date and time
    @model_validator(mode="after")
    def not_in_past(self):
        # self holds the finished model, so both fields are available
        if datetime.combine(self.session_date, self.session_time) < datetime.now():
            raise ValueError("The session can't start in the past")
        return self      # a model validator returns the model, unlike a field validator