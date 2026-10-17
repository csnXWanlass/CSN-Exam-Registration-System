# INCOMPLETE! DO NOT CALL

import re
# data validation library
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional

EXAM_LEVEL = re.compile(r"[A-Z0-9]{1,4}")  # Exam level must be 1-4 uppercase letters or numbers

class ExamCreate(BaseModel):  # pydantic: BaseModel is a class that provides data validation and serialization capabilities
    exam_name:  str = Field(max_length = 100)  # pydantic: Field function is used to specify constraints on the fields
    exam_level: str = Field(max_length = 4)
    exam_date:  str = Field(max_length = 10)  # Format: YYYY-MM-DD
    exam_time:  str = Field(max_length = 5)  # Format: HH:MM
    @field_validator("exam_level")  # pydantic: any time the exam_level field is set, this function will be called to validate it
    @classmethod
    def chk_exam_level(cls, exam_level: str) -> str: # check exam level
        if not EXAM_LEVEL.fullmatch(exam_level):
            raise ValueError("must be 1-4 uppercase letters or numbers")
        return exam_level

# will be necessary for faculty later, but not right now
# class SessionCreate(BaseModel):  # pydantic: BaseModel is a class that provides data validation and serialization capabilities