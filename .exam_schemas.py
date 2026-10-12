# INCOMPLETE! DO NOT CALL

import re
# data validation library
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional

STUDENT_EMAIL = re.compile(r"[0-9]{10}@student\.csn\.edu")
FACULTY_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@csn\.edu")
class ExamCreate(BaseModel):  # pydantic: BaseModel is a class that provides data validation and serialization capabilities
    first_name: str = Field(max_length=35)  # pydantic: Field function is used to specify constraints on the fields
    last_name: str = Field(max_length=35)
    email: EmailStr     # pydantic: premade type for email validation
    password: str = Field(max_length=10)
    @field_validator("email")  # pydantic: any time the email field is set, this function will be called to validate it
    @classmethod               # 

    @property  # 