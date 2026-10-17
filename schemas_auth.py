#Schemas for user registration, login, and session tracking
#This is all just data validation, not database models. The database models are in models.py.

import re
# data validation library
from pydantic import BaseModel, EmailStr, Field, field_validator, model_validator
from typing import Optional

STUDENT_EMAIL = re.compile(r"[0-9]{10}@student\.csn\.edu")
FACULTY_EMAIL = re.compile(r"[a-zA-Z0-9._%+-]+@csn\.edu")
class UserRegister(BaseModel):  # pydantic: BaseModel is a class that provides data validation and serialization capabilities
    first_name: str = Field(max_length=35)  # pydantic: Field function is used to specify constraints on the fields
    last_name: str = Field(max_length=35)
    email: EmailStr     # pydantic: premade type for email validation
    password: str = Field(max_length=10)
    @field_validator("email")  # pydantic: any time the email field is set, this function will be called to validate it
    @classmethod
    def chk_student_email(cls, email: str) -> str:  # check student email
        if not (STUDENT_EMAIL.fullmatch(email) or FACULTY_EMAIL.fullmatch(email)):
            raise ValueError("must be a CSN email address")
        return email

    @property  # allows role to be accessed as an attribute rather than a method
    def role(self) -> str:
        return "Student" if STUDENT_EMAIL.fullmatch(self.email) else "Faculty"
 

class UserLogin(BaseModel):
    email: EmailStr  # Emails have UNIQUE constraint, so can be used as an identifier
    password: str = Field(max_length=10)


# as far as I can tell, these are unused.
class ForgotPassword(BaseModel):
    email: EmailStr

class ResetPassword(BaseModel):
    token: str
    new_password: str

class TokenResponse(BaseModel):
    access_token: str
    token_type: str
    user_name: str
    user_email: str
